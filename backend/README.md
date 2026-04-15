# 后台端

当前后台实现位于 `backend/api_service/`，聚焦第 1 迭代的最小可用闭环。

## 当前已实现接口

- `POST /api/v1/ingest/batch`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{id}`
- `POST /api/v1/devices/{id}/config`
- `POST /api/v1/auth/login`（预留，当前返回 `501`）
- `POST /api/v1/auth/refresh`（预留，当前返回 `501`）
- `POST /api/v1/devices/{id}/ota`（预留，当前返回 `501`）
- `GET /api/v1/ota/tasks`（预留，当前返回 `501`）
- `GET /api/v1/ota/tasks/{task_id}`（预留，当前返回 `501`）
- `GET /api/v1/gateway/{gateway_id}/commands/pending`
- `GET /api/v1/gateway/commands/{command_id}`
- `POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`
- `POST /api/v1/ai/analyze`（预留，当前返回 `501`）
- `GET /api/v1/ai/reports`（预留，当前返回 `501`）
- `GET /api/v1/ai/reports/{id}`（预留，当前返回 `501`）
- `GET /api/v1/system/health`
- `GET /api/v1/system/health/{gateway_id}`
- `POST /api/v1/system/health/report`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{id}`
- `PATCH /api/v1/alerts/{id}/ack`
- `POST /api/v1/alerts/batch-ack`
- `GET /api/v1/telemetry/wristband/{id}`
- `GET /api/v1/telemetry/equipment/{id}`
- `GET /api/v1/telemetry/env/{id}`
- `GET /api/v1/telemetry/env/{id}/aggregate`
- `GET /api/v1/wristband/{id}/bindings`
- `GET /ops/v1/health`
- `GET /ops/v1/health/components`
- `GET /ops/v1/stats`
- `WS /ops/ws`
- `GET /healthz`
- `GET /api/ws`

## 路由逻辑

后台应用在 [main.py](/Users/circuitx/Work/motion_sense/backend/api_service/app/main.py) 中按以下顺序挂载路由：

1. `health.router`：健康检查 `GET /healthz`
2. `ingest.router`：网关批量入库 `POST /api/v1/ingest/batch`
3. `auth.router`：认证接口预留
4. `devices.router`：设备查询与配置下发
5. `alerts.router`：告警查询、确认、批量确认
6. `telemetry.router`：手环 / 器材 / 环境历史查询与环境聚合查询
7. `bindings.router`：手环绑定历史
8. `gateway_commands.router`：配置命令轮询与结果回报
9. `system_health.router`：网关基础设施健康上报与查询
10. `ota.router`：OTA 预留接口
11. `ai.router`：AI 预留接口
12. `websocket.router`：实时推送 `GET /api/ws`
13. `ops.router`：后台自观测接口 `GET /ops/v1/*`、`WS /ops/ws`

主数据流如下：

1. 网关调用 `POST /api/v1/ingest/batch`
2. `IngestService` 解析批次并写入存储层
3. 写入成功后通过 `RealtimeService` 推送到 WebSocket
4. 如启用 `redis`，则经 Redis Pub/Sub 做跨实例广播
5. 后台调用 `POST /api/v1/devices/{id}/config` 时，创建待执行配置命令
6. 网关调用 `GET /api/v1/gateway/{gateway_id}/commands/pending` 拉取命令并在本地执行 / 转发 MQTT
7. 网关调用 `POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result` 回报结果
8. 网关可通过 `POST /api/v1/system/health/report` 上报本地基础设施健康快照

## 运行模式

当前后台是异步 FastAPI 服务，支持两类存储模式：

- `memory`：单元测试与最小本地运行默认使用
- `postgres`：基于异步 `psycopg` 的 PostgreSQL / TimescaleDB 持久化

实时广播支持两类模式：

- `local`：单进程内存广播
- `redis`：跨实例 Redis Pub/Sub 广播

## 本地构建

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  -t motion-sense-backend-api-local \
  -f backend/deployment/api_service/Dockerfile .
```

## 已完成验证

- `POST /api/v1/ingest/batch` 可写入 TimescaleDB / PostgreSQL
- `GET /api/v1/devices/{id}` 可返回设备快照
- `PATCH /api/v1/alerts/{id}/ack` 可更新告警确认状态
- `GET /api/v1/telemetry/equipment/{id}` 可返回历史数据
- `GET /api/v1/wristband/{id}/bindings` 可返回绑定历史
- `GET /api/v1/telemetry/env/{id}/aggregate` 可返回环境聚合结果
- `POST /api/v1/alerts/batch-ack` 可批量确认告警
- `POST /api/v1/devices/{id}/config` 与 `/api/v1/gateway/*/commands/*` 已具备配置命令闭环
- 配置命令已具备领取租约、失败重试与超时收敛能力
- `POST /api/v1/system/health/report` 与 `GET /api/v1/system/health*` 已具备基础设施健康汇聚能力
- `GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`、`WS /ops/ws` 已具备后台自观测能力
- `redis` 实时模式已在 macOS Apple `container` 上验证

## 运行配置

- `/runtime/config/backend/api_service/app_settings.yaml` 首次启动由 `default_app_settings.yaml` 生成
- 修改 `app_settings.yaml` 后需重启 `api_service`
- 修改 Redis 运行参数后需重启 `redis`
- 修改 TimescaleDB 镜像、初始化 SQL 或持久卷参数后需重启 `timescaledb`

## 风险与待补项

- `redis` 仅验证了单后台实例广播，多实例自动化覆盖尚缺
- JWT 黑名单与 AI 报告流程仍待实现；`auth` 路由当前仅预留
- 设备侧当前未预留 ACK 机制，配置命令成功只代表网关已本地执行或已转发 MQTT
- AI 实际集成仍待实现
- OTA 当前仅保留接口预留，不纳入后续开发计划

## 单元测试

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/backend/api_service \
  dockerproxy.net/library/python:3.13-slim \
  sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```
