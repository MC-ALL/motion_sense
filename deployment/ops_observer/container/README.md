# deployment ops_observer container

`deployment/ops_observer/container/` 存放运维聚合模块的 Apple `container` 本地专项验证脚本。

## 目录功能

- 对 `ops_observer` 的基础 REST 聚合接口做快速验证。

## 目录结构

- `verify_ops_observer_api.sh`：检查 `healthz`、`/api/v1/ops/health`、`/api/v1/ops/stats`、`/api/v1/ops/alerts`。

## 脚本用法

```bash
sh deployment/ops_observer/container/verify_ops_observer_api.sh
```

## 环境配置要求

- 依赖本地已启动的 backend 与 `ops_observer` 容器。
- 需要能读取后台 bootstrap admin 凭据或显式提供管理员账号密码。

## 基础设施要求

- `deployment/runtime/config/backend/api_service/bootstrap_admin.txt` 可用。

## 后续改进

- 增加 WebSocket 与异常场景验证。
- 补充与 Linux Compose 正式验收顺序的对应关系说明。
