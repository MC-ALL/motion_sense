#!/bin/sh
set -eu

printf '[1/5] 基础链路联调验证\n'
sh deployment/container/verify_system_stack.sh

printf '[2/5] 数据库联调验证\n'
sh deployment/container/verify_database_stack.sh

printf '[3/5] 用户权限边界验证\n'
sh deployment/container/verify_user_scope_stack.sh

printf '[4/5] 网关韧性回归验证\n'
sh deployment/gateway/container/verify_gateway_resilience.sh

printf '[5/5] 运维鉴权回归验证\n'
sh deployment/gateway/container/verify_ops_auth_stack.sh

printf '整栈回归验证完成\n'
