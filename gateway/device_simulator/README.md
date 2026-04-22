# gateway device_simulator

`gateway/device_simulator` 是独立的异步 Python 服务，用于向 Mosquitto 持续发布虚拟器材、手环与环境节点数据。

## 目录功能

- `app/`：模拟器主逻辑、设备画像、随机场景与 MQTT 发送。
- `tests/`：模拟器单元测试。
- `pyproject.toml`：包定义与测试依赖。
- `README.md`：模块说明。

## 目录结构

- `app/device_profiles.py`：设备 ID 与默认场景画像。
- `app/scenario_engine.py`：随机异常、绑定变化与上下线逻辑。
- `app/mqtt_client.py`：MQTT 发布客户端封装。
- `app/runner.py`：分组发送调度。
- `app/settings.py`：运行时配置解析。
- `tests/unit/`：设备画像、runner、配置解析测试。

## 模块功能

- 默认模拟 10 台器材、10 个手环、10 个环境节点。
- 器材、手环、环境各自使用独立发布队列，避免低频节点被高频设备挤压。
- 可发送 `telemetry`、`status`、`binding` 与手环本地 `alert`。
- 可模拟上下线、绑定变化、跌倒、高低心率、低电量、环境异常等场景。

## 接口约束

- MQTT 主题与字段名必须对齐 [design/07-通讯接口定义.md](/home/circuitx/Work/motion_sense/design/07-通讯接口定义.md)。
- 当前兼容后台与网页实现，手环 `current_equipment_id` 使用字符串设备 ID。
- 运行时配置文件固定为 `/runtime/config/device_simulator/simulator_settings.yaml`，首次启动由 `deployment/gateway/device_simulator/defaults/default_simulator_settings.yaml` 生成。

## 测试流程

```bash
container run --remove --volume "$PWD:/workspace" --workdir /workspace/gateway/device_simulator python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 部署流程

1. 使用 `deployment/gateway/device_simulator/Dockerfile` 构建镜像。
2. 由 `deployment/gateway/device_simulator/entrypoint.sh` 生成或读取运行时配置。
3. 根据需要把容器加入本地联调网络或独立测试环境，连接到目标 Mosquitto。

## 后续改进

- 增加更可控的场景脚本，而不是只依赖概率扰动。
- 增加 TLS、认证异常与弱网环境模拟。
- 增加可回放的数据样本集，用于稳定回归测试。
