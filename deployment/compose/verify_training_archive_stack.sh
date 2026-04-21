#!/bin/sh
set -eu

compose_file="${COMPOSE_FILE_PATH:-deployment/compose/docker-compose.yaml}"
backend_service="${BACKEND_SERVICE_NAME:-backend_api_service}"
web_service="${WEB_SERVICE_NAME:-web_portal_app}"
suffix="$(date +%s)"
student_username="student-archive-${suffix}"
student_password="${TRAINING_ARCHIVE_STUDENT_PASSWORD:-student123}"
wristband_id="wb-archive-${suffix}"
equipment_id="eq-archive-${suffix}"
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
  -e "EQUIPMENT_ID=${equipment_id}" \
  -e "GYM_ID=${gym_id}" \
  -e "WEB_SERVICE_HOST=${web_service}" \
  "${backend_service}" python - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BACKEND_BASE_URL = "http://127.0.0.1:8000"
WEB_BASE_URL = f"http://{os.environ['WEB_SERVICE_HOST']}:8080"

BACKEND_ADMIN_USERNAME = os.environ["BACKEND_ADMIN_USERNAME"]
BACKEND_ADMIN_PASSWORD = os.environ["BACKEND_ADMIN_PASSWORD"]
STUDENT_USERNAME = os.environ["STUDENT_USERNAME"]
STUDENT_PASSWORD = os.environ["STUDENT_PASSWORD"]
WRISTBAND_ID = os.environ["WRISTBAND_ID"]
EQUIPMENT_ID = os.environ["EQUIPMENT_ID"]
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
        "device_ids": [WRISTBAND_ID, EQUIPMENT_ID],
    },
)
if user_status not in {200, 201}:
    raise AssertionError(f"create student failed: {user_status} {user_body}")
user_json = json.loads(user_body)
print("create student: ok")

for device_type, device_id, display_name in [
    ("wristband", WRISTBAND_ID, f"训练手环 {WRISTBAND_ID}"),
    ("equipment", EQUIPMENT_ID, f"训练器材 {EQUIPMENT_ID}"),
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
            "location": "训练档案自动回归",
        },
    )
    if device_status not in {200, 201}:
        raise AssertionError(f"create device failed: {device_type} {device_status} {device_body}")
    print(f"create {device_type}: ok")

binding_status, binding_body = request(
    f"{BACKEND_BASE_URL}/api/v1/user-wristband-bindings",
    method="POST",
    headers=auth_headers,
    data={
        "username": STUDENT_USERNAME,
        "wristband_id": WRISTBAND_ID,
        "gym_id": GYM_ID,
        "source": "manual",
        "note": "training archive regression bind",
    },
)
if binding_status != 201:
    raise AssertionError(f"create binding failed: {binding_status} {binding_body}")
binding_json = json.loads(binding_body)
print("create binding: ok")

session_status, session_body = request(
    f"{BACKEND_BASE_URL}/api/v1/workout-sessions",
    method="POST",
    headers=auth_headers,
    data={
        "username": STUDENT_USERNAME,
        "wristband_id": WRISTBAND_ID,
        "gym_id": GYM_ID,
        "status": "completed",
        "source": "manual",
        "started_at": "2026-04-19T08:00:00Z",
        "ended_at": "2026-04-19T08:45:00Z",
        "equipment_ids": [EQUIPMENT_ID],
        "segments": [
            {
                "equipment_id": EQUIPMENT_ID,
                "started_at": "2026-04-19T08:00:00Z",
                "ended_at": "2026-04-19T08:45:00Z",
                "duration_s": 2700,
                "rep_count": 36,
                "energy_wh": 18.5,
            }
        ],
        "metrics": {
            "avg_heart_rate": 132.5,
            "max_heart_rate": 161,
            "total_rep_count": 36,
            "total_energy_wh": 18.5,
            "total_steps": 4200,
            "alert_count": 0,
        },
        "notes": "training archive regression session",
    },
)
if session_status != 201:
    raise AssertionError(f"create workout session failed: {session_status} {session_body}")
session_json = json.loads(session_body)
print("create workout session: ok")

profile_status, profile_body = request(
    f"{BACKEND_BASE_URL}/api/v1/users/{STUDENT_USERNAME}/training-profile",
    headers=auth_headers,
)
if profile_status != 200:
    raise AssertionError(f"fetch training profile failed: {profile_status} {profile_body}")
profile_json = json.loads(profile_body)
if profile_json["user"]["username"] != STUDENT_USERNAME:
    raise AssertionError("unexpected training profile username")
if profile_json["active_binding"]["wristband_id"] != WRISTBAND_ID:
    raise AssertionError("unexpected active binding")
if profile_json["summary"]["total_sessions"] < 1:
    raise AssertionError("unexpected total_sessions")
