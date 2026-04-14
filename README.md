# motion_sense

本仓库是 `04-网关端` 与 `05-后台端` 的第 1 迭代工作区，包含需求文档、实现代码、部署文件与本地联调脚本。

## 当前状态

- `gateway/`：异步边缘处理服务、Mosquitto、InfluxDB 3 Core 部署资产，以及 Apple `container` 本地测试脚本
- `backend/`：异步 FastAPI 后台服务、TimescaleDB 持久化、Redis 实时广播
- `docs/`：系统架构、各子系统规格、接口契约与开发排期

当前机器上已完成并验证：

- 后台入库与查询主链路
- 后台 `local` / `redis` 两种 WebSocket 实时推送路径
- 后台 `POST /api/v1/devices/{id}/config` MQTT 配置下发基础能力
- 网关基于 InfluxDB 的本地缓存与补发链路
- 网关 P1 规则引擎与规则热重载
- 网关 `DEVICE_OFFLINE` 告警与 retained 状态发布
- 本地链路 `mosquitto -> edge_processor -> POST /api/v1/ingest/batch -> backend/api_service`

当前缺口：

- 后台鉴权 / JWT / AI 报告流程尚未实现
- 设备配置下发尚未实现设备 ack / 回执追踪
- 网关仍缺真实 Broker 重连、规则热重载边界场景的端到端覆盖

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
5. 后台配置下发通过 `POST /api/v1/devices/{id}/config` 发布到 MQTT `config` topic

当前后端对外路由分为：

- `GET /healthz`
- `POST /api/v1/ingest/batch`
- `GET /api/v1/devices`、`GET /api/v1/devices/{id}`、`POST /api/v1/devices/{id}/config`
- `GET /api/v1/alerts`、`GET /api/v1/alerts/{id}`、`PATCH /api/v1/alerts/{id}/ack`、`POST /api/v1/alerts/batch-ack`
- `GET /api/v1/telemetry/wristband/{id}`
- `GET /api/v1/telemetry/equipment/{id}`
- `GET /api/v1/telemetry/env/{id}`、`GET /api/v1/telemetry/env/{id}/aggregate`
- `GET /api/v1/wristband/{id}/bindings`
- `GET /api/ws`

网关 HTTP 侧目前仅暴露：

- `GET /healthz`

## 常用命令

构建后台镜像：

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

运行后台单元测试：

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-backend-api-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 httpx==0.28.1 >/tmp/pip.log 2>&1 && cd /workspace/backend/api_service && PYTHONPATH=/workspace/backend/api_service pytest tests/unit -q"
```

运行网关单元测试：

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-edge-processor-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 >/tmp/pip.log 2>&1 && cd /workspace/gateway/edge_processor && PYTHONPATH=/workspace/gateway/edge_processor pytest tests/unit -q"
```

## 本地平台说明

- 开发平台：macOS + Apple `container`
- 目标部署平台：Linux + Docker
- 本地 ad hoc 栈不提供 Compose 风格的服务名 DNS，脚本会显式解析容器 IP
- 当前镜像源基线：`dockerproxy.net`
