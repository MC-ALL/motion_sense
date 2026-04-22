# Production Reference

适用范围：
- Linux + Docker Compose 正式部署
- 对照当前仓库中的 `deployment/compose/docker-compose.yaml` 与各模块 `compose/docker-compose.yaml`

## 1. 宿主机端口对照

| 宿主机端口 | 容器端口 | 服务 | 用途 | 建议暴露范围 |
|-----------|---------|------|------|-------------|
| `1883/tcp` | `1883` | `gateway_mosquitto` | MQTT Broker 明文监听 | 仅内网或设备接入网段 |
| `5432/tcp` | `5432` | `backend_timescaledb` | PostgreSQL / TimescaleDB | 尽量不对公网开放 |
| `6379/tcp` | `6379` | `backend_redis` | Redis | 尽量不对公网开放 |
| `8000/tcp` | `8000` | `backend_api_service` | 后台 REST / WS / ops API | 内网或受控入口 |
| `8080/tcp` | `8080` | `web_portal_app` | 网页端入口 | 面向浏览器访问 |
| `8090/tcp` | `8090` | `ops_observer_api_service` | 运维观测 REST / WS | 内网或受控入口 |
| `8181/tcp` | `8181` | `gateway_influxdb` | InfluxDB 3 HTTP API | 尽量不对公网开放 |

说明：
- `gateway_edge_processor` 运行在容器内 `8080`，当前未直接映射宿主机端口。
- 网页端默认通过 `8080` 同源代理 backend / `ops_observer`；浏览器访问时优先使用 `8080` 单入口，不要求再直接暴露 `8000` / `8090` 给浏览器。
- 若需要修改宿主机端口，优先改模块 Compose 文件中的 `ports:` 映射，不要只改文档。

## 2. Compose 覆盖变量对照

以下变量通过 Compose `${VAR:-default}` 方式读取，适合在部署时覆盖。

| 变量名 | 默认值 | 作用服务 | 用途 | 正式环境建议 |
|-------|-------|---------|------|-------------|
| `BACKEND_DATABASE_PASSWORD` | `change_me_at_deploy` | `backend_timescaledb` `backend_api_service` | PostgreSQL 账号 `motion_sense` 的密码 | 必改 |
| `MOSQUITTO_USER` | `admin` | `gateway_mosquitto` `gateway_edge_processor` | MQTT 用户名 | 建议改 |
| `MOSQUITTO_PASSWORD` | `admin123` | `gateway_mosquitto` `gateway_edge_processor` | MQTT 密码 | 必改 |
| `WEB_PORTAL_BACKEND_BASE_URL` | `''` | `web_portal_app` | 网页端访问后台 REST 地址 | 默认保持同源；仅在你明确不用 Nginx 同源代理时再覆盖 |
| `WEB_PORTAL_BACKEND_WS_URL` | `/api/ws` | `web_portal_app` | 网页端访问后台业务 WS 地址 | 默认保持同源 |
| `WEB_PORTAL_OPS_BASE_URL` | `''` | `web_portal_app` | 网页端访问运维 REST 地址 | 默认保持同源；仅在你明确不用 Nginx 同源代理时再覆盖 |
| `WEB_PORTAL_OPS_WS_URL` | `/api/ws/ops` | `web_portal_app` | 网页端访问运维 WS 地址 | 默认保持同源 |
| `WEB_PORTAL_RUNTIME_CONFIG_MODE` | `render` | `web_portal_app` | 网页运行时配置生成策略 | 默认每次启动按环境变量重渲染；仅在明确要保留宿主机现有文件时改为 `preserve` |

说明：
- 当前根 Compose 未使用 `.env`，但 Docker Compose 仍支持从当前 shell 环境读取这些变量。
- 若需要固定部署值，建议在部署脚本或运维系统中显式导出环境变量后再执行 `start_stack.sh`。

示例：

```bash
export BACKEND_DATABASE_PASSWORD='replace_me'
export MOSQUITTO_USER='motion_sense'
export MOSQUITTO_PASSWORD='replace_me'
sh deployment/compose/start_stack.sh
```

## 3. 容器内固定环境变量对照

以下变量在 Compose 内部写死，用于容器之间互联，通常不需要部署时修改。

