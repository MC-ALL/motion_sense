# 网关专项脚本

本目录仅保留网关专项联调脚本：

- `publish_sample_telemetry.sh`：向本地 Mosquitto 发布测试遥测。
- `verify_gateway_resilience.sh`：验证 Broker 重启重连、规则热重载与告警生效。
- `verify_ops_auth_stack.sh`：验证网关 `/ops/v1/*` 与 `ops_observer` 运维鉴权边界。

整栈 Apple `container` 构建、启动、停止与基础回归脚本已统一移动到仓库级 [deployment/container/README.md](/Users/circuitx/Work/motion_sense/deployment/container/README.md)。
