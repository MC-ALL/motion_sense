# Linux Server Init Checklist

适用范围：
- 目标环境为 Linux 主机
- 部署方式为 Docker Compose
- 项目根目录包含 `deployment/compose/docker-compose.yaml`

本文只覆盖主机初始化，不替代正式起栈与验收流程。
正式操作顺序见 `deployment/compose/RUNBOOK.md`。

## 1. 主机基础信息确认

- 确认目标主机 IP、主机名、时区、SSH 登录方式
- 确认磁盘空间足够容纳镜像、容器卷与 `deployment/runtime/`
- 确认系统时间准确，避免 JWT、日志时间与健康判定异常

建议执行：

```bash
hostnamectl
timedatectl
df -h
free -h
```

## 2. Docker 与 Compose 安装确认

最低要求：
- Docker Engine 可用
- Docker Compose 支持 `include`
- 建议 Docker Compose `2.20.3+`

建议执行：

```bash
docker version
docker compose version
docker compose -f deployment/compose/docker-compose.yaml config >/tmp/motion_sense.compose.config.yaml
```

预期结果：
- `docker` 与 `docker compose` 命令可执行
- `config` 退出码为 `0`
- 没有 `include`、相对路径、变量解析错误

## 3. 仓库目录与权限确认

确认仓库已放置在稳定路径，例如：

```text
/opt/motion_sense
```

确认部署用户对以下目录具有读写权限：
- 仓库根目录
- `deployment/runtime/`
- Docker socket 所在组权限

建议执行：

```bash
pwd
id
ls -ld .
ls -ld deployment deployment/runtime
```

## 4. 运行时目录初始化预期

Linux Compose 首启前无需手工创建完整运行时树。
根 Compose 中的 `runtime_init` 会自动创建并放宽以下目录：

- `deployment/runtime/config/`
- `deployment/runtime/secrets/`
- `deployment/runtime/certs/`
- `deployment/runtime/data/ops_observer/`

但仍建议确认 `deployment/runtime/` 本身存在并可写：

```bash
mkdir -p deployment/runtime
test -w deployment/runtime
```

## 5. 端口占用检查

默认会占用以下宿主机端口：
- `1883` MQTT
- `5432` TimescaleDB / PostgreSQL
- `6379` Redis
- `8000` Backend API
- `8080` Web Portal
- `8090` Ops Observer API
- `8181` InfluxDB

建议执行：

```bash
ss -ltnp | egrep ':1883|:5432|:6379|:8000|:8080|:8090|:8181'
```

要求：
- 若这些端口已有现网服务占用，必须先改端口映射或调整部署主机
- 不要在起栈后才处理端口冲突

## 6. 防火墙与访问面确认

按当前默认部署，通常只需要按实际访问面开放：
- `8080/tcp` 网页端单入口
- `1883/tcp` MQTT 接入

以下端口通常只建议内网或仅主机侧使用：
- `8000/tcp`
- `8090/tcp`
- `5432/tcp`
- `6379/tcp`
- `8181/tcp`

要求：
- 浏览器访问场景优先只暴露 `8080`，通过同源代理转发 backend 与 `ops_observer`
- `8000`、`8090` 仅在需要直连 API / 运维接口时再开放到受控来源
- 如果数据库与 Redis 不需要对外访问，应通过主机防火墙或安全组限制来源
- 不要默认把 `5432`、`6379`、`8181` 暴露到公网

## 7. 镜像拉取与网络连通性确认

确认主机可以正常访问你当前配置的镜像源与依赖源。

建议执行：

```bash
docker pull python:3.13-slim
docker pull redis:8.6-alpine
docker pull eclipse-mosquitto:2.1-alpine
docker pull influxdb:3.9-core
docker pull timescale/timescaledb:latest-pg17
docker pull nginx:1.29-alpine
docker pull node:24-alpine
```

要求：
- 至少确认基础镜像能拉取
- 若需要代理或镜像源，先在主机 Docker 侧配置完成，再进行项目起栈

## 8. 必要密钥与凭据策略确认

当前正式部署中，以下内容默认可首启自动生成：
- 后台 bootstrap admin 密码
- 后台 JWT `access_secret` / `refresh_secret`
- 网关 ops token
- InfluxDB admin token
- Mosquitto `mosquitto.passwd`
- 网页端 `runtime_config.js`

当前需要你在部署策略上明确的内容：
- `BACKEND_DATABASE_PASSWORD`
- `MOSQUITTO_USER`
- `MOSQUITTO_PASSWORD`
- 是否启用 MQTT TLS
- 网页端是否继续使用默认同源配置（推荐），还是显式改成实际域名 / IP / 路径前缀

要求：
- 正式环境不要长期保留默认数据库密码 `change_me_at_deploy`
- 正式环境不要长期保留默认 MQTT 账号 `admin` / `admin123`

## 9. MQTT TLS 预检查

仅在启用 MQTT TLS 时执行。

Mosquitto 配置若启用 `listener 8883`，入口脚本会强制检查以下文件：
- `deployment/runtime/certs/server.crt`
- `deployment/runtime/certs/server.key`
- `deployment/runtime/certs/ca.crt`

要求：
- 三个文件必须存在
- 文件内容必须与 broker 配置匹配
- 文件权限与属主需满足 Mosquitto 读取要求

建议执行：

```bash
ls -l deployment/runtime/certs
```

## 10. 首次启动后必须核对的运行时文件

起栈完成后，至少确认以下文件已经生成：

- `deployment/runtime/config/backend/api_service/app_settings.yaml`
- `deployment/runtime/config/backend/api_service/bootstrap_admin.txt`
- `deployment/runtime/config/influxdb/admin_token.txt`
- `deployment/runtime/config/web/portal_app/runtime_config.js`
- `deployment/runtime/secrets/backend_gateway_command_token.txt`
- `deployment/runtime/secrets/edge_processor_ops_token.txt`
- `deployment/runtime/secrets/mosquitto.passwd`

若启用 TLS，再确认：
- `deployment/runtime/certs/server.crt`
- `deployment/runtime/certs/server.key`
- `deployment/runtime/certs/ca.crt`

## 11. 进入正式起栈

完成本清单后，按以下文档继续：

- `deployment/compose/RUNBOOK.md`
- `deployment/compose/README.md`
