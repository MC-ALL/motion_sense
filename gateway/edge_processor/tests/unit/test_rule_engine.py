from pathlib import Path

from app.services.rule_engine import RuleEngine
from app.utils.topic_parser import parse_topic


def test_rule_engine_uses_window_and_emits_once_until_recovery(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: true",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
                "global:",
                "  check_interval_s: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = RuleEngine(rules_path)
    engine.reload_rules()
    topic = parse_topic("gym/gym-gz-01/env/env-zone-a/telemetry")

    assert engine.evaluate_telemetry(topic, {"ts": 100, "co2_ppm": 1100}) == []
    assert engine.evaluate_telemetry(topic, {"ts": 101, "co2_ppm": 1200}) == []

    alerts = engine.evaluate_telemetry(topic, {"ts": 102, "co2_ppm": 1300})
    assert len(alerts) == 1
    assert alerts[0].code == "CO2_HIGH"
    assert alerts[0].value == 1300

    assert engine.evaluate_telemetry(topic, {"ts": 103, "co2_ppm": 1400}) == []
    assert engine.evaluate_telemetry(topic, {"ts": 104, "co2_ppm": 900}) == []
    assert engine.evaluate_telemetry(topic, {"ts": 105, "co2_ppm": 1200}) == []
    assert len(engine.evaluate_telemetry(topic, {"ts": 107, "co2_ppm": 1200})) == 1


def test_rule_engine_reads_device_offline_timeout(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  DEVICE_OFFLINE:",
                "    enabled: true",
                "    timeout_s: 45",
                "    level: warning",
                "global:",
                "  check_interval_s: 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = RuleEngine(rules_path)
    engine.reload_rules()

    offline_rule = engine.device_offline_rule()
    assert offline_rule.enabled is True
    assert offline_rule.timeout_s == 45
    assert engine.check_interval_s() == 3
    assert engine.time_source() == "payload_ts"


def test_rule_engine_clears_window_state_after_rule_disabled(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: true",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = RuleEngine(rules_path)
    engine.reload_rules()
    topic = parse_topic("gym/gym-gz-01/env/env-zone-a/telemetry")

    assert engine.evaluate_telemetry(topic, {"ts": 100, "co2_ppm": 1200}) == []

    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: false",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    engine.reload_rules()
    assert engine.evaluate_telemetry(topic, {"ts": 101, "co2_ppm": 1300}) == []

    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: true",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    engine.reload_rules()

    assert engine.evaluate_telemetry(topic, {"ts": 102, "co2_ppm": 1400}) == []
    assert engine.evaluate_telemetry(topic, {"ts": 103, "co2_ppm": 1500}) == []
    alerts = engine.evaluate_telemetry(topic, {"ts": 104, "co2_ppm": 1600})
    assert len(alerts) == 1
    assert alerts[0].code == "CO2_HIGH"


def test_rule_engine_uses_gateway_received_time_source(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: true",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
                "global:",
                "  time_source: gateway_received_ts",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = RuleEngine(rules_path)
    engine.reload_rules()
    topic = parse_topic("gym/gym-gz-01/env/env-zone-a/telemetry")

    assert engine.evaluate_telemetry(topic, {"ts": 100, "co2_ppm": 1200}, gateway_received_at_s=200) == []
    alerts = engine.evaluate_telemetry(topic, {"ts": 101, "co2_ppm": 1300}, gateway_received_at_s=202)
    assert len(alerts) == 1
    assert alerts[0].observed_at_s == 202


def test_rule_engine_backend_received_at_falls_back_to_gateway_time(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "\n".join(
            [
                "alert_rules:",
                "  CO2_HIGH:",
                "    enabled: true",
                "    threshold_ppm: 1000",
                "    window_s: 2",
                "    level: warning",
                "global:",
                "  time_source: backend_received_at",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = RuleEngine(rules_path)
    engine.reload_rules()
    topic = parse_topic("gym/gym-gz-01/env/env-zone-a/telemetry")

    assert engine.evaluate_telemetry(topic, {"ts": 100, "co2_ppm": 1200}, gateway_received_at_s=300) == []
    alerts = engine.evaluate_telemetry(
        topic,
        {"ts": 101, "co2_ppm": 1300, "backend_received_at": "1970-01-01T00:05:02+00:00"},
        gateway_received_at_s=302,
    )
    assert len(alerts) == 1
    assert alerts[0].observed_at_s == 302
