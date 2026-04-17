# motion_sense

本仓库是 `04-网关端`、`05-后台端`、`06-网页端` 与 `09-运维观测端` 的第 1 迭代工作区，包含需求文档、实现代码、部署文件与本地联调脚本。

## 当前状态

- `gateway/`：异步边缘处理服务、Mosquitto、InfluxDB 3 Core 部署资产，以及 Apple `container` 本地测试脚本
- `backend/`：异步 FastAPI 后台服务、TimescaleDB 持久化、Redis 实时广播
- `ops_observer/`：独立运维观测服务、SQLite 持久化、基础设施健康聚合
- `web/`：业务与运维一体化门户前端、运行时配置注入
- `docs/`：系统架构、各子系统规格、接口契约与开发排期

当前机器上已完成并验证：

- 后台入库与查询主链路
- 后台 `local` / `redis` 两种 WebSocket 实时推送路径
- 后台 `POST /api/v1/devices/{id}/config` 配置命令入库
- 后台 `POST /api/v1/devices`、`PATCH /api/v1/devices/{id}`、`DELETE /api/v1/devices/{id}` 设备注册管理
- 网关 `GET /api/v1/gateway/{gateway_id}/commands/pending` 轮询执行与结果回报
- 配置命令失败重试、租约领取与 `timed_out` 超时收敛
- 后台 JWT 登录、刷新、退出接口已实现
- 后台 `GET/POST/PATCH/DELETE /api/v1/users` 用户管理接口已实现，支持 `admin` / `teacher` / `student`，并支持 `gym_ids` / `device_ids` 归属映射
- 后台 AI / OTA 预留接口已占位，当前返回 `501 reserved`
- 网关基于 InfluxDB 的本地缓存与补发链路
- 网关 P1 规则引擎与规则热重载
- 网关 `DEVICE_OFFLINE` 告警与 retained 状态发布
- 网关基础设施健康采集与 `POST /api/v1/system/health/report` 上报
- 网关真实 Broker 重启后的自动重连回归，以及规则热重载端到端回归
- `ops_observer` 轮询 + 订阅网关与后台 `/ops/v1/*` / `/ops/ws`，并对外提供 `GET /api/v1/ops/*`、`PATCH /api/v1/ops/alerts/{id}/close`、`WS /api/ws/ops`
- `web/portal_app` 已落地运维门户骨架、健康中心页面、运行时配置注入与前端构建拆包
- `web/portal_app` 已接入实时仪表盘、器材管理、环境质量、告警管理、用户管理、设备注册，以及后台 JWT 登录与业务 WebSocket
- `web/portal_app` 已新增独立登录页 `/login`，并统一未登录跳转与登录后回跳
- `web/portal_app` 已按角色收敛页面可见性：学生隐藏“告警管理”，教师 / 学生在器材与环境页隐藏配置下发控件
- 本地链路 `mosquitto -> edge_processor -> InfluxDB 缓冲 -> POST /api/v1/ingest/batch -> backend/api_service -> TimescaleDB`
- Apple `container` 本地脚本 `verify_system_stack.sh` 已验证通过：
  设备入库、健康汇聚、配置命令闭环、健康汇总视图、`ops_observer` 聚合健康视图，以及网页端入口与运行时配置
- Apple `container` 本地脚本 `verify_user_scope_stack.sh` 已验证通过：
  `teacher` / `student` 的 `gym_ids` / `device_ids` 权限边界、越权 `403`、告警确认角色边界
- Apple `container` 本地脚本 `verify_gateway_resilience.sh` 已验证通过：
  Mosquitto 异常重启后的网关自动重连、InfluxDB 本地缓冲补发、规则热重载后 `CO2_HIGH` 生效
- Apple `container` 本地脚本 `verify_regression_stack.sh` 已验证通过：
  串行覆盖基础链路、权限隔离与网关韧性三类回归

当前缺口：

- 当前 `04 / 05` 核心功能链路已闭合，剩余以生产化收尾与预留能力为主
- Linux 正式部署仍需补齐 Mosquitto `acl.conf`、`passwd`、证书文件的属主与权限初始化
- 设备侧当前未预留 ACK 机制，配置下发成功仅表示网关已本地执行或已转发 MQTT
- OTA 当前仅保留接口预留，不纳入后续开发计划
- AI 当前继续搁置，仅保留预留接口，不纳入本轮开发
- Apple `container build` 直接打包仓库根上下文仍可能出现归档兼容性问题；当前已由 `build_local_images.sh` 通过最小临时上下文规避

## 目录结构

