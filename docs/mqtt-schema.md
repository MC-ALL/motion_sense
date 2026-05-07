# MQTT 字段规范

## 版本说明

| 项目 | 内容 |
|---|---|
| 版本 | `v1.0.0-rc2` |
| 作者 | `CircuitX` |
| 日期 | `2026/05/07` |
| 状态 | 发布候选版 |

## 修改历史

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| `v1.0.0-rc2` | `2026/05/07` | `CircuitX` | 明确网关生成告警 / 状态事件使用 MQTT 兼容 Payload 写入本地可靠投递队列，不要求真实发布到 MQTT Broker；移除 `published_by` 回环标记语义 |
| `v1.0.0-rc1` | `2026/04/27` | `CircuitX` | 首个发布候选版；定义通用字段、状态消息、告警消息、`equipment`、`wristband`、`env` 与设备 `config` 字段 |

## 文档说明

本文定义运动感知系统的 MQTT 字段规范，覆盖通用字段、状态消息、告警消息、`equipment`、`wristband`、`env` 与设备 `config` 字段。该版本作为 `v1.0.0` 发布前的候选契约，用于后续设备模拟器、网关、后台入库与前端展示的实现对齐。

本文各设备 Payload 表只列 MQTT 业务字段，不列网关入站预处理字段。网关本地生成的告警 / 状态事件可复用本文定义的 MQTT 兼容 Payload 形状写入网关本地可靠投递队列，但不代表这些事件一定真实发布到 MQTT Broker。

## 1. 通用约定

### 1.1 Topic

Topic 格式：

```text
gym/{gym_id}/{device_type}/{device_id}/{action}
```

| 字段 | 位置 | 类型 / 枚举 | 说明 |
|---|---|---|---|
| `gym` | 第 1 段 | 固定值：`gym` | 固定前缀 |
| `gym_id` | 第 2 段 | `string` | 场馆 ID |
| `device_type` | 第 3 段 | `equipment` / `wristband` / `env` | 设备类型 |
| `device_id` | 第 4 段 | `string` | Topic 主设备 ID；`binding` 中表示手环 ID |
| `action` | 第 5 段 | `telemetry` / `status` / `alert` / `binding` / `config` | 消息类型 |

说明：设备身份以 Topic 中的 `device_id` 为准，Payload 不重复携带 `device_id`。

### 1.2 Payload 字段

| 字段 | 类型 / 枚举 | 适用消息 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 全部消息 | 设备 / 网关 | Unix 秒级时间戳 |

### 1.3 网关入站预处理字段

| 字段 | 类型 / 枚举 | 适用消息 | 来源 | 说明 |
|---|---|---|---|---|
| `gateway_received_ts` | `int` | 网关入站消息 | 网关 | 网关接收 MQTT 消息的 Unix 秒级时间戳；由网关入站预处理阶段补充，不属于设备原始 MQTT Payload，不出现在设备 Payload 表中 |

### 1.4 网关生成事件 Payload

网关本地规则或连通性判定可生成 `alert` / `status` 事件。该类事件用于写入网关本地可靠投递队列并上传后台，Payload 复用本文对应 `alert` / `status` 字段约束，但不要求通过 MQTT Broker 发布。

| 项目 | 说明 |
|---|---|
| 表达形式 | 使用 MQTT topic 形状和 MQTT 兼容 Payload 表达事件身份与内容 |
| 存储位置 | 写入网关本地可靠投递队列 |
| 后续流向 | 由网关批量上报后台 |
| 是否真实 MQTT 发布 | 否；除非后续另行设计本地广播需求 |

### 1.5 QoS / Retain 约定

| action | QoS | retain | 说明 |
|---|---:|---|---|
| `telemetry` | `1` | `false` | 连续遥测数据，不保留旧快照 |
| `status` | `1` | `true` | 当前状态快照，新订阅方需要立即获得最新状态 |
| `alert` | `1` | `false` | 告警是事件，不保留，避免重连后误判为新告警 |
| `binding` | `1` | `false` | 绑定 / 解绑是事件流，不保留 |
| `config` | `1` | `false` | 配置下发是命令式消息，不保留，避免设备重连后重复执行旧命令 |

