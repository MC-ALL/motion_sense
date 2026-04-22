# gateway edge_processor

`gateway/edge_processor` 是网关异步处理服务，负责 MQTT 数据接入、规则判定、本地缓冲、后台上报与运维健康输出。

## 目录功能

- `app/api/`：健康与运维接口。
- `app/services/`：MQTT 订阅、InfluxDB 缓冲、批上传、规则引擎、命令通道与健康汇报。
- `app/models/`：领域模型。
- `app/utils/`：topic 解析等工具。
- `tests/`：单元测试与预留的契约/集成测试目录。

## 目录结构

- `app/main.py`：FastAPI 应用与 runner 生命周期。
- `app/services/mqtt_ingest.py`：MQTT 入站订阅与解析。
- `app/services/influx_event_buffer.py`：本地缓冲与补发。
- `app/services/batch_uploader.py`：批量上传后台。
- `app/services/rule_engine.py`：规则匹配与热重载。
- `app/services/backend_client.py`：后台 pending/result REST 交互。
- `app/services/gateway_command_channel.py`：后台命令 WebSocket 连接与 `command_ready` 唤醒。
- `app/services/health_reporter.py`：网关健康快照与 `/ops/ws` 推送。
- `tests/unit/`：配置、MQTT、规则、命令、健康与运行时配置测试。

## 模块功能

- 订阅默认主题：
  - `gym/+/wristband/+/telemetry`
  - `gym/+/wristband/+/binding`
  - `gym/+/equipment/+/telemetry`
  - `gym/+/equipment/+/alert`
  - `gym/+/equipment/+/status`
  - `gym/+/env/+/telemetry`
  - `gym/+/env/+/alert`
  - `gym/+/env/+/status`
  - `gym/+/gateway/+/config`
- 将事件先写入 InfluxDB 3 Core 本地缓冲，再按“最小聚合窗口 + 阈值触发 + 定时兜底回放”策略批量上报后台 `POST /api/v1/ingest/batch`。
- 通过后台命令 WebSocket 接收 `command_ready`，并在长连接异常时回退到 pending 轮询；执行后回报结果。
- 通过规则文件热重载生成本地告警与 retained 状态。
- 对外提供 `GET /healthz`、`GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`、`WS /ops/ws`。

## 接口约束

- HTTP 后台交互路径由 `app/settings.py` 管理，默认前缀为 `http://backend:8000/api/v1`。
- MQTT 主题与消息字段必须对齐 [design/07-通讯接口定义.md](../../design/07-通讯接口定义.md)。
- `ops_auth.enforce_rest` / `ops_auth.enforce_ws` 开启后，运维接口必须携带 token。
- 运行时配置路径固定为 `/runtime/config/edge_processor/app_settings.yaml`，规则与日志模板分别位于 `/runtime/config/edge_processor/rules.yaml`、`logging.yaml`。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall gateway/edge_processor/app
docker run --rm -v "$PWD:/workspace" -w /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

补充目录：
- `tests/contract/`：预留接口契约测试。
- `tests/integration/`：预留端到端联调测试。

## 部署流程

1. 使用 `deployment/gateway/edge_processor/Dockerfile` 构建镜像。
2. 由 `deployment/gateway/edge_processor/entrypoint.sh` 生成默认配置、规则和日志配置。
3. Linux 正式部署通过 `deployment/gateway/compose/docker-compose.yaml` 与 Mosquitto、InfluxDB 一起启动。
4. 回归验证可使用 `deployment/gateway/container/verify_gateway_resilience.sh` 或根级 Compose 验证脚本。

## 后续改进

- MQTT TLS 与证书权限检查需要落到正式手册和自动校验脚本。
- 规则体系仍偏 P0/P1，后续可补充更细粒度阈值与动态配置。
- 契约/集成测试目录需要从“预留”推进到真正可执行的自动化测试。
