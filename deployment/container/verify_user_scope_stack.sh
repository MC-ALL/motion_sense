#!/bin/sh
set -eu

backend_host_port="${BACKEND_HOST_PORT:-18000}"
backend_bootstrap_admin_path="${BACKEND_BOOTSTRAP_ADMIN_PATH:-${PWD}/deployment/runtime/config/backend/api_service/bootstrap_admin.txt}"
backend_admin_username="${BACKEND_ADMIN_USERNAME:-}"
backend_admin_password="${BACKEND_ADMIN_PASSWORD:-}"
gateway_id="${EDGE_PROCESSOR_GATEWAY_ID:-gw-001}"

teacher_username=""
student_username=""
admin_auth_header=""
batch_file="$(mktemp)"

cleanup() {
  if [ -n "${teacher_username}" ] && [ -n "${admin_auth_header}" ]; then
    curl -fsS -X DELETE "http://127.0.0.1:${backend_host_port}/api/v1/users/${teacher_username}" \
      -H "${admin_auth_header}" >/dev/null 2>&1 || true
  fi
  if [ -n "${student_username}" ] && [ -n "${admin_auth_header}" ]; then
    curl -fsS -X DELETE "http://127.0.0.1:${backend_host_port}/api/v1/users/${student_username}" \
      -H "${admin_auth_header}" >/dev/null 2>&1 || true
  fi
  rm -f "${batch_file}"
}
trap cleanup EXIT INT TERM

wait_for_json() {
  url="$1"
  check_code="$2"
  max_attempts="${3:-60}"
  auth_header="${4:-}"
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if [ -n "$auth_header" ]; then
      body="$(curl -fsS -H "$auth_header" "$url" 2>/dev/null || true)"
    else
      body="$(curl -fsS "$url" 2>/dev/null || true)"
    fi
    if [ -n "$body" ] && BODY_JSON="$body" python3 -c "$check_code" >/dev/null 2>&1; then
      printf '%s\n' "$body"
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "timeout waiting for ${url}" >&2
  return 1
}

expect_status() {
  method="$1"
  url="$2"
  expected_status="$3"
  auth_header="${4:-}"
  body="${5:-}"

  response_file="$(mktemp)"
  status_code="$(
    if [ -n "$auth_header" ] && [ -n "$body" ]; then
      curl -sS -o "${response_file}" -w '%{http_code}' -X "$method" "$url" \
        -H "$auth_header" \
        -H 'Content-Type: application/json' \
        -d "$body"
    elif [ -n "$auth_header" ]; then
      curl -sS -o "${response_file}" -w '%{http_code}' -X "$method" "$url" \
        -H "$auth_header"
    elif [ -n "$body" ]; then
      curl -sS -o "${response_file}" -w '%{http_code}' -X "$method" "$url" \
        -H 'Content-Type: application/json' \
        -d "$body"
    else
      curl -sS -o "${response_file}" -w '%{http_code}' -X "$method" "$url"
    fi
  )"

  response_body="$(cat "${response_file}")"
  rm -f "${response_file}"

  if [ "${status_code}" != "${expected_status}" ]; then
    printf 'unexpected status %s for %s %s: %s\n' "${status_code}" "$method" "$url" "${response_body}" >&2
    exit 1
  fi

  printf '%s\n' "${response_body}"
}

extract_json() {
  expression="$1"
  BODY_JSON="${2}" python3 -c "import json, os; body=json.loads(os.environ['BODY_JSON']); print(${expression})"
}

login_and_get_json() {
  username="$1"
  password="$2"
  curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${username}\",\"password\":\"${password}\"}"
}

ensure_device_registered() {
  gym_id="$1"
  device_type="$2"
  device_id="$3"
  gateway_id_value="$4"
  display_name="$5"
  location="$6"

  if curl -fsS "http://127.0.0.1:${backend_host_port}/api/v1/devices/${device_id}" -H "${admin_auth_header}" >/dev/null 2>&1; then
    return 0
  fi

  curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/devices" \
    -H "${admin_auth_header}" \
    -H 'Content-Type: application/json' \
    -d "{\"gym_id\":\"${gym_id}\",\"device_type\":\"${device_type}\",\"device_id\":\"${device_id}\",\"gateway_id\":\"${gateway_id_value}\",\"display_name\":\"${display_name}\",\"location\":\"${location}\"}" \
    >/dev/null
}

curl -fsS "http://127.0.0.1:${backend_host_port}/healthz" >/dev/null

if [ -z "${backend_admin_username}" ] && [ -f "${backend_bootstrap_admin_path}" ]; then
  backend_admin_username="$(sed -n 's/^username: //p' "${backend_bootstrap_admin_path}" | head -n 1)"
fi

if [ -z "${backend_admin_password}" ] && [ -f "${backend_bootstrap_admin_path}" ]; then
  backend_admin_password="$(sed -n 's/^password: //p' "${backend_bootstrap_admin_path}" | head -n 1)"
fi

backend_admin_username="${backend_admin_username:-admin}"

if [ -z "${backend_admin_password}" ]; then
  echo "missing backend admin password; set BACKEND_ADMIN_PASSWORD or ensure bootstrap_admin.txt exists" >&2
  exit 1
fi

admin_login_json="$(login_and_get_json "${backend_admin_username}" "${backend_admin_password}")"
admin_access_token="$(extract_json "body['access_token']" "${admin_login_json}")"
admin_auth_header="Authorization: Bearer ${admin_access_token}"

current_ts="$(date +%s)"
teacher_username="scope_teacher_${current_ts}"
student_username="scope_student_${current_ts}"
teacher_password="teacher12345"
student_password="student12345"

teacher_create_json="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/users" \
  -H "${admin_auth_header}" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${teacher_username}\",\"password\":\"${teacher_password}\",\"role\":\"teacher\",\"gym_ids\":[\"gym-scope-a\"],\"device_ids\":[]}")"

