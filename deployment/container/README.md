# Apple Container 本地联调

本目录存放仓库级 Apple `container` 本地联调脚本，负责统一拉起 `04 网关端`、`05 后台端`、`06 网页端` 与 `09 运维观测端`。

## 脚本说明

- `build_local_images.sh`：构建整栈本地镜像。
- `start_local_stack.sh`：拉起整栈本地容器。
- `verify_system_stack.sh`：验证基础链路、登录、配置闭环与页面入口。
- `verify_database_stack.sh`：验证 TimescaleDB / Redis / InfluxDB 联调。
- `verify_user_scope_stack.sh`：验证 `teacher` / `student` 权限边界。
- `verify_regression_stack.sh`：按顺序串行执行整栈回归。
- `stop_local_stack.sh`：停止本地联调容器与网络。

## 常用命令

```bash
sh deployment/container/build_local_images.sh
sh deployment/gateway/container/prepare_runtime.sh
sh deployment/container/start_local_stack.sh
sh deployment/container/verify_regression_stack.sh
sh deployment/container/stop_local_stack.sh
```

说明：
- 这些脚本约定在仓库根目录执行。
- 网关特有的运行时初始化、MQTT 打点、韧性验证、运维鉴权验证仍保留在 `deployment/gateway/container/`。
- 所有容器共享统一运行时目录 `deployment/runtime/`。