- `docs/`：需求与接口源文档
- `gateway/edge_processor/`：网关 Python 服务
- `gateway/deployment/`：网关 Dockerfile、入口脚本、Compose 与 Apple `container` 辅助脚本
- `backend/api_service/`：后台 Python 服务
- `backend/deployment/`：后台 Dockerfile 与部署基线
- `ops_observer/api_service/`：运维观测 Python 服务
- `ops_observer/deployment/`：运维观测 Dockerfile 与默认配置
- `web/portal_app/`：网页端前端源码
- `web/deployment/`：网页端 Dockerfile、Nginx 配置与默认运行时配置

## 路由与数据流总览

系统当前的入口与转发关系如下：

1. 设备通过 MQTT 向网关 Broker 上报 `telemetry / alert / binding / status`
2. 网关 `edge_processor` 订阅 MQTT，先写入本地 InfluxDB 缓冲
3. 网关将批量数据通过 `POST /api/v1/ingest/batch` 发送到后台
4. 后台完成持久化后，通过 Redis Pub/Sub 或本地内存广播到 `/api/ws`
5. 后台配置下发通过 `POST /api/v1/devices/{id}/config` 创建待执行命令
6. 网关轮询 `GET /api/v1/gateway/{gateway_id}/commands/pending`，执行本地配置或转发到局域网 MQTT `config` topic
7. 网关通过 `POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result` 回报结果

当前后端对外路由分为：

- `GET /healthz`
- `POST /api/v1/ingest/batch`
- `GET /api/v1/devices`、`GET /api/v1/devices/{id}`、`POST /api/v1/devices/{id}/config`
- `GET /api/v1/gateway/{gateway_id}/commands/pending`、`GET /api/v1/gateway/commands/{command_id}`、`POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`
- `GET /api/v1/alerts`、`GET /api/v1/alerts/{id}`、`PATCH /api/v1/alerts/{id}/ack`、`POST /api/v1/alerts/batch-ack`
- `GET /api/v1/telemetry/wristband/{id}`
- `GET /api/v1/telemetry/equipment/{id}`
- `GET /api/v1/telemetry/env/{id}`、`GET /api/v1/telemetry/env/{id}/aggregate`
- `GET /api/v1/wristband/{id}/bindings`
- `POST /api/v1/system/health/report`、`GET /api/v1/system/health*`
- `GET /api/ws`
- `GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`、`WS /ops/ws`

默认部署配置下：

- `GET /api/ws?token={access_token}` 与 `WS /ops/ws?token={access_token}` 需要 JWT
- 业务查询、设备管理、后台自观测查询都需要 `Authorization: Bearer {access_token}`
- 仅网关采集、命令轮询 / 结果回报、健康上报这四类内网接口保留免鉴权
- 业务 `WS /api/ws?token={access_token}` 会继续按用户归属过滤，只推送已授权的 `gym_id` / `device_id` 数据

网关 HTTP 侧目前仅暴露：

- `GET /healthz`

## 常用命令

Linux / Docker 目标镜像构建：

```bash
container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

构建网关镜像：

```bash
container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

在 Apple `container` 中运行后台单元测试：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/backend/api_service \
  python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

在 Apple `container` 中运行网关单元测试：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/gateway/edge_processor \
  python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

在 Apple `container` 中运行运维观测端单元测试：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/ops_observer/api_service \
  python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

本地单容器启动 `ops_observer`：

```bash
container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  -t motion-sense-ops-observer-local \
  -f ops_observer/deployment/api_service/Dockerfile .
```

本地构建网页端镜像：

```bash
container build \
  --build-arg BUILD_BASE=node:24-alpine \
  --build-arg NGINX_BASE=nginx:1.29-alpine \
  -t motion-sense-web-portal-local \
  -f web/deployment/portal_app/Dockerfile .
```

启动 `04 / 05 / 06 / 09` 完整本地联调栈：

```bash
sh gateway/deployment/container/build_local_images.sh
sh gateway/deployment/container/prepare_runtime.sh
sh gateway/deployment/container/start_local_stack.sh
sh gateway/deployment/container/verify_regression_stack.sh
sh gateway/deployment/container/stop_local_stack.sh
```

联调脚本默认读取 `backend/deployment/compose/runtime/config/backend/api_service/bootstrap_admin.txt` 中首次生成的后台管理员账号；如需覆盖，可在执行前传入：

```bash
BACKEND_ADMIN_USERNAME=admin BACKEND_ADMIN_PASSWORD='<your-password>' \
  sh gateway/deployment/container/verify_system_stack.sh
```

## 本地平台说明

- 开发平台：macOS + Apple `container`
- 目标部署平台：Linux + Docker
- 本地 ad hoc 栈不提供 Compose 风格的服务名 DNS，脚本会显式解析容器 IP
- 当前基础镜像基线：`python:3.13-slim`、`eclipse-mosquitto:2.1-alpine`、`influxdb:3.9-core`、`redis:8.6-alpine`、`timescale/timescaledb:latest-pg17`、`node:24-alpine`、`nginx:1.29-alpine`
