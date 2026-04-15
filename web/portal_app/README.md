# web portal_app

06 网页端前端模块，当前已落地业务后台与运维观测端双接入版本。

## 当前能力

- React + TypeScript + Vite 前端骨架
- 左侧导航与页面布局
- 实时仪表盘
- 器材管理
- 环境质量
- 告警管理
- 系统健康中心
- 后台登录、Token 本地持久化、REST Bearer 注入、业务 WS `token` 透传
- 调用 `GET /api/v1/devices`、`GET /api/v1/telemetry/equipment/{id}`、`GET /api/v1/telemetry/env/{id}`、`GET /api/v1/telemetry/env/{id}/aggregate`
- 调用 `GET /api/v1/alerts`、`PATCH /api/v1/alerts/{id}/ack`、`POST /api/v1/alerts/batch-ack`
- 调用 `POST /api/v1/devices/{id}/config`
- 订阅 `WS /api/ws`
- 调用 `GET /api/v1/ops/health`、`GET /api/v1/ops/health/{module_id}`、`GET /api/v1/ops/alerts`、`PATCH /api/v1/ops/alerts/{id}/close`、`GET /api/v1/ops/stats`
- 订阅 `WS /api/ws/ops`
- 运行时配置通过 `runtime_config.js` 注入，不依赖 `.env`

## 本地开发

推荐使用 Apple `container` 运行 Node 容器，不在宿主机安装 `npm`。

示例：

```bash
container run --remove \
  --volume "$PWD:/workspace" \
  --workdir /workspace/web/portal_app \
  node:24-alpine \
  sh -lc "npm config set registry https://registry.npmmirror.com && npm ci && npm run build"
```

说明：

- 当前构建阶段直接使用 `node:24-alpine`
- 仓库已提交 `package-lock.json`，容器内优先使用 `npm ci`
- 已验证 `npm audit --registry=https://registry.npmjs.org` 为 0 漏洞
- 当前运行时配置至少包含：`backend_base_url`、`backend_ws_url`、`ops_base_url`、`ops_ws_url`
