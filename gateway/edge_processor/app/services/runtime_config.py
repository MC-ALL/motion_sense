from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from app.settings import RuntimeSettings


LOGGER = logging.getLogger(__name__)


class RuntimeConfigManager:
    """Apply runtime config updates that do not require process restart."""

    def __init__(self, settings: RuntimeSettings) -> None:
        """Create a runtime config manager.

        :param settings: Runtime settings for this edge processor instance.
        """
        self._settings = settings
        self._rules_path = Path("/runtime/config/edge_processor/rules.yaml")
        self._last_rules_mtime_ns: int | None = None
        self._rules_reload_event = asyncio.Event()

    @property
    def rules_path(self) -> Path:
        """Return the active rules file path watched by the rule engine."""
        return self._rules_path

    def update_from_gateway_config(self, payload: dict[str, Any]) -> None:
        """Apply gateway configuration received from the backend command channel.

        :param payload: Gateway config payload. Alert rules are written to the
            runtime rules file; restart-required settings are logged only.
        """
        alert_rules = payload.get("alert_rules")
        rule_global = payload.get("global")
        time_source = payload.get("time_source")
        if isinstance(alert_rules, dict) or isinstance(rule_global, dict) or isinstance(time_source, str):
            current = self._read_yaml(self._rules_path)
            if isinstance(alert_rules, dict):
                current["alert_rules"] = alert_rules
            if isinstance(rule_global, dict):
                current_global = current.setdefault("global", {})
                current_global.update(rule_global)
            if isinstance(time_source, str):
                current_global = current.setdefault("global", {})
                current_global["time_source"] = time_source
            self._rules_path.write_text(
                yaml.safe_dump(current, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            self._mark_rules_changed()
            LOGGER.info("updated alert rules from gateway config")

        if (
            "batch_interval_s" in payload
            or "batch_min_window_s" in payload
            or "batch_trigger_threshold" in payload
            or "backend_base_url" in payload
        ):
            LOGGER.warning(
                "gateway config contains restart-required fields; change will apply after edge_processor restart"
            )

    def poll_rules_reload(self) -> bool:
        """Check whether the rules file changed since the previous poll.

        :return: ``True`` when the rule engine should reload its rules.
        """
        if not self._rules_path.exists():
            return False

        stat = self._rules_path.stat()
        if self._last_rules_mtime_ns == stat.st_mtime_ns:
            return False

        self._last_rules_mtime_ns = stat.st_mtime_ns
        LOGGER.info("rules file change detected", extra={"path": str(self._rules_path)})
        return True

    async def wait_for_rules_reload(self, timeout_s: float) -> bool:
        """Wait for an explicit or filesystem-detected rules reload signal.

        :param timeout_s: Maximum seconds to wait before falling back to polling.
        :return: ``True`` when rules should be reloaded.
        """
        try:
            await asyncio.wait_for(self._rules_reload_event.wait(), timeout=timeout_s)
        except TimeoutError:
            return self.poll_rules_reload()

        self._rules_reload_event.clear()
        return True

    def sync_rules_reload_state(self) -> None:
        """Align the cached file mtime with the current rules file state."""
        if not self._rules_path.exists():
            self._last_rules_mtime_ns = None
            return
        self._last_rules_mtime_ns = self._rules_path.stat().st_mtime_ns

    def _mark_rules_changed(self) -> None:
        """Mark rules as changed after this process writes the rules file."""
        if self._rules_path.exists():
            self._last_rules_mtime_ns = self._rules_path.stat().st_mtime_ns
        else:
            self._last_rules_mtime_ns = None
        self._rules_reload_event.set()

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        """Read a YAML mapping from disk, returning an empty mapping if missing."""
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
