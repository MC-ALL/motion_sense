#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
web_service="${WEB_SERVICE_NAME:-web_portal_app}"
suffix="$(date +%s)"
student_username="student-aggregate-${suffix}"
student_password="${WORKOUT_AGGREGATION_STUDENT_PASSWORD:-student123}"
wristband_id="wb-aggregate-${suffix}"
equipment_one_id="eq-aggregate-a-${suffix}"
equipment_two_id="eq-aggregate-b-${suffix}"
gym_id="${EDGE_PROCESSOR_GYM_ID:-gym-gz-01}"

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

backend_bootstrap="$({
  docker compose -f "${compose_file}" exec -T "${backend_service}" \
    sh -lc 'cat /runtime/config/backend/api_service/bootstrap_admin.txt'
})"

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
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def iso_from_ts(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


login_status, login_body = request(
    f"{BACKEND_BASE_URL}/api/v1/auth/login",
    method="POST",
    data={"username": BACKEND_ADMIN_USERNAME, "password": BACKEND_ADMIN_PASSWORD},
)
if login_status != 200:
    raise AssertionError(f"backend admin login failed: {login_status} {login_body}")
print("backend admin login: 200")
access_token = json.loads(login_body)["access_token"]
auth_headers = {"Authorization": f"Bearer {access_token}"}

user_status, user_body = request(
    f"{BACKEND_BASE_URL}/api/v1/users",
    method="POST",
    headers=auth_headers,
    data={
        "username": STUDENT_USERNAME,
        "password": STUDENT_PASSWORD,
        "role": "student",
        "gym_ids": [],
        "device_ids": [WRISTBAND_ID, EQUIPMENT_ONE_ID, EQUIPMENT_TWO_ID],
    },
)
if user_status not in {200, 201}:
    raise AssertionError(f"create student failed: {user_status} {user_body}")
user_json = json.loads(user_body)
print("create student: ok")

for device_type, device_id, display_name in [
    ("wristband", WRISTBAND_ID, f"汇聚手环 {WRISTBAND_ID}"),
    ("equipment", EQUIPMENT_ONE_ID, f"汇聚器材 A {EQUIPMENT_ONE_ID}"),
    ("equipment", EQUIPMENT_TWO_ID, f"汇聚器材 B {EQUIPMENT_TWO_ID}"),
]:
    device_status, device_body = request(
        f"{BACKEND_BASE_URL}/api/v1/devices",
        method="POST",
        headers=auth_headers,
        data={
            "gym_id": GYM_ID,
            "device_type": device_type,
            "device_id": device_id,
            "gateway_id": "gw-001",
            "display_name": display_name,
            "location": "训练会话自动汇聚回归",
        },
    )
    if device_status not in {200, 201}:
        raise AssertionError(f"create device failed: {device_type} {device_status} {device_body}")
    print(f"create {device_type} {device_id}: ok")

current_ts = int(time.time())
segment_one_bind_ts = current_ts - 300
segment_one_mid_ts = current_ts - 240
segment_one_unbind_ts = current_ts - 180
segment_two_bind_ts = current_ts - 120
segment_two_mid_ts = current_ts - 60
segment_two_unbind_ts = current_ts
binding_bound_at = iso_from_ts(segment_one_bind_ts - 60)

binding_status, binding_body = request(
    f"{BACKEND_BASE_URL}/api/v1/user-wristband-bindings",
    method="POST",
    headers=auth_headers,
    data={
        "username": STUDENT_USERNAME,
        "wristband_id": WRISTBAND_ID,
        "gym_id": GYM_ID,
        "bound_at": binding_bound_at,
        "source": "manual",
        "note": "workout aggregation regression bind",
    },
)
if binding_status != 201:
    raise AssertionError(f"create user wristband binding failed: {binding_status} {binding_body}")
binding_json = json.loads(binding_body)
print("create user wristband binding: ok")

ingest_status, ingest_body = request(
    f"{BACKEND_BASE_URL}/api/v1/ingest/batch",
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
                "payload": {"ts": segment_one_mid_ts, "heart_rate": 132, "step_count": 1040},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_ONE_ID}/telemetry",
                "payload": {"ts": segment_one_mid_ts, "rep_count": 15, "energy_wh": 1.5},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_ONE_ID}/telemetry",
                "payload": {"ts": segment_one_unbind_ts, "rep_count": 15, "energy_wh": 1.5},
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
                "payload": {"ts": segment_two_mid_ts, "heart_rate": 141, "step_count": 1075},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/equipment/{EQUIPMENT_TWO_ID}/telemetry",
                "payload": {"ts": segment_two_mid_ts, "rep_count": 10, "energy_wh": 0.8},
            },
            {
                "kind": "telemetry",
                "topic": f"gym/{GYM_ID}/wristband/{WRISTBAND_ID}/telemetry",
                "payload": {"ts": segment_two_unbind_ts, "heart_rate": 138, "step_count": 1100},
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

sessions_status, sessions_body = request(
    f"{BACKEND_BASE_URL}/api/v1/workout-sessions?username={urllib.parse.quote(STUDENT_USERNAME)}",
    headers=auth_headers,
)
if sessions_status != 200:
    raise AssertionError(f"list workout sessions failed: {sessions_status} {sessions_body}")
sessions_json = json.loads(sessions_body)
if len(sessions_json) != 1:
    raise AssertionError(f"expected exactly 1 aggregated workout session, got {len(sessions_json)}")
session_json = sessions_json[0]
if session_json["source"] != "aggregated":
    raise AssertionError("expected workout session source=aggregated")
if session_json["status"] != "completed":
    raise AssertionError("expected completed workout session")
if session_json["equipment_ids"] != [EQUIPMENT_ONE_ID, EQUIPMENT_TWO_ID]:
    raise AssertionError(f"unexpected equipment_ids: {session_json['equipment_ids']}")
if len(session_json["segments"]) != 2:
    raise AssertionError("expected two workout segments")
if session_json["segments"][0]["equipment_id"] != EQUIPMENT_ONE_ID:
    raise AssertionError("unexpected first segment equipment")
if session_json["segments"][0]["rep_count"] != 15:
    raise AssertionError("unexpected first segment rep_count")
if session_json["segments"][1]["equipment_id"] != EQUIPMENT_TWO_ID:
    raise AssertionError("unexpected second segment equipment")
if session_json["segments"][1]["rep_count"] != 10:
    raise AssertionError("unexpected second segment rep_count")
if session_json["metrics"]["total_rep_count"] != 25:
    raise AssertionError("unexpected total_rep_count")
if abs(session_json["metrics"]["total_energy_wh"] - 2.3) > 1e-6:
    raise AssertionError("unexpected total_energy_wh")
if session_json["metrics"]["total_steps"] != 100:
    raise AssertionError("unexpected total_steps")
if session_json["metrics"]["max_heart_rate"] != 141:
    raise AssertionError("unexpected max_heart_rate")
if abs(session_json["metrics"]["avg_heart_rate"] - 132.8) > 1e-6:
    raise AssertionError("unexpected avg_heart_rate")
print("automatic workout aggregation: ok")

aggregate_status, aggregate_body = request(
    f"{BACKEND_BASE_URL}/api/v1/workout-sessions/aggregate",
    method="POST",
    headers=auth_headers,
    data={
        "username": STUDENT_USERNAME,
        "wristband_id": WRISTBAND_ID,
        "gym_id": GYM_ID,
        "start": iso_from_ts(segment_one_bind_ts - 60),
        "end": iso_from_ts(segment_two_unbind_ts + 60),
    },
)
if aggregate_status != 200:
    raise AssertionError(f"manual workout aggregation failed: {aggregate_status} {aggregate_body}")
aggregate_json = json.loads(aggregate_body)
if aggregate_json["created_sessions"] != 0:
    raise AssertionError("manual aggregation should not create duplicate sessions")
if aggregate_json["updated_sessions"] < 1:
    raise AssertionError("manual aggregation did not update existing session")
if not aggregate_json["sessions"]:
    raise AssertionError("manual aggregation returned no sessions")
if aggregate_json["sessions"][0]["session_id"] != session_json["session_id"]:
    raise AssertionError("manual aggregation returned unexpected session")
print("manual workout aggregation backfill: ok")

profile_status, profile_body = request(
    f"{BACKEND_BASE_URL}/api/v1/users/{urllib.parse.quote(STUDENT_USERNAME)}/training-profile",
    headers=auth_headers,
)
if profile_status != 200:
    raise AssertionError(f"fetch training profile failed: {profile_status} {profile_body}")
profile_json = json.loads(profile_body)
if profile_json["user"]["username"] != STUDENT_USERNAME:
    raise AssertionError("unexpected training profile username")
if profile_json["active_binding"]["wristband_id"] != WRISTBAND_ID:
    raise AssertionError("unexpected active binding in training profile")
if profile_json["summary"]["total_sessions"] < 1:
    raise AssertionError("unexpected total_sessions in training profile")
if profile_json["summary"]["total_rep_count"] < 25:
    raise AssertionError("unexpected total_rep_count in training profile")
if abs(profile_json["summary"]["total_energy_wh"] - 2.3) > 1e-6:
    raise AssertionError("unexpected total_energy_wh in training profile")
if EQUIPMENT_ONE_ID not in profile_json["summary"]["equipment_ids"]:
    raise AssertionError("equipment one missing from training profile summary")
if EQUIPMENT_TWO_ID not in profile_json["summary"]["equipment_ids"]:
    raise AssertionError("equipment two missing from training profile summary")
if not any(item["session_id"] == session_json["session_id"] for item in profile_json["recent_sessions"]):
    raise AssertionError("aggregated workout session missing from training profile")
print("training profile after aggregation: ok")

student_login_status, student_login_body = request(
    f"{BACKEND_BASE_URL}/api/v1/auth/login",
    method="POST",
    data={"username": STUDENT_USERNAME, "password": STUDENT_PASSWORD},
)
if student_login_status != 200:
    raise AssertionError(f"student login failed: {student_login_status} {student_login_body}")
student_access_token = json.loads(student_login_body)["access_token"]
student_headers = {"Authorization": f"Bearer {student_access_token}"}
student_profile_status, student_profile_body = request(
    f"{BACKEND_BASE_URL}/api/v1/users/{urllib.parse.quote(STUDENT_USERNAME)}/training-profile",
    headers=student_headers,
)
if student_profile_status != 200:
    raise AssertionError(f"student self profile failed: {student_profile_status} {student_profile_body}")
print("student self profile access after aggregation: ok")

web_status, web_body = request(f"{WEB_BASE_URL}/training-archive/{urllib.parse.quote(STUDENT_USERNAME)}")
if web_status != 200 or '<div id="root"></div>' not in web_body:
    raise AssertionError(f"training archive route failed: {web_status}")
print("web training archive route after aggregation: ok")

print(
    json.dumps(
        {
            "user": user_json,
            "binding": binding_json,
            "aggregated_session": session_json,
            "manual_aggregate": aggregate_json,
            "profile_summary": profile_json["summary"],
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
