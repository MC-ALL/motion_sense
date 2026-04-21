#!/bin/sh
set -eu

script_dir=$(
  CDPATH= cd -- "$(dirname "$0")" && pwd
)
repo_root=$(
  CDPATH= cd -- "${script_dir}/../.." && pwd
)

target_path="${BACKEND_AI_API_KEY_PATH:-${repo_root}/deployment/runtime/secrets/backend_ai_api_key.txt}"
target_dir=$(dirname "${target_path}")

print_hint_and_exit() {
  message="$1"
  echo "${message}" >&2
  echo "hint: if deployment/runtime is root-owned, run: sudo sh deployment/compose/write_backend_ai_api_key.sh" >&2
  exit 1
}

if ! mkdir -p "${target_dir}" 2>/dev/null; then
  print_hint_and_exit "cannot create secret directory: ${target_dir}"
fi

if ! chmod 700 "${target_dir}" 2>/dev/null; then
  print_hint_and_exit "cannot set directory permission: ${target_dir}"
fi

if [ -t 0 ]; then
  printf 'AI API token: ' >&2
  tty_state="$(stty -g 2>/dev/null || true)"
  trap 'if [ -n "${tty_state:-}" ]; then stty "${tty_state}" 2>/dev/null || true; fi' EXIT HUP INT TERM
  stty -echo 2>/dev/null || true
  if ! IFS= read -r token; then
    token=""
  fi
  if [ -n "${tty_state:-}" ]; then
    stty "${tty_state}" 2>/dev/null || true
  fi
  trap - EXIT HUP INT TERM
  printf '\n' >&2
else
  if ! IFS= read -r token; then
    token=""
  fi
fi

token=$(printf '%s' "${token}" | tr -d '\r')

if [ -z "${token}" ]; then
  echo "empty token, nothing written" >&2
  exit 1
fi

umask 077
if ! printf '%s\n' "${token}" > "${target_path}" 2>/dev/null; then
  print_hint_and_exit "cannot write token file: ${target_path}"
fi

if ! chmod 600 "${target_path}" 2>/dev/null; then
  print_hint_and_exit "cannot set file permission: ${target_path}"
fi

echo "token saved: ${target_path}" >&2
