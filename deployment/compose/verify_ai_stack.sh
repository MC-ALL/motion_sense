#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
web_service="${WEB_SERVICE_NAME:-web_portal_app}"
gym_id="${EDGE_PROCESSOR_GYM_ID:-gym-gz-01}"
suffix="$(date +%s)"
student_username="student-ai-data-${suffix}"
student_password="${AI_VERIFY_STUDENT_PASSWORD:-student123}"
wristband_id="wb-ai-data-${suffix}"
equipment_one_id="eq-ai-data-a-${suffix}"
equipment_two_id="eq-ai-data-b-${suffix}"

require_running_service() {
  service_name="$1"
  container_id="$(docker compose -f "${compose_file}" ps -q "${service_name}")"
  if [ -z "${container_id}" ]; then
    echo "service not found in compose stack: ${service_name}" >&2
    exit 1
  fi

  running_state="$(docker inspect -f '{{.State.Running}}' "${container_id}")"
  if [ "${running_state}" != "true" ]; then
    echo "service is not running: ${service_name}" >&2
    exit 1
  fi
}

for service in "${backend_service}" "${web_service}"; do
  require_running_service "${service}"
done

backend_bootstrap="$(
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
)"

backend_admin_username="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^username: //p' | head -n 1)"
backend_admin_password="$(printf '%s\n' "${backend_bootstrap}" | sed -n 's/^password: //p' | head -n 1)"

if [ -z "${backend_admin_username}" ] || [ -z "${backend_admin_password}" ]; then
  echo "failed to read backend bootstrap admin credentials from running container" >&2
  exit 1
fi

docker compose -f "${compose_file}" exec -T \
  -e "BACKEND_ADMIN_USERNAME=${backend_admin_username}" \
  -e "BACKEND_ADMIN_PASSWORD=${backend_admin_password}" \
  -e "STUDENT_USERNAME=${student_username}" \
  -e "STUDENT_PASSWORD=${student_password}" \
  -e "WRISTBAND_ID=${wristband_id}" \
  -e "EQUIPMENT_ONE_ID=${equipment_one_id}" \
  -e "EQUIPMENT_TWO_ID=${equipment_two_id}" \
  -e "GYM_ID=${gym_id}" \
  -e "WEB_SERVICE_HOST=${web_service}" \
  "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from app.settings import load_settings

BACKEND_BASE_URL = "http://127.0.0.1:8000"
WEB_BASE_URL = f"http://{os.environ['WEB_SERVICE_HOST']}:8080"

BACKEND_ADMIN_USERNAME = os.environ["BACKEND_ADMIN_USERNAME"]
BACKEND_ADMIN_PASSWORD = os.environ["BACKEND_ADMIN_PASSWORD"]
STUDENT_USERNAME = os.environ["STUDENT_USERNAME"]
STUDENT_PASSWORD = os.environ["STUDENT_PASSWORD"]
WRISTBAND_ID = os.environ["WRISTBAND_ID"]
EQUIPMENT_ONE_ID = os.environ["EQUIPMENT_ONE_ID"]
EQUIPMENT_TWO_ID = os.environ["EQUIPMENT_TWO_ID"]
GYM_ID = os.environ["GYM_ID"]
AI_POLL_ATTEMPTS = int(os.environ.get("AI_VERIFY_POLL_ATTEMPTS", "120"))


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, object] | None = None,
) -> tuple[int, str]:
    payload = None
    actual_headers = dict(headers or {})
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=actual_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def request_json(
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    data: dict[str, object] | None = None,
) -> tuple[int, object]:
    headers: dict[str, str] | None = None
    if token:
        headers = {"Authorization": f"Bearer {token}"}
    status, body = request(
        f"{BACKEND_BASE_URL}{path}",
        method=method,
        headers=headers,
        data=data,
    )
    return status, json.loads(body) if body else {}


def iso_from_ts(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in value)


settings = load_settings()
print(
    f"ai provider: {settings.ai.provider}, model: {settings.ai.model}, api_key_set: {bool(settings.ai.api_key)}"
)
if settings.ai.provider == "openai_compatible" and not settings.ai.api_key:
    raise AssertionError("openai_compatible provider requires api key")

health_status, _ = request(f"{WEB_BASE_URL}/")
if health_status != 200:
    raise AssertionError(f"web route failed: {health_status}")
print("web root: 200")

login_status, login_body = request_json(
    "/api/v1/auth/login",
    method="POST",
    data={"username": BACKEND_ADMIN_USERNAME, "password": BACKEND_ADMIN_PASSWORD},
)
if login_status != 200:
    raise AssertionError(f"backend admin login failed: {login_status} {login_body}")
