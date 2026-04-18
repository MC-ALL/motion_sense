# Docker Compose 正式部署目录

本目录预留给 Linux + Docker 的正式部署编排。

- `docker-compose.yaml`：仓库级整栈 Compose 入口。
- 根文件使用 Compose `include` 聚合各模块 Compose，要求 Docker Compose `2.20.3+`。
- `../runtime/`：宿主机挂载的统一运行时目录，首次启动后由各容器自行生成配置与数据文件。

约束：
- `deployment/runtime/` 下不提交口令、证书、token 等敏感数据。
- 配置模板统一来自各模块 `deployment/*/defaults/default_*`。
- 允许热重载的配置由各模块文档单独说明；其余修改后需要重启对应容器。
