# deployment ops_observer

`deployment/ops_observer/` 存放运维聚合服务的部署资产与专项验证脚本。

## 目录功能

- 提供 `ops_observer_api_service` 的镜像、默认配置与 Compose 样例。
- 提供运维聚合模块的本地专项验证脚本。

## 目录结构

- `api_service/`：Dockerfile、entrypoint、默认配置模板。
- `compose/docker-compose.yaml`：运维聚合模块 Compose 样例。
- `container/`：本地验证脚本。

## 脚本与配置文件

- `api_service/Dockerfile`：构建 `ops_observer_api_service` 镜像。
- `api_service/entrypoint.sh`：生成运行时配置并启动服务。
- `api_service/defaults/default_app_settings.yaml`：默认配置模板。
- `compose/docker-compose.yaml`：定义 `ops_observer_api_service` 服务。
- `container/verify_ops_observer_api.sh`：验证健康、聚合健康、统计与告警接口。

## 环境配置要求

- Docker Engine 与 Compose。
- 宿主机挂载 `deployment/runtime/config`、`deployment/runtime/secrets`、`deployment/runtime/data`。
- `ops_observer` 需要能够访问 backend 与 gateway 的运维接口。

## 基础设施要求

- SQLite 数据文件目录可写。
- backend JWT 参数、bootstrap admin 与 gateway ops token 可通过共享 runtime 回填。

## 使用方式

```bash
docker compose -f deployment/ops_observer/compose/docker-compose.yaml config
sh deployment/ops_observer/container/verify_ops_observer_api.sh
```

## 后续改进

- 补充运维聚合模块单独起栈与 smoke test 说明。
- 强化阈值与告警策略的运行时配置方式。
- 补充聚合层日志/异常观测与生产化验收说明。