print("backend admin login: 200")
access_token = login_body["access_token"]

user_status, user_body = request_json(
    "/api/v1/users",
    method="POST",
    token=access_token,
    data={
        "username": STUDENT_USERNAME,
        "password": STUDENT_PASSWORD,
        "role": "student",
        "gym_ids": [GYM_ID],
        "device_ids": [WRISTBAND_ID, EQUIPMENT_ONE_ID, EQUIPMENT_TWO_ID],
    },
)
if user_status not in {200, 201}:
    raise AssertionError(f"create student failed: {user_status} {user_body}")
print("create student: ok")

for device_type, device_id, display_name in [
    ("wristband", WRISTBAND_ID, f"AI 验证手环 {WRISTBAND_ID}"),
    ("equipment", EQUIPMENT_ONE_ID, f"AI 验证器材 A {EQUIPMENT_ONE_ID}"),
    ("equipment", EQUIPMENT_TWO_ID, f"AI 验证器材 B {EQUIPMENT_TWO_ID}"),
]:
    status, body = request_json(
        "/api/v1/devices",
        method="POST",
        token=access_token,
        data={
            "gym_id": GYM_ID,
            "device_type": device_type,
            "device_id": device_id,
            "gateway_id": "gw-001",
            "display_name": display_name,
            "location": "AI regression verification",
        },
    )
    if status not in {200, 201}:
        raise AssertionError(f"create device failed: {device_type} {status} {body}")
    print(f"create {device_type} {device_id}: ok")

current_ts = int(time.time())
segment_one_bind_ts = current_ts - 300
segment_one_mid_ts = current_ts - 240
segment_one_unbind_ts = current_ts - 180
segment_two_bind_ts = current_ts - 120
segment_two_mid_ts = current_ts - 60
segment_two_unbind_ts = current_ts

binding_status, binding_body = request_json(
    "/api/v1/user-wristband-bindings",
    method="POST",
    token=access_token,
    data={
        "username": STUDENT_USERNAME,
        "wristband_id": WRISTBAND_ID,
        "gym_id": GYM_ID,
        "bound_at": iso_from_ts(segment_one_bind_ts - 60),
        "source": "manual",
        "note": "ai regression bind",
    },
)
if binding_status != 201:
    raise AssertionError(f"create binding failed: {binding_status} {binding_body}")
print("create binding: ok")

ingest_status, ingest_body = request_json(
    "/api/v1/ingest/batch",
    method="POST",
    data={
        "gateway_id": "gw-001",
        "sent_at": iso_from_ts(current_ts),
        "items": [
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/telemetry",
                "payload": {"ts": segment_one_bind_ts, "heart_rate": 120, "step_count": 1000},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_ONE_ID}/telemetry",
                "payload": {"ts": segment_one_bind_ts, "rep_count": 0, "energy_wh": 0.0},
            },
            {
                "kind": "binding",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/binding",
                "payload": {
                    "ts": segment_one_bind_ts,
                    "wristband_id": WRISTBAND_ID,
                    "equipment_id": EQUIPMENT_ONE_ID,
                    "action": "bind",
                    "reason": "ble_connected",
                },
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/telemetry",
                "payload": {"ts": segment_one_mid_ts, "heart_rate": 134, "step_count": 1040},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_ONE_ID}/telemetry",
                "payload": {"ts": segment_one_mid_ts, "rep_count": 18, "energy_wh": 1.9},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_ONE_ID}/telemetry",
                "payload": {"ts": segment_one_unbind_ts, "rep_count": 18, "energy_wh": 1.9},
            },
            {
                "kind": "binding",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/binding",
                "payload": {
                    "ts": segment_one_unbind_ts,
                    "wristband_id": WRISTBAND_ID,
                    "equipment_id": EQUIPMENT_ONE_ID,
                    "action": "unbind",
                    "reason": "exercise_completed",
                },
            },
            {
                "kind": "binding",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/binding",
                "payload": {
                    "ts": segment_two_bind_ts,
                    "wristband_id": WRISTBAND_ID,
                    "equipment_id": EQUIPMENT_TWO_ID,
                    "action": "bind",
                    "reason": "ble_connected",
                },
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_TWO_ID}/telemetry",
                "payload": {"ts": segment_two_bind_ts, "rep_count": 0, "energy_wh": 0.0},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/telemetry",
                "payload": {"ts": segment_two_mid_ts, "heart_rate": 146, "step_count": 1100},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_TWO_ID}/telemetry",
                "payload": {"ts": segment_two_mid_ts, "rep_count": 14, "energy_wh": 1.1},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/telemetry",
                "payload": {"ts": segment_two_unbind_ts, "heart_rate": 142, "step_count": 1160},
            },
            {
                "kind": "binding",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/binding",
                "payload": {
                    "ts": segment_two_unbind_ts,
                    "wristband_id": WRISTBAND_ID,
                    "equipment_id": EQUIPMENT_TWO_ID,
                    "action": "unbind",
                    "reason": "exercise_completed",
                },
            },
        ],
    },
)
if ingest_status != 200:
    raise AssertionError(f"ingest batch failed: {ingest_status} {ingest_body}")
