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