| 变量名 | 值 | 作用服务 | 说明 |
|-------|----|---------|------|
| `BACKEND_STORAGE_BACKEND` | `postgres` | `backend_api_service` | 后台存储后端 |
| `BACKEND_REALTIME_BACKEND` | `redis` | `backend_api_service` | 后台实时后端 |
| `BACKEND_DATABASE_HOST` | `backend_timescaledb` | `backend_api_service` | 后台连接 DB 的容器地址 |
| `BACKEND_DATABASE_PORT` | `5432` | `backend_api_service` | 后台连接 DB 端口 |
| `BACKEND_DATABASE_NAME` | `motion_sense` | `backend_api_service` | 后台数据库名 |
| `BACKEND_DATABASE_USER` | `motion_sense` | `backend_api_service` | 后台数据库用户 |
| `BACKEND_REDIS_HOST` | `backend_redis` | `backend_api_service` | 后台连接 Redis 的容器地址 |
| `BACKEND_REDIS_PORT` | `6379` | `backend_api_service` | 后台连接 Redis 端口 |
| `EDGE_PROCESSOR_BACKEND_BASE_URL` | `http://backend_api_service:8000/api/v1` | `gateway_edge_processor` | 网关访问后台业务 API |
| `EDGE_PROCESSOR_INFLUXDB_BASE_URL` | `http://gateway_influxdb:8181` | `gateway_edge_processor` | 网关访问 InfluxDB |
| `EDGE_PROCESSOR_MQTT_HOST` | `gateway_mosquitto` | `gateway_edge_processor` | 网关访问 MQTT Broker |
| `EDGE_PROCESSOR_OPS_AUTH_ENFORCE_REST` | `true` | `gateway_edge_processor` | 网关 ops REST 强制鉴权 |
| `EDGE_PROCESSOR_OPS_AUTH_ENFORCE_WS` | `true` | `gateway_edge_processor` | 网关 ops WS 强制鉴权 |
| `OPS_OBSERVER_BACKEND_BASE_URL` | `http://backend_api_service:8000` | `ops_observer_api_service` | 运维端访问后台 |
| `OPS_OBSERVER_GATEWAY_BASE_URL` | `http://gateway_edge_processor:8080` | `ops_observer_api_service` | 运维端访问网关 |
| `OPS_OBSERVER_AUTH_ENFORCE_REST` | `true` | `ops_observer_api_service` | 运维 REST 强制鉴权 |
| `OPS_OBSERVER_AUTH_ENFORCE_WS` | `true` | `ops_observer_api_service` | 运维 WS 强制鉴权 |

## 4. 首启自动生成文件对照

| 文件路径 | 生成方 | 用途 | 备注 |
|---------|-------|------|------|
| `deployment/runtime/config/backend/api_service/app_settings.yaml` | `backend_api_service` entrypoint | 后台运行时配置 | 首次从默认模板复制 |
| `deployment/runtime/config/backend/api_service/bootstrap_admin.txt` | `backend_api_service` entrypoint | 后台首登管理员凭据 | 首次生成，权限 `600` |
| `deployment/runtime/config/influxdb/influxdb3_init.txt` | `gateway_influxdb` entrypoint | Influx 初始化参数 | 首次从默认模板复制 |
| `deployment/runtime/config/influxdb/admin_token.txt` | `gateway_influxdb` entrypoint | Influx 管理 token | 首次生成，权限 `600` |
| `deployment/runtime/config/edge_processor/app_settings.yaml` | `gateway_edge_processor` entrypoint | 网关运行时配置 | 首次从默认模板复制 |
| `deployment/runtime/config/edge_processor/logging.yaml` | `gateway_edge_processor` entrypoint | 网关日志配置 | 首次从默认模板复制 |
| `deployment/runtime/config/edge_processor/rules.yaml` | `gateway_edge_processor` entrypoint | 网关规则配置 | 首次从默认模板复制 |
| `deployment/runtime/config/mosquitto/mosquitto.conf` | `gateway_mosquitto` entrypoint | Broker 运行配置 | 首次从默认模板复制 |
| `deployment/runtime/config/mosquitto/acl.conf` | `gateway_mosquitto` entrypoint | Broker ACL | 首次按 `MOSQUITTO_USER` 渲染 |
| `deployment/runtime/config/ops_observer/api_service/app_settings.yaml` | `ops_observer_api_service` entrypoint | 运维端运行时配置 | 首次从默认模板复制 |
| `deployment/runtime/config/web/portal_app/runtime_config.js` | `web_portal_app` entrypoint | 网页运行时配置 | 默认随容器启动按环境变量重渲染；`WEB_PORTAL_RUNTIME_CONFIG_MODE=preserve` 时保留现有文件 |
| `deployment/runtime/secrets/backend_gateway_command_token.txt` | `backend_api_service` entrypoint | 后台到网关命令通道共享 token | 首次生成，权限 `600`；`gateway_edge_processor` 启动时会等待该文件 |
| `deployment/runtime/secrets/mosquitto.passwd` | `gateway_mosquitto` entrypoint | MQTT 口令文件 | 首次生成 |
| `deployment/runtime/secrets/edge_processor_ops_token.txt` | `gateway_edge_processor` entrypoint | 网关 ops token | 首次生成，权限 `600` |
| `deployment/runtime/secrets/backend_ai_api_key.txt` | 宿主机人工投放 | 外部 AI 提供方 token | 可选；建议权限 `600`；可通过 `sh deployment/compose/write_backend_ai_api_key.sh` 写入 |

