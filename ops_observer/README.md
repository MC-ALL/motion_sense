# ops_observer

`ops_observer` 是独立的运维观测模块，负责通过 REST 拉取网关与后台的自观测接口，汇聚基础设施健康状态、组件明细、运行统计与运维告警。

## 目录

- `api_service/`：运维聚合 FastAPI 服务
- `deployment/api_service/`：Dockerfile、入口脚本与默认配置模板

## 当前能力

- 轮询上游 `/ops/v1/health`、`/ops/v1/health/components`、`/ops/v1/stats`
- 订阅上游 `/ops/ws`，在状态变化时触发即时刷新
- 当上游开启 JWT 时，可使用配置中的 `auth_username` / `auth_password` 自动登录并续期 token
- 使用 SQLite 持久化模块快照、组件明细、统计与运维告警
- 支持运维告警人工关闭
- 对网页端暴露 `GET /api/v1/ops/*` 与 `WS /api/ws/ops`
- 首次启动自动生成运行时 `app_settings.yaml`
