# motion_sense

本仓库是 `04-网关端` 与 `05-后台端` 的第 1 迭代工作区，包含需求文档、实现代码、部署文件与本地联调脚本。

## 当前状态

- `gateway/`：异步边缘处理服务、Mosquitto、InfluxDB 3 Core 部署资产，以及 Apple `container` 本地测试脚本
- `backend/`：异步 FastAPI 后台服务、TimescaleDB 持久化、Redis 实时广播
- `docs/`：系统架构、各子系统规格、接口契约与开发排期

当前机器上已完成并验证：

- 后台入库与查询主链路
- 后台 `local` / `redis` 两种 WebSocket 实时推送路径
- 后台 `POST /api/v1/devices/{id}/config` 配置命令入库
- 网关 `GET /api/v1/gateway/{gateway_id}/commands/pending` 轮询执行与结果回报
- 配置命令失败重试、租约领取与 `timed_out` 超时收敛
- 后台 `POST /api/v1/auth/login`、`POST /api/v1/auth/refresh` 认证接口已预留
- 后台 AI / OTA 预留接口已占位，当前返回 `501 reserved`
- 网关基于 InfluxDB 的本地缓存与补发链路
- 网关 P1 规则引擎与规则热重载
- 网关 `DEVICE_OFFLINE` 告警与 retained 状态发布
- 网关基础设施健康采集与 `POST /api/v1/system/health/report` 上报
- 本地链路 `mosquitto -> edge_processor -> InfluxDB 缓冲 -> POST /api/v1/ingest/batch -> backend/api_service -> TimescaleDB`
- Apple `container` 本地脚本 `verify_system_stack.sh` 已验证通过：
  设备入库、健康汇聚、配置命令闭环、健康汇总视图

当前缺口：

- 后台 JWT 鉴权 / AI 报告流程尚未实现，`auth` 路由当前仅预留
- 设备侧当前未预留 ACK 机制，配置下发成功仅表示网关已本地执行或已转发 MQTT
- 网关仍缺真实 Broker 重连、规则热重载边界场景的端到端覆盖
- OTA 当前仅保留接口预留，不纳入后续开发计划
- AI 当前继续搁置，仅保留预留接口，不纳入本轮开发
- Apple `container build` 直接打包仓库根上下文仍存在归档兼容性问题，当前单测采用 `container run` 挂载代码目录规避

## 目录结构

- `docs/`：需求与接口源文档
- `gateway/edge_processor/`：网关 Python 服务
- `gateway/deployment/`：网关 Dockerfile、入口脚本、Compose 与 Apple `container` 辅助脚本
- `backend/api_service/`：后台 Python 服务
- `backend/deployment/`：后台 Dockerfile 与部署基线

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

网关 HTTP 侧目前仅暴露：

- `GET /healthz`

## 常用命令

Linux / Docker 目标镜像构建：

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

构建网关镜像：

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

在 Apple `container` 中运行后台单元测试：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/backend/api_service \
  dockerproxy.net/library/python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

在 Apple `container` 中运行网关单元测试：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/gateway/edge_processor \
  dockerproxy.net/library/python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 本地平台说明

- 开发平台：macOS + Apple `container`
- 目标部署平台：Linux + Docker
- 本地 ad hoc 栈不提供 Compose 风格的服务名 DNS，脚本会显式解析容器 IP
- 当前镜像源基线：`dockerproxy.net`
