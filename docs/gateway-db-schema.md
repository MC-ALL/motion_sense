# 网关本地数据库规范

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
| `v1.0.0-rc2` | `2026/05/07` | `CircuitX` | 明确 `ingest_events` 同时保存设备原始事件和网关生成事件；网关生成事件不要求发布到 MQTT Broker，但保存 MQTT topic 形状和 MQTT 兼容 Payload |
| `v1.0.0-rc1` | `2026/04/29` | `CircuitX` | 首个发布候选版；定义网关本地 SQLite 元信息、可靠投递队列、设备连通性、批次历史、清理索引与运行语义 |

## 文档说明

本文定义运动感知系统网关侧本地 SQLite 数据库规范。该数据库用于承载网关本地可靠投递、设备连通性、不可达判断与运行诊断所需的本地事实数据。

本文当前版本为 `v1.0.0-rc2` 发布候选版，按表定义字段、类型、约束、状态流转、清理策略与运行语义。外部 MQTT 字段仍以 [docs/mqtt-schema.md](mqtt-schema.md) 为准；本网关数据库规范只描述网关本地持久化模型，不直接定义 MQTT Topic、MQTT Payload、后台 REST API 或应用配置项。

## 1. 通用约定

### 1.1 时间字段

| 字段类型 | 类型 | 说明 |
|---|---|---|
| Unix 秒级时间戳 | `INTEGER` | 所有时间字段默认使用 Unix 秒级时间戳 |

### 1.2 字符串枚举

| 约定 | 说明 |
|---|---|
| 枚举值 | 使用小写 `snake_case` 字符串 |
| 未知值 | 不允许写入未在对应表结构中声明的枚举值 |

## 2. `schema_meta`

### 2.1 表作用

`schema_meta` 用于保存网关本地数据库自身的元信息。该表不保存业务事件，也不保存设备状态，只用于数据库初始化、版本检查、迁移判断与数据目录归属校验。

### 2.2 表结构

| 字段 | SQLite 类型 | 必填 | 说明 |
|---|---|---|---|
| `key` | `TEXT` | 是 | 元信息键名，主键；用于区分这一行记录保存的是什么信息 |
| `value` | `TEXT` | 是 | 元信息值；统一按字符串保存，具体含义由 `key` 决定 |
| `updated_at` | `INTEGER` | 是 | 该条元信息最近更新时间，Unix 秒 |

### 2.3 主键

| 主键 | 说明 |
|---|---|
| `key` | 每个元信息键只能有一条记录 |

### 2.4 初始记录

| `key` | `value` 类型 | 示例值 | 必填 | 说明 |
|---|---|---|---|---|
| `schema_version` | `integer string` | `1` | 是 | 当前数据库 schema 版本号；用于启动时判断是否需要迁移 |
| `gateway_id` | `string` | `gw-001` | 是 | 当前数据库所属网关 ID；用于防止误挂载其他网关的数据目录 |
| `created_at` | `integer string` | `1714200000` | 是 | 数据库首次初始化时间，Unix 秒 |
| `updated_at` | `integer string` | `1714200000` | 是 | 最近一次 schema 初始化或迁移时间，Unix 秒 |

### 2.5 约束

| 约束 | 说明 |
|---|---|
| 必需 `key` | 必须存在 `schema_version`、`gateway_id`、`created_at`、`updated_at` 四个键 |
| 扩展 `key` | 允许未来增加其他元信息键；未识别的扩展键不得改变四个必需键的语义 |
| `schema_version` | 必须是可解析为正整数的字符串 |
| `gateway_id` | 必须与当前网关运行配置中的 `gateway_id` 一致 |
| `created_at` / `updated_at` | 必须是可解析为 Unix 秒级时间戳的字符串 |

说明：`schema_meta` 的四个必需键属于应用层约束，SQLite DDL 只保证单个 `key` 唯一，不能保证这些键必然存在。数据库初始化和网关启动检查必须验证四个必需键；缺失任一必需键时，应拒绝启动或进入明确的初始化 / 迁移流程。

### 2.6 建表语义

