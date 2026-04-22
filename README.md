# motion_sense

`motion_sense` 是一个面向校园 / 场馆运动感知场景的整栈仓库，当前包含网关、后台、网页端、运维观测端、设备模拟器，以及 Linux Docker Compose 与 Apple `container` 两套部署 / 联调入口。

## 仓库功能

- `gateway/`：网关侧代码，包含边缘处理服务与 MQTT 设备模拟器。
- `backend/`：后台业务服务代码，负责鉴权、入库、设备管理、训练档案与 AI 报告。
- `ops_observer/`：运维观测聚合服务代码，统一汇聚 backend 与 gateway 的健康状态。
- `web/`：业务与运维一体化门户前端代码。
- `deployment/`：唯一部署目录，存放镜像构建资产、Compose 编排、联调脚本与默认配置模板。
- `design/`：设计资料目录，存放模块设计、接口契约、进展记录与 AI 接入草案。

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

## 设计文档入口

- [design/04-网关端.md](design/04-%E7%BD%91%E5%85%B3%E7%AB%AF.md)：网关职责、边缘规则、命令链路与运行边界
- [design/05-后台端.md](design/05-%E5%90%8E%E5%8F%B0%E7%AB%AF.md)：后台数据模型、实时链路、AI 基线与权限模型
- [design/06-网页端.md](design/06-%E7%BD%91%E9%A1%B5%E7%AB%AF.md)：页面结构、状态模型、权限边界与接入规范
- [design/07-通讯接口定义.md](design/07-%E9%80%9A%E8%AE%AF%E6%8E%A5%E5%8F%A3%E5%AE%9A%E4%B9%89.md)：唯一接口契约来源
- [design/08-开发排期.md](design/08-%E5%BC%80%E5%8F%91%E6%8E%92%E6%9C%9F.md)：当前进展、验证状态与后续计划
- [design/09-运维观测端.md](design/09-%E8%BF%90%E7%BB%B4%E8%A7%82%E6%B5%8B%E7%AB%AF.md)：运维聚合边界、鉴权关系与限制
- [design/10-AI前端接入草案.md](design/10-AI%E5%89%8D%E7%AB%AF%E6%8E%A5%E5%85%A5%E8%8D%89%E6%A1%88.md)：AI 前端交互的当前范围与演进草案

## 当前实现边界

- 已完成 `04/05/06/09` 第一轮主链路：MQTT 上报、网关缓冲与补发、后台入库、实时推送、网页展示、运维健康聚合。
- 已完成后台 JWT、用户 / 设备管理、手环绑定、训练会话自动汇聚与训练档案查询。
- 已完成后台到网关的配置命令主链路：在线网关通过专用 WebSocket 收到 `command_ready` 后立即补拉 pending，长连接异常时保留轮询兜底。
- 已完成 AI 报告最小可用闭环：训练档案页可发起分析，后台可基于训练会话自动生成中文报告，支持内置规则生成器和 OpenAI 兼容外部模型，网页端可查看列表 / 详情并重新生成。
- 已完成 Linux Compose 单端口同源网页入口，适合远端 Linux 主机通过 SSH 端口转发访问。

当前未完成边界：
- AI 流式输出尚未实现，`ai_chunk` 仅保留契约。
- 设备配置命令仍缺设备侧 ACK，后台目前只能确认“网关已执行 / 已转发”。
- 运维观测当前只聚合网关与后台自观测接口，不采集日志。

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
- REST 路径、MQTT topic、字段名以 [design/07-通讯接口定义.md](design/07-%E9%80%9A%E8%AE%AF%E6%8E%A5%E5%8F%A3%E5%AE%9A%E4%B9%89.md) 为准。
- 涉及 `04/05/06/09` 任一实现变更时，需要同步检查对应设计文档与 [design/08-开发排期.md](design/08-%E5%BC%80%E5%8F%91%E6%8E%92%E6%9C%9F.md)。
