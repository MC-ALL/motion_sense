from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.models.ingest import AlertRecord, DeviceSummary
from app.settings import RuntimeSettings


class PostgresStore:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._pool = AsyncConnectionPool(
            conninfo=settings.database.dsn(),
            min_size=settings.database.min_pool_size,
            max_size=settings.database.max_pool_size,
            open=False,
            kwargs={"row_factory": dict_row},
        )

    async def initialize(self) -> None:
        await self._pool.open()
        await self._bootstrap_schema()

    async def close(self) -> None:
        await self._pool.close()

    async def upsert_device(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        status: str,
        online: bool,
        last_seen_ts: int | None,
        payload: dict,
    ) -> DeviceSummary:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO devices (
                        gym_id,
                        device_type,
                        device_id,
                        status,
                        online,
                        last_seen_ts,
                        last_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gym_id, device_type, device_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        online = EXCLUDED.online,
                        last_seen_ts = EXCLUDED.last_seen_ts,
                        last_payload = EXCLUDED.last_payload,
                        updated_at = NOW()
                    RETURNING gym_id, device_type, device_id, status, online, last_seen_ts, last_payload
                    """,
                    (
                        gym_id,
                        device_type,
                        device_id,
                        status,
                        online,
                        last_seen_ts,
                        Jsonb(payload),
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return DeviceSummary.model_validate(row)

    async def add_alert(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        level: str,
        code: str,
        message: str,
        priority: str | None,
        triggered_at: str,
        payload: dict,
    ) -> AlertRecord:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO alerts (
                        gym_id,
                        device_type,
                        device_id,
                        level,
                        code,
                        message,
                        priority,
                        triggered_at,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, gym_id, device_type, device_id, level, code, message, priority, is_ack, triggered_at, payload
                    """,
                    (
                        gym_id,
                        device_type,
                        device_id,
                        level,
                        code,
                        message,
                        priority,
                        _coerce_timestamptz(triggered_at),
                        Jsonb(payload),
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _alert_record_from_row(row)

    async def record_binding_event(
        self,
        *,
        gym_id: str,
        wristband_id: str,
        equipment_id: str,
        action: str,
        reason: str | None,
        ts: int | None,
    ) -> None:
        event_time = _coerce_timestamptz(ts)
        duration_s = None

        if action == "unbind":
            async with self._pool.connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT ts
                        FROM equipment_binding_events
                        WHERE gym_id = %s
                          AND wristband_id = %s
                          AND equipment_id = %s
                          AND action = 'bind'
                        ORDER BY ts DESC
                        LIMIT 1
                        """,
                        (gym_id, wristband_id, equipment_id),
                    )
                    row = await cursor.fetchone()
                    if row is not None:
                        duration_s = int((event_time - row["ts"]).total_seconds())

                    await cursor.execute(
                        """
                        INSERT INTO equipment_binding_events (
                            wristband_id,
                            equipment_id,
                            gym_id,
                            action,
                            reason,
                            ts,
                            duration_s
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            wristband_id,
                            equipment_id,
                            gym_id,
                            action,
                            reason,
                            event_time,
                            duration_s,
                        ),
                    )
                await connection.commit()
            return

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO equipment_binding_events (
                        wristband_id,
                        equipment_id,
                        gym_id,
                        action,
                        reason,
                        ts,
                        duration_s
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        wristband_id,
                        equipment_id,
                        gym_id,
                        action,
                        reason,
                        event_time,
                        duration_s,
                    ),
                )
            await connection.commit()

    async def record_telemetry(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        payload: dict,
    ) -> None:
        table_name = _telemetry_table_name(device_type)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    INSERT INTO {table_name} (ts, gym_id, device_id, payload)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        _coerce_timestamptz(payload.get("ts")),
                        gym_id,
                        device_id,
                        Jsonb(payload),
                    ),
                )
            await connection.commit()

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[DeviceSummary]:
        clauses: list[str] = []
        params: list[Any] = []

        if device_type is not None:
            clauses.append("device_type = %s")
            params.append(device_type)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT gym_id, device_type, device_id, status, online, last_seen_ts, last_payload
                    FROM devices
                    {where_clause}
                    ORDER BY device_type, device_id
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [DeviceSummary.model_validate(row) for row in rows]

    async def get_device(self, *, device_id: str) -> DeviceSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT gym_id, device_type, device_id, status, online, last_seen_ts, last_payload
                    FROM devices
                    WHERE device_id = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (device_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return DeviceSummary.model_validate(row)

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
    ) -> list[AlertRecord]:
        clauses: list[str] = []
        params: list[Any] = []

        if level is not None:
            clauses.append("level = %s")
            params.append(level)
        if is_ack is not None:
            clauses.append("is_ack = %s")
            params.append(is_ack)

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT id, gym_id, device_type, device_id, level, code, message, priority, is_ack, triggered_at, payload
                    FROM alerts
                    {where_clause}
                    ORDER BY triggered_at DESC, id DESC
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [_alert_record_from_row(row) for row in rows]

    async def get_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, gym_id, device_type, device_id, level, code, message, priority, is_ack, triggered_at, payload
                    FROM alerts
                    WHERE id = %s
                    """,
                    (alert_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return _alert_record_from_row(row)

    async def ack_alert(self, *, alert_id: int) -> AlertRecord | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE alerts
                    SET is_ack = TRUE
                    WHERE id = %s
                    RETURNING id, gym_id, device_type, device_id, level, code, message, priority, is_ack, triggered_at, payload
                    """,
                    (alert_id,),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _alert_record_from_row(row)

    async def _bootstrap_schema(self) -> None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS devices (
                        gym_id TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        online BOOLEAN NOT NULL,
                        last_seen_ts BIGINT,
                        last_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (gym_id, device_type, device_id)
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        gym_id TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        level TEXT NOT NULL,
                        code TEXT NOT NULL,
                        message TEXT NOT NULL,
                        priority TEXT,
                        is_ack BOOLEAN NOT NULL DEFAULT FALSE,
                        triggered_at TIMESTAMPTZ NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS equipment_binding_events (
                        id BIGSERIAL PRIMARY KEY,
                        wristband_id TEXT NOT NULL,
                        equipment_id TEXT NOT NULL,
                        gym_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        reason TEXT,
                        ts TIMESTAMPTZ NOT NULL,
                        duration_s INTEGER
                    )
                    """
                )
                for table_name in (
                    "wristband_telemetry",
                    "equipment_telemetry",
                    "env_telemetry",
                ):
                    await cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            ts TIMESTAMPTZ NOT NULL,
                            gym_id TEXT NOT NULL,
                            device_id TEXT NOT NULL,
                            payload JSONB NOT NULL
                        )
                        """
                    )
                    await cursor.execute(
                        """
                        SELECT create_hypertable(%s, by_range('ts'), if_not_exists => TRUE)
                        """,
                        (table_name,),
                    )

                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at
                    ON alerts (triggered_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_binding_wristband_ts
                    ON equipment_binding_events (wristband_id, ts DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_binding_equipment_ts
                    ON equipment_binding_events (equipment_id, ts DESC)
                    """
                )
            await connection.commit()


def _telemetry_table_name(device_type: str) -> str:
    if device_type == "wristband":
        return "wristband_telemetry"
    if device_type == "equipment":
        return "equipment_telemetry"
    if device_type == "env":
        return "env_telemetry"
    raise ValueError(f"unsupported telemetry device type: {device_type}")


def _coerce_timestamptz(value: str | int | None) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC)
    return datetime.now(UTC)


def _alert_record_from_row(row: dict[str, Any]) -> AlertRecord:
    payload = row.get("payload") or {}
    return AlertRecord(
        id=row["id"],
        gym_id=row["gym_id"],
        device_type=row["device_type"],
        device_id=row["device_id"],
        level=row["level"],
        code=row["code"],
        message=row["message"],
        priority=row.get("priority"),
        is_ack=row["is_ack"],
        triggered_at=row["triggered_at"].isoformat(),
        payload=payload,
    )
