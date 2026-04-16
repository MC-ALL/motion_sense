# Apple Container 本地测试说明

本目录说明如何在 macOS 上使用 Apple `container` CLI 测试网关栈。
当前脚本已扩展为同时拉起 `04 网关端`、`05 后台端`、`06 网页端` 与 `09 运维观测端`。
`build_local_images.sh` 会先为每个镜像生成最小临时构建上下文，再调用 Apple `container build`，规避直接打包仓库根目录时偶发的归档失败。

## 前置条件

1. 首次启动 Apple container 系统服务：

```bash
container system start
```

2. 创建运行时目录：

```bash
mkdir -p gateway/deployment/compose/runtime/config
mkdir -p gateway/deployment/compose/runtime/secrets
mkdir -p gateway/deployment/compose/runtime/certs
```

3. 启动 Mosquitto 前，准备 `gateway/deployment/compose/runtime/secrets/mosquitto.passwd`
   或在本地 Mosquitto 镜像构建完成后执行 `gateway/deployment/container/prepare_runtime.sh`

4. `mosquitto` 首次启动会从镜像模板生成 `runtime/config/mosquitto/acl.conf`
   如果之后修改了 `MOSQUITTO_USER`，需要在重启前删除或更新该 ACL 文件

## 使用官方镜像构建

当前在 macOS 上直接使用 Docker Hub 官方镜像标签。

统一构建本地镜像：

```bash
sh gateway/deployment/container/build_local_images.sh
```

该脚本会统一构建：
- `motion-sense-edge-processor-local`
- `motion-sense-mosquitto-local`
- `motion-sense-influxdb-local`
- `motion-sense-backend-api-local`
- `motion-sense-timescaledb-local`
- `motion-sense-ops-observer-local`
- `motion-sense-mock-backend-local`
- `motion-sense-web-portal-local`

## 单服务运行

例如仅运行 `edge_processor`：

```bash
container run \
  --name edge-test \
  --remove \
  -d \
  -p 18080:8080 \
  --mount type=bind,source=$PWD/gateway/deployment/compose/runtime/config,target=/runtime/config \
  motion-sense-edge-processor-local
```

查看日志：

```bash
container logs edge-test
```

停止服务：

```bash
container stop edge-test
```

## 启动完整本地栈

在仓库根目录执行：

```bash
sh gateway/deployment/container/build_local_images.sh
sh gateway/deployment/container/prepare_runtime.sh
sh gateway/deployment/container/start_local_stack.sh
```

执行完整联调验证：

```bash
sh gateway/deployment/container/verify_system_stack.sh
```

执行业务账号权限隔离验证：

```bash
sh gateway/deployment/container/verify_user_scope_stack.sh
```

执行数据库联调验证：

```bash
sh gateway/deployment/container/verify_database_stack.sh
```

执行整栈串行回归验证：

```bash
sh gateway/deployment/container/verify_regression_stack.sh
```

脚本默认读取 `backend/deployment/compose/runtime/config/backend/api_service/bootstrap_admin.txt` 中首次生成的后台管理员账号；如需覆盖，可在执行前传入：

```bash
BACKEND_ADMIN_USERNAME=admin BACKEND_ADMIN_PASSWORD='<your-password>' \
  sh gateway/deployment/container/verify_system_stack.sh
```

执行网关韧性回归验证：

```bash
sh gateway/deployment/container/verify_gateway_resilience.sh
```

运行网关单元测试：

```bash
container run --remove \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --entrypoint sh motion-sense-edge-processor-local \
  -lc "pip install --no-cache-dir pytest==8.3.5 >/tmp/pip.log 2>&1 && cd /workspace/gateway/edge_processor && PYTHONPATH=/workspace/gateway/edge_processor pytest tests/unit -q"
```

停止本地栈：

```bash
sh gateway/deployment/container/stop_local_stack.sh
```

## 说明

- Apple `container` CLI 支持镜像构建、容器运行、卷、网络、绑定挂载、端口映射和环境文件
- 当前工具链不提供 Compose 兼容的编排层，因此多服务本地联调需要逐个服务启动，或使用仓库自带辅助脚本
- 当前本地镜像构建不再直接使用仓库根目录作为上下文，而是按模块裁剪最小临时上下文，以减少归档失败概率
- 当前本地栈默认启动真实后台 API 镜像 `motion-sense-backend-api-local`，并联动 `timescaledb` 与 `redis`
- 当前本地栈还会启动 `motion-sense-ops-observer-local`
- 当前本地栈还会启动 `motion-sense-web-portal-local`
- `verify_system_stack.sh` 会先调用后台 `POST /api/v1/auth/login` 获取 JWT，再验证受保护业务接口与免鉴权内网接口
- `verify_system_stack.sh` 目标验证项包括：设备入库、健康汇聚、配置命令闭环、后台健康汇总视图、`ops_observer` 健康汇总与详情视图，以及网页端入口与运行时配置
- `verify_database_stack.sh` 目标验证项包括：refresh session 持久化、TimescaleDB / PostgreSQL 时序与结构化写库、Redis 连通性、Influx 缓冲写入与补发确认
- `verify_user_scope_stack.sh` 会创建临时 `teacher` / `student` 账号，验证 `gym_ids` / `device_ids` 归属下的设备、遥测、告警、绑定历史与告警确认边界；脚本结束后会自动删除临时账号
- `verify_gateway_resilience.sh` 目标验证项包括：Mosquitto 异常重启后的网关自动重连，以及 `rules.yaml` 热重载后的 P1 规则生效
- `verify_regression_stack.sh` 会按 `verify_system_stack.sh -> verify_database_stack.sh -> verify_user_scope_stack.sh -> verify_gateway_resilience.sh` 顺序串行执行，适合作为本地整栈固定回归入口
- 为了覆盖本地 Broker 重连场景，`edge_processor` 在 Apple `container` 联调中会连接宿主机网关地址 `192.168.65.1:1883`，而不是直接连接 `mosquitto` 容器瞬时 IP
- `start_local_stack.sh` 会解析后台与 InfluxDB 容器 IP，并通过环境变量注入 `edge_processor`；MQTT 入口固定使用宿主机网关地址
- `start_local_stack.sh` 也会解析 `edge_processor` 与 `backend` 容器 IP，并把后台首次生成的管理员账号注入到 `ops_observer`，用于访问受保护的后台 `/ops/v1/*` 与 `/ops/ws`
- `start_local_stack.sh` 也会注入 `MOSQUITTO_USER` / `MOSQUITTO_PASSWORD`
- 首次启动后，生成的配置文件会出现在挂载的 `runtime/config/...` 目录中
- `influxdb` 首次启动还会生成 `runtime/config/influxdb/admin_token.txt`，供 `edge_processor` 通过共享挂载读取
- 当前机器上已验证链路：`mosquitto -> edge_processor -> InfluxDB 缓冲 -> POST /api/v1/ingest/batch -> backend/api_service -> TimescaleDB`
- 当前机器上已验证：`edge_processor` 能写入 InfluxDB 缓冲、回读待补发事件，并在写入 `edge_delivery_log` 后不再重复补发
- 已知风险：Apple `container` 下绑定挂载的 `acl.conf` 保留宿主机所有者和权限，Mosquitto 2.1.2 会给出告警。当前功能可用，但 Linux 生产部署仍需显式权限初始化
