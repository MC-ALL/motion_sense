# ops_observer api_service

`ops_observer/api_service` 是独立的运维观测聚合 FastAPI 服务，负责统一汇聚后台与网关的健康与统计信息。

## 目录功能

- `app/api/`：健康检查与运维聚合接口。
- `app/services/`：上游轮询、WebSocket 订阅、SQLite 存储与本地广播。
- `tests/`：单元测试。
- `pyproject.toml`：包定义与依赖。

## 目录结构

- `app/main.py`：FastAPI 应用与生命周期。
- `app/settings.py`：运行时配置解析、上游回填与鉴权配置。
- `app/services/observer_service.py`：上游轮询与订阅主逻辑。
- `app/services/sqlite_store.py`：SQLite 存储实现。
- `app/services/auth_service.py`：JWT 校验。
- `tests/unit/test_ops_api.py`：聚合接口测试。

## 模块功能

- 轮询上游 `GET /ops/v1/health`、`GET /ops/v1/health/components`、`GET /ops/v1/stats`。
- 订阅上游 `WS /ops/ws`，在状态变化时刷新本地快照。
- 在上游开启鉴权时，自动使用后台 bootstrap admin 或 gateway ops token 完成访问。
- 把快照、组件状态、统计和运维告警持久化到 SQLite。
- 对外提供：
  - `GET /healthz`
  - `GET /api/v1/ops/health`
  - `GET /api/v1/ops/health/{module_id}`
  - `GET /api/v1/ops/alerts`
  - `PATCH /api/v1/ops/alerts/{alert_id}/close`
  - `GET /api/v1/ops/stats`
  - `WS /api/ws/ops`

## 接口约束

- 接口输出字段与权限约束以 [design/09-运维观测端.md](/home/circuitx/Work/motion_sense/design/09-运维观测端.md) 和 [design/07-通讯接口定义.md](/home/circuitx/Work/motion_sense/design/07-通讯接口定义.md) 为准。
- 运行时配置路径固定为 `/runtime/config/ops_observer/api_service/app_settings.yaml`。
- SQLite 数据路径默认 `/runtime/data/ops_observer/ops_observer.sqlite3`。
- 开启 `auth.enforce_rest/ws` 后，网页端必须使用后台 JWT 访问该服务。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall ops_observer/api_service/app
docker run --rm -v "$PWD:/workspace" -w /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 部署流程

1. 使用 `deployment/ops_observer/api_service/Dockerfile` 构建镜像。
2. 由 `deployment/ops_observer/api_service/entrypoint.sh` 生成默认运行时配置。
3. Linux 正式部署通过 `deployment/ops_observer/compose/docker-compose.yaml` 启动。
4. 本地专项验证可使用 `deployment/ops_observer/container/verify_ops_observer_api.sh`。

## 后续改进

- 增加更细粒度的告警阈值、静默策略与恢复判断。
- 增加更多聚合单元测试与跨模块故障回归。
- 补充与外部日志/指标系统的对接能力。