## 5. 宿主机需重点保管的敏感文件

| 文件路径 | 敏感级别 | 说明 |
|---------|---------|------|
| `deployment/runtime/config/backend/api_service/bootstrap_admin.txt` | 高 | 包含后台 bootstrap admin 明文密码 |
| `deployment/runtime/config/backend/api_service/app_settings.yaml` | 高 | 包含后台 JWT secret 与密码哈希 |
| `deployment/runtime/config/influxdb/admin_token.txt` | 高 | 包含 Influx admin token |
| `deployment/runtime/secrets/backend_gateway_command_token.txt` | 高 | 后台到网关命令通道共享 token |
| `deployment/runtime/secrets/mosquitto.passwd` | 高 | MQTT 账号密码文件 |
| `deployment/runtime/secrets/edge_processor_ops_token.txt` | 高 | 网关运维 token |
| `deployment/runtime/secrets/backend_ai_api_key.txt` | 高 | 外部 AI 提供方 token |
| `deployment/runtime/data/ops_observer/ops_observer.sqlite3` | 中 | 运维观测历史数据 |

要求：
- 这些文件不得提交到 Git
- 不要通过不受控目录同步到公共位置
- 备份时需要按敏感数据处理

## 6. MQTT TLS 证书对照

当 `deployment/runtime/config/mosquitto/mosquitto.conf` 中出现 `listener 8883` 时，Mosquitto 入口脚本会强制检查以下文件：

| 文件路径 | 是否必须 | 用途 |
|---------|---------|------|
| `deployment/runtime/certs/server.crt` | 是 | Broker 服务端证书 |
| `deployment/runtime/certs/server.key` | 是 | Broker 服务端私钥 |
| `deployment/runtime/certs/ca.crt` | 是 | 签发链 / 客户端校验证书 |

要求：
- 三个文件缺一不可
- 文件名必须与上表一致，除非你同时修改 Broker 配置与文档
- TLS 失败时优先检查文件存在性、权限与配置项是否一致

## 7. 默认鉴权状态对照

| 模块 | 接口类型 | 当前默认状态 | 说明 |
|------|---------|-------------|------|
| `backend_api_service` | REST | 强制鉴权 | 网关内网接口例外 |
| `backend_api_service` | WS | 强制鉴权 | `/api/ws` 与 `/ops/ws` 需要 token |
| `gateway_edge_processor` | ops REST | 强制鉴权 | Compose 里显式开启 |
| `gateway_edge_processor` | ops WS | 强制鉴权 | Compose 里显式开启 |
| `ops_observer_api_service` | REST | 强制鉴权 | 仅后台管理员 JWT 可访问 |
| `ops_observer_api_service` | WS | 强制鉴权 | 仅后台管理员 JWT 可访问 |

## 8. 正式部署常用入口

| 用途 | 命令 |
|------|------|
| 启动并等待健康 | `sh deployment/compose/start_stack.sh` |
| 打印首登信息 | `sh deployment/compose/print_bootstrap_credentials.sh` |
| 写入 AI token | `sh deployment/compose/write_backend_ai_api_key.sh` |
| 切换 AI 模型档位 | `sh deployment/compose/switch_backend_ai_model.sh reasoner` |
| 运维鉴权回归 | `sh deployment/compose/verify_ops_auth_stack.sh` |
| 业务链路回归 | `sh deployment/compose/verify_system_stack.sh` |
| 网关批量上报回归 | `sh deployment/compose/verify_gateway_batch_stack.sh` |
| 训练档案回归 | `sh deployment/compose/verify_training_archive_stack.sh` |
| 训练会话汇聚回归 | `sh deployment/compose/verify_workout_aggregation_stack.sh` |
| AI 报告回归 | `sh deployment/compose/verify_ai_stack.sh` |
| 数据链路回归 | `sh deployment/compose/verify_database_stack.sh` |
| 停栈 | `sh deployment/compose/stop_stack.sh` |

## 9. 推荐阅读顺序

1. `deployment/compose/SERVER_INIT_CHECKLIST.md`
2. `deployment/compose/RUNBOOK.md`
3. `deployment/compose/README.md`