说明：本节 QoS / Retain 只适用于真实 MQTT 发布消息。网关本地生成的告警 / 状态事件写入本地可靠投递队列，不适用 retain 语义。如后续需要设备重连后获取最新配置，应单独设计 `desired_config` 或 `config_snapshot`，不复用命令式 `config`。

### 1.6 数值范围

| 字段 | 类型 | 合法范围 | 说明 |
|---|---|---|---|
| `heart_rate` | `int` | `30..240` | 心率，单位 bpm |
| `step_count` | `int` | `0..2147483647` | 累计步数 |
| `battery_pct` | `int` | `0..100` | 电量百分比 |
| `rep_count` | `int` | `0..2147483647` | 累计重复次数 |
| `power_w` | `number` | `0..10000` | 当前功率，单位 W |
| `rated_power_w` | `number` | `1..10000` | 额定功率，单位 W，必须大于 0 |
| `energy_wh` | `number` | `0..100000000` | 累计能耗，单位 Wh |
| `humidity` | `number` | `0..100` | 相对湿度，单位 % |
| `temperature` | `number` | `-20..80` | 温度，单位 °C |
| `co2_ppm` | `number` | `0..10000` | CO2 浓度，单位 ppm |
| `pm2_5` | `number` | `0..1000` | PM2.5 浓度，单位 μg/m³ |
| `lux` | `number` | `0..200000` | 光照强度，单位 lx |
| `accel` | `number[3]` | 长度必须为 `3`；每个元素必须为 `number` | 三轴加速度，顺序固定为 `[x, y, z]` |
| `gyro` | `number[3]` | 长度必须为 `3`；每个元素必须为 `number` | 三轴陀螺仪，顺序固定为 `[x, y, z]` |
| `target_reps` | `int` | `1..9999` | 目标重复次数 |
| `hr_alert_threshold_high` | `int` | `60..240` | 高心率告警阈值 |
| `hr_alert_threshold_low` | `int` | `20..120` | 低心率告警阈值 |
| `notify_interval_ms` | `int` | `20..5000` | 手环 notify 周期，单位 ms |
| `telemetry_interval_s` | `int` | `1..3600` | 环境节点遥测上报周期，单位秒 |
| `co2_threshold_ppm` | `number` | `400..10000` | CO2 告警阈值，单位 ppm |
| `pm25_threshold_ugm3` | `number` | `1..1000` | PM2.5 告警阈值，单位 μg/m³ |

## 2. 状态消息

### 2.1 Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `status` | `offline` / `standby` / `active` / `warning` / `critical` / `fault` | 是 | 设备 / 网关 | 统一状态字段 |
| `firmware_version` | `string` | 是 | 设备 / 网关 | 固件版本；网关生成时固定为 `edge-generated` |
| `mac` | `string` | 是 | 设备 / 网关 | MAC 地址；网关生成时固定为 `00:00:00:00:00:00` |

### 2.2 统一语义

| `status` | 统一含义 | 适用设备 |
|---|---|---|
| `offline` | 离线 / 不可达 | 全部 |
| `standby` | 在线但未进行主要活动 | 全部 |
| `active` | 正在工作 / 使用中 / 已绑定 | 全部 |
| `warning` | 有警告但未到严重异常 | 全部 |
| `critical` | 严重异常 | 全部 |
| `fault` | 设备自身故障 | 全部 |

### 2.3 字段组合约束

| 来源 | `status` | `firmware_version` | `mac` | 说明 |
|---|---|---|---|---|
| 设备原始上报 | 按对应设备 Status Payload 表枚举 | 真实固件版本 | 真实 MAC 地址 | 设备原始 `status` 必须携带真实设备信息，不得使用网关 magic value |
| 网关生成离线状态 | `offline` | 固定值：`edge-generated` | 固定值：`00:00:00:00:00:00` | 网关判断设备不可达时生成；作为 MQTT 兼容事件写入本地可靠投递队列，不要求发布到 MQTT Broker |
| 网关生成故障状态 | `fault` | 固定值：`edge-generated` | 固定值：`00:00:00:00:00:00` | 网关判断设备协议异常或本地处理异常时生成；作为 MQTT 兼容事件写入本地可靠投递队列，不要求发布到 MQTT Broker |

## 3. 告警消息

