# 网关端

本目录对应 `04-网关端` 的服务栈与部署资产。

## 目录结构

- `edge_processor/`：Python 3.13 异步应用源码与测试
- `device_simulator/`：独立 Python 3.13 异步 MQTT 设备模拟器源码与测试
- `../deployment/gateway/mosquitto/defaults/`：Broker 默认配置模板，首次启动复制到运行挂载目录
- `../deployment/gateway/influxdb/defaults/`：InfluxDB 默认初始化模板
- `../deployment/gateway/`：Dockerfile、入口脚本、默认模板与网关专项测试脚本

## 路由与链路逻辑

网关当前 HTTP / WebSocket 侧暴露以下路由：

- `GET /healthz`
- `GET /ops/v1/health`
- `GET /ops/v1/health/components`
- `GET /ops/v1/stats`
- `WS /ops/ws`

真正的主链路不在 HTTP，而在 MQTT 与后台 HTTP 批量上报：

1. `edge_processor` 订阅 `telemetry / alert / binding / status`
2. 收到事件后先写入本地 InfluxDB 缓冲
3. 按批次调用后台 `POST /api/v1/ingest/batch`
4. 网关侧生成的 `alert/status` 也会先写入缓冲，再发布回 MQTT
5. 配置更新通过 `gym/{gym_id}/gateway/{gateway_id}/config` 写入本地规则文件并热重载

## macOS 本地测试

Linux 部署仍以 Docker Compose 为主。

在 macOS 上，使用 Apple `container` CLI 按镜像分别构建与运行，而不是直接使用 Compose。例如：

```bash
container build \
  --build-arg PYTHON_BASE=python:3.13-slim \
  -t motion-sense-edge-processor-local \
  -f deployment/gateway/edge_processor/Dockerfile .
```

整栈联调命令见仓库根目录 `deployment/container/README.md`；网关专项脚本说明见 `deployment/gateway/container/README.md`。

## 运行时挂载

Compose 约定以下宿主机挂载目录位于 `deployment/runtime/`：

- `config/`
- `secrets/`
- `certs/`

运行期数据使用 Docker 命名卷保存 Mosquitto 与 InfluxDB 数据。

## 当前进展

- `edge_processor` 已支持 MQTT 事件落地到本地 InfluxDB 后再上传后台
- 后台成功响应后，会在 InfluxDB 中写入投递标记，避免重复补发
- `rules.yaml` 改写与重载检测已实现
- 已支持 P1 规则：`EQ_OVERLOAD`、`CO2_HIGH`、`CO2_CRITICAL`、`PM25_HIGH`、`TEMP_HIGH`
- 已支持 `DEVICE_OFFLINE` 监控，并发布 MQTT `alert` 与 retained `status`
- 已支持后台配置命令轮询、失败回报、重试领取与超时收敛
- 已支持基础设施健康采集并上报后台 `/api/v1/system/health/report`
- 已支持网关自观测接口 `/ops/v1/*` 与 `/ops/ws`
- 在 macOS + Apple `container` 上已验证完整链路：
  `mosquitto -> edge_processor -> InfluxDB 缓冲 -> backend/api_service -> TimescaleDB`
- 在 macOS + Apple `container` 上已验证：
  设备入库、健康汇聚、配置命令闭环、健康汇总视图
- 设备在线/离线检测改为使用网关接收时间，避免设备时钟漂移导致瞬时误判离线
- 已新增独立 `device_simulator` 模块骨架，默认可模拟 10 台器材、10 个手环、10 个环境节点，并通过单 MQTT 连接持续发布随机场景数据

## 当前风险

- Linux 生产环境下，Mosquitto 绑定挂载的密钥 / 证书文件权限初始化仍需进一步加固
- 设备侧仍未提供 ACK 机制，当前“配置成功”仅表示网关已执行本地处理或已转发到局域网 MQTT

## 运行时规则说明

- `/runtime/config/edge_processor/app_settings.yaml`、`rules.yaml`、`logging.yaml` 首次启动自动生成
- `/runtime/config/device_simulator/simulator_settings.yaml` 首次启动自动生成
- `/runtime/config/influxdb/admin_token.txt` 由 InfluxDB 首次启动生成，`edge_processor` 会复用
- 编辑 `rules.yaml` 可热重载
- 编辑 `app_settings.yaml` 需要重启 `edge_processor`
- 编辑 `simulator_settings.yaml` 需要重启 `device_simulator`
- 修改 InfluxDB 保留策略或存储参数需要重启 `influxdb`