if profile_json["summary"]["total_rep_count"] < 36:
    raise AssertionError("unexpected total_rep_count")
if EQUIPMENT_ID not in profile_json["summary"]["equipment_ids"]:
    raise AssertionError("equipment id missing from profile summary")
if not any(item["session_id"] == session_json["session_id"] for item in profile_json["recent_sessions"]):
    raise AssertionError("created workout session missing from recent_sessions")
if not any(item["id"] == binding_json["id"] for item in profile_json["recent_bindings"]):
    raise AssertionError("created binding missing from recent_bindings")
print("fetch training profile: ok")

binding_overview_status, binding_overview_body = request(
    f"{BACKEND_BASE_URL}/api/v1/user-wristband-bindings/overview?username={STUDENT_USERNAME}",
    headers=auth_headers,
)
if binding_overview_status != 200:
    raise AssertionError(f"fetch binding overview failed: {binding_overview_status} {binding_overview_body}")
binding_overview_json = json.loads(binding_overview_body)
if len(binding_overview_json["active_bindings"]) != 1:
    raise AssertionError("unexpected active binding count in overview")
if binding_overview_json["active_bindings"][0]["id"] != binding_json["id"]:
    raise AssertionError("overview active binding mismatch")
if not any(item["id"] == binding_json["id"] for item in binding_overview_json["binding_history"]):
    raise AssertionError("overview binding history missing created binding")
print("binding overview: ok")

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
    f"{BACKEND_BASE_URL}/api/v1/users/{STUDENT_USERNAME}/training-profile",
    headers=student_headers,
)
if student_profile_status != 200:
    raise AssertionError(f"student profile access failed: {student_profile_status} {student_profile_body}")
print("student self profile access: ok")

web_status, web_body = request(f"{WEB_BASE_URL}/training-archive/{STUDENT_USERNAME}")
if web_status != 200 or '<div id="root"></div>' not in web_body:
    raise AssertionError(f"training archive route failed: {web_status}")
print("web training archive route: ok")

device_management_status, device_management_body = request(
    f"{WEB_BASE_URL}/device-registry?tab=wristband-bindings&username={STUDENT_USERNAME}"
)
if device_management_status != 200 or '<div id="root"></div>' not in device_management_body:
    raise AssertionError(f"device management route failed: {device_management_status}")
print("web device management route: ok")

unbind_status, unbind_body = request(
    f"{BACKEND_BASE_URL}/api/v1/user-wristband-bindings/{binding_json['id']}/unbind",
    method="POST",
    headers=auth_headers,
    data={"note": "training archive regression unbind"},
)
if unbind_status != 200:
    raise AssertionError(f"unbind failed: {unbind_status} {unbind_body}")
unbound_json = json.loads(unbind_body)
if unbound_json["is_active"] is not False:
    raise AssertionError("binding still active after unbind")
print("unbind binding: ok")

after_unbind_status, after_unbind_body = request(
    f"{BACKEND_BASE_URL}/api/v1/users/{STUDENT_USERNAME}/training-profile",
    headers=auth_headers,
)
if after_unbind_status != 200:
    raise AssertionError(f"fetch profile after unbind failed: {after_unbind_status} {after_unbind_body}")
after_unbind_json = json.loads(after_unbind_body)
active_binding = after_unbind_json.get("active_binding")
if active_binding is not None:
    raise AssertionError("active_binding should be empty after unbind")
latest_binding = after_unbind_json["recent_bindings"][0]
if latest_binding["id"] != binding_json["id"] or latest_binding["is_active"] is not False:
    raise AssertionError("latest binding history did not update after unbind")
print("profile after unbind: ok")

after_unbind_overview_status, after_unbind_overview_body = request(
    f"{BACKEND_BASE_URL}/api/v1/user-wristband-bindings/overview?username={STUDENT_USERNAME}",
    headers=auth_headers,
)
if after_unbind_overview_status != 200:
    raise AssertionError(
        f"fetch binding overview after unbind failed: {after_unbind_overview_status} {after_unbind_overview_body}"
    )
after_unbind_overview_json = json.loads(after_unbind_overview_body)
if after_unbind_overview_json["active_bindings"]:
    raise AssertionError("active_bindings should be empty after unbind")
if after_unbind_overview_json["binding_history"][0]["id"] != binding_json["id"]:
    raise AssertionError("binding history ordering mismatch after unbind")
if after_unbind_overview_json["binding_history"][0]["is_active"] is not False:
    raise AssertionError("binding history did not reflect unbind state")
print("binding overview after unbind: ok")

print(
    json.dumps(
        {
            "user": user_json,
            "binding": binding_json,
            "workout_session": session_json,
            "profile_summary": profile_json["summary"],
            "latest_binding_after_unbind": latest_binding,
            "binding_overview_after_unbind": after_unbind_overview_json,
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
