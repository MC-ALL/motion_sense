# Docker Compose 正式部署目录

本目录预留给 Linux + Docker 的正式部署编排。

- `docker-compose.yaml`：仓库级整栈 Compose 入口。
- 根文件使用 Compose `include` 聚合各模块 Compose，要求 Docker Compose `2.20.3+`。
- `../runtime/`：宿主机挂载的统一运行时目录，首次启动后由各容器自行生成配置、口令、token 与数据文件。

正式部署入口：

```bash
sh deployment/compose/start_stack.sh
```

如需更短的现场操作版步骤，可直接查看 `deployment/compose/RUNBOOK.md`。
如需主机初始化清单，可查看 `deployment/compose/SERVER_INIT_CHECKLIST.md`。
如需生产环境变量、端口与证书对照表，可查看 `deployment/compose/PRODUCTION_REFERENCE.md`。

如需手动分步执行，底层命令等价为：

```bash
docker compose -f deployment/compose/docker-compose.yaml build
docker compose -f deployment/compose/docker-compose.yaml up -d
```

`start_stack.sh` 会在起栈后自动：
- 等待 `runtime_init` 成功完成
- 等待整栈关键服务进入 `healthy`
- 打印 `docker compose ps`
- 打印后台 bootstrap admin、网关 ops token 与默认访问入口
- 打印 backend / gateway / ops / web 健康状态，以及 `ops_observer` 聚合到的模块在线摘要

首次启动后，如需在宿主机启用 `userns-remap` 场景下读取后台首登账号与网关 ops token，可执行：

```bash
sh deployment/compose/print_bootstrap_credentials.sh
```

如需一键验证后台登录、gateway ops token、`ops_observer` 管理员 JWT，以及两侧运维 WebSocket 鉴权，可执行：

```bash
sh deployment/compose/verify_ops_auth_stack.sh
```

如需验证整栈业务链路与网页/运维聚合视图，可执行：

```bash
sh deployment/compose/verify_system_stack.sh
```

如需验证学生训练档案聚合、管理员页内绑定维护与学生自助查看链路，可执行：

```bash
sh deployment/compose/verify_training_archive_stack.sh
```

如需验证 TimescaleDB、Redis、Influx 的落盘与补发链路，可执行：

```bash
sh deployment/compose/verify_database_stack.sh
```

如需停止正式栈，可执行：

```bash
sh deployment/compose/stop_stack.sh
```

如需同时清理命名卷或 `deployment/runtime/` 下的首启产物，可显式开启：

```bash
PURGE_VOLUMES=true sh deployment/compose/stop_stack.sh
PURGE_RUNTIME=true sh deployment/compose/stop_stack.sh
```

当前正式部署基线：
- 根 Compose 支持单条命令启动，不依赖额外 `prepare` 脚本。
- 根 Compose 会先运行一次性 `runtime_init`，自动创建共享 runtime 目录并初始化 Linux bind mount 所需的基础权限。
- `backend_api_service` 首启自动生成 bootstrap admin 与 JWT secrets。
- `gateway_mosquitto` 首启自动生成 `mosquitto.passwd`。
- `gateway_edge_processor` 首启自动生成 `edge_processor_ops_token.txt`。
- `ops_observer_api_service` 默认启用管理员 JWT 鉴权，并会从共享 runtime 自动读取后台 JWT 校验参数、后台 bootstrap admin 凭据与网关 ops token。
- `web_portal_app` 默认会在每次容器启动时按当前环境变量重渲染正式环境 `runtime_config.js`；如需保留宿主机上已有文件，可设置 `WEB_PORTAL_RUNTIME_CONFIG_MODE=preserve`。
- `web_portal_app` 默认通过 Nginx 提供单端口同源入口，统一代理 backend / `ops_observer` 的 REST 与 WebSocket。

约束：
- `deployment/runtime/` 下不提交口令、证书、token 等敏感数据。
- 配置模板统一来自各模块 `deployment/*/defaults/default_*`。
- 允许热重载的配置由各模块文档单独说明；其余修改后需要重启对应容器。
- Linux 正式部署下，运行时目录基础权限已由 `runtime_init` 自动处理；如果启用 MQTT TLS，仍需在宿主机侧补齐证书文件投放与权限校验。