### 3.1 Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `priority` | `P0` / `P1` / `P2` | 是 | 设备 / 网关 | 处置优先级；`P0` 涉及生命安全，`P1` 不涉及生命安全但需要及时处理，`P2` 为低于 `P1` 的维护或提醒类优先级 |
| `level` | `critical` / `warning` / `info` | 是 | 设备 / 网关 | 告警等级 |
| `alert_type` | 见下表 | 是 | 设备 / 网关 | 告警类型 |
| `message` | `string` | 是 | 设备 / 网关 | 告警文案 |
| `value` | `number` | 否 | 设备 / 网关 | 触发值 |
| `threshold` | `number` | 否 | 设备 / 网关 | 阈值 |

### 3.2 Alert Type 枚举

#### 3.2.1 通用

| `alert_type` | 适用设备 | 说明 |
|---|---|---|
| `device_offline` | `equipment` / `wristband` / `env` | 设备离线 |
| `device_fault` | `equipment` / `wristband` / `env` | 设备故障 |

#### 3.2.2 Equipment

| `alert_type` | 说明 |
|---|---|
| `overload` | 器材过载 |

#### 3.2.3 Wristband

| `alert_type` | 说明 |
|---|---|
| `heart_rate_high` | 心率过高 |
| `heart_rate_low` | 心率过低 |
| `fall_detected` | 跌倒检测 |
| `battery_low` | 电量过低 |

#### 3.2.4 Env

| `alert_type` | 说明 |
|---|---|
| `co2_high` | CO2 超标 |
| `co2_critical` | CO2 严重超标 |
| `pm25_high` | PM2.5 超标 |
| `temperature_high` | 温度超标 |

### 3.3 字段组合约束

#### 3.3.1 `alert_type` / `priority` / `level`

优先级语义：

| `priority` | 说明 |
|---|---|
| `P0` | 涉及生命安全，需要最高优先级处置 |
| `P1` | 不涉及生命安全，但需要及时处理 |
| `P2` | 低于 `P1` 的维护或提醒类优先级 |

| `alert_type` | `priority` | `level` | 说明 |
|---|---|---|---|
| `device_offline` | `P1` | `warning` | 设备离线，需要人工关注但不直接判定为设备故障 |
| `device_fault` | `P1` | `critical` | 设备自身故障，不直接判定为生命安全事件 |
| `overload` | `P1` | `critical` | 器材过载，不直接判定为生命安全事件 |
| `heart_rate_high` | `P0` | `critical` | 心率超过高阈值，涉及生命安全 |
| `heart_rate_low` | `P0` | `critical` | 心率低于低阈值，涉及生命安全 |
| `fall_detected` | `P0` | `critical` | 疑似跌倒 |
| `battery_low` | `P2` | `warning` | 电量过低 |
| `co2_high` | `P1` | `warning` | CO2 超过告警阈值 |
| `co2_critical` | `P0` | `critical` | CO2 超过严重告警阈值 |
| `pm25_high` | `P1` | `warning` | PM2.5 超过告警阈值 |
| `temperature_high` | `P1` | `warning` | 温度超过告警阈值 |

#### 3.3.2 `alert_type` / `value` / `threshold`

| `alert_type` | `value` | `threshold` | 说明 |
|---|---|---|---|
| `device_offline` | 否 | 否 | 事件型告警，不携带触发值 |
| `device_fault` | 否 | 否 | 事件型告警，不携带触发值 |
| `fall_detected` | 否 | 否 | 事件型告警，不携带触发值 |
| `overload` | 是 | 是 | `value` 表示当前功率或负载值，`threshold` 表示过载阈值 |
| `heart_rate_high` | 是 | 是 | `value` 表示当前心率，`threshold` 表示高心率阈值 |
| `heart_rate_low` | 是 | 是 | `value` 表示当前心率，`threshold` 表示低心率阈值 |
| `battery_low` | 是 | 是 | `value` 表示当前电量百分比，`threshold` 表示低电量阈值 |
| `co2_high` | 是 | 是 | `value` 表示当前 CO2 浓度，`threshold` 表示 CO2 告警阈值 |
| `co2_critical` | 是 | 是 | `value` 表示当前 CO2 浓度，`threshold` 表示 CO2 严重告警阈值 |
| `pm25_high` | 是 | 是 | `value` 表示当前 PM2.5 浓度，`threshold` 表示 PM2.5 告警阈值 |
| `temperature_high` | 是 | 是 | `value` 表示当前温度，`threshold` 表示温度告警阈值 |

