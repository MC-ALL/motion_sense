# deployment compose

`deployment/compose/` 是 Linux + Docker 正式部署入口，负责整栈构建、起栈、验收、停栈与运行时操作辅助。

## 目录功能

- 提供仓库级 Compose 入口。
- 提供整栈起停、凭据打印、AI 切换、AI token 写入与一组正式验收脚本。
- 维护生产环境短版操作卡、初始化清单与参考对照表。

## 目录结构

- `docker-compose.yaml`：仓库级 Compose 根文件，通过 `include` 聚合模块 Compose。
- `start_stack.sh`：构建、起栈、等待健康、打印运行时摘要。
- `stop_stack.sh`：停栈，可选清理命名卷或 `deployment/runtime/`。
- `print_bootstrap_credentials.sh`：打印后台 bootstrap admin 与网关 ops token。
- `write_backend_ai_api_key.sh`：安全写入 AI provider token。
- `switch_backend_ai_model.sh`：切换 `reasoner|chat` 模型档位并重启后台。
- `verify_ops_auth_stack.sh`、`verify_system_stack.sh`、`verify_training_archive_stack.sh`、`verify_workout_aggregation_stack.sh`、`verify_ai_stack.sh`、`verify_database_stack.sh`：正式验收脚本。
- `RUNBOOK.md`、`SERVER_INIT_CHECKLIST.md`、`PRODUCTION_REFERENCE.md`：现场操作与初始化说明。

## 脚本用法

推荐顺序：

```bash
docker compose -f deployment/compose/docker-compose.yaml config
sh deployment/compose/start_stack.sh
sh deployment/compose/verify_ops_auth_stack.sh
sh deployment/compose/verify_system_stack.sh
sh deployment/compose/verify_training_archive_stack.sh
sh deployment/compose/verify_workout_aggregation_stack.sh
sh deployment/compose/verify_ai_stack.sh
sh deployment/compose/verify_database_stack.sh
sh deployment/compose/stop_stack.sh
```

辅助脚本：

```bash
sh deployment/compose/print_bootstrap_credentials.sh
sh deployment/compose/write_backend_ai_api_key.sh
sh deployment/compose/switch_backend_ai_model.sh reasoner
```

## 环境配置要求

- Docker Engine 与 Docker Compose `2.20.3+`。
- 宿主机需支持 Compose `include`。
- 需要 `sh`、`curl`、`python3`、`sed`、`grep`、`openssl` 等常用工具。
- 远端 Linux 场景建议通过单端口转发访问 `web_portal_app:8080`。

## 基础设施要求

- backend：TimescaleDB、Redis
- gateway：Mosquitto、InfluxDB 3 Core
- ops_observer：SQLite 文件持久化
- web：Nginx 同源代理
- 宿主机共享目录：`deployment/runtime/config`、`deployment/runtime/secrets`、`deployment/runtime/certs`、`deployment/runtime/data`

## 运行时约束

- `runtime_init` 会先创建共享目录并初始化基础权限。
- 首次启动后，后台 bootstrap admin、网关 ops token、web 运行时配置等都落在 `deployment/runtime/`。
- 敏感信息不提交入库。
- 启用 MQTT TLS 时，需要宿主机侧额外准备证书与权限。

## 后续改进

- 增加 MQTT TLS 自动检查脚本。
- 继续细化上线、回滚和故障排查手册。
- 视生产环境需要补充日志、指标与备份脚本。
