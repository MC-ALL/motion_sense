# backend api_service

`backend/api_service` 是后台异步 FastAPI 服务，负责业务 API、鉴权、实时广播、训练会话聚合与 AI 报告生成基线。

## 目录功能

- `app/`：业务代码、路由、模型、服务层与存储层。
- `tests/`：单元测试。
- `pyproject.toml`：Python 包与测试依赖定义。
- `README.md`：模块说明。

## 目录结构

- `app/api/`：FastAPI 路由。
- `app/models/`：请求/响应与领域模型。
- `app/services/`：鉴权、入库、实时推送、AI 报告、训练会话聚合等服务。
- `app/storage/`：`memory` 与 `postgres` 两套存储实现。
- `tests/unit/`：后台单元测试。

## 模块功能

- 接收网关批量入库请求，并把遥测、告警、绑定、状态写入存储层。
- 管理用户、设备、告警、训练档案、训练会话与 AI 报告。
- 通过 `local` 或 `redis` 实时广播业务事件到 `/api/ws`。
- 提供后台自观测 `/ops/v1/health`、`/ops/v1/health/components`、`/ops/v1/stats` 与 `WS /ops/ws`。
- 在 `ai.auto_process=true` 时自动消费 `queued` 报告，推进到 `completed/failed`。
- 在 `ai.wakeup_backend=redis` 时支持多实例 AI 唤醒；正式生成前会原子抢占 `queued -> generating`。

## 接口约束

核心路由如下：
- 健康：`GET /healthz`
- 入库：`POST /api/v1/ingest/batch`
- 认证：`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`POST /api/v1/auth/logout`
- 用户：`GET/POST/PATCH/DELETE /api/v1/users`
- 设备：`GET /api/v1/devices`、`GET /api/v1/devices/{id}`、`POST /api/v1/devices`、`PATCH /api/v1/devices/{id}`、`DELETE /api/v1/devices/{id}`、`POST /api/v1/devices/{id}/config`
- 告警：`GET /api/v1/alerts`、`GET /api/v1/alerts/{id}`、`PATCH /api/v1/alerts/{id}/ack`、`POST /api/v1/alerts/batch-ack`
- 遥测：`GET /api/v1/telemetry/wristband/{id}`、`GET /api/v1/telemetry/equipment/{id}`、`GET /api/v1/telemetry/env/{id}`、`GET /api/v1/telemetry/env/{id}/aggregate`
- 绑定：`GET /api/v1/wristband/{id}/bindings`、`GET/POST /api/v1/user-wristband-bindings`、`POST /api/v1/user-wristband-bindings/{id}/unbind`、`GET /api/v1/user-wristband-bindings/overview`
- 训练：`GET /api/v1/users/{username}/training-profile`、`GET/POST/PATCH /api/v1/workout-sessions`、`GET /api/v1/workout-sessions/{session_id}`、`POST /api/v1/workout-sessions/aggregate`
- AI：`POST /api/v1/ai/analyze`、`GET /api/v1/ai/reports`、`GET /api/v1/ai/reports/{report_id}`、`POST /api/v1/ai/reports/{report_id}/retry`
- 网关配置命令：`WS /api/v1/gateway/{gateway_id}/commands/ws`、`GET /api/v1/gateway/{gateway_id}/commands/pending`、`GET /api/v1/gateway/commands/{command_id}`、`POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`
- WebSocket：`GET /api/ws`
- 运维：`GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`、`WS /ops/ws`
- OTA 占位：`POST /api/v1/devices/{id}/ota`、`GET /api/v1/ota/tasks`、`GET /api/v1/ota/tasks/{task_id}`

约束：
- 路径、字段与权限边界必须与 [design/07-通讯接口定义.md](../../design/07-通讯接口定义.md) 一致。
- `storage_backend` 仅支持 `memory`、`postgres`；`realtime_backend` 仅支持 `local`、`redis`。
- `ai.provider` 当前支持 `builtin` 与 OpenAI 兼容模式；模型变体通过 `model_variant=reasoner|chat` 切换。
- `ai.wakeup_backend` 当前支持 `local`、`redis`；Linux Compose 默认使用 `redis` 以适配多实例唤醒。
- OpenAI 兼容模式的 token 默认从 `/runtime/secrets/backend_ai_api_key.txt` 读取，不写入仓库。
- 网关命令通道共享 token 默认从 `/runtime/secrets/backend_gateway_command_token.txt` 读取；在线网关通过 `command_ready` 事件被唤醒后再补拉 pending。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall backend/api_service/app
docker run --rm -v "$PWD:/workspace" -w /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

当前测试覆盖：
- 健康检查、配置与权限设置
- 入库、设备管理、用户管理、权限边界
- 告警、训练会话、AI 报告、WebSocket
- 预留接口与角色访问控制

## 部署流程

1. 使用 `deployment/backend/api_service/Dockerfile` 构建后台镜像。
2. 首次启动由 `deployment/backend/api_service/entrypoint.sh` 把 `default_app_settings.yaml` 渲染到 `/runtime/config/backend/api_service/app_settings.yaml`。
3. Linux 正式部署通过 `deployment/backend/compose/docker-compose.yaml` 启动 `backend_timescaledb`、`backend_redis`、`backend_api_service`。
4. 整栈验证建议从仓库根执行 `sh deployment/compose/start_stack.sh` 和对应 `verify_*` 脚本。

## 后续改进

- 将 AI 处理从当前进程内 worker 继续演进到独立任务队列 / 独立进程。
- 细化 AI 失败分类、超时收敛、重试与人工恢复流程，并继续增强报告内容质量与证据引用。
- 强化数据库迁移、会话黑名单与多实例集成测试；流式输出仍作为后续增强项。
