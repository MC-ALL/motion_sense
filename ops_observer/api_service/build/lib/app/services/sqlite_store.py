from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from app.models.ops import ModuleComponent, ModuleHealthSummary, ModuleStats, OpsAlertRecord


class OpsSqliteStore:
    def __init__(self, database_path: str) -> None:
        self._database_path = Path(database_path)
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._database_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS module_health (
                module_id TEXT PRIMARY KEY,
                module_type TEXT NOT NULL,
                display_name TEXT,
                online INTEGER NOT NULL,
                health_status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS module_components (
                module_id TEXT NOT NULL,
                component_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (module_id, component_id)
            );

            CREATE TABLE IF NOT EXISTS module_stats (
                module_id TEXT PRIMARY KEY,
                module_type TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ops_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL,
                module_type TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                payload_json TEXT NOT NULL
            );
            """
        )
        await self._ensure_column("ops_alerts", "closed_at", "TEXT")
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def save_module_snapshot(
        self,
        summary: ModuleHealthSummary,
        components: list[ModuleComponent],
        stats: ModuleStats | None,
        persisted_at: str,
    ) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
            INSERT INTO module_health (
                module_id,
                module_type,
                display_name,
                online,
                health_status,
                checked_at,
                payload_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(module_id) DO UPDATE SET
                module_type = excluded.module_type,
                display_name = excluded.display_name,
                online = excluded.online,
                health_status = excluded.health_status,
                checked_at = excluded.checked_at,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                summary.module_id,
                summary.module_type,
                summary.display_name,
                1 if summary.online else 0,
                summary.health_status,
                summary.checked_at,
                summary.model_dump_json(),
                persisted_at,
            ),
        )
        await connection.execute("DELETE FROM module_components WHERE module_id = ?", (summary.module_id,))
        for component in components:
            await connection.execute(
                """
                INSERT INTO module_components (module_id, component_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    component.module_id,
                    component.component_id,
                    component.model_dump_json(),
                    persisted_at,
                ),
            )

        if stats is not None:
            await connection.execute(
                """
                INSERT INTO module_stats (module_id, module_type, updated_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    module_type = excluded.module_type,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (stats.module_id, stats.module_type, persisted_at, stats.model_dump_json()),
            )

        await connection.commit()

    async def create_alert(
        self,
        *,
        module_id: str,
        module_type: str,
        alert_type: str,
        severity: str,
        title: str,
        detail: str,
        payload: dict,
        created_at: str,
    ) -> OpsAlertRecord:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            INSERT INTO ops_alerts (
                module_id,
                module_type,
                alert_type,
                severity,
                status,
                title,
                detail,
                created_at,
                updated_at,
                closed_at,
                payload_json
            ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, NULL, ?)
            """,
            (
                module_id,
                module_type,
                alert_type,
                severity,
                title,
                detail,
                created_at,
                created_at,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        await connection.commit()
        alert_id = cursor.lastrowid
        assert alert_id is not None
        return OpsAlertRecord(
            id=alert_id,
            module_id=module_id,
            module_type=module_type,
            alert_type=alert_type,
            severity=severity,
            status="open",
            title=title,
            detail=detail,
            created_at=created_at,
            updated_at=created_at,
            closed_at=None,
            payload=payload,
        )

    async def list_health(self) -> list[ModuleHealthSummary]:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT payload_json FROM module_health ORDER BY module_type, module_id"
        )
        rows = await cursor.fetchall()
        return [ModuleHealthSummary.model_validate_json(row["payload_json"]) for row in rows]

    async def get_health_detail(self, module_id: str) -> tuple[ModuleHealthSummary | None, list[ModuleComponent], ModuleStats | None]:
        connection = self._require_connection()
        summary_cursor = await connection.execute(
            "SELECT payload_json FROM module_health WHERE module_id = ?",
            (module_id,),
        )
        summary_row = await summary_cursor.fetchone()
        if summary_row is None:
            return None, [], None

        component_cursor = await connection.execute(
            "SELECT payload_json FROM module_components WHERE module_id = ? ORDER BY component_id",
            (module_id,),
        )
        component_rows = await component_cursor.fetchall()
        stats_cursor = await connection.execute(
            "SELECT payload_json FROM module_stats WHERE module_id = ?",
            (module_id,),
        )
        stats_row = await stats_cursor.fetchone()
        return (
            ModuleHealthSummary.model_validate_json(summary_row["payload_json"]),
            [ModuleComponent.model_validate_json(row["payload_json"]) for row in component_rows],
            ModuleStats.model_validate_json(stats_row["payload_json"]) if stats_row is not None else None,
        )

    async def list_stats(self) -> list[ModuleStats]:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT payload_json FROM module_stats ORDER BY module_type, module_id"
        )
        rows = await cursor.fetchall()
        return [ModuleStats.model_validate_json(row["payload_json"]) for row in rows]

    async def list_alerts(self, *, limit: int, status: str | None = None) -> list[OpsAlertRecord]:
        connection = self._require_connection()
        if status is None:
            cursor = await connection.execute(
                "SELECT * FROM ops_alerts ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = await connection.execute(
                "SELECT * FROM ops_alerts WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        rows = await cursor.fetchall()
        return [self._map_alert(row) for row in rows]

    async def close_alert(self, alert_id: int, updated_at: str) -> OpsAlertRecord | None:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            UPDATE ops_alerts
            SET status = 'closed', updated_at = ?, closed_at = COALESCE(closed_at, ?)
            WHERE id = ? AND status != 'closed'
            RETURNING *
            """,
            (updated_at, updated_at, alert_id),
        )
        row = await cursor.fetchone()
        if row is None:
            existing_cursor = await connection.execute(
                "SELECT * FROM ops_alerts WHERE id = ?",
                (alert_id,),
            )
            existing_row = await existing_cursor.fetchone()
            if existing_row is None:
                return None
            return self._map_alert(existing_row)
        await connection.commit()
        return self._map_alert(row)

    async def latest_updated_at(self) -> str | None:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT MAX(updated_at) AS updated_at FROM module_health"
        )
        row = await cursor.fetchone()
        return row["updated_at"] if row is not None else None

    def _map_alert(self, row: aiosqlite.Row) -> OpsAlertRecord:
        return OpsAlertRecord(
            id=row["id"],
            module_id=row["module_id"],
            module_type=row["module_type"],
            alert_type=row["alert_type"],
            severity=row["severity"],
            status=row["status"],
            title=row["title"],
            detail=row["detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            payload=json.loads(row["payload_json"]),
        )

    async def _ensure_column(self, table_name: str, column_name: str, column_sql: str) -> None:
        connection = self._require_connection()
        cursor = await connection.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        if any(row["name"] == column_name for row in rows):
            return
        await connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
        )

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("sqlite store is not initialized")
        return self._connection
