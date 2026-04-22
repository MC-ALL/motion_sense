# ops_observer

`ops_observer/` 存放独立的运维观测聚合模块源码入口，当前只有一个可运行模块 `api_service/`。

## 目录功能

- 聚合运维观测模块源码与说明。
- 对 backend 与 gateway 的自观测接口做统一汇聚。
- 约定部署资产位于仓库根目录 `deployment/ops_observer/`。

## 目录结构

- `api_service/`：运维聚合 FastAPI 服务。
- `README.md`：目录入口说明。

## 模块功能

- 拉取 backend 与 gateway 的 `/ops/v1/*`。
- 订阅上游 `/ops/ws`，在上游快照变化时加速刷新。
- 对网页端提供统一的健康摘要、组件明细、告警与统计接口。

## 接口约束

- 上游模块信息、健康模型与输出字段统一以 [design/09-运维观测端.md](/home/circuitx/Work/motion_sense/design/09-运维观测端.md) 和 [design/07-通讯接口定义.md](/home/circuitx/Work/motion_sense/design/07-通讯接口定义.md) 为准。
- 当前聚合依赖 backend JWT 参数与 gateway ops token 的运行时回填。

## 测试流程

```bash
# 从仓库根目录执行
python3 -m compileall ops_observer/api_service/app
docker run --rm -v "$PWD:/workspace" -w /workspace/ops_observer/api_service python:3.13-slim sh -lc "pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple .[dev] >/tmp/pip.log && pytest tests/unit -q"
```

## 部署流程

- 镜像与默认配置位于 `deployment/ops_observer/`。
- Linux 正式部署由 `deployment/ops_observer/compose/docker-compose.yaml` 启动。
- 整栈联调统一走仓库根 `deployment/compose/` 或 `deployment/container/`。

## 后续改进

- 丰富运维告警阈值的运行时调节能力。
- 增加更细的模块可观测性与日志采集对接。
- 增补更全面的聚合层测试与故障演练脚本。
