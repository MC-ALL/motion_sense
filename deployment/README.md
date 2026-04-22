# deployment

`deployment/` 是仓库唯一部署目录，统一存放镜像构建资产、默认配置模板、本地联调脚本、正式 Compose 编排与共享运行时目录约束。

## 目录功能

- 统一管理 backend、gateway、ops_observer、web 的部署资产。
- 提供 Apple `container` 本地联调与 Linux Docker Compose 正式部署入口。
- 约束所有运行时配置、密钥、数据文件统一落在 `deployment/runtime/`。

## 目录结构

- `backend/`：后台镜像、Compose 样例、默认配置模板。
- `gateway/`：Mosquitto、InfluxDB、edge_processor、device_simulator 与网关专项脚本。
- `ops_observer/`：运维聚合服务镜像、Compose 样例与专项验证脚本。
- `web/`：网页端镜像、Nginx 配置与 Compose 样例。
- `container/`：Apple `container` 整栈联调脚本。
- `compose/`：Linux + Docker 正式部署脚本与整栈编排入口。
- `runtime/`：唯一运行时目录。

## 脚本与配置文件

关键入口：
- `compose/docker-compose.yaml`：仓库级正式 Compose 入口，通过 `include` 聚合各模块 Compose。
- `compose/start_stack.sh`：构建、起栈、等待健康、打印基础访问信息。
- `compose/stop_stack.sh`：停栈，可选清理命名卷与运行时目录。
- `compose/verify_*.sh`：Linux 正式部署验收脚本。
- `container/build_local_images.sh`：构建 Apple `container` 本地镜像。
- `container/start_local_stack.sh`：启动本地联调栈。
- `container/stop_local_stack.sh`：停止本地联调栈。
- `runtime/.gitignore`：确保运行时目录默认不入库。

默认配置约束：
- 各模块首启配置必须从对应 `default_*` 模板生成。
- 不在源码目录旁散落 Dockerfile、Compose 或运行时脚本。

## 环境配置要求

- Linux 正式部署：Docker Engine、Docker Compose `2.20.3+`，支持 Compose `include`。
- Apple 本地联调：需安装 Apple `container` CLI。
- 宿主机需具备 `sh`、`curl`、`python3`；部分脚本还依赖 `sed`、`grep`、`nc`、`openssl`。
- 使用外部 AI provider 时，需在 `deployment/runtime/secrets/backend_ai_api_key.txt` 提供 token。

## 基础设施要求

- backend：PostgreSQL/TimescaleDB、Redis
- gateway：Mosquitto、InfluxDB 3 Core
- ops_observer：SQLite 文件存储
- web：Nginx 同源代理
- 共享宿主机目录：`deployment/runtime/config`、`deployment/runtime/secrets`、`deployment/runtime/certs`、`deployment/runtime/data`

## 使用方式

Linux 正式部署：

```bash
docker compose -f deployment/compose/docker-compose.yaml config
sh deployment/compose/start_stack.sh
sh deployment/compose/verify_ops_auth_stack.sh
sh deployment/compose/verify_system_stack.sh
sh deployment/compose/verify_gateway_batch_stack.sh
sh deployment/compose/verify_training_archive_stack.sh
sh deployment/compose/verify_workout_aggregation_stack.sh
sh deployment/compose/verify_ai_stack.sh
sh deployment/compose/verify_database_stack.sh
sh deployment/compose/stop_stack.sh
```

Apple `container` 本地联调：

```bash
sh deployment/container/build_local_images.sh
sh deployment/gateway/container/prepare_runtime.sh
sh deployment/container/start_local_stack.sh
sh deployment/container/verify_regression_stack.sh
sh deployment/container/stop_local_stack.sh
```

## 后续改进

- 增加 MQTT TLS 资产校验脚本与上线手册。
- 继续细化回滚流程、主机初始化检查与生产环境验收卡片。
- 视需要补充更多部署适配器与日志采集方案。
