# deployment runtime

`deployment/runtime/` 是整套系统唯一的共享运行时目录，用于承载配置、密钥、证书和本地数据。

## 目录功能

- 为 backend、gateway、ops_observer、web 提供统一的宿主机挂载入口。
- 保存首次启动后生成的正式配置与运行时产物。
- 隔离仓库源码与部署期敏感信息。

## 目录结构

- `config/`：运行时配置文件。
- `secrets/`：口令、token、密码文件。
- `certs/`：证书与私钥。
- `data/`：本地持久化数据，如 `ops_observer.sqlite3`。

## 使用要求

- 本目录默认不提交运行时产物，`.gitignore` 只放行说明文件本身。
- 正式配置必须由各模块 `default_*` 模板或启动脚本生成，不直接手工复制旧环境文件。
- 外部 AI provider token 推荐写入 `secrets/backend_ai_api_key.txt`。
- backend 与 edge_processor 共享的命令通道 token 默认位于 `secrets/backend_gateway_command_token.txt`，由 backend 首启自动生成。
- 启用 MQTT TLS 时，需要在 `certs/` 投放 `server.crt`、`server.key`、`ca.crt`。

## 环境与基础设施要求

- 宿主机需保证该目录对 Docker bind mount 可读写。
- 若启用更严格权限策略，需要额外校验 `secrets/` 与 `certs/` 的属主和权限。

## 后续改进

- 增加 runtime 资产完整性检查脚本。
- 继续细化密钥和证书的初始化与轮换手册。
