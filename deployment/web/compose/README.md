# deployment web compose

`deployment/web/compose/` 提供网页端模块级 Compose 样例，供仓库级正式编排复用。

## 目录功能

- 定义 `web_portal_app` 服务。
- 说明网页端运行时配置通过共享 runtime 挂载注入。

## 目录结构

- `docker-compose.yaml`：网页端模块 Compose 样例。

## 配置与用法

- `web_portal_app` 暴露 `8080` 端口。
- 运行时配置挂载目录为 `deployment/runtime/config`。
- 默认通过环境变量覆盖 `backend/ops` 地址和刷新周期。

## 环境配置要求

- Docker Engine 与 Compose。
- 建议与 backend、`ops_observer` 一起由仓库级 `deployment/compose/docker-compose.yaml` 启动。

## 基础设施要求

- 后端与运维服务在同一 Compose 网络中可达。