```sql
CREATE TABLE schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

### 2.7 生命周期与清理策略

| 项目 | 说明 |
|---|---|
| 生命周期 | 数据库初始化时写入；schema 迁移或网关归属校验时更新 |
| 清理策略 | 永久保留，不自动清理 |
| 迁移要求 | `schema_version` 只能由迁移流程更新，不能由运行时业务流程修改 |
| 扩展要求 | 当前只要求四个必需键；未来可按需增加扩展键，但启动逻辑不得依赖未定义扩展键 |

## 3. `ingest_events`

### 3.1 表作用

`ingest_events` 用于保存网关本地收到或生成、并需要上传到后台的事件。它是网关本地可靠投递队列表。

设备原始事件来自 MQTT 入站消息；网关生成事件来自本地规则或连通性判定。网关生成事件不要求发布到 MQTT Broker，但为兼容后台批量入库和既有 topic 解析模型，仍保存 MQTT topic 形状和 MQTT 兼容 Payload。

| 能力 | 说明 |
|---|---|
| 本地缓存 | 后台不可用时，事件先保存在 SQLite 中 |
| 批量上传 | 上传任务从该表读取待投递事件组成批次 |
| 失败重试 | 上传失败后保留事件，并增加尝试次数 |
| 成功确认 | 后台接受后，将事件标记为 `delivered` |
| 事件丢弃 | 对不应再上传的旧事件标记为 `dropped`，保留排查记录 |
| 顺序追踪 | 通过自增 `id` 保留事件进入网关本地库的顺序 |

### 3.2 表结构

| 字段 | SQLite 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | `INTEGER` | 是 | 本地自增主键；表示事件进入网关本地库的顺序 |
| `gw_event_id` | `TEXT` | 是 | 网关本地生成的事件 ID；用于日志、批次关联、重试排查和未来跨表关联 |
| `gateway_id` | `TEXT` | 是 | 事件所属网关 ID |
| `gym_id` | `TEXT` | 是 | 场馆 ID，来自 `mqtt_topic` 解析结果 |
| `device_type` | `TEXT` | 是 | 设备类型，来自 `mqtt_topic` 解析结果 |
| `device_id` | `TEXT` | 是 | 设备 ID，来自 `mqtt_topic` 解析结果 |
| `mqtt_action` | `TEXT` | 是 | MQTT action，取值为 `telemetry` / `status` / `alert` / `binding` |
| `mqtt_topic` | `TEXT` | 是 | MQTT topic 形状的事件标识；设备原始事件保存原始 MQTT topic，网关生成事件保存兼容 topic，用于后台上传、重放和调试 |
| `mqtt_payload_json` | `TEXT` | 是 | MQTT payload JSON 字符串；设备原始事件保存规范化后的原始 payload，网关生成事件保存 MQTT 兼容 Payload，入库前被拒绝的丢弃占位记录可保存 `{}` |
| `mqtt_payload_ts` | `INTEGER` | 否 | MQTT payload 中的 `ts`，Unix 秒；无合法 `ts` 时为空 |
| `gw_received_ts` | `INTEGER` | 是 | 网关实际收到设备原始事件或生成本地事件的 Unix 秒时间戳 |
| `delivery_state` | `TEXT` | 是 | 本地投递状态，取值为 `pending` / `delivering` / `delivered` / `dropped` |
| `delivery_priority` | `INTEGER` | 是 | 本地投递优先级保留字段；`v1.0.0-rc1` 暂不参与实际上传排序，默认上传仍按 `id ASC` |
| `delivery_attempts` | `INTEGER` | 是 | 上传尝试次数，初始为 `0` |
| `delivery_next_attempt_at` | `INTEGER` | 否 | 下一次允许上传尝试的 Unix 秒时间戳；为空表示可立即尝试 |
| `delivery_err_msg` | `TEXT` | 否 | 最近一次上传失败原因，或事件被丢弃的原因 |
| `created_at` | `INTEGER` | 是 | 事件写入 SQLite 的 Unix 秒时间戳 |
| `updated_at` | `INTEGER` | 是 | 事件最近一次状态更新时间，Unix 秒 |
| `delivery_delivered_at` | `INTEGER` | 否 | 后台接受该事件的 Unix 秒时间戳 |

### 3.3 `gw_event_id` 生成规则

| 项目 | 说明 |
|---|---|
| 来源 | 网关本地生成，不来自 MQTT topic 或 payload |
| 生成时机 | 设备原始事件被网关接收并解析后，或网关本地事件被生成后，写入 `ingest_events` 前 |
| 推荐生成方式 | 优先使用时间有序 ID，例如 `uuid7` / `ULID`；如运行环境不方便提供，可使用 `uuid4` |
| 对接用途 | 批量上报对接时应随事件传递，用作后台幂等键 |
| 是否等同于 `id` | 否；`id` 是 SQLite 本地顺序号，`gw_event_id` 是事件稳定标识 |

#### 3.3.1 后台幂等规则

本节只说明本地数据库事件 ID 与后台批量上报之间的对接假设，不定义后台 REST API 的请求格式。具体接口字段仍应由通信接口文档或后台接口文档定义。

| 项目 | 说明 |
|---|---|
| 幂等键 | `gateway_id` + `gw_event_id` |
| 对接要求 | 网关批量上报事件时应携带 `gw_event_id` |
| 后台对接假设 | 后台按 `gateway_id` + `gw_event_id` 去重；重复事件不得重复入库或重复触发业务副作用 |
| `batch_id` | 可随批量上报上传后台，用于排查一次上传尝试；不得作为单条事件幂等键 |

说明：网关请求超时不代表后台没有成功写入。使用 `gw_event_id` 做后台幂等键，可以避免网关重试导致重复事件。

### 3.4 主键与唯一约束

| 类型 | 字段 | 说明 |
|---|---|---|
| 主键 | `id` | 本地自增主键，用于保留入库顺序 |
| 唯一约束 | `gw_event_id` | 同一事件 ID 只能入库一次 |

### 3.5 枚举值

#### 3.5.1 `mqtt_action`

| 值 | 说明 |
|---|---|
| `telemetry` | 遥测事件 |
| `status` | 状态事件 |
| `alert` | 告警事件 |
| `binding` | 绑定 / 解绑事件 |

#### 3.5.2 `delivery_state`

| 值 | 说明 |
|---|---|
| `pending` | 等待上传 |
| `delivering` | 已被上传任务取出，正在发送 |
| `delivered` | 后台已接受 |
| `dropped` | 网关判定不应再上传，已丢弃但保留记录 |

#### 3.5.3 `delivery_priority`

| `mqtt_action` | `delivery_priority` | 说明 |
|---|---:|---|
| `alert` | `10` | 保留值，未来用于告警优先上传 |
| `status` | `20` | 保留值，未来用于状态事件优先上传 |
| `binding` | `30` | 保留值，未来用于绑定事件优先上传 |
| `telemetry` | `40` | 保留值，未来用于降低高频遥测优先级 |

说明：`delivery_priority` 当前为保留字段。`v1.0.0-rc1` 不得使用 `delivery_priority` 打乱同一设备或全局事件上传顺序，默认上传顺序为：

```text
id ASC
```

### 3.6 初始值

新事件写入时：

| 字段 | 初始值 | 说明 |
|---|---|---|
| `gw_event_id` | 网关生成的时间有序 ID 或 `uuid4` | 写入前生成 |
| `delivery_state` | `pending` | 新事件默认等待上传 |
| `delivery_priority` | 按 `mqtt_action` 映射 | 当前为保留字段 |
| `delivery_attempts` | `0` | 尚未尝试上传 |
| `delivery_next_attempt_at` | `NULL` | 新事件可立即尝试上传 |
| `delivery_err_msg` | `NULL` | 尚无错误 |
| `delivery_delivered_at` | `NULL` | 尚未被后台接受 |
| `created_at` | 当前 Unix 秒 | 事件写入 SQLite 的时间 |
| `updated_at` | 当前 Unix 秒 | 初始状态更新时间 |

### 3.7 约束

| 约束 | 说明 |
|---|---|
| `gw_event_id` 唯一 | 防止同一事件 ID 重复入库 |
| `device_type` 固定集合 | 只能是 `equipment`、`wristband`、`env` |
| `mqtt_action` 固定集合 | 只能是 `telemetry`、`status`、`alert`、`binding` |
| `delivery_state` 固定集合 | 只能是 `pending`、`delivering`、`delivered`、`dropped` |
| `delivery_attempts >= 0` | 上传次数不能为负数 |
| `delivery_next_attempt_at` 可为空 | 为空表示事件可立即被上传任务领取 |
| `delivery_priority` 固定集合 | 只能是 `10`、`20`、`30`、`40` |
| `delivery_state = delivered` 时 `delivery_delivered_at` 必填 | 已投递事件必须记录后台接受时间 |
| `delivery_state != delivered` 时 `delivery_delivered_at` 必须为空 | 未成功投递的事件不应保留成功投递时间 |
| `delivery_state = delivered` 时 `delivery_err_msg` 必须为空 | 已成功投递的事件不应保留旧错误 |
| `delivery_state = delivered` 时 `delivery_next_attempt_at` 必须为空 | 已成功投递的事件不应保留重试时间 |
| `delivery_state = dropped` 时 `delivery_err_msg` 必填 | 被丢弃事件必须记录丢弃原因 |
| `delivery_state = dropped` 时 `delivery_next_attempt_at` 必须为空 | 已丢弃事件不再重试 |
| `delivery_state = pending` 时 `delivery_err_msg` 可保留 | 上传失败回到 `pending` 后可保留最近失败原因，便于排查 |
| `mqtt_payload_json` 必须是 JSON 对象字符串 | 保存规范化后的 MQTT payload |
| `mqtt_payload_json` 大小限制 | UTF-8 编码后不得超过 `16 KiB`；超过时按入库前丢弃策略处理 |
| `mqtt_payload_ts` 可为空 | 当 payload 中不存在合法 `ts` 时为空 |
| `gw_received_ts` 必填 | 所有事件必须有网关接收或生成时间 |
| `delivery_err_msg` 长度限制 | 最多 `1024` 个字符；超出时截断，完整错误写入日志文件 |

### 3.8 状态流转

| 流转 | 说明 |
|---|---|
| `pending -> delivering` | 上传任务选中事件并准备发送；`delivery_attempts` 必须加 `1`，`delivery_next_attempt_at` 必须清空 |
| `delivering -> delivered` | 后台成功接受该事件所属批次 |
| `delivering -> pending` | 上传失败或进程中断后，事件回到等待上传状态；`delivery_attempts` 不回退，并设置下一次重试时间 |
| `pending -> dropped` | 网关判定事件不应再上传，例如不可达后迟到的旧 telemetry |
| `delivering -> dropped` | 发送前复查发现事件已不应上传 |

说明：`v1.0.0-rc1` 默认上传顺序为 `id ASC`，不得使用 `delivery_priority` 打乱同一设备或全局事件上传顺序。

### 3.9 队列领取与并发策略

`v1.0.0-rc1` 允许多个上传 worker，但事件领取必须通过事务内状态抢占完成，不能只依赖先查询再更新的进程内约定。

| 步骤 | 动作 | 说明 |
|---|---|---|
| 1 | 开启写事务 | SQLite 实现建议使用 `BEGIN IMMEDIATE`，提前获得写锁 |
| 2 | 读取待上传事件 | 查询可重试的 `pending` 事件，按 `id ASC` 取前 `N` 条 |
| 3 | 创建批次 | 写入 `delivery_batches`，状态为 `created` |
| 4 | 写入批次明细 | 按本批次顺序写入 `delivery_batch_items` |
| 5 | 抢占事件 | 将本批次事件从 `pending` 更新为 `delivering`，将 `delivery_attempts` 加 `1`，并清空 `delivery_next_attempt_at` |
| 6 | 提交事务 | 事务提交后，该批事件才算被当前 worker 成功领取 |

约束说明：

| 约束 | 说明 |
|---|---|
| 原子性 | 创建批次、写入批次明细、事件 `pending -> delivering` 必须处于同一事务 |
| 多 worker | 多 worker 可以并发运行，但同一时刻只有成功完成状态抢占的 worker 拥有该事件 |
| 失败处理 | 如果事务失败，不能发送该批次；事件应保持 `pending` 或由启动恢复规则修复 |
| 上传时机 | HTTP 上传必须发生在领取事务提交之后，避免长时间持有 SQLite 写锁 |

待上传事件筛选条件：

```sql
delivery_state = 'pending'
AND (delivery_next_attempt_at IS NULL OR delivery_next_attempt_at <= 当前 Unix 秒)
```

SQLite 领取事务示意：

```sql
BEGIN IMMEDIATE;
-- SELECT retryable pending events ORDER BY id ASC LIMIT N
-- INSERT delivery_batches
-- INSERT delivery_batch_items
-- UPDATE ingest_events
-- SET delivery_state = 'delivering',
--     delivery_attempts = delivery_attempts + 1,
--     delivery_next_attempt_at = NULL
COMMIT;
```

### 3.10 上传完成事务

HTTP 上传完成后，批次状态和事件状态必须在同一事务中更新，避免批次与事件状态分裂。

`v1.0.0-rc1` 的网关本地投递模型按 all-or-nothing 批次结果处理。具体后台响应格式不由本文定义。

| 后台结果 | 网关处理 |
|---|---|
| 后台接受批次 | 批次内全部事件视为成功 |
| 后台拒绝批次 | 批次内全部事件视为失败 |
| 部分成功 / 部分失败 | 当前本地数据库模型不保存逐条结果；如后台接口未来支持部分成功，需要扩展本地模型 |

说明：如果未来需要逐条结果，应扩展 `delivery_batch_items`，增加 item-level state；当前版本不在 `delivery_batch_items` 中保存逐条投递状态。

#### 3.10.1 上传成功

后台成功接受批次时：

| 对象 | 更新动作 |
|---|---|
| `delivery_batches` | `batch_state = succeeded` |
| `delivery_batches` | `delivery_finished_at = 当前 Unix 秒` |
| `delivery_batches` | `delivery_http_status = 后台 HTTP 状态码` |
| `delivery_batches` | `delivery_err_msg = NULL` |
| `ingest_events` | 关联事件 `delivery_state = delivered` |
| `ingest_events` | 关联事件 `delivery_delivered_at = 当前 Unix 秒` |
| `ingest_events` | 关联事件 `delivery_next_attempt_at = NULL` |
| `ingest_events` | 关联事件 `delivery_err_msg = NULL` |
| `updated_at` | 批次和事件均更新为当前 Unix 秒 |

#### 3.10.2 上传失败

网络异常、超时或后台返回失败状态时：

| 对象 | 更新动作 |
|---|---|
| `delivery_batches` | `batch_state = failed` |
| `delivery_batches` | `delivery_finished_at = 当前 Unix 秒` |
| `delivery_batches` | `delivery_http_status = 后台 HTTP 状态码；网络异常时为 NULL` |
| `delivery_batches` | `delivery_err_msg = 失败原因` |
| `ingest_events` | 关联事件 `delivery_state = pending` |
| `ingest_events` | 关联事件 `delivery_attempts` 不回退 |
| `ingest_events` | 关联事件 `delivery_next_attempt_at = 按重试退避规则计算的未来时间` |
| `ingest_events` | 关联事件 `delivery_err_msg = 失败原因` |
| `ingest_events` | 关联事件 `delivery_delivered_at = NULL` |
| `updated_at` | 批次和事件均更新为当前 Unix 秒 |

#### 3.10.3 最大重试与死信规则

上传失败后，如果事件的 `delivery_attempts` 已达到 `max_delivery_attempts`，该事件不再回到 `pending`，而是标记为 `dropped`。

| 条件 | 动作 |
|---|---|
| `delivery_attempts < max_delivery_attempts` | `delivery_state = pending`，设置 `delivery_next_attempt_at` |
| `delivery_attempts >= max_delivery_attempts` | `delivery_state = dropped`，`delivery_err_msg = max delivery attempts exceeded`，`delivery_next_attempt_at = NULL`，`delivery_delivered_at = NULL` |

说明：`v1.0.0-rc1` 对全部 `mqtt_action` 使用统一最大重试次数。未来如需要区分 `alert`、`status`、`binding`、`telemetry` 的重试策略，可在运行参数或上传策略中扩展，不改变表结构。

#### 3.10.4 重试退避规则

重试退避用于避免后台不可用时网关立即反复重试。

建议计算方式：

```text
delay_s = min(delivery_retry_base_delay_s * 2 ^ (delivery_attempts - 1), delivery_retry_max_delay_s)
delivery_next_attempt_at = 当前 Unix 秒 + delay_s
```

说明：`delivery_attempts` 在 `pending -> delivering` 时已经加 `1`，因此第一次失败后的退避使用 `delivery_attempts = 1`。

### 3.11 入库前丢弃策略

入库前丢弃指事件尚未完整写入 `ingest_events`，就因为 payload 过大、本地数据库容量压力或格式异常而不能进入正常上传队列。

处理顺序：

| 步骤 | 动作 | 说明 |
|---|---|---|
| 1 | 优先清理历史数据 | 先按清理策略删除已过保留期的 `delivered` / `dropped` 事件和历史批次 |
| 2 | 重新检查容量 | 清理后如果容量恢复，正常写入事件 |
| 3 | 写入丢弃占位记录 | 如果事件不能正常入库，尽量写入一条 `delivery_state = dropped` 的占位记录 |
| 4 | 最后退化为日志 | 如果 SQLite 已无法写入占位记录，只能写运行日志和指标，不得反复重试同一异常事件 |

丢弃占位记录写入规则：

| 字段 | 值 | 说明 |
|---|---|---|
| `gw_event_id` | 新生成 ID | 仍生成本地事件 ID，便于排查 |
| `mqtt_topic` | 原始 topic | 保留事件来源 |
| `mqtt_payload_json` | `{}` | 不保存超大或非法 payload |
| `mqtt_payload_ts` | 可解析则填写，否则 `NULL` | 尽量保留设备时间 |
| `delivery_state` | `dropped` | 明确该事件不会上传 |
| `delivery_next_attempt_at` | `NULL` | 丢弃事件不再重试 |
| `delivery_err_msg` | 丢弃原因 | 例如 `payload too large` / `local db capacity exceeded` / `invalid mqtt payload` |

优先级策略：

| 场景 | 处理 |
|---|---|
| 正常容量压力 | 优先清理历史数据，不主动丢弃新事件 |
| 清理后仍超限 | 可优先丢弃新进入的 `telemetry`，尽量保留 `alert` / `status` / `binding` |
| payload 超过 `16 KiB` | 不保存完整 payload，写入丢弃占位记录 |
| 占位记录也无法写入 | 写日志和指标后丢弃，避免数据库满时进入死循环 |

### 3.12 启动恢复规则

网关进程启动时必须修复上一次异常退出遗留的半投递状态。

| 启动时 `delivery_state` | 恢复动作 | 说明 |
|---|---|---|
| `pending` | 保持不变 | 等待后续上传 |
| `delivering` | 改回 `pending` | 上一次进程可能在发送中退出，必须允许重新上传 |
| `delivered` | 保持不变 | 已被后台接受，不再重复上传 |
| `dropped` | 保持不变 | 已明确丢弃，不再上传 |

恢复 `delivering -> pending` 时，应增加或保留可排查信息：

| 字段 | 更新建议 |
|---|---|
| `delivery_err_msg` | `interrupted during delivery` |
| `delivery_next_attempt_at` | `NULL` 或按重试退避规则设置 | 如果希望重启后立即补偿上传可设为 `NULL`；如果后台故障持续可按退避规则设置 |
| `updated_at` | 当前 Unix 秒 |

### 3.13 清理策略

| 数据 | 清理策略 |
|---|---|
| `pending` / `delivering` 事件 | 不自动清理，必须等待成功投递、恢复为 `pending` 或显式标记为 `dropped` |
| `delivered` 事件 | 默认保留 `7` 天，或在超过本地容量阈值时按 `delivery_delivered_at` 从旧到新清理 |
| `dropped` 事件 | 默认保留 `7` 天，或在超过本地容量阈值时按 `updated_at` 从旧到新清理 |
| 仍被 `delivery_batch_items` 引用的事件 | 删除时由外键级联清理关联记录 |

### 3.14 建表语义

```sql
CREATE TABLE ingest_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gw_event_id TEXT NOT NULL UNIQUE,
  gateway_id TEXT NOT NULL,
  gym_id TEXT NOT NULL,
  device_type TEXT NOT NULL,
  device_id TEXT NOT NULL,
  mqtt_action TEXT NOT NULL,
  mqtt_topic TEXT NOT NULL,
  mqtt_payload_json TEXT NOT NULL,
  mqtt_payload_ts INTEGER,
  gw_received_ts INTEGER NOT NULL,
  delivery_state TEXT NOT NULL,
  delivery_priority INTEGER NOT NULL,
  delivery_attempts INTEGER NOT NULL DEFAULT 0,
  delivery_next_attempt_at INTEGER,
  delivery_err_msg TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  delivery_delivered_at INTEGER,
  CHECK (device_type IN ('equipment', 'wristband', 'env')),
  CHECK (mqtt_action IN ('telemetry', 'status', 'alert', 'binding')),
  CHECK (delivery_state IN ('pending', 'delivering', 'delivered', 'dropped')),
  CHECK (delivery_priority IN (10, 20, 30, 40)),
  CHECK (delivery_attempts >= 0),
  CHECK (length(CAST(mqtt_payload_json AS BLOB)) <= 16384),
  CHECK (delivery_err_msg IS NULL OR length(delivery_err_msg) <= 1024),
  CHECK (
    (delivery_state = 'delivered' AND delivery_delivered_at IS NOT NULL)
    OR
    (delivery_state != 'delivered' AND delivery_delivered_at IS NULL)
  ),
  CHECK (
    (delivery_state = 'delivered' AND delivery_err_msg IS NULL)
    OR
    (delivery_state != 'delivered')
  ),
  CHECK (
    (delivery_state IN ('delivered', 'dropped') AND delivery_next_attempt_at IS NULL)
    OR
    (delivery_state NOT IN ('delivered', 'dropped'))
  ),
  CHECK (
    (delivery_state = 'dropped' AND delivery_err_msg IS NOT NULL)
    OR
    (delivery_state != 'dropped')
  )
);
```

## 4. `device_connectivity`

### 4.1 表作用

`device_connectivity` 用于保存网关侧观察到的设备连通性状态，是网关本地的设备可达 / 不可达事实表。该表不保存每条遥测数据，只保存每台设备当前在网关看来是否可连通，以及最近一次被网关看到的时间。

| 能力 | 说明 |
|---|---|
| 连通性状态持久化 | 网关重启后仍能知道之前见过哪些设备，以及最后一次见到它们的时间 |
| 不可达判断依据 | 不可达扫描查询该表，而不是只依赖进程内内存 |
| 恢复连通判断依据 | 不可达设备再次上报时，可以根据该表判断是否从 `disconnected` 恢复为 `connected` |
| 防止永久连通 | 设备停止上报后，即使网关重启，也能继续根据 `gw_last_seen_ts` 判定不可达 |
| 旧数据辅助判断 | 通过 `mqtt_last_payload_ts` 辅助识别明显迟到的旧 MQTT payload |

### 4.2 表结构

| 字段 | SQLite 类型 | 必填 | 说明 |
|---|---|---|---|
| `gateway_id` | `TEXT` | 是 | 当前网关 ID |
| `gym_id` | `TEXT` | 是 | 场馆 ID，来自 MQTT topic 解析结果 |
| `device_type` | `TEXT` | 是 | 设备类型，来自 MQTT topic 解析结果 |
| `device_id` | `TEXT` | 是 | 设备 ID，来自 MQTT topic 解析结果 |
| `connectivity_state` | `TEXT` | 是 | 网关侧连通性状态，取值为 `unknown` / `connected` / `disconnected` |
| `gw_first_seen_ts` | `INTEGER` | 是 | 网关第一次看到该设备的 Unix 秒时间戳 |
| `gw_last_seen_ts` | `INTEGER` | 是 | 网关最近一次看到该设备的 Unix 秒时间戳；不可达判断的主要依据 |
| `mqtt_last_payload_ts` | `INTEGER` | 否 | 最近一次合法 MQTT payload `ts`，Unix 秒；用于辅助识别旧数据和排查设备时钟问题 |
| `connectivity_disconnected_since_ts` | `INTEGER` | 否 | 当前不可达状态开始时间；仅当 `connectivity_state = disconnected` 时填写 |
| `created_at` | `INTEGER` | 是 | 记录创建时间，Unix 秒 |
| `updated_at` | `INTEGER` | 是 | 记录最近更新时间，Unix 秒 |

### 4.3 主键

| 类型 | 字段 | 说明 |
|---|---|---|
| 复合主键 | `gateway_id`, `gym_id`, `device_type`, `device_id` | 同一网关下每台设备只有一条 connectivity 记录 |

### 4.4 枚举值

#### 4.4.1 `connectivity_state`

| 值 | 说明 |
|---|---|
| `unknown` | 网关知道这台设备，但还没有收到过它的有效 MQTT 消息 |
| `connected` | 网关最近在超时时间内收到过该设备消息 |
| `disconnected` | 网关超过超时时间未收到该设备消息，并已判定设备不可达 |

说明：`connectivity_state` 只表示网关连通性，不表示设备业务运行状态。

```text
connected != active
disconnected != fault
```

### 4.5 初始值

#### 4.5.1 网关首次收到设备消息

| 字段 | 初始值 | 说明 |
|---|---|---|
| `connectivity_state` | `connected` | 收到有效 MQTT 消息即认为设备对网关可连通 |
| `gw_first_seen_ts` | 当前 `gw_received_ts` | 第一次看到该设备 |
| `gw_last_seen_ts` | 当前 `gw_received_ts` | 最近一次看到该设备 |
| `mqtt_last_payload_ts` | 当前 `mqtt_payload_ts` 或 `NULL` | 有合法 payload `ts` 时写入 |
| `connectivity_disconnected_since_ts` | `NULL` | 尚未判定为不可达 |
| `created_at` | 当前 Unix 秒 | 记录创建时间 |
| `updated_at` | 当前 Unix 秒 | 记录更新时间 |

#### 4.5.2 未来从后台 / 配置同步已知设备

| 字段 | 初始值 | 说明 |
|---|---|---|
| `connectivity_state` | `unknown` | 网关知道设备存在，但还不能判断是否可连通 |
| `gw_first_seen_ts` | 同步时间 | 表示网关首次知道该设备的时间 |
| `gw_last_seen_ts` | 同步时间 | 表示最近一次同步该设备存在的时间 |
| `mqtt_last_payload_ts` | `NULL` | 尚无设备 payload 时间 |
| `connectivity_disconnected_since_ts` | `NULL` | 不直接判定为不可达 |
| `created_at` | 当前 Unix 秒 | 记录创建时间 |
| `updated_at` | 当前 Unix 秒 | 记录更新时间 |

说明：后台 / 配置同步已知设备是预留能力，`v1.0.0-rc1` 可以不实现。

### 4.6 约束

| 约束 | 说明 |
|---|---|
| `connectivity_state` 固定集合 | 只能是 `unknown`、`connected`、`disconnected` |
| `device_type` 固定集合 | 只能是 `equipment`、`wristband`、`env` |
| `gw_first_seen_ts <= gw_last_seen_ts` | 最近看到时间不能早于首次看到时间 |
| `mqtt_last_payload_ts` 可为空 | payload 没有合法 `ts` 时为空 |
| `connectivity_disconnected_since_ts` 可为空 | 只有进入 `disconnected` 时才有值 |
| `connectivity_state = disconnected` 时 `connectivity_disconnected_since_ts` 必填 | 不可达状态必须记录从什么时候开始 |
| `connectivity_state != disconnected` 时 `connectivity_disconnected_since_ts` 必须为空 | 可连通或未知状态不应保留当前不可达开始时间 |

### 4.7 状态流转

| 流转 | 说明 |
|---|---|
| `unknown -> connected` | 网关首次收到该设备有效 MQTT 消息 |
| `connected -> disconnected` | 网关超过超时时间未收到设备消息，判定设备不可达 |
| `disconnected -> connected` | 不可达设备再次被网关收到有效 MQTT 消息 |

说明：`connectivity_state` 只描述网关和设备之间的连通性，不描述设备业务状态。

### 4.8 清理策略

| 数据 | 清理策略 |
|---|---|
| `connected` / `disconnected` 记录 | 默认不自动清理，作为网关重启后的连通性恢复依据 |
| `unknown` 记录 | 如果未来实现设备清单同步，可在设备从清单移除后清理 |
| 已删除设备 | 由显式设备移除流程清理，不由周期性任务误删 |

### 4.9 建表语义

```sql
CREATE TABLE device_connectivity (
  gateway_id TEXT NOT NULL,
  gym_id TEXT NOT NULL,
  device_type TEXT NOT NULL,
  device_id TEXT NOT NULL,
  connectivity_state TEXT NOT NULL,
  gw_first_seen_ts INTEGER NOT NULL,
  gw_last_seen_ts INTEGER NOT NULL,
  mqtt_last_payload_ts INTEGER,
  connectivity_disconnected_since_ts INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (gateway_id, gym_id, device_type, device_id),
  CHECK (device_type IN ('equipment', 'wristband', 'env')),
  CHECK (connectivity_state IN ('unknown', 'connected', 'disconnected')),
  CHECK (gw_first_seen_ts <= gw_last_seen_ts),
  CHECK (
    (connectivity_state = 'disconnected' AND connectivity_disconnected_since_ts IS NOT NULL)
    OR
    (connectivity_state != 'disconnected' AND connectivity_disconnected_since_ts IS NULL)
  )
);
```

## 5. `delivery_batches`

### 5.1 表作用

`delivery_batches` 用于记录网关每一次向后台批量上传事件的尝试。该表不保存具体事件 payload，只保存一次上传批次的整体状态。

| 能力 | 说明 |
|---|---|
| 上传审计 | 记录每次批量上传什么时候创建、发送、结束 |
| 故障排查 | 后台不可用、超时或 HTTP 错误时，可以查看失败原因 |
| 统计指标 | 可统计成功批次数、失败批次数和平均事件数量 |
| 批次关联 | 配合 `delivery_batch_items` 追踪某条事件属于哪些上传批次 |

### 5.2 表结构

| 字段 | SQLite 类型 | 必填 | 说明 |
|---|---|---|---|
| `batch_id` | `TEXT` | 是 | 网关本地生成的批次 ID，主键 |
| `gateway_id` | `TEXT` | 是 | 发起上传的网关 ID |
| `batch_state` | `TEXT` | 是 | 批次状态，取值为 `created` / `sending` / `succeeded` / `failed` |
| `event_count` | `INTEGER` | 是 | 本批次创建时包含的事件数量快照 |
| `delivery_sent_at` | `INTEGER` | 否 | 批次开始发送的 Unix 秒时间戳 |
| `delivery_finished_at` | `INTEGER` | 否 | 批次结束的 Unix 秒时间戳 |
| `delivery_http_status` | `INTEGER` | 否 | 后台返回的 HTTP 状态码；网络异常或尚未发送时为空 |
| `delivery_err_msg` | `TEXT` | 否 | 上传失败原因或异常信息 |
| `created_at` | `INTEGER` | 是 | 批次记录创建时间，Unix 秒 |
| `updated_at` | `INTEGER` | 是 | 批次记录最近更新时间，Unix 秒 |

### 5.3 主键

| 类型 | 字段 | 说明 |
|---|---|---|
| 主键 | `batch_id` | 每次上传尝试对应一个唯一批次 ID |

### 5.4 枚举值

#### 5.4.1 `batch_state`

| 值 | 说明 |
|---|---|
| `created` | 批次已创建，但还没有开始发送 |
| `sending` | 批次正在发送 |
| `succeeded` | 后台成功接受该批次 |
| `failed` | 批次发送失败，或后台返回失败状态 |

### 5.5 初始值与状态更新

#### 5.5.1 批次创建时

| 字段 | 初始值 | 说明 |
|---|---|---|
| `batch_id` | 网关生成的时间有序 ID 或 `uuid4` | 写入前生成 |
| `batch_state` | `created` | 批次刚创建 |
| `event_count` | 本批次事件数量 | 必须大于 `0` |
| `delivery_sent_at` | `NULL` | 尚未开始发送 |
| `delivery_finished_at` | `NULL` | 尚未结束 |
| `delivery_http_status` | `NULL` | 尚无后台响应 |
| `delivery_err_msg` | `NULL` | 尚无错误 |
| `created_at` | 当前 Unix 秒 | 批次记录创建时间 |
| `updated_at` | 当前 Unix 秒 | 初始状态更新时间 |

#### 5.5.2 发送开始时

发送开始前必须使用独立短事务将批次从 `created` 更新为 `sending`。HTTP 上传不得在该事务内执行，避免长时间持有 SQLite 写锁。

| 字段 | 更新值 |
|---|---|
| `batch_state` | `sending` |
| `delivery_sent_at` | 当前 Unix 秒 |
| `updated_at` | 当前 Unix 秒 |

#### 5.5.3 发送成功时

| 字段 | 更新值 |
|---|---|
| `batch_state` | `succeeded` |
| `delivery_finished_at` | 当前 Unix 秒 |
| `delivery_http_status` | 后台 HTTP 状态码，例如 `200` |
| `delivery_err_msg` | `NULL` |
| `updated_at` | 当前 Unix 秒 |

#### 5.5.4 发送失败时

| 字段 | 更新值 |
|---|---|
| `batch_state` | `failed` |
| `delivery_finished_at` | 当前 Unix 秒 |
| `delivery_http_status` | 后台 HTTP 状态码；网络异常时为 `NULL` |
| `delivery_err_msg` | 失败原因 |
| `updated_at` | 当前 Unix 秒 |

### 5.6 约束

| 约束 | 说明 |
|---|---|
| `batch_id` 唯一 | 每个批次只能有一条记录 |
| `batch_state` 固定集合 | 只能是 `created`、`sending`、`succeeded`、`failed` |
| `event_count > 0` | 空批次不应入库 |
| `event_count` 为创建时快照 | 后续清理 `delivery_batch_items` 时不反向修改该值 |
| `delivery_sent_at` 可为空 | 批次未发送时为空 |
| `delivery_finished_at` 可为空 | 批次未结束时为空 |
| `delivery_http_status` 可为空 | 网络异常或尚未发送时为空 |
| `delivery_http_status` 非空范围 | 非空时必须在 `100..599` 之间 |
| `batch_state = succeeded` 时 `delivery_http_status` 必须为 `2xx` | 成功批次必须对应后台成功响应 |
| `batch_state = failed` 时 `delivery_http_status` 可为空或非 `2xx` | 网络异常时为空；后台拒绝时记录非 `2xx` 状态码 |
| `batch_state = succeeded` 时 `delivery_finished_at` 必填 | 成功批次必须有结束时间 |
| `batch_state = succeeded` 时 `delivery_err_msg` 必须为空 | 成功批次不应保留旧错误 |
| `batch_state = failed` 时 `delivery_finished_at` 必填 | 失败批次必须有结束时间 |
| `batch_state = failed` 时 `delivery_err_msg` 必填 | 失败批次必须记录原因 |
| `delivery_err_msg` 长度限制 | 最多 `1024` 个字符；超出时截断，完整错误写入日志文件 |
| `created -> failed` 时 `delivery_sent_at` 为空 | 启动恢复或发送前中断，批次没有真正开始 HTTP 发送 |
| `sending -> failed` 时 `delivery_sent_at` 必填 | 批次已经开始 HTTP 发送，必须记录发送开始时间 |

### 5.7 状态流转

| 流转 | 说明 |
|---|---|
| `created -> sending` | 批次开始向后台发送 |
| `sending -> succeeded` | 后台成功接受该批次 |
| `sending -> failed` | 网络异常、超时或后台返回失败状态 |
| `created -> failed` | 启动恢复时发现批次创建后未进入发送流程 |

说明：批次状态描述一次上传尝试，不等同于单条事件的 `delivery_state`。

推荐上传生命周期：

| 阶段 | 动作 | 说明 |
|---|---|---|
| 领取事务 | 创建 `created` 批次并抢占事件 | 见 `ingest_events` 队列领取与并发策略 |
| 发送前事务 | `created -> sending`，写入 `delivery_sent_at` | 短事务，不执行 HTTP |
| HTTP 上传 | 向后台发送批次 | 不持有 SQLite 写锁 |
| 完成事务 | `sending -> succeeded` 或 `sending -> failed`，并同步更新事件状态 | 见 `ingest_events` 上传完成事务 |

说明：`created -> failed` 与 `sending -> failed` 的来源差异由状态流转代码保证，SQLite DDL 只约束最终字段组合，不完整保存历史来源。如未来需要直接查询失败阶段，可新增专门字段；当前版本不增加。

### 5.8 启动恢复规则

网关进程启动时必须修复上一次异常退出遗留的半发送批次。

| 启动时 `batch_state` | 恢复动作 | 说明 |
|---|---|---|
| `created` | 标记为 `failed` | 批次已创建但未确认开始发送 |
| `sending` | 标记为 `failed` | 批次可能发送中断，关联事件应回到 `pending` 等待重新上传 |
| `succeeded` | 保持不变 | 已成功接受 |
| `failed` | 保持不变 | 已失败并保留排查记录 |

恢复 `created` / `sending` 为 `failed` 时，应更新：

| 字段 | 更新建议 |
|---|---|
| `delivery_finished_at` | 当前 Unix 秒 |
| `delivery_err_msg` | `interrupted before sending` 或 `interrupted during sending` |
| `updated_at` | 当前 Unix 秒 |

恢复 `created` / `sending` 批次时，应同时通过 `delivery_batch_items` 找到该批次关联的 `delivering` 事件，并将这些事件恢复为 `pending`。该恢复动作必须与批次状态更新处于同一事务中，避免批次已标记失败但事件仍停留在 `delivering`。

### 5.9 清理策略

| 数据 | 清理策略 |
|---|---|
| `succeeded` 批次 | 默认保留 `7` 天，或在超过本地容量阈值时按 `created_at` 从旧到新清理 |
| `failed` 批次 | 默认保留 `30` 天，用于排查后台不可用、网络异常或数据格式错误 |
| `created` / `sending` 批次 | 启动恢复时应检查并修正；长时间停留在该状态的批次应标记为 `failed` |
| 批次明细 | 删除批次时通过外键级联删除 `delivery_batch_items` 记录 |

### 5.10 建表语义

```sql
CREATE TABLE delivery_batches (
  batch_id TEXT PRIMARY KEY,
  gateway_id TEXT NOT NULL,
  batch_state TEXT NOT NULL,
  event_count INTEGER NOT NULL,
  delivery_sent_at INTEGER,
  delivery_finished_at INTEGER,
  delivery_http_status INTEGER,
  delivery_err_msg TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK (batch_state IN ('created', 'sending', 'succeeded', 'failed')),
  CHECK (event_count > 0),
  CHECK (delivery_http_status IS NULL OR (delivery_http_status >= 100 AND delivery_http_status <= 599)),
  CHECK (delivery_err_msg IS NULL OR length(delivery_err_msg) <= 1024),
  CHECK (
    (batch_state = 'created' AND delivery_sent_at IS NULL AND delivery_finished_at IS NULL)
    OR
    (batch_state = 'sending' AND delivery_sent_at IS NOT NULL AND delivery_finished_at IS NULL)
    OR
    (batch_state = 'succeeded' AND delivery_sent_at IS NOT NULL AND delivery_finished_at IS NOT NULL)
    OR
    (batch_state = 'failed' AND delivery_finished_at IS NOT NULL)
  ),
  CHECK (
    (batch_state = 'failed' AND delivery_err_msg IS NOT NULL)
    OR
    (batch_state != 'failed')
  ),
  CHECK (
    (batch_state = 'succeeded' AND delivery_http_status >= 200 AND delivery_http_status <= 299)
    OR
    (batch_state != 'succeeded')
  ),
  CHECK (
    (batch_state = 'succeeded' AND delivery_err_msg IS NULL)
    OR
    (batch_state != 'succeeded')
  ),
  CHECK (
    (batch_state = 'failed' AND (delivery_http_status IS NULL OR delivery_http_status < 200 OR delivery_http_status > 299))
    OR
    (batch_state != 'failed')
  )
);
```

## 6. `delivery_batch_items`

### 6.1 表作用

`delivery_batch_items` 用于记录上传批次和具体事件之间的关联关系。该表说明某个批次包含哪些 `ingest_events` 事件，以及这些事件在批次中的顺序。

不建议在 `ingest_events` 中直接保存 `batch_id`，因为同一事件可能经历多次上传尝试。例如第一次批次失败、第二次批次成功时，一条事件会关联多个批次。

| 能力 | 说明 |
|---|---|
| 批次明细 | 查询某个批次具体上传了哪些事件 |
| 事件投递历史 | 查询某条事件曾经进入过哪些批次 |
| 顺序追踪 | 记录事件在批次中的发送顺序 |
| 失败排查 | 结合 `delivery_batches` 可以定位失败批次中的事件集合 |

### 6.2 表结构

| 字段 | SQLite 类型 | 必填 | 说明 |
|---|---|---|---|
| `batch_id` | `TEXT` | 是 | 所属批次 ID，关联 `delivery_batches.batch_id` |
| `gw_event_id` | `TEXT` | 是 | 事件 ID，关联 `ingest_events.gw_event_id` |
| `position` | `INTEGER` | 是 | 事件在批次中的顺序，从 `0` 开始 |
| `created_at` | `INTEGER` | 是 | 记录创建时间，Unix 秒 |

### 6.3 主键与唯一约束

| 类型 | 字段 | 说明 |
|---|---|---|
| 复合主键 | `batch_id`, `gw_event_id` | 同一批次不能重复包含同一事件 |
| 唯一约束 | `batch_id`, `position` | 同一批次中每个位置只能对应一条事件 |

### 6.4 外键

| 字段 | 关联目标 | 说明 |
|---|---|---|
| `batch_id` | `delivery_batches.batch_id` | 关联所属上传批次；批次删除时级联删除关联记录 |
| `gw_event_id` | `ingest_events.gw_event_id` | 关联具体事件；事件删除时级联删除关联记录 |

说明：SQLite 默认不强制外键，运行时必须开启：

```sql
PRAGMA foreign_keys = ON;
```

### 6.5 初始值

批次创建并写入明细时：

| 字段 | 初始值 | 说明 |
|---|---|---|
| `batch_id` | 当前批次 ID | 来自 `delivery_batches.batch_id` |
| `gw_event_id` | 当前事件 ID | 来自 `ingest_events.gw_event_id` |
| `position` | 批次内顺序 | 从 `0` 开始递增 |
| `created_at` | 当前 Unix 秒 | 记录创建时间 |

### 6.6 约束

| 约束 | 说明 |
|---|---|
| `position >= 0` | 批次内顺序不能为负数 |
| `batch_id` 必须存在 | 必须先创建 `delivery_batches` 记录 |
| `gw_event_id` 必须存在 | 必须关联已存在的 `ingest_events` 事件 |
| 同一事件可出现在多个批次 | 用于保留失败重试历史 |

### 6.7 清理策略

| 数据 | 清理策略 |
|---|---|
| 批次关联记录 | 不单独清理，随 `delivery_batches` 或 `ingest_events` 删除时通过外键级联删除 |
| 失败重试历史 | 在对应批次保留期内保留，用于追踪单条事件的多次上传尝试 |

说明：`delivery_batches.event_count` 是批次创建时的事件数量快照，`delivery_batch_items` 是当前仍保留的批次明细。清理旧 `ingest_events` 时会通过外键级联删除对应的 `delivery_batch_items`，因此后续查询到的明细行数可以小于 `event_count`。这是运行库清理后的正常现象，不表示批次创建时写入异常。

如果未来需要永久审计完整批次内容，应增加独立归档表、导出日志或后台审计存储，不应依赖网关本地运行库永久保存所有明细。

### 6.8 建表语义

```sql
CREATE TABLE delivery_batch_items (
  batch_id TEXT NOT NULL,
  gw_event_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (batch_id, gw_event_id),
  UNIQUE (batch_id, position),
  FOREIGN KEY (batch_id) REFERENCES delivery_batches(batch_id) ON DELETE CASCADE,
  FOREIGN KEY (gw_event_id) REFERENCES ingest_events(gw_event_id) ON DELETE CASCADE,
  CHECK (position >= 0)
);
```


## 7. 本地数据库运行约定

### 7.1 通用说明

本章节定义网关本地数据库运行时必须满足的通用行为。具体数据库实现可以不同，但必须满足可靠投递、异常恢复和数据一致性的要求。

| 约定 | 说明 |
|---|---|
| 事务边界 | 同一业务动作中的事件写入、连通性更新、批次状态更新必须放在同一事务或等价原子操作中 |
| 外键约束 | 如果数据库支持外键，必须启用；如果不支持，应用层必须保证关联数据一致性 |
| 并发写入 | 必须避免多个写事务互相破坏；短暂锁冲突应等待或重试 |
| 崩溃恢复 | 启动时必须执行 `ingest_events` 和 `delivery_batches` 的恢复规则 |
| 启动恢复事务 | 启动恢复必须在单个事务中完成：先将 `created` / `sending` 批次标记为 `failed`，再将关联的 `delivering` 事件恢复为 `pending`，并写入错误原因与更新时间 |
| 网关归属校验 | 启动时必须校验 `schema_meta.gateway_id` 与当前运行配置中的 `gateway_id` 一致；不一致时拒绝启动，避免误用其他网关数据目录 |
| JSON 校验 | `mqtt_payload_json` 必须由应用层保证为 JSON 对象字符串；数据库层不强依赖 JSON 扩展 |
| 时间口径 | 运行时写入的时间字段使用 Unix 秒级时间戳 |
| 连通性判断时间 | 设备连通性判断只能使用 `gw_received_ts` / `gw_last_seen_ts`，不能使用设备上报的 `mqtt_payload_ts` |
| 设备时间用途 | `mqtt_payload_ts` 只用于排查设备时钟、识别旧数据和辅助调试，不作为设备连通性判定依据 |

### 7.2 SQLite 实现方式

当前 `v1.0.0-rc1` 设计以 SQLite 作为网关本地数据库实现。SQLite 连接建立后必须执行以下运行参数。

| 参数 | 建议值 | 说明 |
|---|---|---|
| `PRAGMA foreign_keys` | `ON` | 启用外键约束，保证 `delivery_batch_items` 与批次 / 事件表关联一致 |
| `PRAGMA journal_mode` | `WAL` | 使用 WAL 日志模式，提高读写并发与异常恢复能力 |
| `PRAGMA synchronous` | `NORMAL` | 在性能和可靠性之间折中；如部署环境对断电安全要求更高，可改为 `FULL` |
| `PRAGMA busy_timeout` | `5000` | 短暂锁冲突时最多等待 5000 ms，避免立即失败 |

建议初始化语句：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

说明：`journal_mode = WAL` 会生成 `-wal` 和 `-shm` 辅助文件，部署和清理脚本必须把这些文件视为 SQLite 数据库运行时文件的一部分。

### 7.3 运行参数语义

本节只描述网关本地数据库依赖的运行参数语义，不规定参数来源，不要求写入数据库，也不限制应用层使用配置文件、环境变量或后台下发配置实现。

参考值仅用于实现初始版本和测试，不属于数据库持久化 schema。正式默认值应由网关应用配置定义。

| 参数语义 | 参考值 | 说明 |
|---|---:|---|
| `max_delivered_event_retention_days` | `7` | `delivered` 事件默认保留天数 |
| `max_dropped_event_retention_days` | `7` | `dropped` 事件默认保留天数 |
| `max_failed_batch_retention_days` | `30` | `failed` 批次默认保留天数 |
| `max_succeeded_batch_retention_days` | `7` | `succeeded` 批次默认保留天数 |
| `max_local_db_size_mb` | `512` | 本地数据库建议容量上限；超过后优先清理已成功投递和已丢弃的历史数据 |
| `max_mqtt_payload_json_bytes` | `16384` | 单条 `mqtt_payload_json` 的 UTF-8 字节上限 |
| `max_delivery_err_msg_chars` | `1024` | `delivery_err_msg` 的字符上限 |
| `max_delivery_attempts` | `10` | 单条事件最大上传尝试次数；达到后标记为 `dropped` |
| `delivery_retry_base_delay_s` | `5` | 上传失败后的基础退避时间，单位秒 |
| `delivery_retry_max_delay_s` | `300` | 上传失败后的最大退避时间，单位秒 |
| `delivery_batch_max_events` | `500` | 单个批次最多包含的事件数量，对应队列领取查询中的 `LIMIT N` |
| `delivery_flush_interval_s` | `1` | 上传 worker 空闲时检查并刷新队列的参考间隔 |
| `delivery_http_timeout_s` | `5` | 单次批量上报 HTTP 请求超时时间 |
| `delivery_worker_count` | `1` | 上传 worker 数量；可大于 `1`，但必须遵守队列领取事务约束 |
| `connectivity_timeout_s` | `30` | 判定设备不可达的超时时间；用于计算 `timeout_cutoff = 当前 Unix 秒 - connectivity_timeout_s` |
| `connectivity_scan_interval_s` | `5` | 扫描 `device_connectivity` 并生成不可达事件的参考间隔 |

### 7.4 SQLite 维护策略

SQLite WAL 模式适合网关本地运行库，但长期运行后需要配合维护动作控制文件大小。

| 维护动作 | 触发时机 | 说明 |
|---|---|---|
| `PRAGMA wal_checkpoint(TRUNCATE)` | 低峰期、停机维护、清理大量历史数据后 | 截断 WAL 文件，避免 `-wal` 长期膨胀 |
| `VACUUM` | 维护窗口 | 回收主数据库文件空间；不应放在高频运行路径中执行 |
| 容量复查 | 清理历史数据后 | 如果数据库仍超过容量阈值，可触发维护流程或继续按丢弃策略降级 |

说明：维护动作属于运行流程，不改变表结构。部署和运维脚本执行维护动作前应确保不会与高频写入任务冲突。

## 8. 索引设计

### 8.1 索引总览

| 索引 | 表 | 字段 | 主要作用 | 重要性 |
|---|---|---|---|---|
| `idx_ingest_events_pending` | `ingest_events` | `delivery_state`, `delivery_next_attempt_at`, `id` | 按重试时间和本地顺序读取待上传事件 | 必需 |
| `idx_ingest_events_device` | `ingest_events` | `gateway_id`, `gym_id`, `device_type`, `device_id`, `id` | 查询单台设备的本地事件历史 | 建议 |
| `idx_ingest_events_cleanup_delivered` | `ingest_events` | `delivery_state`, `delivery_delivered_at` | 清理已成功投递的旧事件 | 建议 |
| `idx_ingest_events_cleanup_dropped` | `ingest_events` | `delivery_state`, `updated_at` | 清理已丢弃的旧事件 | 建议 |
| `idx_device_connectivity_scan` | `device_connectivity` | `connectivity_state`, `gw_last_seen_ts` | 扫描超时未上报设备 | 必需 |
| `idx_delivery_batches_state` | `delivery_batches` | `batch_state`, `created_at` | 查询和清理成功 / 失败批次历史 | 建议 |
| `idx_delivery_batch_items_event` | `delivery_batch_items` | `gw_event_id` | 查询单条事件参与过的上传批次 | 建议 |

### 8.2 `idx_ingest_events_pending`

```sql
CREATE INDEX idx_ingest_events_pending
ON ingest_events(delivery_state, delivery_next_attempt_at, id);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 先按 `delivery_state` 筛选事件状态，再按 `delivery_next_attempt_at` 跳过未到重试时间的事件，最后按 `id` 保持本地入库顺序 |
| 主要查询 | `delivery_state = 'pending' AND (delivery_next_attempt_at IS NULL OR delivery_next_attempt_at <= now) ORDER BY id ASC LIMIT N` |
| 使用场景 | 上传任务从本地队列中取出待上传事件 |
| 重要性 | 必需 |

