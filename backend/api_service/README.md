# API 服务

这是第 1 迭代的异步 FastAPI 后台服务。

## 当前实现范围

- 批量入库：`POST /api/v1/ingest/batch`
- 认证接口预留：`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`
- 设备、告警、遥测、绑定历史查询接口
- WebSocket 实时接口：`GET /api/ws`
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
- `/api/v1/auth/*`：认证接口预留
- `/api/v1/devices/*`：设备查询与配置下发
- `/api/v1/ota/*`：OTA 预留接口
- `/api/v1/gateway/*`：配置命令轮询与状态回报
- `/api/v1/alerts/*`：告警查询与确认
- `/api/v1/telemetry/*`：历史遥测与环境聚合
- `/api/v1/wristband/*`：手环绑定历史
- `/api/v1/system/health/*`：网关基础设施健康汇聚与查询
- `/api/v1/ai/*`：AI 预留接口
- `/api/ws`：实时推送

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
- 后续修改在下次 `api_service` 重启后生效
