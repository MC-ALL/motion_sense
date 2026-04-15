# Repository Guidelines

## 项目结构与模块组织
仓库同时包含需求文档与第 1 迭代实现代码：
- `docs/`：系统总览、01-06 子系统规格、07 接口契约、08 排期、09 运维观测端设计。
- `gateway/edge_processor/app/`：04 网关端异步服务源码；部署文件在 `gateway/deployment/`。
- `backend/api_service/app/`：05 后台端异步 FastAPI 服务；部署文件在 `backend/deployment/`。
- `ops_observer/api_service/app/`：09 运维观测端异步 FastAPI 服务；部署文件在 `ops_observer/deployment/`。
- `web/portal_app/`：06 网页端 React + Vite 前端；部署文件在 `web/deployment/`。

修改实现时，至少同步检查 `docs/04-网关端.md`、`docs/05-后台端.md`、`docs/07-通讯接口定义.md`；涉及运维健康时还要同步 `docs/09-运维观测端.md` 与 `docs/06-网页端.md`。

## 构建、测试与开发命令
- `rg -n "TODO|FIXME|待补充" docs gateway backend ops_observer web`：扫描待补项。
- `python3 -m compileall backend/api_service/app gateway/edge_processor/app ops_observer/api_service/app`：快速做语法检查。
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`：运行后台单测。
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/gateway/edge_processor python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`：运行网关单测。
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"`：运行运维观测端单测。
- `container run --remove --volume "$PWD:/workspace" --workdir /workspace/web/portal_app node:24-alpine sh -lc "npm ci && npm run build"`：按锁文件构建网页端。
- `sh gateway/deployment/container/build_local_images.sh && sh gateway/deployment/container/prepare_runtime.sh && sh gateway/deployment/container/start_local_stack.sh && sh gateway/deployment/container/verify_system_stack.sh && sh gateway/deployment/container/stop_local_stack.sh`：运行 Apple `container` 本地整栈联调。
- `sh ops_observer/deployment/container/verify_ops_observer_api.sh`：校验运行中的运维观测端基础 REST 接口。

## 代码风格与命名规范
- Python 服务优先保持异步架构，配置键、模块名、消息字段统一使用 `snake_case`。
- 部署相关文件一律放在各模块自己的 `deployment/` 下，不在仓库根目录散落脚本。
- 首次运行生成的运行时文件必须来自 `default_*` 模板。
- 严禁提交证书、口令文件、运行期 token、`.env` 或其他敏感数据。
- REST 路径、MQTT topic、字段名必须与 `docs/07-通讯接口定义.md` 保持一致。

## 测试规范
- 修改后台逻辑后，至少运行后台单测；修改网关逻辑后，至少运行网关单测。
- 涉及配置下发时，重点验证“后台建单 -> 网关轮询 -> 本地执行/转发 -> 结果回报”闭环。
- 涉及接口契约变更时，必须同步更新文档示例与字段说明。

## 提交与合并请求规范
使用带 scope 的 Conventional Commits，例如 `feat(gateway): add health reporter`、`fix(backend): persist config commands`。PR 说明应包含：改动目的、影响模块、文档是否同步、以及本地验证结果（如 `pytest`、Apple `container` 联调）。
