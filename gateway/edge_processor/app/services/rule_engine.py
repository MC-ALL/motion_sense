from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.utils.topic_parser import ParsedTopic


DEFAULT_RULES_PATH = Path("/runtime/config/edge_processor/rules.yaml")


@dataclass(slots=True, frozen=True)
class DeviceOfflineRule:
    enabled: bool
    timeout_s: int
    level: str


@dataclass(slots=True, frozen=True)
class EmittedAlert:
    gym_id: str
    device_type: str
    device_id: str
    code: str
    level: str
    value: float
    threshold: float
    observed_at_s: int
    message: str


@dataclass(slots=True)
class _WindowState:
    started_at_s: int
    fired: bool


class RuleEngine:
    def __init__(self, rules_path: Path = DEFAULT_RULES_PATH) -> None:
        self._rules_path = Path(rules_path)
        self._alert_rules: dict[str, dict[str, Any]] = {}
        self._global: dict[str, Any] = {}
        self._window_state: dict[tuple[str, str, str, str], _WindowState] = {}

    def reload_rules(self) -> None:
        data = self._read_yaml(self._rules_path)
        raw_rules = data.get("alert_rules", {})
        if isinstance(raw_rules, dict):
            self._alert_rules = {
                str(rule_code): rule_config
                for rule_code, rule_config in raw_rules.items()
                if isinstance(rule_config, dict)
            }
        else:
            self._alert_rules = {}

        raw_global = data.get("global", {})
        self._global = raw_global if isinstance(raw_global, dict) else {}
        self._prune_window_state()

    def evaluate_telemetry(self, parsed_topic: ParsedTopic, payload: dict[str, Any]) -> list[EmittedAlert]:
        if parsed_topic.action != "telemetry":
            return []

        observed_at_s = _to_unix_seconds(payload.get("ts"))
        emitted: list[EmittedAlert] = []
        emitted.extend(self._evaluate_eq_overload(parsed_topic, payload, observed_at_s))
        emitted.extend(self._evaluate_env_threshold(parsed_topic, payload, observed_at_s, "CO2_HIGH", "co2_ppm", "threshold_ppm"))
        emitted.extend(
            self._evaluate_env_threshold(parsed_topic, payload, observed_at_s, "PM25_HIGH", "pm2_5", "threshold_ugm3")
        )
        emitted.extend(
            self._evaluate_env_threshold(parsed_topic, payload, observed_at_s, "TEMP_HIGH", "temperature", "threshold_c")
        )
        emitted.extend(
            self._evaluate_env_threshold(parsed_topic, payload, observed_at_s, "CO2_CRITICAL", "co2_ppm", "threshold_ppm")
        )
        return emitted

    def device_offline_rule(self) -> DeviceOfflineRule:
        config = self._alert_rules.get("DEVICE_OFFLINE", {})
        enabled = bool(config.get("enabled", False))
        timeout_s = max(1, int(_as_number(config.get("timeout_s"), 30.0)))
        level = str(config.get("level") or "warning")
        return DeviceOfflineRule(enabled=enabled, timeout_s=timeout_s, level=level)

    def check_interval_s(self) -> int:
        return max(1, int(_as_number(self._global.get("check_interval_s"), 1.0)))

    def _evaluate_eq_overload(
        self,
        parsed_topic: ParsedTopic,
        payload: dict[str, Any],
        observed_at_s: int,
    ) -> list[EmittedAlert]:
        if parsed_topic.device_type != "equipment":
            return []

        config = self._alert_rules.get("EQ_OVERLOAD", {})
        if not bool(config.get("enabled", False)):
            self._clear_state("EQ_OVERLOAD", parsed_topic)
            return []

        power_w = _as_number(payload.get("power_w"))
        rated_power_w = _as_number(payload.get("rated_power_w"))
        ratio_threshold = _as_number(config.get("threshold_ratio"))
        if power_w is None or rated_power_w is None or ratio_threshold is None or rated_power_w <= 0:
            self._clear_state("EQ_OVERLOAD", parsed_topic)
            return []

        threshold = rated_power_w * ratio_threshold
        condition = power_w >= threshold
        return self._advance_window(
            parsed_topic=parsed_topic,
            rule_code="EQ_OVERLOAD",
            level=str(config.get("level") or "warning"),
            observed_at_s=observed_at_s,
            condition=condition,
            value=power_w,
            threshold=threshold,
            message=f"equipment overload: power_w={power_w:.2f}, threshold={threshold:.2f}",
            window_s=max(1, int(_as_number(config.get("window_s"), 1.0))),
        )

    def _evaluate_env_threshold(
        self,
        parsed_topic: ParsedTopic,
        payload: dict[str, Any],
        observed_at_s: int,
        rule_code: str,
        payload_field: str,
        threshold_field: str,
    ) -> list[EmittedAlert]:
        if parsed_topic.device_type != "env":
            return []

        config = self._alert_rules.get(rule_code, {})
        if not bool(config.get("enabled", False)):
            self._clear_state(rule_code, parsed_topic)
            return []

        value = _as_number(payload.get(payload_field))
        threshold = _as_number(config.get(threshold_field))
        if value is None or threshold is None:
            self._clear_state(rule_code, parsed_topic)
            return []

        return self._advance_window(
            parsed_topic=parsed_topic,
            rule_code=rule_code,
            level=str(config.get("level") or "warning"),
            observed_at_s=observed_at_s,
            condition=value >= threshold,
            value=value,
            threshold=threshold,
            message=f"{rule_code} triggered: {payload_field}={value:.2f}, threshold={threshold:.2f}",
            window_s=max(1, int(_as_number(config.get("window_s"), 1.0))),
        )

    def _advance_window(
        self,
        *,
        parsed_topic: ParsedTopic,
        rule_code: str,
        level: str,
        observed_at_s: int,
        condition: bool,
        value: float,
        threshold: float,
        message: str,
        window_s: int,
    ) -> list[EmittedAlert]:
        key = (rule_code, parsed_topic.gym_id, parsed_topic.device_type, parsed_topic.device_id)

        if not condition:
            self._window_state.pop(key, None)
            return []

        state = self._window_state.get(key)
        if state is None:
            state = _WindowState(started_at_s=observed_at_s, fired=False)
            self._window_state[key] = state

        if state.fired:
            return []

        if observed_at_s - state.started_at_s < window_s:
            return []

        state.fired = True
        return [
            EmittedAlert(
                gym_id=parsed_topic.gym_id,
                device_type=parsed_topic.device_type,
                device_id=parsed_topic.device_id,
                code=rule_code,
                level=level,
                value=float(value),
                threshold=float(threshold),
                observed_at_s=observed_at_s,
                message=message,
            )
        ]

    def _prune_window_state(self) -> None:
        enabled_rules = {rule_code for rule_code, config in self._alert_rules.items() if bool(config.get("enabled", False))}
        self._window_state = {
            key: value
            for key, value in self._window_state.items()
            if key[0] in enabled_rules
        }

    def _clear_state(self, rule_code: str, parsed_topic: ParsedTopic) -> None:
        key = (rule_code, parsed_topic.gym_id, parsed_topic.device_type, parsed_topic.device_id)
        self._window_state.pop(key, None)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _as_number(raw: Any, default: float | None = None) -> float | None:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, (int, float)):
        return float(raw)
    return default


def _to_unix_seconds(raw: Any) -> int:
    value = _as_number(raw)
    if value is None:
        return int(__import__("time").time())
    return int(value)
