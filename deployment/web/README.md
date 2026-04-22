# deployment web

`deployment/web/` 存放网页端镜像、Nginx 配置、默认运行时配置模板与模块级 Compose 样例。

## 目录功能

- 构建网页端生产镜像。
- 通过 Nginx 提供单端口同源入口。
- 为仓库级 Compose 提供 `web_portal_app` 服务定义。

## 目录结构

- `portal_app/`：Dockerfile、entrypoint、Nginx 配置、默认 `runtime_config.js`。
- `compose/`：网页端模块 Compose 样例与补充说明。

## 脚本与配置文件

- `portal_app/Dockerfile`：前端构建与 Nginx 运行镜像。
- `portal_app/entrypoint.sh`：启动时生成或保留 `runtime_config.js`。
- `portal_app/nginx.conf`：静态资源服务与 backend/ops 同源代理配置。
- `portal_app/defaults/default_runtime_config.js`：默认运行时配置模板。
- `compose/docker-compose.yaml`：定义 `web_portal_app` 服务。

## 环境配置要求

- Docker Engine 与 Compose。
- 宿主机挂载 `deployment/runtime/config`。
- 正式环境可通过环境变量覆盖 `WEB_PORTAL_BACKEND_BASE_URL`、`WEB_PORTAL_BACKEND_WS_URL`、`WEB_PORTAL_OPS_BASE_URL`、`WEB_PORTAL_OPS_WS_URL`。

## 基础设施要求

- 需能访问 backend 与 `ops_observer` 容器。
- 默认对外暴露 `8080` 端口，适合 SSH 单端口转发。

## 使用方式

```bash
docker compose -f deployment/web/compose/docker-compose.yaml config
```

整栈访问建议仍走：

```bash
sh deployment/compose/start_stack.sh
```

## 后续改进

- 增加前端 smoke test 与静态资源校验。
- 继续细化远端 SSH 转发访问场景下的部署说明。
- 补充“WebSocket 重连后单次 REST 补同步”相关的排障说明与浏览器验收要点。
