# 边缘处理服务

这是网关侧的异步 Python 3.13 服务，负责 MQTT 数据接入、本地缓冲、规则判定，以及向后台批量上传。

当前实现要点：

- MQTT 订阅协程只负责快速解码与入缓冲，避免被单条 Influx 写入阻塞。
- Influx 本地缓冲先进入进程内队列，再按批量写入，相关参数见 `influxdb.write_queue_size`、`influxdb.write_batch_size`。
- 后台补发由独立批上传循环负责，默认通过 `/api/v1/ingest/batch` 上报。