student_create_json="$(curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/users" \
  -H "${admin_auth_header}" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${student_username}\",\"password\":\"${student_password}\",\"role\":\"student\",\"gym_ids\":[\"gym-scope-a\"],\"device_ids\":[\"eq-scope-a\",\"wb-scope-a\"]}")"

teacher_login_json="$(login_and_get_json "${teacher_username}" "${teacher_password}")"
student_login_json="$(login_and_get_json "${student_username}" "${student_password}")"

teacher_access_token="$(extract_json "body['access_token']" "${teacher_login_json}")"
student_access_token="$(extract_json "body['access_token']" "${student_login_json}")"
teacher_auth_header="Authorization: Bearer ${teacher_access_token}"
student_auth_header="Authorization: Bearer ${student_access_token}"

BODY_JSON="${teacher_login_json}" python3 -c "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['user']['role']=='teacher'; assert body['user']['gym_ids']==['gym-scope-a']; assert body['user']['device_ids']==[]"
BODY_JSON="${student_login_json}" python3 -c "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['user']['role']=='student'; assert body['user']['gym_ids']==['gym-scope-a']; assert body['user']['device_ids']==['eq-scope-a', 'wb-scope-a']"

ensure_device_registered "gym-scope-a" "equipment" "eq-scope-a" "${gateway_id}" "权限验证器材 A" "权限验证区 A"
ensure_device_registered "gym-scope-a" "wristband" "wb-scope-a" "${gateway_id}" "权限验证手环 A" "权限验证区 A"
ensure_device_registered "gym-scope-a" "env" "env-scope-a" "${gateway_id}" "权限验证环境 A" "权限验证区 A"
ensure_device_registered "gym-scope-b" "equipment" "eq-scope-b" "${gateway_id}" "权限验证器材 B" "权限验证区 B"

cat > "${batch_file}" <<EOF
{
  "gateway_id": "${gateway_id}",
  "sent_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "items": [
    {
      "kind": "telemetry",
      "topic": "gym/gym-scope-a/equipment/eq-scope-a/telemetry",
      "payload": {
        "ts": ${current_ts},
        "device_id": "eq-scope-a",
        "power_w": 321.5,
        "rep_count": 18
      }
    },
    {
      "kind": "telemetry",
      "topic": "gym/gym-scope-a/env/env-scope-a/telemetry",
      "payload": {
        "ts": ${current_ts},
        "device_id": "env-scope-a",
        "temperature_c": 24.5,
        "co2_ppm": 760
      }
    },
    {
      "kind": "telemetry",
      "topic": "gym/gym-scope-b/equipment/eq-scope-b/telemetry",
      "payload": {
        "ts": ${current_ts},
        "device_id": "eq-scope-b",
        "power_w": 222.0,
        "rep_count": 9
      }
    },
    {
      "kind": "alert",
      "topic": "gym/gym-scope-a/equipment/eq-scope-a/alert",
      "payload": {
        "ts": ${current_ts},
        "code": "OVERLOAD_SCOPE_A",
        "level": "warning",
        "message": "scope a overload",
        "priority": "P1"
      }
    },
    {
      "kind": "alert",
      "topic": "gym/gym-scope-b/equipment/eq-scope-b/alert",
      "payload": {
        "ts": ${current_ts},
        "code": "OVERLOAD_SCOPE_B",
        "level": "warning",
        "message": "scope b overload",
        "priority": "P1"
      }
    },
    {
      "kind": "binding",
      "topic": "gym/gym-scope-a/wristband/wb-scope-a/binding",
      "payload": {
        "ts": ${current_ts},
        "wristband_id": "wb-scope-a",
        "equipment_id": "eq-scope-a",
        "action": "bind",
        "reason": "integration_scope_test"
      }
    }
  ]
}
EOF