典型查询：

```sql
SELECT *
FROM ingest_events
WHERE delivery_state = 'pending'
  AND (delivery_next_attempt_at IS NULL OR delivery_next_attempt_at <= ?)
ORDER BY id ASC
LIMIT 500;
```

说明：该索引优先服务“跳过未到重试时间的事件”。如果实际队列规模较小，或实现更强调严格按 `id ASC` 的入库顺序扫描，也可以保留核心队列索引 `(delivery_state, id)`，将 `delivery_next_attempt_at` 作为应用层过滤条件。具体实现可根据压测结果选择单索引或双索引，但必须保持语义：未到 `delivery_next_attempt_at` 的事件不得被领取。

### 8.3 `idx_ingest_events_device`

```sql
CREATE INDEX idx_ingest_events_device
ON ingest_events(gateway_id, gym_id, device_type, device_id, id);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 按网关、场馆、设备类型和设备 ID 定位单台设备，再按 `id` 查看事件顺序 |
| 主要查询 | 查询某台设备的本地事件历史 |
| 使用场景 | 排查某台设备上报、不可达、恢复连通、上传失败等问题 |
| 重要性 | 建议 |

典型查询：

```sql
SELECT *
FROM ingest_events
WHERE gateway_id = ?
  AND gym_id = ?
  AND device_type = ?
  AND device_id = ?
