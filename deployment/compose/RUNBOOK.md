# Linux Compose Runbook

适用范围：
- 目标环境为 Linux + Docker + Docker Compose v2
- 正式入口为 `deployment/compose/docker-compose.yaml`
- 推荐按本文顺序执行，不要跳步

相关文档：
- 主机初始化：`deployment/compose/SERVER_INIT_CHECKLIST.md`
- 变量与端口对照：`deployment/compose/PRODUCTION_REFERENCE.md`

## 0. 进入仓库

```bash
cd /path/to/motion_sense
```

## 1. 启动前检查

确认 Compose `include`、相对路径与变量解析正常：

```bash
docker compose -f deployment/compose/docker-compose.yaml config >/tmp/motion_sense.compose.config.yaml
```

预期结果：
- 命令退出码为 `0`
- 没有 `include`、路径、变量解析错误

如需启用外部 AI 提供方，再额外准备 token 文件：

```bash
sh deployment/compose/write_backend_ai_api_key.sh
```

若 `deployment/runtime/` 由 root 初始化过，改用：

```bash
sudo sh deployment/compose/write_backend_ai_api_key.sh
```

推荐同时在 `deployment/runtime/config/backend/api_service/app_settings.yaml` 中保持：

```yaml
ai:
  provider: openai_compatible
  base_url: https://api.deepseek.com/v1
  model_variant: reasoner
  model: null
  api_key: null
```

说明：
- token 文件由后台容器在启动时自动读取，不需要把明文写入仓库内 YAML
- 常规切换推荐只改 `model_variant`：`reasoner` 或 `chat`
- 如需使用厂商新模型名，再显式写 `model`
- 如需改路径，可额外设置 `BACKEND_AI_API_KEY_FILE`
- 如未投放 token 文件，后台会继续使用内置规则化生成器离线生成报告
- 如已启动栈并修改了 `deployment/runtime/config/backend/api_service/app_settings.yaml`，需执行 `docker compose -f deployment/compose/docker-compose.yaml up -d --build backend_api_service` 使配置生效
- `deepseek-reasoner` 仍走 OpenAI 兼容的 `chat/completions` 路径，不需要改成其他 REST endpoint

如果只想一条命令切换模型档位，可直接执行：

```bash
sh deployment/compose/switch_backend_ai_model.sh reasoner
sh deployment/compose/switch_backend_ai_model.sh chat
```

如 `deployment/runtime/` 由 root 初始化过，可改用：

```bash
sudo sh deployment/compose/switch_backend_ai_model.sh reasoner
```

## 2. 正式起栈

```bash
sh deployment/compose/start_stack.sh
```

预期结果：
- 打印 `runtime init ready: runtime_init`
- 打印各关键服务 `service ready: ... (healthy)`
- 打印 `compose services:`
- 打印 `bootstrap info:`
- 打印 `stack summary:`

## 3. 记录首登信息

```bash
sh deployment/compose/print_bootstrap_credentials.sh
```

记录以下信息：
- 后台 bootstrap admin 用户名与密码
- 网关 ops token

## 4. 运维鉴权验收

```bash
sh deployment/compose/verify_ops_auth_stack.sh
```

预期结果：
- 后台管理员登录通过
- 网关 ops token 校验通过
- `ops_observer` 管理员 JWT 校验通过
- gateway / `ops_observer` 运维 WebSocket 鉴权通过

## 5. 业务链路验收

```bash
sh deployment/compose/verify_system_stack.sh
```

预期结果：
- 设备入库通过
- 健康聚合通过
- 配置命令闭环通过
- 网页入口与运维聚合视图通过

## 6. 数据链路验收

```bash
sh deployment/compose/verify_database_stack.sh
```

预期结果：
- refresh session 通过
- TimescaleDB 写入与查询通过
- Redis 链路通过
- Influx 缓冲与补发通过

## 6.1 训练档案验收

```bash
sh deployment/compose/verify_training_archive_stack.sh
```

预期结果：
- 学生训练档案聚合通过
- 设备管理页中的手环绑定 / 解绑链路通过
- 学生自助查看训练档案链路通过

## 6.2 训练会话汇聚验收

```bash
sh deployment/compose/verify_workout_aggregation_stack.sh
```

预期结果：
- `binding/unbind` 事件自动汇聚通过
- 管理员手动回填训练会话通过
- 训练档案汇总可见自动汇聚结果

## 6.3 AI 报告验收

如需验证 AI 自动报告闭环：

```bash
sh deployment/compose/verify_ai_stack.sh
```

预期结果：
- 训练会话自动汇聚通过
- AI 报告从 `queued` 推进到 `completed`
- 报告包含摘要、观察结论、建议与证据训练会话
- 网页 AI 报告详情路由可正常加载

## 7. 浏览器人工验收

打开：

```text
http://127.0.0.1:8080/
```

人工检查：
- 使用 bootstrap admin 登录网页端
- “健康中心”显示 backend / gateway 为 `healthy`
- “训练档案”可以正常展示绑定与训练摘要
- “AI 报告”可以打开已完成报告详情
- 关键业务页面可以正常加载

## 8. TLS 补充验收

仅在启用 MQTT TLS 时执行：
- 检查 `deployment/runtime/certs/`
- 确认证书文件存在：`server.crt`、`server.key`、`ca.crt`
- 确认属主与权限符合 Mosquitto 要求

## 快速排障

先看服务状态：

```bash
docker compose -f deployment/compose/docker-compose.yaml ps
```

若首启卡住，先看：

```bash
docker compose -f deployment/compose/docker-compose.yaml logs runtime_init
```

若某个服务不健康，查看单服务日志：

```bash
docker compose -f deployment/compose/docker-compose.yaml logs --tail=120 backend_api_service
docker compose -f deployment/compose/docker-compose.yaml logs --tail=120 gateway_edge_processor
docker compose -f deployment/compose/docker-compose.yaml logs --tail=120 ops_observer_api_service
docker compose -f deployment/compose/docker-compose.yaml logs --tail=120 web_portal_app
```

若表现为鉴权异常，先执行：

```bash
sh deployment/compose/print_bootstrap_credentials.sh
sh deployment/compose/verify_ops_auth_stack.sh
```

若表现为业务链路异常，再执行：

```bash
sh deployment/compose/verify_system_stack.sh
```

若表现为训练档案、绑定维护或训练会话摘要异常，再执行：

```bash
sh deployment/compose/verify_training_archive_stack.sh
sh deployment/compose/verify_workout_aggregation_stack.sh
```

若表现为 AI 报告状态异常、内容异常或网页 AI 报告详情异常，再执行：

```bash
sh deployment/compose/verify_ai_stack.sh
```

若表现为数据库或补发异常，再执行：

```bash
sh deployment/compose/verify_database_stack.sh
```

## 停栈

正常停栈：

```bash
sh deployment/compose/stop_stack.sh
```

仅在明确需要清空时才使用：

```bash
PURGE_VOLUMES=true sh deployment/compose/stop_stack.sh
PURGE_RUNTIME=true sh deployment/compose/stop_stack.sh
```
