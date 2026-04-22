# backend

`backend/` 存放后台业务模块源码入口，当前只有一个可运行模块 `api_service/`。

## 目录功能

- 提供后台业务代码入口与模块级说明。
- 聚合后台 API、鉴权、训练档案、AI 报告相关实现。
- 约定后台部署资产位于仓库根目录 `deployment/backend/`。

## 目录结构

- `api_service/`：异步 FastAPI 服务。
- `README.md`：后台目录入口说明。

## 模块功能

当前后台负责：
- 网关批量入库 `POST /api/v1/ingest/batch`
- JWT 登录、刷新、退出
- 用户管理、设备管理、告警查询与确认
- 遥测历史查询、训练档案、训练会话聚合
- 手环绑定维护与绑定历史查询
- 业务 WebSocket 推送
- AI 报告创建、列表、详情与重新生成
- 后台自观测 `/ops/v1/*` 与 `/ops/ws`

## 接口约束

- 业务 REST、WebSocket、MQTT 映射统一以 [design/07-通讯接口定义.md](/home/circuitx/Work/motion_sense/design/07-通讯接口定义.md) 为准。
- 设备配置结果当前只能确认“网关已执行/已转发”，不代表设备最终 ACK。
- OTA 相关路由仍保留占位接口，不纳入当前实现范围。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall backend/api_service/app
docker run --rm -v "$PWD:/workspace" -w /workspace/backend/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 部署流程

- 镜像与默认配置位于 `deployment/backend/`。
- Linux 正式部署由 `deployment/compose/docker-compose.yaml` 聚合 `deployment/backend/compose/docker-compose.yaml`。
- 运行时配置与密钥统一落在 `deployment/runtime/`。

## 后续改进

- AI 从当前单进程自动消费推进到独立 worker / 队列化。
- 强化 refresh session 与审计持久化能力。
- 在不破坏接口契约的前提下补充更多后台集成测试。
