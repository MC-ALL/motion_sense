from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.models.device_config import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.models.ingest import (
    AlertRecord,
    BindingEventRecord,
    DeviceSummary,
    EnvTelemetryAggregateRecord,
    TelemetryRecord,
)
from app.models.system_health import (
    GatewayHealthComponentRecord,
    GatewayHealthDetail,
    GatewayHealthReportRequest,
    GatewayHealthSummary,
    derive_overall_status,
)
from app.settings import RuntimeSettings
from app.storage.telemetry_aggregate import aggregate_env_records


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

    async def batch_ack_alerts(self, *, alert_ids: list[int]) -> list[AlertRecord]:
        if not alert_ids:
            return []

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE alerts
                    SET is_ack = TRUE
                    WHERE id = ANY(%s)
                    RETURNING id, gym_id, device_type, device_id, level, code, message, priority, is_ack, triggered_at, payload
                    """,
                    (alert_ids,),
                )
                rows = await cursor.fetchall()
            await connection.commit()

        return sorted((_alert_record_from_row(row) for row in rows), key=lambda item: item.id)

    async def list_telemetry(
        self,
        *,
        device_type: str,
        device_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TelemetryRecord]:
        clauses = ["device_id = %s"]
        params: list[Any] = [device_id]
        table_name = _telemetry_table_name(device_type)

        if start is not None:
            clauses.append("ts >= %s")
            params.append(_coerce_timestamptz(start))
        if end is not None:
            clauses.append("ts <= %s")
            params.append(_coerce_timestamptz(end))

        params.extend([limit, offset])
        where_clause = " AND ".join(clauses)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT ts, gym_id, device_id, payload
                    FROM {table_name}
                    WHERE {where_clause}
                    ORDER BY ts DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [
            TelemetryRecord(
                ts=row["ts"].isoformat(),
                gym_id=row["gym_id"],
                device_type=device_type,
                device_id=row["device_id"],
                payload=row["payload"] or {},
            )
            for row in rows
        ]

    async def list_binding_events(
        self,
        *,
        wristband_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[BindingEventRecord]:
        clauses = ["wristband_id = %s"]
        params: list[Any] = [wristband_id]

        if start is not None:
            clauses.append("ts >= %s")
            params.append(_coerce_timestamptz(start))
        if end is not None:
            clauses.append("ts <= %s")
            params.append(_coerce_timestamptz(end))

        params.extend([limit, offset])
        where_clause = " AND ".join(clauses)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT id, wristband_id, equipment_id, gym_id, action, reason, ts, duration_s
                    FROM equipment_binding_events
                    WHERE {where_clause}
                    ORDER BY ts DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [
            BindingEventRecord(
                id=row["id"],
                wristband_id=row["wristband_id"],
                equipment_id=row["equipment_id"],
                gym_id=row["gym_id"],
                action=row["action"],
                reason=row["reason"],
                ts=row["ts"].isoformat(),
                duration_s=row["duration_s"],
            )
            for row in rows
        ]

    async def aggregate_env_telemetry(
        self,
        *,
        device_id: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[EnvTelemetryAggregateRecord]:
        records = await self.list_telemetry(
            device_type="env",
            device_id=device_id,
            start=start,
            end=end,
            limit=100000,
            offset=0,
        )
        return aggregate_env_records(records, interval, limit=limit, offset=offset)

    async def upsert_gateway_health_report(
        self,
        *,
        report: GatewayHealthReportRequest,
    ) -> GatewayHealthDetail:
        component_ids = [component.component_id for component in report.components]
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM gateway_component_health
                    WHERE gateway_id = %s
                      AND NOT (component_id = ANY(%s))
                    """,
                    (report.gateway_id, component_ids),
                )
                for component in report.components:
                    await cursor.execute(
                        """
                        INSERT INTO gateway_component_health (
                            gateway_id,
                            gym_id,
                            component_id,
                            component_type,
                            display_name,
                            online,
                            health_status,
                            reported_at,
                            checked_at,
                            endpoint,
                            latency_ms,
                            detail,
                            extra
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (gateway_id, component_id)
                        DO UPDATE SET
                            gym_id = EXCLUDED.gym_id,
                            component_type = EXCLUDED.component_type,
                            display_name = EXCLUDED.display_name,
                            online = EXCLUDED.online,
                            health_status = EXCLUDED.health_status,
                            reported_at = EXCLUDED.reported_at,
                            checked_at = EXCLUDED.checked_at,
                            endpoint = EXCLUDED.endpoint,
                            latency_ms = EXCLUDED.latency_ms,
                            detail = EXCLUDED.detail,
                            extra = EXCLUDED.extra
                        """,
                        (
                            report.gateway_id,
                            report.gym_id,
                            component.component_id,
                            component.component_type,
                            component.display_name,
                            component.online,
                            component.health_status,
                            _coerce_timestamptz(report.reported_at),
                            _coerce_timestamptz(component.checked_at),
                            component.endpoint,
                            component.latency_ms,
                            component.detail,
                            Jsonb(component.extra),
                        ),
                    )
            await connection.commit()

        detail = await self.get_gateway_health_detail(gateway_id=report.gateway_id)
        assert detail is not None
        return detail

    async def list_gateway_health_summaries(
        self,
        *,
        gym_id: str | None = None,
        gateway_id: str | None = None,
        component_type: str | None = None,
        overall_status: str | None = None,
    ) -> list[GatewayHealthSummary]:
        details = await self._list_gateway_health_details(
            gym_id=gym_id,
            gateway_id=gateway_id,
            component_type=component_type,
        )
        summaries = [
            GatewayHealthSummary(
                gateway_id=item.gateway_id,
                gym_id=item.gym_id,
                reported_at=item.reported_at,
                component_count=item.component_count,
                online_count=item.online_count,
                unhealthy_count=item.unhealthy_count,
                overall_status=item.overall_status,
            )
            for item in details
            if overall_status is None or item.overall_status == overall_status
        ]
        return summaries

    async def get_gateway_health_detail(
        self,
        *,
        gateway_id: str,
    ) -> GatewayHealthDetail | None:
        details = await self._list_gateway_health_details(gateway_id=gateway_id)
        if not details:
            return None
        return details[0]

    async def create_device_config_command(
        self,
        *,
        gateway_id: str,
        gym_id: str,
        device_type: str,
        device_id: str,
        topic: str,
        qos: int,
        retain: bool,
        payload: dict,
    ) -> DeviceConfigCommandRecord:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO device_config_commands (
                        gateway_id,
                        gym_id,
                        device_type,
                        device_id,
                        topic,
                        qos,
                        retain,
                        payload,
                        status,
                        result_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', '{}'::jsonb)
                    RETURNING command_id, gateway_id, gym_id, device_type, device_id, topic,
                              qos, retain, payload, status, created_at, updated_at,
                              result_detail, result_payload
                    """,
                    (
                        gateway_id,
                        gym_id,
                        device_type,
                        device_id,
                        topic,
                        qos,
                        retain,
                        Jsonb(payload),
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _device_config_command_from_row(row)

    async def list_pending_device_config_commands(
        self,
        *,
        gateway_id: str,
        limit: int = 100,
    ) -> list[DeviceConfigCommandRecord]:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT command_id, gateway_id, gym_id, device_type, device_id, topic,
                           qos, retain, payload, status, created_at, updated_at,
                           result_detail, result_payload
                    FROM device_config_commands
                    WHERE gateway_id = %s
                      AND status = 'pending'
                    ORDER BY created_at ASC, command_id ASC
                    LIMIT %s
                    """,
                    (gateway_id, limit),
                )
                rows = await cursor.fetchall()

        return [_device_config_command_from_row(row) for row in rows]

    async def get_device_config_command(
        self,
        *,
        command_id: str,
    ) -> DeviceConfigCommandRecord | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT command_id, gateway_id, gym_id, device_type, device_id, topic,
                           qos, retain, payload, status, created_at, updated_at,
                           result_detail, result_payload
                    FROM device_config_commands
                    WHERE command_id = %s
                    """,
                    (command_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return _device_config_command_from_row(row)

    async def update_device_config_command_result(
        self,
        *,
        gateway_id: str,
        command_id: str,
        result: GatewayCommandResultRequest,
    ) -> DeviceConfigCommandRecord | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE device_config_commands
                    SET status = %s,
                        updated_at = %s,
                        result_detail = %s,
                        result_payload = %s
                    WHERE command_id = %s
                      AND gateway_id = %s
                    RETURNING command_id, gateway_id, gym_id, device_type, device_id, topic,
                              qos, retain, payload, status, created_at, updated_at,
                              result_detail, result_payload
                    """,
                    (
                        result.status,
                        _coerce_timestamptz(result.reported_at),
                        result.detail,
                        Jsonb(result.result_payload),
                        command_id,
                        gateway_id,
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _device_config_command_from_row(row)

    async def _list_gateway_health_details(
        self,
        *,
        gym_id: str | None = None,
        gateway_id: str | None = None,
        component_type: str | None = None,
    ) -> list[GatewayHealthDetail]:
        clauses: list[str] = []
        params: list[Any] = []

        if gym_id is not None:
            clauses.append("gym_id = %s")
            params.append(gym_id)
        if gateway_id is not None:
            clauses.append("gateway_id = %s")
            params.append(gateway_id)
        if component_type is not None:
            clauses.append("component_type = %s")
            params.append(component_type)

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT gateway_id, gym_id, component_id, component_type, display_name, online,
                           health_status, reported_at, checked_at, endpoint, latency_ms, detail, extra
                    FROM gateway_component_health
                    {where_clause}
                    ORDER BY gateway_id, component_type, component_id
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return _group_gateway_health_rows(rows)

    async def _bootstrap_schema(self) -> None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                await cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
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
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gateway_component_health (
                        gateway_id TEXT NOT NULL,
                        gym_id TEXT NOT NULL,
                        component_id TEXT NOT NULL,
                        component_type TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        online BOOLEAN NOT NULL,
                        health_status TEXT NOT NULL,
                        reported_at TIMESTAMPTZ NOT NULL,
                        checked_at TIMESTAMPTZ NOT NULL,
                        endpoint TEXT,
                        latency_ms INTEGER,
                        detail TEXT,
                        extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                        PRIMARY KEY (gateway_id, component_id)
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_config_commands (
                        command_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        gateway_id TEXT NOT NULL,
                        gym_id TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        qos INTEGER NOT NULL,
                        retain BOOLEAN NOT NULL,
                        payload JSONB NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        result_detail TEXT,
                        result_payload JSONB NOT NULL DEFAULT '{}'::jsonb
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
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{table_name}_device_ts
                        ON {table_name} (device_id, ts DESC)
                        """
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
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_gateway_component_health_gateway
                    ON gateway_component_health (gateway_id, reported_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_device_config_commands_gateway_pending
                    ON device_config_commands (gateway_id, status, created_at ASC)
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


def _device_config_command_from_row(row: dict[str, Any]) -> DeviceConfigCommandRecord:
    return DeviceConfigCommandRecord(
        command_id=str(row["command_id"]),
        gateway_id=row["gateway_id"],
        gym_id=row["gym_id"],
        device_type=row["device_type"],
        device_id=row["device_id"],
        topic=row["topic"],
        qos=row["qos"],
        retain=row["retain"],
        payload=row.get("payload") or {},
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
        result_detail=row["result_detail"],
        result_payload=row.get("result_payload") or {},
    )


def _group_gateway_health_rows(rows: list[dict[str, Any]]) -> list[GatewayHealthDetail]:
    grouped: dict[str, list[GatewayHealthComponentRecord]] = {}
    for row in rows:
        grouped.setdefault(row["gateway_id"], []).append(
            GatewayHealthComponentRecord(
                gateway_id=row["gateway_id"],
                gym_id=row["gym_id"],
                reported_at=row["reported_at"].isoformat(),
                component_id=row["component_id"],
                component_type=row["component_type"],
                display_name=row["display_name"],
                online=row["online"],
                health_status=row["health_status"],
                checked_at=row["checked_at"].isoformat(),
                endpoint=row["endpoint"],
                latency_ms=row["latency_ms"],
                detail=row["detail"],
                extra=row.get("extra") or {},
            )
        )

    details: list[GatewayHealthDetail] = []
    for gateway_id, components in grouped.items():
        components = sorted(components, key=lambda item: (item.component_type, item.component_id))
        reported_at = max(item.reported_at for item in components)
        online_count = sum(1 for item in components if item.online)
        unhealthy_count = sum(
            1 for item in components if (not item.online) or item.health_status != "healthy"
        )
        details.append(
            GatewayHealthDetail(
                gateway_id=gateway_id,
                gym_id=components[0].gym_id,
                reported_at=reported_at,
                component_count=len(components),
                online_count=online_count,
                unhealthy_count=unhealthy_count,
                overall_status=derive_overall_status(components),
                components=components,
            )
        )

    return sorted(details, key=lambda item: item.gateway_id)
