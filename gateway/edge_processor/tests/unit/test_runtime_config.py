import os
import asyncio
from pathlib import Path

from app.services.runtime_config import RuntimeConfigManager
from app.settings import RuntimeSettings


def test_gateway_config_rewrites_rules_file(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("alert_rules: {}\n", encoding="utf-8")

    settings = RuntimeSettings()
    manager = RuntimeConfigManager(settings)
    monkeypatch.setattr(manager, "_rules_path", rules_path)

    manager.update_from_gateway_config(
        {
            "alert_rules": {
                "DEVICE_OFFLINE": {
                    "enabled": True,
                    "timeout_s": 30,
                    "level": "warning",
                }
            }
        }
    )

    assert "DEVICE_OFFLINE" in rules_path.read_text(encoding="utf-8")


def test_gateway_config_updates_rule_global_settings(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("alert_rules: {}\nglobal:\n  time_source: payload_ts\n", encoding="utf-8")

    settings = RuntimeSettings()
    manager = RuntimeConfigManager(settings)
    monkeypatch.setattr(manager, "_rules_path", rules_path)

    manager.update_from_gateway_config({"global": {"check_interval_s": 2}, "time_source": "gateway_received_ts"})

    rendered = rules_path.read_text(encoding="utf-8")
    assert "check_interval_s: 2" in rendered
    assert "time_source: gateway_received_ts" in rendered


def test_poll_rules_reload_only_reports_actual_changes(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("alert_rules: {}\n", encoding="utf-8")

    settings = RuntimeSettings()
    manager = RuntimeConfigManager(settings)
    monkeypatch.setattr(manager, "_rules_path", rules_path)

    assert manager.poll_rules_reload() is True
    assert manager.poll_rules_reload() is False

    previous_mtime_ns = rules_path.stat().st_mtime_ns
    rules_path.write_text("alert_rules:\n  CO2_HIGH:\n    enabled: true\n", encoding="utf-8")
    os.utime(rules_path, ns=(previous_mtime_ns + 1_000_000, previous_mtime_ns + 1_000_000))
    assert manager.poll_rules_reload() is True


def test_wait_for_rules_reload_is_notified_by_gateway_config_update(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("alert_rules: {}\n", encoding="utf-8")

    settings = RuntimeSettings()
    manager = RuntimeConfigManager(settings)
    monkeypatch.setattr(manager, "_rules_path", rules_path)
    manager.sync_rules_reload_state()

    async def scenario() -> None:
        waiter = asyncio.create_task(manager.wait_for_rules_reload(timeout_s=1.0))
        await asyncio.sleep(0)
        manager.update_from_gateway_config({"alert_rules": {"DEVICE_OFFLINE": {"enabled": True}}})
        assert await waiter is True

    asyncio.run(scenario())
