# deployment container

`deployment/container/` 存放 Apple `container` 本地整栈联调脚本。

## 目录功能

- 构建本地联调镜像。
- 拉起 backend、gateway、ops_observer、web 的本地容器栈。
- 提供数据库、权限与基础链路回归脚本。

## 目录结构

- `build_local_images.sh`：构建本地镜像。
- `start_local_stack.sh`：启动本地整栈容器。
- `stop_local_stack.sh`：停止容器与网络。
- `verify_system_stack.sh`：验证基础业务链路与网页入口。
- `verify_database_stack.sh`：验证 TimescaleDB、Redis、InfluxDB 链路。
- `verify_user_scope_stack.sh`：验证教师/学生权限边界。
- `verify_regression_stack.sh`：串行执行基础链路、数据库、权限，以及 `deployment/gateway/container/verify_gateway_resilience.sh` 网关韧性回归。

## 脚本用法

```bash
sh deployment/container/build_local_images.sh
sh deployment/gateway/container/prepare_runtime.sh
sh deployment/container/start_local_stack.sh
sh deployment/container/verify_regression_stack.sh
sh deployment/container/stop_local_stack.sh
```

## 环境配置要求

- macOS 或支持 Apple `container` CLI 的环境。
- 需要本地可用的 `container` 命令。
- 这些脚本约定在仓库根目录执行。

## 基础设施要求

- 所有容器共享 `deployment/runtime/`。
- 网关专项脚本仍位于 `deployment/gateway/container/`，其中 `prepare_runtime.sh` 用于预生成网关运行时目录，`verify_gateway_resilience.sh` 用于 Broker 重连、缓冲补发与规则热重载回归。

## 后续改进

- 补充更多本地专项回归组合脚本。
- 继续降低宿主机环境差异带来的联调问题。
