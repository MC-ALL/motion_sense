# web portal_app

`web/portal_app` 是业务与运维一体化门户前端，基于 React、TypeScript、Vite 和 Ant Design 实现。

## 目录功能

- `src/app/`：应用入口、路由与布局。
- `src/pages/`：页面级功能。
- `src/api/`：backend 与 `ops_observer` API 客户端。
- `src/store/`：认证、业务实时流与运维状态存储。
- `src/components/`：页面复用组件。
- `src/config/`：运行时配置解析。

## 目录结构

- `src/app/router.tsx`：路由、导航与角色可见性。
- `src/pages/`：
  - `login_page.tsx`
  - `realtime_dashboard_page.tsx`
  - `equipment_page.tsx`
  - `wristband_page.tsx`
  - `env_quality_page.tsx`
  - `alerts_page.tsx`
  - `training_archive_page.tsx`
  - `ai_reports_page.tsx`
  - `device_registry_page.tsx`
  - `user_management_page.tsx`
  - `profile_page.tsx`
  - `health_center_page.tsx`
- `src/api/backend_client.ts`：业务接口封装。
- `src/api/ops_client.ts`：运维聚合接口封装。
- `src/config/runtime_config.ts`：读取 `window.__motion_sense_runtime__`。

## 模块功能

- 登录后提供统一侧栏导航。
- 业务页面：实时仪表盘、器材/手环/环境、告警管理、训练档案、AI 报告。
- 管理页面：设备管理、用户管理。
- 运维页面：系统健康中心。
- 角色边界：
  - `student` 看不到“告警管理”“设备管理”“用户管理”“系统健康中心”
  - `teacher` 看不到“设备管理”“用户管理”“系统健康中心”
  - `admin` 可访问全部页面
- 使用 backend JWT 访问业务 API，并通过同一 token 访问 `ops_observer`。

## 接口约束

- 业务接口：`/api/v1/*` 与 `WS /api/ws`
- 运维接口：`/api/v1/ops/*` 与 `WS /api/ws/ops`
- 默认部署下通过 Nginx 单端口同源代理访问，不直接把浏览器指向多个后端端口。
- 运行时配置包含：`app_name`、`backend_base_url`、`backend_ws_url`、`ops_base_url`、`ops_ws_url`、`refresh_interval_ms`。
- 页面说明、文案与权限边界应与 [design/06-网页端.md](/home/circuitx/Work/motion_sense/design/06-网页端.md) 一致。

## 测试流程

```bash
# 从仓库根目录执行
docker run --rm -v "$PWD:/workspace" -w /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"
```

当前构建检查：
- TypeScript 类型检查 `tsc --noEmit`
- Vite 生产构建 `vite build`

## 部署流程

1. 使用 `deployment/web/portal_app/Dockerfile` 构建镜像。
2. `deployment/web/portal_app/entrypoint.sh` 在容器启动时生成或保留 `runtime_config.js`。
3. `deployment/web/portal_app/nginx.conf` 提供静态资源服务与 backend/ops 同源代理。
4. Linux 正式部署由 `deployment/web/compose/docker-compose.yaml` 启动。

## 后续改进

- 增加页面级自动化回归测试。
- 补齐 AI 流式输出、长任务提示与验收流程组件。
- 继续优化训练档案、设备管理和健康中心的操作效率。