## 4. Equipment

### 4.1 Topic

| action | Topic | 说明 |
|---|---|---|
| `telemetry` | `gym/{gym_id}/equipment/{device_id}/telemetry` | 器材运行遥测 |
| `status` | `gym/{gym_id}/equipment/{device_id}/status` | 器材在线与运行状态 |
| `alert` | `gym/{gym_id}/equipment/{device_id}/alert` | 器材告警 |

### 4.2 Telemetry Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 | 见通用 Payload 字段 |
| `rep_count` | `int` | 是 | 设备 | 累计重复次数，非负整数 |
| `power_w` | `number` | 是 | 设备 | 当前功率，单位 W |
| `rated_power_w` | `number` | 是 | 设备 | 额定功率，单位 W |
| `energy_wh` | `number` | 是 | 设备 | 累计能耗，单位 Wh |
| `axis_angle` | `number` | 否 | 设备 | 保留字段；器材运动角度或轴角 |
| `voltage_v` | `number` | 否 | 设备 | 保留字段；电压，单位 V |
| `current_ma` | `number` | 否 | 设备 | 保留字段；电流，单位 mA |

### 4.3 Status Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `status` | `offline` / `standby` / `active` / `warning` / `critical` / `fault` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `firmware_version` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `mac` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |

### 4.4 Alert Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `priority` | `P0` / `P1` / `P2` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `level` | `critical` / `warning` / `info` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `alert_type` | `overload` / `device_offline` / `device_fault` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `message` | `string` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `value` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |
| `threshold` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |

## 5. Wristband

### 5.1 Topic

| action | Topic | 说明 |
|---|---|---|
| `telemetry` | `gym/{gym_id}/wristband/{device_id}/telemetry` | 手环运行遥测 |
| `status` | `gym/{gym_id}/wristband/{device_id}/status` | 手环在线与运行状态 |
| `alert` | `gym/{gym_id}/wristband/{device_id}/alert` | 手环告警 |
| `binding` | `gym/{gym_id}/wristband/{device_id}/binding` | 手环与器材绑定事件 |

### 5.2 Telemetry Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 | 见通用 Payload 字段 |
| `heart_rate` | `int` | 是 | 设备 | 当前心率，单位 bpm |
| `step_count` | `int` | 是 | 设备 | 累计步数，非负整数 |
| `battery_pct` | `int` | 是 | 设备 | 电量百分比，范围 `0` 到 `100` |
| `current_equipment_id` | `string` / `null` | 是 | 设备 | 当前绑定器材 ID；未绑定为 `null` |
| `relayed_by` | `string` / `null` | 是 | 设备 / 器材 | 当前转发手环数据的器材 ID；未转发为 `null` |
| `accel` | `number[3]` | 是 | 设备 | 保留字段；三轴加速度，顺序固定为 `[x, y, z]`，设备原始单位 |
| `gyro` | `number[3]` | 是 | 设备 | 保留字段；三轴陀螺仪，顺序固定为 `[x, y, z]`，设备原始单位 |
| `flags` | 固定值：`0` | 是 | 设备 | 保留字段；当前未定义位含义，设备必须填 `0` |

### 5.3 Binding Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `equipment_id` | `string` | 是 | 设备 / 网关 | 绑定或解绑的器材 ID |
| `bound` | `bool` | 是 | 设备 / 网关 | 绑定状态；`true` 表示绑定，`false` 表示解绑 |
| `reason` | `ble_connected` / `ble_disconnected` / `idle_timeout` / `manual_bind` / `manual_unbind` | 是 | 设备 / 网关 | 绑定变化原因 |

字段组合约束：

| `bound` | 允许的 `reason` | 说明 |
|---|---|---|
| `true` | `ble_connected` / `manual_bind` | 建立绑定 |
| `false` | `ble_disconnected` / `idle_timeout` / `manual_unbind` | 解除绑定 |

### 5.4 Status Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `status` | `offline` / `standby` / `active` / `warning` / `critical` / `fault` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `firmware_version` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `mac` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |

### 5.5 Alert Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `priority` | `P0` / `P1` / `P2` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `level` | `critical` / `warning` / `info` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `alert_type` | `heart_rate_high` / `heart_rate_low` / `fall_detected` / `battery_low` / `device_offline` / `device_fault` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `message` | `string` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `value` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |
| `threshold` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |

## 6. Env

### 6.1 Topic

| action | Topic | 说明 |
|---|---|---|
| `telemetry` | `gym/{gym_id}/env/{device_id}/telemetry` | 环境节点遥测 |
| `status` | `gym/{gym_id}/env/{device_id}/status` | 环境节点在线与运行状态 |
| `alert` | `gym/{gym_id}/env/{device_id}/alert` | 环境节点告警 |

### 6.2 Telemetry Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 | 见通用 Payload 字段 |
| `temperature` | `number` | 是 | 设备 | 温度，单位 °C |
| `humidity` | `number` | 是 | 设备 | 相对湿度，单位 % |
| `co2_ppm` | `number` | 是 | 设备 | CO2 浓度，单位 ppm |
| `pm2_5` | `number` | 是 | 设备 | PM2.5 浓度，单位 μg/m³ |
| `lux` | `number` | 是 | 设备 | 光照强度，单位 lx |

### 6.3 Status Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `status` | `offline` / `standby` / `warning` / `critical` / `fault` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `firmware_version` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |
| `mac` | `string` | 是 | 设备 / 网关 | 见 Status Payload 字段 |

### 6.4 Alert Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 设备 / 网关 | 见通用 Payload 字段 |
| `priority` | `P0` / `P1` / `P2` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `level` | `critical` / `warning` / `info` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `alert_type` | `co2_high` / `co2_critical` / `pm25_high` / `temperature_high` / `device_offline` / `device_fault` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `message` | `string` | 是 | 设备 / 网关 | 见 Alert Payload 字段 |
| `value` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |
| `threshold` | `number` | 否 | 设备 / 网关 | 见 Alert Payload 字段 |

## 7. Config

### 7.1 Topic

| action | Topic | 说明 |
|---|---|---|
| `config` | `gym/{gym_id}/equipment/{device_id}/config` | 网关向器材下发配置 |
| `config` | `gym/{gym_id}/wristband/{device_id}/config` | 网关向手环下发配置 |
| `config` | `gym/{gym_id}/env/{device_id}/config` | 网关向环境节点下发配置 |

### 7.2 通用 Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 网关 | 见通用 Payload 字段 |

约束说明：

| 项目 | 适用 | 说明 |
|---|---|---|
| `gateway_received_ts` | 否 | 不适用于 `config`，因为 `config` 是网关出站消息，不是网关入站消息 |

说明：`config` 是全量配置消息，设备收到后按完整配置覆盖相关配置项；不定义局部 PATCH。

### 7.3 Equipment Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 网关 | 见 Config 通用 Payload 字段 |
| `target_reps` | `int` | 是 | 网关 | 目标重复次数，正整数 |

### 7.4 Wristband Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 网关 | 见 Config 通用 Payload 字段 |
| `hr_alert_threshold_high` | `int` | 是 | 网关 | 高心率告警阈值，单位 bpm |
| `hr_alert_threshold_low` | `int` | 是 | 网关 | 低心率告警阈值，单位 bpm |
| `notify_interval_ms` | `int` | 是 | 网关 | 手环 notify 周期，单位 ms |
| `fall_detect_enabled` | `bool` | 是 | 网关 | 是否启用跌倒检测 |

字段组合约束：

| 字段组合 | 约束 | 说明 |
|---|---|---|
| `hr_alert_threshold_low` / `hr_alert_threshold_high` | `hr_alert_threshold_low < hr_alert_threshold_high` | 低心率阈值必须小于高心率阈值 |

### 7.5 Env Payload 字段

| 字段 | 类型 / 枚举 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| `ts` | `int` | 是 | 网关 | 见 Config 通用 Payload 字段 |
| `telemetry_interval_s` | `int` | 是 | 网关 | 环境节点遥测上报周期，单位秒 |
| `co2_threshold_ppm` | `number` | 是 | 网关 | CO2 告警阈值，单位 ppm |
| `pm25_threshold_ugm3` | `number` | 是 | 网关 | PM2.5 告警阈值，单位 μg/m³ |
