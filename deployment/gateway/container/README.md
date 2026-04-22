# deployment gateway container

`deployment/gateway/container/` 存放网关专项的 Apple `container` 本地联调脚本。

## 目录功能

- 初始化网关运行时目录。
- 发布测试 MQTT 消息。
- 验证 Broker 重启、规则热重载与网关运维鉴权。

## 目录结构

- `prepare_runtime.sh`：初始化 `deployment/runtime/` 下网关需要的目录与 `mosquitto.passwd`。
- `publish_sample_telemetry.sh`：向本地 Mosquitto 发送测试消息。
- `verify_gateway_resilience.sh`：验证 Broker 重启重连、规则热重载与告警链路。
- `verify_ops_auth_stack.sh`：验证 gateway 与 `ops_observer` 的运维鉴权边界。

## 脚本用法

```bash
sh deployment/gateway/container/prepare_runtime.sh
sh deployment/gateway/container/publish_sample_telemetry.sh
sh deployment/gateway/container/verify_gateway_resilience.sh
sh deployment/gateway/container/verify_ops_auth_stack.sh
```

## 环境配置要求

- 依赖 Apple `container` CLI。
- 约定在仓库根目录执行。
- 部分脚本依赖 `curl`、`nc`、`python3`。

## 基础设施要求

- 本地容器网络中已存在 `mosquitto`、`edge_processor`、`backend`、`ops_observer` 等对应容器。
- 共享运行时目录已准备好。

## 后续改进

- 增加 MQTT TLS 本地验证脚本。
- 补充更多异常场景回归。
