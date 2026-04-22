# gateway

`gateway/` 存放网关侧代码，包含边缘处理服务 `edge_processor` 与联调用设备模拟器 `device_simulator`。

## 目录功能

- 承载 MQTT 数据接入、规则处理、本地缓冲与后台上报代码。
- 提供设备模拟器，便于在没有真实设备时持续打点。
- 约定网关部署资产位于仓库根目录 `deployment/gateway/`。

## 目录结构

- `edge_processor/`：网关异步处理服务。
- `device_simulator/`：MQTT 模拟器。
- `README.md`：网关目录入口说明。

## 模块功能

- `edge_processor`：订阅设备 MQTT、写入 InfluxDB 本地缓冲、按聚合窗口/阈值策略批量上报后台、通过命令 WebSocket + pending 兜底执行配置命令、输出健康快照。
- `device_simulator`：批量模拟器材、手环、环境节点的遥测、状态、绑定与异常场景。

## 接口约束

- MQTT topic、payload 字段、后台命令通道路径以 [design/07-通讯接口定义.md](/home/circuitx/Work/motion_sense/design/07-通讯接口定义.md) 为准。
- `edge_processor` 对外只开放健康与运维接口；业务侧不直接暴露设备管理 REST。
- 部署与镜像构建统一走 `deployment/gateway/`，不要在源码目录下新增独立部署脚本。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall gateway/edge_processor/app
docker run --rm -v "$PWD:/workspace" -w /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
docker run --rm -v "$PWD:/workspace" -w /workspace/gateway/device_simulator python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 部署流程

- 镜像、默认配置、Broker、InfluxDB 与专项脚本统一位于 `deployment/gateway/`。
- Linux 正式部署由 `deployment/gateway/compose/docker-compose.yaml` 负责网关相关服务。
- Apple `container` 本地联调通过 `deployment/container/` 与 `deployment/gateway/container/` 的组合脚本完成。

## 后续改进

- MQTT TLS 与证书权限检查仍需收尾。
- 设备 ACK 机制尚未落地，配置闭环仍停留在“网关已执行/已转发”。
- 真实设备接入前仍应补充更多契约测试与端到端回归。