print("ingest telemetry and binding batch: ok")

sessions_status, sessions_body = request_json(
    f"/api/v1/workout-sessions?username={urllib.parse.quote(STUDENT_USERNAME)}",
    token=access_token,
)
if sessions_status != 200:
    raise AssertionError(f"list workout sessions failed: {sessions_status} {sessions_body}")
if len(sessions_body) != 1:
    raise AssertionError(f"expected exactly one aggregated session, got {len(sessions_body)}")
session_body = sessions_body[0]
if session_body["source"] != "aggregated":
    raise AssertionError("expected aggregated session source")
if session_body["status"] != "completed":
    raise AssertionError("expected completed session")
if session_body["metrics"]["total_rep_count"] != 32:
    raise AssertionError("unexpected total_rep_count")
if abs(session_body["metrics"]["total_energy_wh"] - 3.0) > 1e-6:
    raise AssertionError("unexpected total_energy_wh")
if session_body["metrics"]["max_heart_rate"] != 146:
    raise AssertionError("unexpected max_heart_rate")
print("automatic workout aggregation: ok")

window_start = iso_from_ts(current_ts - 600)
window_end = iso_from_ts(current_ts + 120)
analyze_status, analyze_body = request_json(
    "/api/v1/ai/analyze",
    method="POST",
    token=access_token,
    data={"user_id": STUDENT_USERNAME, "start": window_start, "end": window_end},
)
if analyze_status != 201:
    raise AssertionError(f"create ai report failed: {analyze_status} {analyze_body}")
report_id = analyze_body["report_id"]
print("create ai report: 201")

detail_body = None
for _ in range(AI_POLL_ATTEMPTS):
    time.sleep(2)
    detail_status, detail_body = request_json(
        f"/api/v1/ai/reports/{report_id}",
        token=access_token,
    )
    if detail_status != 200:
        raise AssertionError(f"fetch ai report failed: {detail_status} {detail_body}")
    if detail_body["status"] in {"completed", "failed"}:
        break
else:
    raise AssertionError("ai report did not finish within polling window")

if detail_body["status"] != "completed":
    raise AssertionError(f"ai report failed: {detail_body}")
if detail_body["evidence_session_ids"] != [session_body["session_id"]]:
    raise AssertionError("unexpected evidence_session_ids")
if "no recorded training sessions" in str(detail_body["summary"]).lower():
    raise AssertionError("report summary fell back to empty-session wording")
if not detail_body["summary_title"] or not detail_body["raw_markdown"]:
    raise AssertionError("report content missing title or markdown")
if len(detail_body["insights"]) < 2 or len(detail_body["recommendations"]) < 2:
    raise AssertionError("report content too short")
if not contains_cjk(str(detail_body["summary_title"])):
    raise AssertionError("report title does not contain Chinese text")
if not contains_cjk(str(detail_body["summary"])):
    raise AssertionError("report summary does not contain Chinese text")
print("ai report completion: ok")

profile_status, profile_body = request_json(
    f"/api/v1/users/{urllib.parse.quote(STUDENT_USERNAME)}/training-profile",
    token=access_token,
)
if profile_status != 200:
    raise AssertionError(f"fetch training profile failed: {profile_status} {profile_body}")
if profile_body["summary"]["total_sessions"] < 1:
    raise AssertionError("training profile missing session summary")
if profile_body["summary"]["total_rep_count"] < 32:
    raise AssertionError("training profile total_rep_count mismatch")
print("training profile summary: ok")

web_ai_status, web_ai_body = request(f"{WEB_BASE_URL}/ai-reports/{report_id}")
if web_ai_status != 200 or '<div id="root"></div>' not in web_ai_body:
    raise AssertionError(f"web ai report route failed: {web_ai_status}")
print("web ai report route: ok")

print(
    json.dumps(
        {
            "provider": settings.ai.provider,
            "model": settings.ai.model,
            "student_username": STUDENT_USERNAME,
            "session_id": session_body["session_id"],
            "session_metrics": session_body["metrics"],
            "report_id": report_id,
            "summary_title": detail_body["summary_title"],
            "summary": detail_body["summary"],
            "insights": detail_body["insights"],
            "recommendations": detail_body["recommendations"],
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