ORDER BY id ASC;
```

### 8.4 `idx_ingest_events_cleanup_delivered`

```sql
CREATE INDEX idx_ingest_events_cleanup_delivered
ON ingest_events(delivery_state, delivery_delivered_at);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 先筛选 `delivered` 事件，再按 `delivery_delivered_at` 找出超过保留期的事件 |
| 主要查询 | `delivery_state = 'delivered' AND delivery_delivered_at <= retention_cutoff` |
| 使用场景 | 清理已成功上传且超过保留期的历史事件 |
| 重要性 | 建议 |

典型查询：

```sql
SELECT *
FROM ingest_events
WHERE delivery_state = 'delivered'
  AND delivery_delivered_at <= ?
ORDER BY delivery_delivered_at ASC
LIMIT 1000;
```

### 8.5 `idx_ingest_events_cleanup_dropped`

```sql
CREATE INDEX idx_ingest_events_cleanup_dropped
ON ingest_events(delivery_state, updated_at);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 先筛选 `dropped` 事件，再按 `updated_at` 找出超过保留期的事件 |
| 主要查询 | `delivery_state = 'dropped' AND updated_at <= retention_cutoff` |
| 使用场景 | 清理已明确丢弃且超过保留期的历史事件 |
| 重要性 | 建议 |

典型查询：

```sql
SELECT *
FROM ingest_events
WHERE delivery_state = 'dropped'
  AND updated_at <= ?
