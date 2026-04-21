# Repository Guidelines

## 关键路径
- 总览与当前范围：`README.md`、`docs/00-系统总览.md`
- 网关设计：`docs/04-网关端.md`
- 后台设计：`docs/05-后台端.md`
- 网页端设计：`docs/06-网页端.md`
- 接口契约：`docs/07-通讯接口定义.md`
- 当前进展：`docs/08-开发排期.md`
- 运维观测：`docs/09-运维观测端.md`
- 部署规范：`deployment/README.md`、`deployment/container/README.md`、`deployment/compose/README.md`

## 项目结构
- `gateway/edge_processor/app/`：04 网关异步服务；测试在 `gateway/edge_processor/tests/`
- `gateway/device_simulator/app/`：MQTT 联调用模拟器；测试在 `gateway/device_simulator/tests/`
- `backend/api_service/app/`：05 后台异步 FastAPI；测试在 `backend/api_service/tests/`
- `ops_observer/api_service/app/`：09 运维观测端；测试在 `ops_observer/api_service/tests/`
- `web/portal_app/src/`：06 网页端 React + Vite
- `deployment/gateway/`、`deployment/backend/`、`deployment/ops_observer/`、`deployment/web/`：模块部署资产
- `deployment/container/`：Apple `container` 整栈联调入口
- `deployment/compose/docker-compose.yaml`：Linux + Docker 正式部署入口
- `deployment/runtime/`：唯一运行时目录

## 开发与验证
- `python3 -m compileall backend/api_service/app gateway/edge_processor/app ops_observer/api_service/app`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"`
- `sh deployment/container/build_local_images.sh && sh deployment/gateway/container/prepare_runtime.sh && sh deployment/container/start_local_stack.sh && sh deployment/container/verify_regression_stack.sh && sh deployment/container/stop_local_stack.sh`

## 约束
- Python 服务优先保持异步架构；模块名、配置键、消息字段统一使用 `snake_case`
- 所有部署资产只放在根 `deployment/`，不在源码目录旁散落脚本
- 首次运行生成的正式配置必须来自 `default_*`
- 禁止提交证书、口令、token、`.env` 等敏感文件
- REST 路径、MQTT topic、字段名必须与 `docs/07-通讯接口定义.md` 一致
- 涉及 `04/05/06/09` 任一实现变更时，至少同步检查对应设计文档与 `docs/08-开发排期.md`

## 当前工作记忆
- 已完成：`04/05/06/09` 第 1 迭代核心链路、权限模型、健康观测、Apple `container` 整栈回归
- 已完成：部署目录统一重构为 `deployment/<module>/` + 仓库级 `deployment/container/`、`deployment/compose/`、单一 `deployment/runtime/`
- 已完成：Linux 正式 Compose 已跑通 `start_stack.sh`、`verify_ops_auth_stack.sh`、`verify_system_stack.sh`、`verify_training_archive_stack.sh`、`verify_workout_aggregation_stack.sh`，当前适合作为远端 Linux 主机的正式开发/验收入口
- 已完成：网页端已切到 Nginx 单端口同源代理，适合 SSH 单端口转发访问；后台与 `ops_observer` 默认强制鉴权已开启
- 已完成：训练档案聚合、设备管理中的手环绑定维护、训练会话自动汇聚 / 手动回填已落地，管理员/教师/学生的页面与接口权限边界已联通
- 已完成：后台 AI 已从 `501 reserved` 预留接口推进到真实 `queued` 报告基线；`POST /api/v1/ai/analyze`、`GET /api/v1/ai/reports`、`GET /api/v1/ai/reports/{report_id}` 已落库并在 Linux Compose 运行栈复验通过
- 已完成：文档已同步到当前结构与当前实现口径，重点包括 AI `queued` 基线、`ops_observer` 聚合健康、训练档案与 Linux Compose 正式部署流程

## 下一步
- 迁移前在目标主机执行 `docker compose -f deployment/compose/docker-compose.yaml config`，确认 Compose `include` 可用
- Linux 正式部署时补齐 Mosquitto `acl.conf`、`passwd`、证书文件的属主与权限初始化
- 继续工作时优先做迁移验证、整栈起栈回归，再进入剩余生产化收尾
- 后台 AI 的下一阶段工作聚焦：异步 worker / 任务队列、状态流转、模型推理接入、流式输出、失败重试与正式报告内容回填
- 网页端 AI 的下一阶段工作聚焦：报告详情页异常态、生成中状态、人工验收清单，以及与后续流式输出链路对齐
- 生产化剩余收尾聚焦：MQTT TLS 证书投放与权限检查、上线验收/回滚手册继续细化、必要时补充更多运维适配器或日志采集能力

## 提交规范
- 使用带 scope 的 Conventional Commits，例如 `feat(gateway): add health reporter`
- 提交前清理临时文件、停掉容器
- PR 说明至少写明：改动目的、影响模块、文档是否同步、本地验证结果
