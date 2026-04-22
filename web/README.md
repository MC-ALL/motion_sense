# web

`web/` 存放网页端源码，当前包含一个可运行前端模块 `portal_app/`。

## 目录功能

- 提供业务与运维一体化门户前端。
- 约定网页端部署资产位于仓库根目录 `deployment/web/`。
- 作为远端 Linux 部署时的单端口访问入口。

## 目录结构

- `portal_app/`：React + Vite 单页应用。
- `README.md`：网页端目录入口说明。

## 模块功能

- 提供登录、实时仪表盘、设备管理、训练档案、AI 报告、健康中心等页面。
- 对接 backend 业务 API 与 `ops_observer` 运维 API。
- 通过 Nginx 同源代理规避远端 SSH 转发下的跨域问题。

## 接口约束

- 页面可见性与权限边界必须与后台角色模型一致。
- 运行时地址通过 `runtime_config.js` 注入，不依赖构建期 `.env`。
- 实时仪表盘与 AI 报告页采用“REST 首次加载 + WebSocket 增量 + WebSocket 重连后单次 REST 补同步”，不保留固定低频轮询。
- 业务和运维接口契约以 [design/06-网页端.md](../design/06-网页端.md) 与 [design/07-通讯接口定义.md](../design/07-通讯接口定义.md) 为准。

## 测试流程

```bash
# 从仓库根目录执行
docker run --rm -v "$PWD:/workspace" -w /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"
```

## 部署流程

- 镜像、Nginx 配置与默认运行时配置位于 `deployment/web/`。
- Linux 正式部署由 `deployment/web/compose/docker-compose.yaml` 启动。
- 运行时配置文件生成到 `deployment/runtime/config/web/portal_app/runtime_config.js`。

## 后续改进

- 增加更多页面级回归测试与自动化 UI 验收。
- 补训练时间线、结构化证据视图、更细粒度长任务提示与人工校对流程；AI 流式生成仍作为后续增强项。
- 继续打磨教师/管理员的操作效率与页面引导。
