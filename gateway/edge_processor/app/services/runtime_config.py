from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.settings import RuntimeSettings


LOGGER = logging.getLogger(__name__)


class RuntimeConfigManager:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._rules_path = Path("/runtime/config/edge_processor/rules.yaml")
        self._last_rules_mtime_ns: int | None = None

    @property
    def rules_path(self) -> Path:
        return self._rules_path

    def update_from_gateway_config(self, payload: dict[str, Any]) -> None:
        alert_rules = payload.get("alert_rules")
        if isinstance(alert_rules, dict):
            current = self._read_yaml(self._rules_path)
            current["alert_rules"] = alert_rules
            self._rules_path.write_text(
                yaml.safe_dump(current, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            LOGGER.info("updated alert rules from gateway config")

        if "batch_interval_s" in payload or "backend_base_url" in payload:
            LOGGER.warning(
                "gateway config contains restart-required fields; change will apply after edge_processor restart"
            )

    def poll_rules_reload(self) -> bool:
        if not self._rules_path.exists():
            return False

        stat = self._rules_path.stat()
        if self._last_rules_mtime_ns == stat.st_mtime_ns:
            return False

        self._last_rules_mtime_ns = stat.st_mtime_ns
        LOGGER.info("rules file change detected", extra={"path": str(self._rules_path)})
        return True

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
