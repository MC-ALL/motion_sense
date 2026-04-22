# Repository Guidelines

## 关键路径
- 总览与仓库入口：`README.md`
- 设计资料总览：`design/README.md`
- 系统总览：`design/00-系统总览.md`
- 网关设计：`design/04-网关端.md`
- 后台设计：`design/05-后台端.md`
- 网页端设计：`design/06-网页端.md`
- 接口契约：`design/07-通讯接口定义.md`
- 当前进展：`design/08-开发排期.md`
- 运维观测设计：`design/09-运维观测端.md`
- AI 前端接入草案：`design/10-AI前端接入草案.md`
- 部署目录：`deployment/README.md`、`deployment/container/README.md`、`deployment/compose/README.md`

## 项目结构
- `gateway/edge_processor/app/`：网关异步服务；测试在 `gateway/edge_processor/tests/`
- `gateway/device_simulator/app/`：MQTT 联调用模拟器；测试在 `gateway/device_simulator/tests/`
- `backend/api_service/app/`：后台异步 FastAPI；测试在 `backend/api_service/tests/`
- `ops_observer/api_service/app/`：运维观测聚合 FastAPI；测试在 `ops_observer/api_service/tests/`
- `web/portal_app/src/`：React + Vite 前端
- `deployment/backend/`、`deployment/gateway/`、`deployment/ops_observer/`、`deployment/web/`：各模块部署资产
- `deployment/container/`：Apple `container` 本地整栈联调入口
- `deployment/compose/docker-compose.yaml`：Linux + Docker 正式部署入口
- `deployment/runtime/`：唯一运行时目录
- `design/`：系统设计、接口契约、排期与接入草案

## 开发与验证
- `python3 -m compileall backend/api_service/app gateway/edge_processor/app ops_observer/api_service/app`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/gateway/device_simulator python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"`
- `sh deployment/container/build_local_images.sh && sh deployment/gateway/container/prepare_runtime.sh && sh deployment/container/start_local_stack.sh && sh deployment/container/verify_regression_stack.sh && sh deployment/container/stop_local_stack.sh`

## 约束
- Python 服务优先保持异步架构；模块名、配置键、消息字段统一使用 `snake_case`
- 所有部署资产只放在根 `deployment/`，不在源码目录旁散落脚本
- 首次运行生成的正式配置必须来自 `default_*`
- 禁止提交证书、口令、token、`.env` 与 `deployment/runtime/` 中的敏感产物
- REST 路径、MQTT topic、字段名必须与 `design/07-通讯接口定义.md` 一致
- 涉及 `04/05/06/09` 任一实现变更时，至少同步检查对应设计文档与 `design/08-开发排期.md`

## 当前工作记忆
- 已完成 `04/05/06/09` 第一迭代核心链路、权限模型、健康观测、Apple `container` 整栈回归
- 已完成部署目录统一重构为 `deployment/<module>/`、仓库级 `deployment/container/`、`deployment/compose/` 与单一 `deployment/runtime/`
- 已完成 Linux Compose 路径上的 `start_stack.sh`、`verify_ops_auth_stack.sh`、`verify_system_stack.sh`、`verify_gateway_batch_stack.sh`、`verify_training_archive_stack.sh`、`verify_workout_aggregation_stack.sh`、`verify_ai_stack.sh`
- 已完成单端口同源网页入口、后台与 `ops_observer` 强制鉴权、训练档案聚合、设备管理中的手环绑定维护
- 已完成后台 AI `queued -> generating -> completed/failed` 基线、重新生成接口、多实例唤醒与网页 AI 报告详情页联通
- 已完成网关批量上报的最小聚合窗口与阈值触发优化，以及网页端“WebSocket 重连后单次 REST 补同步”策略

## 下一步
- 以 `design/08-开发排期.md` 的“2026-04-22 后续工作计划”作为统一后续计划入口；完成一轮工作后先同步回查文档口径
- 在目标主机执行 `docker compose -f deployment/compose/docker-compose.yaml config`，先确认 Compose `include` 可用
- Linux 正式部署时补齐 Mosquitto `acl.conf`、`passwd`、证书文件的属主与权限初始化
- 继续优先做迁移验证、整栈起栈回归，再进入生产化收尾
- 后台 AI 下一阶段聚焦独立队列化、失败恢复与正式报告内容增强；流式输出仅作为后续增强项
- 生产化剩余重点聚焦 MQTT TLS、上线/回滚手册与可观测性补强

## 提交规范
- 使用带 scope 的 Conventional Commits，例如 `feat(gateway): add health reporter`
- 提交前清理临时文件、停掉容器
- PR 说明至少写明：改动目的、影响模块、文档是否同步、本地验证结果
