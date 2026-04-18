# 网页端部署说明

网页端镜像构建资产位于 `deployment/web/portal_app/`。

约定：
- 仓库级正式编排统一放在 `deployment/compose/`
- 模块级 Compose 样例位于 `deployment/web/compose/docker-compose.yaml`
- 统一运行时目录位于 `deployment/runtime/`
- `deployment/runtime/config/web/portal_app/runtime_config.js` 在本地 Apple `container` 联调时由 `deployment/container/start_local_stack.sh` 生成
- Linux 正式部署时，`web_portal_app` 容器会在首次启动时按环境变量自动生成 `runtime_config.js`
