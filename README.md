# motion_sense

`motion_sense` 是一个面向校园/场馆运动感知场景的整栈仓库，当前包含网关、后台、网页端、运维观测端、设备模拟器，以及 Linux Docker Compose 与 Apple `container` 两套部署/联调入口。

## 仓库功能

- `gateway/`：网关侧代码，包含边缘处理服务与 MQTT 设备模拟器。
- `backend/`：后台业务服务代码，负责鉴权、入库、设备管理、训练档案与 AI 报告。
- `ops_observer/`：运维观测聚合服务代码，统一汇聚 backend 与 gateway 的健康状态。
- `web/`：业务与运维一体化门户前端代码。
- `deployment/`：唯一部署目录，存放镜像构建资产、Compose 编排、联调脚本与默认配置模板。
- `design/`：设计资料目录，存放系统总览、模块设计、接口契约、排期与 AI 接入草案。

## 目录结构

```text
.
├── backend/
│   └── api_service/
├── deployment/
│   ├── backend/
│   ├── compose/
│   ├── container/
│   ├── gateway/
│   ├── ops_observer/
│   ├── runtime/
│   └── web/
├── design/
├── gateway/
│   ├── device_simulator/
│   └── edge_processor/
├── ops_observer/
│   └── api_service/
└── web/
    └── portal_app/
```

## 模块入口

- [backend/README.md](backend/README.md)
- [gateway/README.md](gateway/README.md)
- [ops_observer/README.md](ops_observer/README.md)
- [web/README.md](web/README.md)
- [deployment/README.md](deployment/README.md)
- [design/README.md](design/README.md)

## 当前实现边界

- 已完成 `04/05/06/09` 第一轮主链路：MQTT 上报、网关缓冲与补发、后台入库、实时推送、网页展示、运维健康聚合。
- 已完成后台 JWT、用户/设备管理、手环绑定、训练会话自动汇聚与训练档案查询。
- 已完成后台到网关的配置命令主链路升级：在线网关通过专用 WebSocket 收到 `command_ready` 后立即补拉 pending，长连接异常时仍保留轮询兜底。
- 已完成 AI 报告最小可用闭环：训练档案页可发起分析，后台可基于训练会话自动生成中文报告，支持内置规则生成器和 OpenAI 兼容外部模型，网页端可查看列表/详情并重新生成；当前已改为“首次加载 + WebSocket 状态推进 + 重连后单次 REST 补同步”，并补齐 Redis 多实例唤醒与原子状态抢占，仍不支持流式输出。
- 已完成 Linux Compose 单端口同源代理，适合远端 Linux 主机通过 SSH 端口转发访问网页。

## 未来计划

- 生产化收尾：MQTT TLS 投放与校验、Mosquitto 权限资产初始化、Linux 上线/回滚/排障手册补齐。
- AI 后台增强：将当前进程内 worker 继续演进到独立队列或独立进程，补细失败分类、重试与恢复策略。
- AI 报告体验增强：补训练时间线、结构化证据视图、更细的生成阶段说明；流式输出仅作为后续增强项，不是当前主路径。
- 可观测性补强：继续增加关键错误、重试次数、队列堆积与基础设施异常的观测口径。

## 快速验证

代码级验证：

```bash
python3 -m compileall backend/api_service/app gateway/edge_processor/app ops_observer/api_service/app
docker run --rm -v "$PWD:/workspace" -w /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
docker run --rm -v "$PWD:/workspace" -w /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
docker run --rm -v "$PWD:/workspace" -w /workspace/gateway/device_simulator python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
docker run --rm -v "$PWD:/workspace" -w /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
docker run --rm -v "$PWD:/workspace" -w /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"
```

以上命令默认从仓库根目录执行；若本机安装了 Apple `container`，也可以将 `docker run` 替换为等价的 `container run` 做本地联调。

整栈验证：

```bash
sh deployment/compose/start_stack.sh
sh deployment/compose/verify_ops_auth_stack.sh
sh deployment/compose/verify_system_stack.sh
sh deployment/compose/verify_gateway_batch_stack.sh
sh deployment/compose/verify_training_archive_stack.sh
sh deployment/compose/verify_workout_aggregation_stack.sh
sh deployment/compose/verify_ai_stack.sh
sh deployment/compose/verify_database_stack.sh
sh deployment/compose/stop_stack.sh
```

## 约束

- Python 服务保持异步优先，配置键、消息字段、主题参数统一使用 `snake_case`。
- 部署资产只放在根目录 `deployment/`，不要在源码目录旁追加散落脚本。
- 首次启动生成的正式配置必须来源于各模块 `default_*` 模板。
- 不提交口令、token、证书、`.env` 与 `deployment/runtime/` 中的运行时产物。
- REST 路径、MQTT topic、字段名以 [design/07-通讯接口定义.md](design/07-通讯接口定义.md) 为准。
- 涉及 `04/05/06/09` 任一实现变更时，需要同步检查对应设计文档与 [design/08-开发排期.md](design/08-开发排期.md)。
