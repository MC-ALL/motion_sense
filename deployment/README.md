# 部署目录总览

本目录是仓库唯一部署入口。

## 结构约定

- `deployment/runtime/`：全仓库唯一运行时目录。
- `deployment/container/`：Apple `container` 整栈联调脚本。
- `deployment/compose/`：Linux + Docker 整栈编排入口。
- `deployment/gateway/`：04 网关端部署资产。
- `deployment/backend/`：05 后台端部署资产。
- `deployment/ops_observer/`：09 运维观测端部署资产。
- `deployment/web/`：06 网页端部署资产。

## 分层原则

- `deployment/<module>/compose/`：模块最小可运行 Compose 样例。
- `deployment/<module>/container/`：模块专项联调或验证脚本。
- `deployment/compose/`：整栈 Compose 入口。
- `deployment/container/`：整栈 Apple `container` 入口。
- 模块级 Compose 服务名统一使用 `module_component` 风格，避免整栈组合时冲突。

## 运行时约束

- 所有容器共享 `deployment/runtime/`。
- 首次运行生成的配置必须来自 `default_*` 模板。
- `deployment/runtime/` 下不提交口令、证书、token 与其他敏感数据。
- Linux 正式部署当前支持单条 `docker compose -f deployment/compose/docker-compose.yaml up -d --build` 自举启动。
- Linux 正式部署推荐直接执行 `deployment/compose/start_stack.sh`，统一完成起栈、健康等待与基础信息输出。
- Linux 正式部署首启后的后台 bootstrap admin 与网关 ops token，可通过 `deployment/compose/print_bootstrap_credentials.sh` 从运行中的容器读取。
- Linux 正式部署的运维鉴权验收与停栈清理脚本位于 `deployment/compose/verify_ops_auth_stack.sh`、`deployment/compose/stop_stack.sh`。
- Linux 正式部署的整栈业务回归与数据库落盘回归脚本位于 `deployment/compose/verify_system_stack.sh`、`deployment/compose/verify_database_stack.sh`。
- Linux 正式部署的推荐上线前验收顺序与异常排障顺序，统一维护在 `deployment/compose/README.md`。
- Linux 正式部署的短版现场操作卡片位于 `deployment/compose/RUNBOOK.md`。
- Linux 正式部署的主机初始化清单位于 `deployment/compose/SERVER_INIT_CHECKLIST.md`。
- Linux 正式部署的环境变量 / 端口 / 证书对照表位于 `deployment/compose/PRODUCTION_REFERENCE.md`。
