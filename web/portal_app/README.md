# web portal_app

06 网页端前端模块，当前已落地系统健康中心基础页面，直接对接 `ops_observer`。

## 当前能力

- React + TypeScript + Vite 前端骨架
- 左侧导航与页面布局
- 系统健康中心页面
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
