from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.models.auth import StoredRefreshSession
from app.models.device_config import DeviceConfigCommandRecord, GatewayCommandResultRequest
from app.models.ingest import (
    AlertRecord,
    BindingEventRecord,
    DeviceSummary,
    EnvTelemetryAggregateRecord,
    TelemetryRecord,
)
from app.models.user import StoredUser, UserRole, UserSummary
from app.models.workout import (
    BindingSource,
    UserWristbandBindingSummary,
    WorkoutSessionMetrics,
    WorkoutSessionSegment,
    WorkoutSessionSource,
    WorkoutSessionStatus,
    WorkoutSessionSummary,
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

    async def list_users(self) -> list[UserSummary]:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT username, role, gym_ids, device_ids, created_at, updated_at
                    FROM users
                    ORDER BY username
                    """
                )
                rows = await cursor.fetchall()

        return [_user_summary_from_row(row) for row in rows]

    async def get_user(self, *, username: str) -> StoredUser | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT username, role, gym_ids, device_ids, password_hash, created_at, updated_at
                    FROM users
                    WHERE username = %s
                    """,
                    (username,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return _stored_user_from_row(row)

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: UserRole,
        gym_ids: list[str],
        device_ids: list[str],
    ) -> UserSummary:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO users (username, role, gym_ids, device_ids, password_hash)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                    RETURNING username, role, gym_ids, device_ids, created_at, updated_at
                    """,
                    (username, role, Jsonb(gym_ids), Jsonb(device_ids), password_hash),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            raise ValueError("username already exists")
        return _user_summary_from_row(row)

    async def update_user(
        self,
        *,
        username: str,
        password_hash: str | None = None,
        role: UserRole | None = None,
        gym_ids: list[str] | None = None,
        device_ids: list[str] | None = None,
    ) -> UserSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE users
                    SET password_hash = COALESCE(%s, password_hash),
                        role = COALESCE(%s, role),
                        gym_ids = COALESCE(%s, gym_ids),
                        device_ids = COALESCE(%s, device_ids),
                        updated_at = NOW()
                    WHERE username = %s
                    RETURNING username, role, gym_ids, device_ids, created_at, updated_at
                    """,
                    (password_hash, role, Jsonb(gym_ids) if gym_ids is not None else None, Jsonb(device_ids) if device_ids is not None else None, username),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _user_summary_from_row(row)

    async def delete_user(self, *, username: str) -> bool:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM users
                    WHERE username = %s
                    RETURNING 1
                    """,
                    (username,),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return row is not None

    async def create_user_wristband_binding(
        self,
        *,
        username: str,
        wristband_id: str,
        gym_id: str,
        bound_at: str | None,
        source: BindingSource,
        note: str | None,
    ) -> UserWristbandBindingSummary:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id
                    FROM user_wristband_bindings
                    WHERE is_active = TRUE
                      AND username = %s
                    LIMIT 1
                    """,
                    (username,),
                )
                if await cursor.fetchone() is not None:
                    raise ValueError("user already has an active wristband binding")

                await cursor.execute(
                    """
                    SELECT id
                    FROM user_wristband_bindings
                    WHERE is_active = TRUE
                      AND wristband_id = %s
                    LIMIT 1
                    """,
                    (wristband_id,),
                )
                if await cursor.fetchone() is not None:
                    raise ValueError("wristband already bound to another user")

                await cursor.execute(
                    """
                    INSERT INTO user_wristband_bindings (
                        username,
                        wristband_id,
                        gym_id,
                        is_active,
                        bound_at,
                        unbound_at,
                        source,
                        note
                    )
                    VALUES (%s, %s, %s, TRUE, %s, NULL, %s, %s)
                    RETURNING id, username, wristband_id, gym_id, is_active, bound_at, unbound_at,
                              source, note, created_at, updated_at
                    """,
                    (
                        username,
                        wristband_id,
                        gym_id,
                        _coerce_timestamptz(bound_at),
                        source,
                        note,
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _user_wristband_binding_from_row(row)

    async def end_user_wristband_binding(
        self,
        *,
        binding_id: int,
        unbound_at: str | None,
        note: str | None,
    ) -> UserWristbandBindingSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE user_wristband_bindings
                    SET is_active = FALSE,
                        unbound_at = COALESCE(unbound_at, %s),
                        note = COALESCE(%s, note),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, username, wristband_id, gym_id, is_active, bound_at, unbound_at,
                              source, note, created_at, updated_at
                    """,
                    (_coerce_timestamptz(unbound_at), note, binding_id),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _user_wristband_binding_from_row(row)

    async def list_user_wristband_bindings(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        active_only: bool | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[UserWristbandBindingSummary]:
        clauses: list[str] = []
        params: list[Any] = []

        if username is not None:
            clauses.append("username = %s")
            params.append(username)
        if wristband_id is not None:
            clauses.append("wristband_id = %s")
            params.append(wristband_id)
        if gym_id is not None:
            clauses.append("gym_id = %s")
            params.append(gym_id)
        if active_only is not None:
            clauses.append("is_active = %s")
            params.append(active_only)

        params.extend([limit, offset])
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT id, username, wristband_id, gym_id, is_active, bound_at, unbound_at,
                           source, note, created_at, updated_at
                    FROM user_wristband_bindings
                    {where_clause}
                    ORDER BY bound_at DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [_user_wristband_binding_from_row(row) for row in rows]

    async def create_workout_session(
        self,
        *,
        username: str,
        wristband_id: str,
        gym_id: str,
        status: WorkoutSessionStatus,
        source: WorkoutSessionSource,
        started_at: str,
        ended_at: str | None,
        equipment_ids: list[str],
        segments: list[WorkoutSessionSegment],
        metrics: WorkoutSessionMetrics,
        notes: str | None,
    ) -> WorkoutSessionSummary:
        normalized_segments = _normalize_segments(segments)
        normalized_equipment_ids = _normalize_equipment_ids(
            equipment_ids=equipment_ids,
            segments=normalized_segments,
        )
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO workout_sessions (
                        username,
                        wristband_id,
                        gym_id,
                        status,
                        source,
                        started_at,
                        ended_at,
                        duration_s,
                        equipment_ids,
                        segments,
                        metrics,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING session_id, username, wristband_id, gym_id, status, source,
                              started_at, ended_at, duration_s, equipment_ids, segments, metrics,
                              notes, created_at, updated_at
                    """,
                    (
                        username,
                        wristband_id,
                        gym_id,
                        status,
                        source,
                        _coerce_timestamptz(started_at),
                        _coerce_timestamptz(ended_at) if ended_at is not None else None,
                        _session_duration_s(started_at=started_at, ended_at=ended_at),
                        Jsonb(normalized_equipment_ids),
                        Jsonb([item.model_dump(exclude_none=True) for item in normalized_segments]),
                        Jsonb(metrics.model_dump(exclude_none=True)),
                        notes,
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _workout_session_from_row(row)

    async def update_workout_session(
        self,
        *,
        session_id: str,
        status: WorkoutSessionStatus | None = None,
        ended_at: str | None = None,
        equipment_ids: list[str] | None = None,
        segments: list[WorkoutSessionSegment] | None = None,
        metrics: WorkoutSessionMetrics | None = None,
        notes: str | None = None,
    ) -> WorkoutSessionSummary | None:
        current = await self.get_workout_session(session_id=session_id)
        if current is None:
            return None

        next_segments = _normalize_segments(segments) if segments is not None else current.segments
        next_equipment_ids = _normalize_equipment_ids(
            equipment_ids=equipment_ids if equipment_ids is not None else current.equipment_ids,
            segments=next_segments,
        )
        next_ended_at = ended_at if ended_at is not None else current.ended_at

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE workout_sessions
                    SET status = COALESCE(%s, status),
                        ended_at = COALESCE(%s, ended_at),
                        duration_s = %s,
                        equipment_ids = %s,
                        segments = %s,
                        metrics = %s,
                        notes = COALESCE(%s, notes),
                        updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, username, wristband_id, gym_id, status, source,
                              started_at, ended_at, duration_s, equipment_ids, segments, metrics,
                              notes, created_at, updated_at
                    """,
                    (
                        status,
                        _coerce_timestamptz(ended_at) if ended_at is not None else None,
                        _session_duration_s(started_at=current.started_at, ended_at=next_ended_at),
                        Jsonb(next_equipment_ids),
                        Jsonb([item.model_dump(exclude_none=True) for item in next_segments]),
                        Jsonb((metrics or current.metrics).model_dump(exclude_none=True)),
                        notes,
                        session_id,
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _workout_session_from_row(row)

    async def get_workout_session(
        self,
        *,
        session_id: str,
    ) -> WorkoutSessionSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT session_id, username, wristband_id, gym_id, status, source,
                           started_at, ended_at, duration_s, equipment_ids, segments, metrics,
                           notes, created_at, updated_at
                    FROM workout_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return _workout_session_from_row(row)

    async def list_workout_sessions(
        self,
        *,
        username: str | None = None,
        wristband_id: str | None = None,
        gym_id: str | None = None,
        status: WorkoutSessionStatus | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[WorkoutSessionSummary]:
        clauses: list[str] = []
        params: list[Any] = []

        if username is not None:
            clauses.append("username = %s")
            params.append(username)
        if wristband_id is not None:
            clauses.append("wristband_id = %s")
            params.append(wristband_id)
        if gym_id is not None:
            clauses.append("gym_id = %s")
            params.append(gym_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        if start is not None:
            clauses.append("started_at >= %s")
            params.append(_coerce_timestamptz(start))
        if end is not None:
            clauses.append("COALESCE(ended_at, started_at) <= %s")
            params.append(_coerce_timestamptz(end))

        params.extend([limit, offset])
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    SELECT session_id, username, wristband_id, gym_id, status, source,
                           started_at, ended_at, duration_s, equipment_ids, segments, metrics,
                           notes, created_at, updated_at
                    FROM workout_sessions
                    {where_clause}
                    ORDER BY started_at DESC, created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [_workout_session_from_row(row) for row in rows]

    async def create_refresh_session(
        self,
        *,
        session_id: str,
        username: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO refresh_sessions (session_id, username, refresh_jti, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        refresh_jti = EXCLUDED.refresh_jti,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = NOW()
                    RETURNING session_id, username, refresh_jti, expires_at
                    """,
                    (session_id, username, refresh_jti, _from_epoch_s(expires_at_s)),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _refresh_session_from_row(row)

    async def get_refresh_session(self, *, session_id: str) -> StoredRefreshSession | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT session_id, username, refresh_jti, expires_at
                    FROM refresh_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return _refresh_session_from_row(row)

    async def update_refresh_session(
        self,
        *,
        session_id: str,
        refresh_jti: str,
        expires_at_s: int,
    ) -> StoredRefreshSession | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE refresh_sessions
                    SET refresh_jti = %s,
                        expires_at = %s,
                        updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, username, refresh_jti, expires_at
                    """,
                    (refresh_jti, _from_epoch_s(expires_at_s), session_id),
                )
                row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _refresh_session_from_row(row)

    async def delete_refresh_session(self, *, session_id: str) -> bool:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM refresh_sessions
                    WHERE session_id = %s
                    RETURNING 1
                    """,
                    (session_id,),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return row is not None

    async def delete_expired_refresh_sessions(self, *, now_s: int) -> int:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM refresh_sessions
                    WHERE expires_at <= %s
                    """,
                    (_from_epoch_s(now_s),),
                )
                deleted = cursor.rowcount
            await connection.commit()

        return deleted

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
        gateway_id = _resolve_gateway_id(device_type=device_type, device_id=device_id, payload=payload)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO devices (
                        gym_id,
                        device_type,
                        device_id,
                        gateway_id,
                        status,
                        online,
                        last_seen_ts,
                        last_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gym_id, device_type, device_id)
                    DO UPDATE SET
                        gateway_id = COALESCE(devices.gateway_id, EXCLUDED.gateway_id),
                        status = EXCLUDED.status,
                        online = EXCLUDED.online,
                        last_seen_ts = EXCLUDED.last_seen_ts,
                        last_payload = EXCLUDED.last_payload,
                        updated_at = NOW()
                    RETURNING gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                              status, online, last_seen_ts, last_payload, registered_at, updated_at
                    """,
                    (
                        gym_id,
                        device_type,
                        device_id,
                        gateway_id,
                        status,
                        online,
                        last_seen_ts,
                        Jsonb(payload),
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _device_summary_from_row(row)

    async def register_device(
        self,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
        gateway_id: str | None,
        display_name: str | None,
        location: str | None,
        metadata: dict,
    ) -> DeviceSummary:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await self._ensure_device_id_unique(
                    cursor,
                    gym_id=gym_id,
                    device_type=device_type,
                    device_id=device_id,
                )
                await cursor.execute(
                    """
                    INSERT INTO devices (
                        gym_id,
                        device_type,
                        device_id,
                        gateway_id,
                        display_name,
                        location,
                        metadata,
                        status,
                        online,
                        last_seen_ts,
                        last_payload,
                        registered_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'registered', FALSE, NULL, '{}'::jsonb, NOW(), NOW())
                    ON CONFLICT (gym_id, device_type, device_id)
                    DO UPDATE SET
                        gateway_id = EXCLUDED.gateway_id,
                        display_name = EXCLUDED.display_name,
                        location = EXCLUDED.location,
                        metadata = EXCLUDED.metadata,
                        registered_at = COALESCE(devices.registered_at, NOW()),
                        updated_at = NOW()
                    RETURNING gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                              status, online, last_seen_ts, last_payload, registered_at, updated_at
                    """,
                    (
                        gym_id,
                        device_type,
                        device_id,
                        gateway_id,
                        display_name,
                        location,
                        Jsonb(metadata),
                    ),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return _device_summary_from_row(row)

    async def update_device_registration(
        self,
        *,
        device_id: str,
        updates: dict,
    ) -> DeviceSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                           status, online, last_seen_ts, last_payload, registered_at, updated_at
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

                gateway_id = updates.get("gateway_id", row.get("gateway_id"))
                display_name = updates.get("display_name", row.get("display_name"))
                location = updates.get("location", row.get("location"))
                metadata = updates.get("metadata", row.get("metadata") or {})

                await cursor.execute(
                    """
                    UPDATE devices
                    SET gateway_id = %s,
                        display_name = %s,
                        location = %s,
                        metadata = %s,
                        updated_at = NOW()
                    WHERE gym_id = %s
                      AND device_type = %s
                      AND device_id = %s
                    RETURNING gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                              status, online, last_seen_ts, last_payload, registered_at, updated_at
                    """,
                    (
                        gateway_id,
                        display_name,
                        location,
                        Jsonb(metadata),
                        row["gym_id"],
                        row["device_type"],
                        row["device_id"],
                    ),
                )
                updated = await cursor.fetchone()
            await connection.commit()

        return _device_summary_from_row(updated)

    async def delete_device(
        self,
        *,
        device_id: str,
    ) -> bool:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    DELETE FROM devices
                    WHERE device_id = %s
                    RETURNING 1
                    """,
                    (device_id,),
                )
                row = await cursor.fetchone()
            await connection.commit()

        return row is not None

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
                    SELECT gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                           status, online, last_seen_ts, last_payload, registered_at, updated_at
                    FROM devices
                    {where_clause}
                    ORDER BY device_type, device_id
                    """,
                    params,
                )
                rows = await cursor.fetchall()

        return [_device_summary_from_row(row) for row in rows]

    async def get_device(self, *, device_id: str) -> DeviceSummary | None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT gym_id, device_type, device_id, gateway_id, display_name, location, metadata,
                           status, online, last_seen_ts, last_payload, registered_at, updated_at
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
        return _device_summary_from_row(row)

    async def list_alerts(
        self,
        level: str | None = None,
        is_ack: bool | None = None,
        device_id: str | None = None,
    ) -> list[AlertRecord]:
        clauses: list[str] = []
        params: list[Any] = []

        if level is not None:
            clauses.append("level = %s")
            params.append(level)
        if is_ack is not None:
            clauses.append("is_ack = %s")
            params.append(is_ack)
        if device_id is not None:
            clauses.append("device_id = %s")
            params.append(device_id)

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
        max_attempts: int,
        retry_backoff_s: int,
        next_retry_at: str,
        expires_at: str,
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
                        attempt_count,
                        max_attempts,
                        retry_backoff_s,
                        next_retry_at,
                        expires_at,
                        result_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', 0, %s, %s, %s, %s, '{}'::jsonb)
                    RETURNING command_id, gateway_id, gym_id, device_type, device_id, topic,
                              qos, retain, payload, status, attempt_count, max_attempts,
                              retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                              expires_at, created_at, updated_at,
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
                        max_attempts,
                        retry_backoff_s,
                        _coerce_timestamptz(next_retry_at),
                        _coerce_timestamptz(expires_at),
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
        delivery_lease_s: int = 15,
    ) -> list[DeviceConfigCommandRecord]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=delivery_lease_s)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE device_config_commands
                    SET status = 'timed_out',
                        updated_at = %s,
                        leased_until = NULL,
                        next_retry_at = NULL,
                        result_detail = COALESCE(result_detail, 'command expired before successful delivery')
                    WHERE gateway_id = %s
                      AND status = 'pending'
                      AND expires_at <= %s
                    """,
                    (now, gateway_id, now),
                )
                await cursor.execute(
                    """
                    SELECT command_id, gateway_id, gym_id, device_type, device_id, topic,
                           qos, retain, payload, status, attempt_count, max_attempts,
                           retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                           expires_at, created_at, updated_at, result_detail, result_payload
                    FROM device_config_commands
                    WHERE gateway_id = %s
                      AND status = 'pending'
                      AND next_retry_at <= %s
                      AND (leased_until IS NULL OR leased_until <= %s)
                      AND expires_at > %s
                    ORDER BY created_at ASC, command_id ASC
                    LIMIT %s
                    FOR UPDATE
                    """,
                    (gateway_id, now, now, now, limit),
                )
                rows = await cursor.fetchall()

                claimed_rows: list[dict[str, Any]] = []
                for row in rows:
                    await cursor.execute(
                        """
                        UPDATE device_config_commands
                        SET attempt_count = attempt_count + 1,
                            last_attempt_at = %s,
                            leased_until = %s,
                            updated_at = %s
                        WHERE command_id = %s
                        RETURNING command_id, gateway_id, gym_id, device_type, device_id, topic,
                                  qos, retain, payload, status, attempt_count, max_attempts,
                                  retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                                  expires_at, created_at, updated_at, result_detail, result_payload
                        """,
                        (now, lease_until, now, row["command_id"]),
                    )
                    claimed_rows.append(await cursor.fetchone())
            await connection.commit()

        return [_device_config_command_from_row(row) for row in claimed_rows]

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
                           qos, retain, payload, status, attempt_count, max_attempts,
                           retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                           expires_at, created_at, updated_at,
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
                    SELECT command_id, gateway_id, gym_id, device_type, device_id, topic,
                           qos, retain, payload, status, attempt_count, max_attempts,
                           retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                           expires_at, created_at, updated_at, result_detail, result_payload
                    FROM device_config_commands
                    WHERE command_id = %s
                      AND gateway_id = %s
                    FOR UPDATE
                    """,
                    (command_id, gateway_id),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    row = None
                elif existing["status"] in {"succeeded", "failed", "timed_out"}:
                    row = existing
                else:
                    reported_at = _coerce_timestamptz(result.reported_at)
                    new_status = result.status
                    next_retry_at: datetime | None = None

                    if result.status == "failed":
                        if reported_at >= existing["expires_at"]:
                            new_status = "timed_out"
                        elif existing["attempt_count"] >= existing["max_attempts"]:
                            new_status = "failed"
                        else:
                            new_status = "pending"
                            next_retry_at = reported_at + timedelta(
                                seconds=existing["retry_backoff_s"]
                            )

                    await cursor.execute(
                        """
                        UPDATE device_config_commands
                        SET status = %s,
                            updated_at = %s,
                            result_detail = %s,
                            result_payload = %s,
                            leased_until = NULL,
                            next_retry_at = %s
                        WHERE command_id = %s
                          AND gateway_id = %s
                        RETURNING command_id, gateway_id, gym_id, device_type, device_id, topic,
                                  qos, retain, payload, status, attempt_count, max_attempts,
                                  retry_backoff_s, last_attempt_at, next_retry_at, leased_until,
                                  expires_at, created_at, updated_at, result_detail, result_payload
                        """,
                        (
                            new_status,
                            reported_at,
                            result.detail,
                            Jsonb(result.result_payload),
                            next_retry_at,
                            command_id,
                            gateway_id,
                        ),
                    )
                    row = await cursor.fetchone()
            await connection.commit()

        if row is None:
            return None
        return _device_config_command_from_row(row)

    async def _bootstrap_schema(self) -> None:
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                await cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        role TEXT NOT NULL,
                        gym_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        device_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS refresh_sessions (
                        session_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        refresh_jti TEXT NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS gym_ids JSONB NOT NULL DEFAULT '[]'::jsonb
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS device_ids JSONB NOT NULL DEFAULT '[]'::jsonb
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS devices (
                        gym_id TEXT NOT NULL,
                        device_type TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        gateway_id TEXT,
                        display_name TEXT,
                        location TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        status TEXT NOT NULL,
                        online BOOLEAN NOT NULL,
                        last_seen_ts BIGINT,
                        last_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        registered_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (gym_id, device_type, device_id)
                    )
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE devices
                    ADD COLUMN IF NOT EXISTS gateway_id TEXT
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE devices
                    ADD COLUMN IF NOT EXISTS display_name TEXT
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE devices
                    ADD COLUMN IF NOT EXISTS location TEXT
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE devices
                    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE devices
                    ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ
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
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_wristband_bindings (
                        id BIGSERIAL PRIMARY KEY,
                        username TEXT NOT NULL,
                        wristband_id TEXT NOT NULL,
                        gym_id TEXT NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        bound_at TIMESTAMPTZ NOT NULL,
                        unbound_at TIMESTAMPTZ,
                        source TEXT NOT NULL DEFAULT 'manual',
                        note TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workout_sessions (
                        session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        username TEXT NOT NULL,
                        wristband_id TEXT NOT NULL,
                        gym_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'manual',
                        started_at TIMESTAMPTZ NOT NULL,
                        ended_at TIMESTAMPTZ,
                        duration_s INTEGER,
                        equipment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        segments JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                        notes TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS retry_backoff_s INTEGER NOT NULL DEFAULT 5
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ DEFAULT NOW()
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS leased_until TIMESTAMPTZ
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '5 minutes')
                    """
                )
                await cursor.execute(
                    """
                    ALTER TABLE device_config_commands
                    ALTER COLUMN next_retry_at DROP NOT NULL
                    """
                )
                await cursor.execute(
                    """
                    UPDATE device_config_commands
                    SET attempt_count = COALESCE(attempt_count, 0),
                        max_attempts = COALESCE(max_attempts, 3),
                        retry_backoff_s = COALESCE(retry_backoff_s, 5),
                        next_retry_at = COALESCE(next_retry_at, created_at),
                        expires_at = COALESCE(expires_at, created_at + INTERVAL '5 minutes')
                    WHERE attempt_count IS NULL
                       OR max_attempts IS NULL
                       OR retry_backoff_s IS NULL
                       OR next_retry_at IS NULL
                       OR expires_at IS NULL
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
                    CREATE INDEX IF NOT EXISTS idx_users_role
                    ON users (role, username)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_refresh_sessions_username
                    ON refresh_sessions (username, expires_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_refresh_sessions_expires_at
                    ON refresh_sessions (expires_at ASC)
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
                    CREATE INDEX IF NOT EXISTS idx_user_wristband_bindings_username_active
                    ON user_wristband_bindings (username, is_active, bound_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_wristband_bindings_wristband_active
                    ON user_wristband_bindings (wristband_id, is_active, bound_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_workout_sessions_username_started_at
                    ON workout_sessions (username, started_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_workout_sessions_wristband_started_at
                    ON workout_sessions (wristband_id, started_at DESC)
                    """
                )
                await cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_device_config_commands_gateway_pending
                    ON device_config_commands (gateway_id, status, next_retry_at ASC, created_at ASC)
                    """
                )
            await connection.commit()

    async def _ensure_device_id_unique(
        self,
        cursor,
        *,
        gym_id: str,
        device_type: str,
        device_id: str,
    ) -> None:
        await cursor.execute(
            """
            SELECT gym_id, device_type
            FROM devices
            WHERE device_id = %s
              AND (gym_id <> %s OR device_type <> %s)
            LIMIT 1
            """,
            (device_id, gym_id, device_type),
        )
        row = await cursor.fetchone()
        if row is not None:
            raise ValueError("device_id already exists with different gym_id or device_type")


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


def _from_epoch_s(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def _device_summary_from_row(row: dict[str, Any]) -> DeviceSummary:
    return DeviceSummary(
        gym_id=row["gym_id"],
        device_type=row["device_type"],
        device_id=row["device_id"],
        gateway_id=row.get("gateway_id"),
        display_name=row.get("display_name"),
        location=row.get("location"),
        metadata=row.get("metadata"),
        status=row["status"],
        online=row["online"],
        last_seen_ts=row.get("last_seen_ts"),
        last_payload=row.get("last_payload") or {},
        registered_at=(
            row["registered_at"].isoformat() if row.get("registered_at") is not None else None
        ),
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
    ).model_copy(
        update={
            "updated_at": (
                row["updated_at"].isoformat()
                if row.get("registered_at") is not None and row.get("updated_at") is not None
                else None
            )
        }
    )


def _stored_user_from_row(row: dict[str, Any]) -> StoredUser:
    return StoredUser(
        username=row["username"],
        role=row["role"],
        gym_ids=list(row.get("gym_ids") or []),
        device_ids=list(row.get("device_ids") or []),
        password_hash=row["password_hash"],
        created_at=row["created_at"].isoformat() if row.get("created_at") is not None else None,
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
    )


def _user_summary_from_row(row: dict[str, Any]) -> UserSummary:
    return UserSummary(
        username=row["username"],
        role=row["role"],
        gym_ids=list(row.get("gym_ids") or []),
        device_ids=list(row.get("device_ids") or []),
        created_at=row["created_at"].isoformat() if row.get("created_at") is not None else None,
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
    )


def _refresh_session_from_row(row: dict[str, Any]) -> StoredRefreshSession:
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return StoredRefreshSession(
        session_id=row["session_id"],
        username=row["username"],
        refresh_jti=row["refresh_jti"],
        expires_at_s=int(expires_at.timestamp()),
    )


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


def _user_wristband_binding_from_row(row: dict[str, Any]) -> UserWristbandBindingSummary:
    return UserWristbandBindingSummary(
        id=row["id"],
        username=row["username"],
        wristband_id=row["wristband_id"],
        gym_id=row["gym_id"],
        is_active=row["is_active"],
        bound_at=row["bound_at"].isoformat(),
        unbound_at=row["unbound_at"].isoformat() if row.get("unbound_at") is not None else None,
        source=row["source"],
        note=row.get("note"),
        created_at=row["created_at"].isoformat() if row.get("created_at") is not None else None,
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
    )


def _workout_session_from_row(row: dict[str, Any]) -> WorkoutSessionSummary:
    segments = [
        WorkoutSessionSegment.model_validate(item)
        for item in (row.get("segments") or [])
    ]
    return WorkoutSessionSummary(
        session_id=str(row["session_id"]),
        username=row["username"],
        wristband_id=row["wristband_id"],
        gym_id=row["gym_id"],
        status=row["status"],
        source=row["source"],
        started_at=row["started_at"].isoformat(),
        ended_at=row["ended_at"].isoformat() if row.get("ended_at") is not None else None,
        duration_s=row.get("duration_s"),
        equipment_ids=list(row.get("equipment_ids") or []),
        segments=segments,
        metrics=WorkoutSessionMetrics.model_validate(row.get("metrics") or {}),
        notes=row.get("notes"),
        created_at=row["created_at"].isoformat() if row.get("created_at") is not None else None,
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") is not None else None,
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
        attempt_count=row.get("attempt_count", 0),
        max_attempts=row.get("max_attempts", 3),
        retry_backoff_s=row.get("retry_backoff_s", 5),
        last_attempt_at=(
            row["last_attempt_at"].isoformat() if row.get("last_attempt_at") is not None else None
        ),
        next_retry_at=(
            row["next_retry_at"].isoformat() if row.get("next_retry_at") is not None else None
        ),
        leased_until=(
            row["leased_until"].isoformat() if row.get("leased_until") is not None else None
        ),
        expires_at=row["expires_at"].isoformat(),
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
        result_detail=row["result_detail"],
        result_payload=row.get("result_payload") or {},
    )



def _resolve_gateway_id(*, device_type: str, device_id: str, payload: dict[str, Any]) -> str | None:
    payload_gateway_id = payload.get("gateway_id")
    if isinstance(payload_gateway_id, str) and payload_gateway_id:
        return payload_gateway_id
    if device_type == "gateway":
        return device_id
    return None


def _normalize_segments(segments: list[WorkoutSessionSegment] | None) -> list[WorkoutSessionSegment]:
    normalized: list[WorkoutSessionSegment] = []
    for segment in segments or []:
        duration_s = segment.duration_s
        normalized_started_at = _coerce_timestamptz(segment.started_at).isoformat()
        normalized_ended_at = _coerce_timestamptz(segment.ended_at).isoformat() if segment.ended_at is not None else None
        if duration_s is None and normalized_ended_at is not None:
            duration_s = _session_duration_s(
                started_at=normalized_started_at,
                ended_at=normalized_ended_at,
            )
        normalized.append(
            segment.model_copy(
                update={
                    "started_at": normalized_started_at,
                    "ended_at": normalized_ended_at,
                    "duration_s": duration_s,
                }
            )
        )
    return normalized


def _normalize_equipment_ids(
    *,
    equipment_ids: list[str] | None,
    segments: list[WorkoutSessionSegment],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in equipment_ids or []:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    for segment in segments:
        if segment.equipment_id in seen:
            continue
        seen.add(segment.equipment_id)
        normalized.append(segment.equipment_id)
    return normalized


def _session_duration_s(*, started_at: str, ended_at: str | None) -> int | None:
    if ended_at is None:
        return None
    return max(int((_coerce_timestamptz(ended_at) - _coerce_timestamptz(started_at)).total_seconds()), 0)
    return None
