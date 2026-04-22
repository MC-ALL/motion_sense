# deployment gateway

`deployment/gateway/` 存放网关相关的全部部署资产，包括 Broker、InfluxDB、edge_processor、device_simulator 与专项联调脚本。

## 目录功能

- 统一管理网关模块所有镜像、默认配置与脚本。
- 为 Apple `container` 本地联调提供专项脚本。
- 为仓库级 Compose 提供网关模块级服务定义。

## 目录结构

- `compose/docker-compose.yaml`：网关模块 Compose 样例。
- `container/`：网关专项本地联调与验证脚本。
- `mosquitto/`：Broker 镜像、默认配置、入口脚本。
- `influxdb/`：InfluxDB 镜像、默认初始化文件、入口脚本。
- `edge_processor/`：网关服务镜像、默认配置、规则模板与入口脚本。
- `device_simulator/`：模拟器镜像、默认配置与入口脚本。

## 脚本与配置文件

- `compose/docker-compose.yaml`：定义 `gateway_mosquitto`、`gateway_influxdb`、`gateway_edge_processor`。
- `container/prepare_runtime.sh`：初始化 `deployment/runtime/` 下网关所需目录与 `mosquitto.passwd`。
- `container/publish_sample_telemetry.sh`：向本地 Broker 发布测试消息。
- `container/verify_gateway_resilience.sh`：验证 Broker 重启重连、规则热重载与告警链路。
- `container/verify_ops_auth_stack.sh`：验证 gateway `/ops/v1/*` 与 `/ops/ws` 鉴权。
- `mosquitto/defaults/default_mosquitto.conf`：Broker 默认配置模板。
- `mosquitto/defaults/default_acl.conf`：ACL 模板。
- `edge_processor/defaults/default_app_settings.yaml`：网关默认配置模板。
- `edge_processor/defaults/default_rules.yaml`：规则模板。
- `edge_processor/defaults/default_logging.yaml`：日志配置模板。
- `edge_processor/entrypoint.sh`：生成默认配置并等待共享的 `backend_gateway_command_token.txt` 就绪。
- `device_simulator/defaults/default_simulator_settings.yaml`：模拟器默认配置模板。

## 环境配置要求

- Docker Engine 与 Compose。
- Apple 本地联调需安装 `container` CLI。
- 宿主机需提供 `deployment/runtime/config`、`deployment/runtime/secrets`、`deployment/runtime/certs`、`deployment/runtime/data`。
- 若启用 MQTT TLS，需要额外投放 `server.crt`、`server.key`、`ca.crt`。
- `deployment/runtime/secrets/backend_gateway_command_token.txt` 由 backend 首启自动生成，edge_processor 启动时会等待该文件可用，再建立命令 WebSocket。

## 基础设施要求

- Mosquitto 监听端口 `1883`；启用 TLS 时还需 `8883`。
- InfluxDB 3 Core 数据目录或命名卷。
- 与 backend 通信的内网网络连通性。

## 使用方式

模块 Compose 预览：

```bash
docker compose -f deployment/gateway/compose/docker-compose.yaml config
```

本地联调常用：

```bash
sh deployment/gateway/container/prepare_runtime.sh
sh deployment/gateway/container/publish_sample_telemetry.sh
sh deployment/gateway/container/verify_gateway_resilience.sh
```

## 后续改进

- 增加 MQTT TLS 资产检查与权限校验脚本。
- 增补真实设备接入前的契约/集成自动化测试。
- 继续细化 Broker 生产安全基线说明。