上线验收清单：
1. 执行 `docker compose -f deployment/compose/docker-compose.yaml ps`，确认 `backend_api_service`、`gateway_mosquitto`、`gateway_influxdb`、`gateway_edge_processor`、`ops_observer_api_service`、`web_portal_app` 均为 `healthy`。
2. 执行 `sh deployment/compose/print_bootstrap_credentials.sh`，记录后台 bootstrap admin 和网关 ops token。
3. 执行 `sh deployment/compose/verify_ops_auth_stack.sh`，确认后台登录、gateway ops token、`ops_observer` 管理员 JWT，以及 gateway / `ops_observer` 的运维 WebSocket 鉴权均通过。
4. 执行 `sh deployment/compose/verify_system_stack.sh`，确认设备入库、健康汇聚、配置命令闭环、`ops_observer` 聚合视图与网页运行时配置均通过。
5. 执行 `sh deployment/compose/verify_training_archive_stack.sh`，确认学生训练档案聚合、管理员绑定/解绑与学生自助查看链路均通过。
6. 执行 `sh deployment/compose/verify_database_stack.sh`，确认 refresh session、TimescaleDB、Redis、Influx 缓冲与补发链路均通过。
7. 打开 `http://127.0.0.1:8080/`，使用 bootstrap admin 登录网页端。
8. 检查网页“健康中心”和“训练档案”，确认 backend 与 gateway 显示 `healthy`，且训练档案页可正常展示绑定与训练摘要。
9. 检查 `deployment/runtime/`，确认运行时文件仅落在该目录，包括 `config/backend/api_service/bootstrap_admin.txt`、`config/influxdb/admin_token.txt`、`config/web/portal_app/runtime_config.js`、`secrets/edge_processor_ops_token.txt`、`secrets/mosquitto.passwd`。
10. 若启用 MQTT TLS，再补充检查 `deployment/runtime/certs/` 中的 `server.crt`、`server.key`、`ca.crt` 已正确投放且权限符合预期。

推荐上线前验收顺序：
1. 执行 `docker compose -f deployment/compose/docker-compose.yaml config`，先确认 Compose `include`、相对路径与变量解析正常。
2. 执行 `sh deployment/compose/start_stack.sh`，统一完成镜像构建、起栈、健康等待、基础访问入口打印与在线摘要输出。
3. 执行 `sh deployment/compose/print_bootstrap_credentials.sh`，记录后台 bootstrap admin、网关 ops token，并确认 `deployment/runtime/` 中已生成首启文件。
4. 执行 `sh deployment/compose/verify_ops_auth_stack.sh`，优先验证后台登录、网关 ops token、`ops_observer` 管理员 JWT 与两侧运维 WebSocket 鉴权。
5. 执行 `sh deployment/compose/verify_system_stack.sh`，验证设备入库、健康聚合、配置命令闭环、网页入口与运维聚合视图。
6. 执行 `sh deployment/compose/verify_training_archive_stack.sh`，验证学生训练档案聚合、页内绑定维护与学生自助查看链路。
7. 执行 `sh deployment/compose/verify_database_stack.sh`，验证 refresh session、TimescaleDB、Redis、Influx 的关键落盘与补发链路。
8. 浏览器打开 `http://127.0.0.1:8080/`，使用 bootstrap admin 登录网页端，手工确认“健康中心”“训练档案”等关键页面展示正常。
9. 若启用 MQTT TLS，再补充检查 `deployment/runtime/certs/` 证书投放、属主、权限与 broker 握手结果。

推荐异常排障顺序：
1. 先执行 `docker compose -f deployment/compose/docker-compose.yaml ps`，确认是否为单点服务未就绪，避免直接重跑整栈。
2. 若卡在首启阶段，优先检查 `runtime_init`：执行 `docker compose -f deployment/compose/docker-compose.yaml logs runtime_init`，确认共享 runtime 目录、属主与基础权限初始化是否成功。
3. 若 `backend_api_service`、`gateway_edge_processor`、`ops_observer_api_service`、`web_portal_app` 未进入 `healthy`，分别执行 `docker compose -f deployment/compose/docker-compose.yaml logs --tail=120 <service>`，按依赖顺序从数据库 / 中间件到上层应用排查。
4. 若表现为账号、token 或运维接口访问异常，先执行 `sh deployment/compose/print_bootstrap_credentials.sh` 与 `sh deployment/compose/verify_ops_auth_stack.sh`，确认 bootstrap admin、JWT secrets、网关 ops token 与 `ops_observer` 上游登录链路。
5. 若表现为网页空白、设备链路不通或运维聚合不完整，再执行 `sh deployment/compose/verify_system_stack.sh`，优先定位是后端业务链路、网关上报链路还是网页运行时配置问题。
6. 若表现为训练档案、学生绑定或训练会话摘要异常，再执行 `sh deployment/compose/verify_training_archive_stack.sh`，优先定位是后台聚合、绑定维护还是网页路由链路问题。
7. 若表现为历史数据、刷新会话或边缘缓冲异常，再执行 `sh deployment/compose/verify_database_stack.sh`，确认 TimescaleDB、Redis、Influx 与补发路径是否正常。
8. 若问题已无法通过增量排障恢复，可执行 `sh deployment/compose/stop_stack.sh` 后重新运行 `sh deployment/compose/start_stack.sh`；仅在明确需要重置首启产物时，才额外使用 `PURGE_VOLUMES=true` 或 `PURGE_RUNTIME=true`。
9. 若启用 MQTT TLS，最后单独检查 `deployment/runtime/certs/` 文件、Mosquitto 日志与客户端握手结果；TLS 问题通常不应与业务 API 问题混排。
