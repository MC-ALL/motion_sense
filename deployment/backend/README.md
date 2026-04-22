# deployment backend

`deployment/backend/` 存放后台服务及其依赖的部署资产。

## 目录功能

- 提供 `backend_api_service` 与 `backend_timescaledb` 的镜像构建资产。
- 提供后台模块级 Compose 样例，供仓库级正式编排复用。
- 提供后台首启默认配置模板。

## 目录结构

- `api_service/`：后台服务 Dockerfile、entrypoint 与默认配置模板。
- `timescaledb/`：数据库镜像 Dockerfile。
- `compose/docker-compose.yaml`：后台模块 Compose 样例。

## 脚本与配置文件

- `api_service/Dockerfile`：构建后台 API 镜像。
- `api_service/entrypoint.sh`：生成 `/runtime/config/backend/api_service/app_settings.yaml`、后台 bootstrap admin/JWT 运行时文件，以及共享的 `/runtime/secrets/backend_gateway_command_token.txt`。
- `api_service/defaults/default_app_settings.yaml`：后台默认配置模板。
- `timescaledb/Dockerfile`：构建 TimescaleDB 镜像。
- `compose/docker-compose.yaml`：定义 `backend_timescaledb`、`backend_redis`、`backend_api_service`。

## 环境配置要求

- Docker Engine 与 Compose。
- `BACKEND_DATABASE_PASSWORD` 可在正式环境显式覆盖，默认占位值仅用于开发联调。
- 如启用 OpenAI 兼容 AI provider，需要在 `deployment/runtime/secrets/backend_ai_api_key.txt` 投放 token。
- gateway 命令通道默认使用 `deployment/runtime/secrets/backend_gateway_command_token.txt` 共享 token；未预置时由 backend entrypoint 首启自动生成。
- 如使用多实例 backend，建议保持 `BACKEND_AI_WAKEUP_BACKEND=redis`；仓库内 Linux Compose 默认已开启该项。

## 基础设施要求

- PostgreSQL/TimescaleDB 持久卷。
- Redis 服务。
- 宿主机挂载 `deployment/runtime/config` 与 `deployment/runtime/secrets`。

## 使用方式

单独查看配置：

```bash
docker compose -f deployment/backend/compose/docker-compose.yaml config
```

整栈启动仍建议走仓库根：

```bash
sh deployment/compose/start_stack.sh
```

## 后续改进

- 补充数据库迁移策略与版本管理。
- 继续细化 AI provider 与密钥管理说明。
- 增补后台单模块 smoke test。
