#!/bin/sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"

printf '[1/3] 基础链路联调验证\n'
sh "${script_dir}/verify_system_stack.sh"

printf '[2/3] 用户权限边界验证\n'
sh "${script_dir}/verify_user_scope_stack.sh"

printf '[3/3] 网关韧性回归验证\n'
sh "${script_dir}/verify_gateway_resilience.sh"

printf '整栈回归验证完成\n'
