# ops_observer api_service

独立运维观测服务，负责汇聚网关与后台的自观测信息，并向网页端提供统一的健康中心接口。

## 主要接口

- `GET /healthz`
- `GET /api/v1/ops/health`
- `GET /api/v1/ops/health/{module_id}`
- `GET /api/v1/ops/alerts`
- `PATCH /api/v1/ops/alerts/{alert_id}/close`
- `GET /api/v1/ops/stats`
- `WS /api/ws/ops`

## 配置

默认配置模板位于 `../deployment/api_service/defaults/default_app_settings.yaml`，容器首次启动时会生成运行时配置：

- `/runtime/config/ops_observer/api_service/app_settings.yaml`
- `/runtime/data/ops_observer/ops_observer.sqlite3`

`app_settings.yaml` 修改后需要重启容器。

## 上游连接

- 默认通过 REST 拉取网关与后台的 `/ops/v1/*`
- 若 `upstream_modules[].ws_enabled = true`，同时订阅 `/ops/ws`，在上游推送 `ops_snapshot` 时立即刷新本地聚合结果
