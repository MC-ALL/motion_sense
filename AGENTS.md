# 仓库协作规范

## 项目结构与模块组织

本仓库同时包含需求文档与第 1 迭代实现代码。

- `docs/`：系统架构、子系统规格、接口契约、开发排期
- `gateway/`：`04-网关端` 代码与部署资产，主服务位于 `gateway/edge_processor/app/`
- `backend/`：`05-后台端` 代码与部署资产，主服务位于 `backend/api_service/app/`

修改实现时，必须同步检查以下文档是否需要更新：

- `docs/04-网关端.md`
- `docs/05-后台端.md`
- `docs/07-通讯接口定义.md`

## 构建、测试与开发命令

- `container build --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim -t motion-sense-edge-processor-local -f gateway/deployment/edge_processor/Dockerfile .`
  用于构建网关本地测试镜像
- `container build --build-arg PYTHON_BASE=dockerproxy.net/library/python:3.13-slim -t motion-sense-backend-api-local -f backend/deployment/api_service/Dockerfile .`
  用于构建后台本地测试镜像
- `container run --remove ... pytest tests/unit -q`
  用于在镜像中运行 `gateway/edge_processor` 或 `backend/api_service` 单元测试
- `sh gateway/deployment/container/start_local_stack.sh`
  用于在 macOS 上启动网关到后台的本地联调链路
- `rg -n "TODO|FIXME|待补充" docs gateway backend`
  用于扫描待补项

## 代码风格与命名规范

- Python 服务优先保持异步架构，运行逻辑要直接、可运维
- Python 模块、配置键、消息字段、内部标识统一使用 `snake_case`
- 部署文件必须放在模块内的 `deployment/` 目录，不在仓库根目录散落脚本
- 首次运行生成的文件必须来自 `default_*` 模板
- 禁止提交密钥、证书、`passwd` 文件、运行期 token 等敏感数据
- API 路径与 MQTT Topic 必须与 `docs/07-通讯接口定义.md` 保持一致

## 测试规范

- 修改任一 Python 服务后，必须运行对应单元测试
- 修改网关逻辑时，优先验证 `mosquitto -> edge_processor -> backend` 本地链路
- 修改后台逻辑时，同时验证持久化行为与 WebSocket / 实时广播行为
- 如果接口契约变更，必须同步更新 `docs/04-05-07`

## 提交与合并请求规范

当前历史使用带 scope 的 Conventional Commits，例如：

- `feat(gateway): add influxdb replay buffer`
- `fix(gateway): fallback when delivery log is absent`
- `feat(backend): add redis realtime broadcast path`
- `chore(local): wire apple container stack to backend api`

提交合并请求时应说明：

- 改了什么，为什么改
- 影响到哪些模块与文档
- 是否影响接口契约或部署方式
- 本地做了哪些验证，如 `pytest`、Apple `container` 联调等