ORDER BY updated_at ASC
LIMIT 1000;
```

### 8.6 `idx_device_connectivity_scan`

```sql
CREATE INDEX idx_device_connectivity_scan
ON device_connectivity(connectivity_state, gw_last_seen_ts);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 先筛选 `connected` 设备，再按 `gw_last_seen_ts` 找出超过超时时间的设备 |
| 主要查询 | `connectivity_state = 'connected' AND gw_last_seen_ts <= timeout_cutoff` |
| 使用场景 | 网关定期扫描设备连通性，生成 `disconnected` 状态事件和 `device_offline` 告警 |
| 重要性 | 必需 |

典型查询：

```sql
SELECT *
FROM device_connectivity
WHERE connectivity_state = 'connected'
  AND gw_last_seen_ts <= ?
ORDER BY gw_last_seen_ts ASC;
```

说明：查询参数为 `当前 Unix 秒 - timeout_s`。

### 8.7 `idx_delivery_batches_state`

```sql
CREATE INDEX idx_delivery_batches_state
ON delivery_batches(batch_state, created_at);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 按批次状态筛选，再按创建时间查看历史 |
| 主要查询 | 查询最近失败 / 成功批次，或清理超过保留期的历史批次 |
| 使用场景 | 运维排查后台不可用、HTTP 错误、上传超时；清理成功或失败的历史上传批次 |
| 重要性 | 建议 |

典型查询：

```sql
SELECT *
FROM delivery_batches
WHERE batch_state = 'failed'
ORDER BY created_at DESC
LIMIT 20;
```

清理查询：

```sql
SELECT *
FROM delivery_batches
WHERE batch_state IN ('succeeded', 'failed')
  AND created_at <= ?
ORDER BY created_at ASC
LIMIT 1000;
```

说明：`idx_delivery_batches_state` 同时服务历史查询和清理查询，不需要创建重复字段的第二个物理索引。

### 8.8 `idx_delivery_batch_items_event`

```sql
CREATE INDEX idx_delivery_batch_items_event
ON delivery_batch_items(gw_event_id);
```

| 项目 | 说明 |
|---|---|
| 负责范围 | 根据 `gw_event_id` 反向查询该事件进入过哪些批次 |
| 主要查询 | 查询某条事件的投递历史 |
| 使用场景 | 排查某条事件是否多次重试、最终在哪个批次成功或失败 |
| 重要性 | 建议 |

典型查询：

```sql
SELECT b.*
FROM delivery_batch_items i
JOIN delivery_batches b ON b.batch_id = i.batch_id
WHERE i.gw_event_id = ?
ORDER BY b.created_at ASC;
```

说明：`delivery_batch_items` 的主键 `(batch_id, gw_event_id)` 已适合查询某个批次内的事件；该索引用于反向查询某条事件的批次历史。