curl -fsS -X POST "http://127.0.0.1:${backend_host_port}/api/v1/ingest/batch" \
  -H 'Content-Type: application/json' \
  --data-binary "@${batch_file}" >/dev/null

teacher_devices_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); ids={item['device_id'] for item in body}; assert 'eq-scope-a' in ids; assert 'wb-scope-a' in ids; assert 'env-scope-a' in ids; assert 'eq-scope-b' not in ids" \
  60 \
  "${teacher_auth_header}")"

student_devices_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); ids={item['device_id'] for item in body}; assert ids == {'eq-scope-a', 'wb-scope-a'}" \
  60 \
  "${student_auth_header}")"

teacher_allowed_device_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/env-scope-a" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['gym_id']=='gym-scope-a'; assert body['device_id']=='env-scope-a'" \
  60 \
  "${teacher_auth_header}")"

teacher_forbidden_device_json="$(expect_status \
  GET \
  "http://127.0.0.1:${backend_host_port}/api/v1/devices/eq-scope-b" \
  403 \
  "${teacher_auth_header}")"

student_allowed_telemetry_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/telemetry/equipment/eq-scope-a" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert len(body) >= 1; assert body[0]['device_id']=='eq-scope-a'" \
  60 \
  "${student_auth_header}")"

student_forbidden_telemetry_json="$(expect_status \
  GET \
  "http://127.0.0.1:${backend_host_port}/api/v1/telemetry/equipment/eq-scope-b" \
  403 \
  "${student_auth_header}")"

student_binding_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/wristband/wb-scope-a/bindings" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert len(body) >= 1; assert body[0]['equipment_id']=='eq-scope-a'" \
  60 \
  "${student_auth_header}")"

teacher_alerts_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); ids={item['device_id'] for item in body}; assert 'eq-scope-a' in ids; assert 'eq-scope-b' not in ids" \
  60 \
  "${teacher_auth_header}")"

student_alerts_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); ids={item['device_id'] for item in body}; assert 'eq-scope-a' in ids; assert 'eq-scope-b' not in ids" \
  60 \
  "${student_auth_header}")"

allowed_alert_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts?device_id=eq-scope-a" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert len(body) >= 1; assert body[0]['device_id']=='eq-scope-a'" \
  60 \
  "${admin_auth_header}")"
allowed_alert_id="$(extract_json "body[0]['id']" "${allowed_alert_json}")"

forbidden_alert_json="$(wait_for_json \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts?device_id=eq-scope-b" \
  "import json, os; body=json.loads(os.environ['BODY_JSON']); assert len(body) >= 1; assert body[0]['device_id']=='eq-scope-b'" \
  60 \
  "${admin_auth_header}")"
forbidden_alert_id="$(extract_json "body[0]['id']" "${forbidden_alert_json}")"

teacher_ack_json="$(expect_status \
  PATCH \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts/${allowed_alert_id}/ack" \
  200 \
  "${teacher_auth_header}")"
BODY_JSON="${teacher_ack_json}" python3 -c "import json, os; body=json.loads(os.environ['BODY_JSON']); assert body['id'] == ${allowed_alert_id}; assert body['is_ack'] is True"

student_forbidden_ack_json="$(expect_status \
  PATCH \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts/${allowed_alert_id}/ack" \
  403 \
  "${student_auth_header}")"

student_forbidden_alert_detail_json="$(expect_status \
  GET \
  "http://127.0.0.1:${backend_host_port}/api/v1/alerts/${forbidden_alert_id}" \
  403 \
  "${student_auth_header}")"

printf '教师登录 scope 验证通过: %s\n' "${teacher_create_json}"
printf '学生登录 scope 验证通过: %s\n' "${student_create_json}"
printf '教师设备范围验证通过: %s\n' "${teacher_devices_json}"
printf '学生设备范围验证通过: %s\n' "${student_devices_json}"
printf '教师可读同馆设备验证通过: %s\n' "${teacher_allowed_device_json}"
printf '教师跨馆设备拦截验证通过: %s\n' "${teacher_forbidden_device_json}"
printf '学生授权遥测验证通过: %s\n' "${student_allowed_telemetry_json}"
printf '学生越权遥测拦截验证通过: %s\n' "${student_forbidden_telemetry_json}"
printf '学生绑定历史验证通过: %s\n' "${student_binding_json}"
printf '教师告警范围验证通过: %s\n' "${teacher_alerts_json}"
printf '学生告警范围验证通过: %s\n' "${student_alerts_json}"
printf '教师告警确认验证通过: %s\n' "${teacher_ack_json}"
printf '学生告警确认拦截验证通过: %s\n' "${student_forbidden_ack_json}"
printf '学生越权告警详情拦截验证通过: %s\n' "${student_forbidden_alert_detail_json}"
