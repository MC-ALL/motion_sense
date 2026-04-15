# Apple Container 本地测试说明

本目录说明如何在 macOS 上使用 Apple `container` CLI 测试网关栈。
当前脚本已扩展为同时拉起 `04 网关端`、`05 后台端` 与 `09 运维观测端`。

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

## 使用镜像源构建

当前在 macOS 上已验证可用的镜像源基线为 `dockerproxy.net`，镜像引用中不要带 `https://` 前缀。

构建 `edge_processor`：

```bash
container build \
  --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t motion-sense-edge-processor-local \
  -f gateway/deployment/edge_processor/Dockerfile .
```

构建 `mosquitto`：

```bash
container build \
  --build-arg MOSQUITTO_BASE=dockerproxy.net/library/eclipse-mosquitto:2.1.2-alpine \
  -t motion-sense-mosquitto-local \
  -f gateway/deployment/mosquitto/Dockerfile .
```

构建 `influxdb`：

```bash
container build \
  --build-arg INFLUXDB_BASE=dockerproxy.net/library/influxdb:3.8.0-core \
  -t motion-sense-influxdb-local \
  -f gateway/deployment/influxdb/Dockerfile .
```

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
- 当前本地栈默认启动真实后台 API 镜像 `motion-sense-backend-api-local`，并联动 `timescaledb` 与 `redis`
- 当前本地栈还会启动 `motion-sense-ops-observer-local`
- `verify_system_stack.sh` 目标验证项包括：设备入库、健康汇聚、配置命令闭环、后台健康汇总视图、`ops_observer` 健康汇总与详情视图
- `start_local_stack.sh` 会解析后台与 Broker 容器 IP，并通过环境变量注入 `edge_processor`
- `start_local_stack.sh` 也会解析 `edge_processor` 与 `backend` 容器 IP，并注入到 `ops_observer`
- `start_local_stack.sh` 也会注入 `MOSQUITTO_USER` / `MOSQUITTO_PASSWORD`
- 首次启动后，生成的配置文件会出现在挂载的 `runtime/config/...` 目录中
- `influxdb` 首次启动还会生成 `runtime/config/influxdb/admin_token.txt`，供 `edge_processor` 通过共享挂载读取
- 当前机器上已验证链路：`mosquitto -> edge_processor -> InfluxDB 缓冲 -> POST /api/v1/ingest/batch -> backend/api_service -> TimescaleDB`
- 当前机器上已验证：`edge_processor` 能写入 InfluxDB 缓冲、回读待补发事件，并在写入 `edge_delivery_log` 后不再重复补发
- 已知风险：Apple `container` 下绑定挂载的 `acl.conf` 保留宿主机所有者和权限，Mosquitto 2.1.2 会给出告警。当前功能可用，但 Linux 生产部署仍需显式权限初始化
