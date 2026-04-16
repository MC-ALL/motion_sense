# API 服务

这是第 1 迭代的异步 FastAPI 后台服务。

## 当前实现范围

- 批量入库：`POST /api/v1/ingest/batch`
- JWT 认证：`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`POST /api/v1/auth/logout`
- 用户管理：`GET/POST/PATCH/DELETE /api/v1/users`
- 设备、告警、遥测、绑定历史查询接口
- WebSocket 实时接口：`GET /api/ws`
- 自观测接口：`GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`、`WS /ops/ws`
- 设备配置下发：`POST /api/v1/devices/{id}/config`
- OTA 预留接口：`POST /api/v1/devices/{id}/ota`、`GET /api/v1/ota/tasks*`
- 网关命令轮询：`GET /api/v1/gateway/{gateway_id}/commands/pending`
- 命令结果回报：`POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`
- 网关基础设施健康汇聚：`POST /api/v1/system/health/report`、`GET /api/v1/system/health*`
- AI 预留接口：`POST /api/v1/ai/analyze`、`GET /api/v1/ai/reports*`
- 存储后端：`memory`、`postgres`
- 实时广播后端：`local`、`redis`

## 路由结构

- `/healthz`：健康检查
- `/api/v1/ingest/*`：网关批量上报入口
- `/api/v1/auth/*`：JWT 登录、刷新、退出
- `/api/v1/users/*`：用户管理
- `/api/v1/devices/*`：设备查询与配置下发
- `/api/v1/ota/*`：OTA 预留接口
- `/api/v1/gateway/*`：配置命令轮询与状态回报
- `/api/v1/alerts/*`：告警查询与确认
- `/api/v1/telemetry/*`：历史遥测与环境聚合
- `/api/v1/wristband/*`：手环绑定历史
- `/api/v1/system/health/*`：网关基础设施健康汇聚与查询
- `/api/v1/ai/*`：AI 预留接口
- `/api/ws`：实时推送
- `/ops/v1/*`、`/ops/ws`：后台自观测接口

## 配置下发行为

- 后台仅负责创建配置命令，不直接连接 MQTT Broker
- 命令由目标网关通过 `/api/v1/gateway/{gateway_id}/commands/pending` 轮询拉取
- 网关对当前网关配置执行本地落地，对器材端 / 环境端配置转发到局域网 MQTT
- 命令状态支持 `pending`、`succeeded`、`failed`、`timed_out`
- 网关拉取待执行命令时，后台会递增 `attempt_count` 并设置短期 `leased_until`
- 网关回报 `failed` 后，命令会按 `retry_backoff_s` 重入队列；超过 `max_attempts` 或 `expires_at` 后结束
- 设备侧当前未预留 ACK 机制，`succeeded` 不代表设备已最终持久化
- 目标 topic 格式仍为 `gym/{gym_id}/{device_type}/{device_id}/config`

## 运行配置文件生成

- 首次启动会将 `backend/deployment/api_service/defaults/default_app_settings.yaml`
  复制到 `/runtime/config/backend/api_service/app_settings.yaml`
- 首次启动会补齐后台管理员密码哈希、JWT 密钥，并生成
  `/runtime/config/backend/api_service/bootstrap_admin.txt`
- refresh session 当前已落地到存储层；在 `memory` 存储模式下随进程生命周期存在，在 `postgres` 存储模式下可跨进程重建继续使用
- `bootstrap_admin.txt` 仅用于首次取回后台管理员用户名/密码，后续应自行轮换
- 当前 bootstrap admin 仍由部署配置托管：可用它登录并创建业务账号，但不允许通过 `/api/v1/users` 直接改密、降权或删除
- 后续修改在下次 `api_service` 重启后生效

## 当前鉴权边界

- 第 1 迭代部署默认 `auth.enforce_rest = true`、`auth.enforce_ws = true`
- 登录后可获得 `admin`、`teacher`、`student` 角色 JWT，并附带 `gym_ids` / `device_ids` 归属范围
- `admin` 不受归属限制；`teacher` 可访问 `gym_ids` 对应场馆与 `device_ids` 明确绑定的设备；`student` 仅可访问 `device_ids` 明确绑定的设备
- `/api/v1/users/*`、`POST/PATCH/DELETE /api/v1/devices*`、`POST /api/v1/devices/{id}/config`、`GET /api/v1/system/health*`、`/ops/v1/*`、`/ops/ws` 仅允许 `admin`
- `PATCH /api/v1/alerts/{id}/ack`、`POST /api/v1/alerts/batch-ack` 允许 `admin | teacher`
- 业务读接口与 `GET /api/ws` 会按登录用户的 `gym_ids` / `device_ids` 继续过滤结果
- 设备查询、告警、遥测、绑定历史、配置下发、健康查询、AI 预留接口、OTA 预留接口、`/api/ws` 会要求 Bearer JWT
- 网关内网链路暂不加 JWT：
  `POST /api/v1/ingest/batch`、
  `GET /api/v1/gateway/{gateway_id}/commands/pending`、
  `POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`、
  `POST /api/v1/system/health/report`
