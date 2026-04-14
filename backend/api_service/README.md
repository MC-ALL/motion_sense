# API 服务

这是第 1 迭代的异步 FastAPI 后台服务。

## 当前实现范围

- 批量入库：`POST /api/v1/ingest/batch`
- 设备、告警、遥测、绑定历史查询接口
- WebSocket 实时接口：`GET /api/ws`
- 设备配置下发：`POST /api/v1/devices/{id}/config`
- 网关命令轮询：`GET /api/v1/gateway/{gateway_id}/commands/pending`
- 命令结果回报：`POST /api/v1/gateway/{gateway_id}/commands/{command_id}/result`
- 网关基础设施健康汇聚：`POST /api/v1/system/health/report`、`GET /api/v1/system/health*`
- 存储后端：`memory`、`postgres`
- 实时广播后端：`local`、`redis`

## 路由结构

- `/healthz`：健康检查
- `/api/v1/ingest/*`：网关批量上报入口
- `/api/v1/devices/*`：设备查询与配置下发
- `/api/v1/gateway/*`：配置命令轮询与状态回报
- `/api/v1/alerts/*`：告警查询与确认
- `/api/v1/telemetry/*`：历史遥测与环境聚合
- `/api/v1/wristband/*`：手环绑定历史
- `/api/v1/system/health/*`：网关基础设施健康汇聚与查询
- `/api/ws`：实时推送

## 配置下发行为

- 后台仅负责创建配置命令，不直接连接 MQTT Broker
- 命令由目标网关通过 `/api/v1/gateway/{gateway_id}/commands/pending` 轮询拉取
- 网关对当前网关配置执行本地落地，对器材端 / 环境端配置转发到局域网 MQTT
- 目标 topic 格式仍为 `gym/{gym_id}/{device_type}/{device_id}/config`

## 运行配置文件生成

- 首次启动会将 `backend/deployment/api_service/defaults/default_app_settings.yaml`
  复制到 `/runtime/config/backend/api_service/app_settings.yaml`
- 后续修改在下次 `api_service` 重启后生效
