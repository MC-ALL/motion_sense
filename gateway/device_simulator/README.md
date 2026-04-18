# 设备模拟器

这是网关侧的独立异步 Python 3.13 服务，用于向本地 Mosquitto 批量发送虚拟设备 MQTT 数据，便于验证 `04-网关端` 与 `05-后台端` 联调链路。

## 当前能力

- 单镜像、单进程、多 MQTT client 分组发布
- 发布路径按 `equipment / wristband / env` 拆成独立 client 与独立发送队列，避免低频环境节点被高频器材/手环流量饿死
- 默认模拟：
  - 10 台器材 `eq-001` ~ `eq-010`
  - 10 个手环 `wb-001` ~ `wb-010`
  - 10 个环境节点 `env-001` ~ `env-010`
- 默认模拟频率为联调友好值：
  - 器材 `1000 ms`
  - 手环 `500 ms`
  - 环境 `5000 ms`
- 支持发送：
  - `telemetry`
  - `status`
  - `binding`
  - 手环本地 P0 `alert`
- 支持随机场景：
  - 上下线
  - 器材活跃/空闲切换
  - 手环绑定/解绑
  - 高心率、低心率、跌倒、低电量
  - 环境 CO2 / PM2.5 / 温度异常

## 运行时配置

- 首次启动自动生成：`/runtime/config/device_simulator/simulator_settings.yaml`
- 默认模板来源：`deployment/gateway/device_simulator/defaults/default_simulator_settings.yaml`
- 修改配置后需要重启容器
- 当前通过 `mqtt.client_id` 自动派生三个连接标识：
  - `device-simulator-equipment`
  - `device-simulator-wristband`
  - `device-simulator-env`
- `mqtt.publish_queue_size` 控制每个设备组自己的发送队列容量

## 兼容说明

- MQTT 主题与字段名优先对齐 `docs/07-通讯接口定义.md`
- 为兼容当前后台与网页端实现，手环 `current_equipment_id` 使用字符串设备 ID，例如 `eq-001`
