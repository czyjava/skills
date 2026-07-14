---
name: wanmeixiangsu-server-ssh
description: Use when the user asks to SSH, inspect, operate, redeploy, or troubleshoot 47.251.185.234 / us-codex, especially decoration-assistant da-v1, v1-da-cx.ppixels.com, Caddy, systemd, FastAPI, or related wanmeixiangsu / ppixels production deployment work.
---

# 完美像素远程服务器 SSH 与部署

## 适用范围

用于登录和操作这台远程服务器，以及部署当前 `decoration-assistant` 装修助手后端：

- 公网 IP：`47.251.185.234`
- SSH 用户：`root`
- 私钥路径：`/Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608`
- 已验证主机名：`us-codex`
- 已验证登录命令：

```bash
ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608 root@47.251.185.234
```

不要用这个 skill 登录 `chenzhiyuan@47.251.185.234`、`ubuntu@47.251.185.234`、`admin@47.251.185.234` 或 `ecs-user@47.251.185.234`；这些用户已验证会被公钥拒绝。

## 装修助手 da-v1 部署事实

飞书文档《codex服务器部署》和远端只读检查确认：

| 项 | 值 |
| --- | --- |
| 服务名 | `da-v1` |
| 描述 | 装修助手后端 |
| 远端代码目录 | `/data/decoration-assistant` |
| 后端工作目录 | `/data/decoration-assistant/backend` |
| 运行端口 | `127.0.0.1:8002` |
| systemd 服务 | `/etc/systemd/system/da-v1.service` |
| 环境变量文件 | `/data/decoration-assistant/prod.env` |
| 数据目录 | `/data/decoration-assistant-data` |
| 静态资源目录 | `/data/decoration-assistant/frontend/dist` |
| 外部域名 | `v1-da-cx.ppixels.com` |
| Caddy 反代 | `reverse_proxy 127.0.0.1:8002` |

当前远端还同时有照片编辑器服务：

- `cpe-v1`：`/data/codex-photo-editor/backend`，监听 `127.0.0.1:8001`。
- 部署 `decoration-assistant` 时不要改动 `cpe-v1`、`/data/codex-photo-editor` 或 `127.0.0.1:8001`。

## 安全规则

- 只引用私钥路径，不读取、不打印、不复制私钥正文。
- 不把私钥、公钥、token、密码、环境变量密文写入仓库、日志、session 或最终回复。
- 首次进入服务器先执行只读探测命令，不直接做部署、重启、删除、覆盖配置等高风险操作。
- 执行部署前先确认当前目录、用户、Git 状态、进程状态和目标服务；涉及生产变更时先向用户说明将执行的命令。
- 输出日志时隐藏密钥、token、Cookie、Authorization、数据库密码等敏感字段。
- 部署时必须保留远端 `/data/decoration-assistant/prod.env` 和 `/data/decoration-assistant-data`，不要用本地 `.env` 或示例配置覆盖生产配置。
- 远端 `/data/decoration-assistant` 可能因目录 owner 触发 Git `dubious ownership`；默认不要依赖远端 `git pull`，优先用本地已验证代码 `rsync` 部署。

## 默认登录检查

先用无交互方式确认连接和身份：

```bash
ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608 \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new \
  root@47.251.185.234 \
  'printf "whoami="; whoami; printf "hostname="; hostname; printf "pwd="; pwd'
```

期望看到：

```text
whoami=root
hostname=us-codex
```

## da-v1 只读现状检查

部署或排障前先跑：

```bash
ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608 root@47.251.185.234 '
  printf "%s\n" "-- identity --"
  whoami; hostname; pwd
  printf "%s\n" "-- paths --"
  ls -ld /data /data/decoration-assistant /data/decoration-assistant/backend /data/decoration-assistant-data 2>/dev/null || true
  printf "%s\n" "-- service --"
  systemctl is-enabled da-v1.service 2>&1 || true
  systemctl is-active da-v1.service 2>&1 || true
  systemctl status da-v1.service --no-pager -l 2>/dev/null | sed -n "1,40p" || true
  printf "%s\n" "-- ports --"
  ss -lntp | grep -E ":8002|:80|:443" || true
  printf "%s\n" "-- caddy --"
  systemctl is-active caddy 2>&1 || true
'
```

健康检查需要读取远端 `APP_AUTH_TOKEN`，但不要输出 token：

```bash
ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608 root@47.251.185.234 '
  TOKEN=$(awk -F= '\''$1=="APP_AUTH_TOKEN"{print substr($0,length($1)+2)}'\'' /data/decoration-assistant/prod.env)
  curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8002/healthz
'
```

期望至少包含：

```json
{"ok":true,"service":"decoration-assistant","backend":"codex","version":"v1","app_server":{"alive":true}}
```

## 远程操作方式

单条命令优先使用这种形式，便于保留本地审计上下文：

```bash
ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608 root@47.251.185.234 '<command>'
```

需要连续排查或部署时，可以开交互式 SSH；进入后先记录当前目录和关键状态：

```bash
pwd
hostname
whoami
ls -la
```

## 推荐重新部署流程

默认采用“本地构建 + rsync 覆盖代码 + 保留远端配置/数据 + 重启 `da-v1`”：

1. 本地确认当前仓库状态、分支、commit 和测试结果。
2. 如前端需要随版本发布，在本地 `frontend` 执行 `npm install` / `npm run build`，生成 `frontend/dist`。
3. 远端备份当前代码目录，例如 `/data/decoration-assistant-backup-<timestamp>`；备份代码即可，生产数据目录保持原位。
4. 用 `rsync` 从本机同步当前项目到 `/data/decoration-assistant/`，必须排除：
   - `.git/`
   - `.venv/`
   - `data/`
   - `.env`
   - `prod.env`
   - `node_modules/`
   - `__pycache__/`
   - `.DS_Store`
5. 远端执行依赖安装：`cd /data/decoration-assistant/backend && .venv/bin/pip install -r requirements.txt`。
6. 重启服务：`systemctl restart da-v1.service`。
7. 验证 `systemctl status da-v1.service`、本机 `8002 /healthz`、`journalctl -u da-v1.service -n 100`，再验证外部域名。

示例 `rsync` 命令：

```bash
rsync -avz --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='.env' \
  --exclude='prod.env' \
  --exclude='node_modules/' \
  --exclude='__pycache__/' \
  --exclude='.DS_Store' \
  -e "ssh -i /Users/chenzhiyuan/.ssh/id_ed25519_wanmeixiangsu_server_20260608" \
  /Users/chenzhiyuan/work/codes/wmxs/agent/decoration-assistant/ \
  root@47.251.185.234:/data/decoration-assistant/
```

`--delete` 只在确认排除项完整、且目标目录确实是 `/data/decoration-assistant/` 时使用；不确定时先加 `--dry-run`。

## 部署前检查清单

在远程服务器上做部署前至少确认：

- 当前要部署的服务、目录、分支或镜像来源。
- 现有进程和端口占用，例如 `ps`、`systemctl status`、`docker ps`、`ss -lntp`。
- 配置文件和 `.env` 是否已存在，避免覆盖生产凭据。
- 是否需要备份当前版本或保留回滚命令。
- 部署后如何验证，例如健康检查 URL、日志关键字、端口监听、进程状态。
- 当前服务是否已有用户流量或正在运行中的长任务；如有，先向用户说明重启影响。

## da-v1 服务与环境参考

远端 `da-v1.service` 当前结构：

```ini
[Service]
User=root
WorkingDirectory=/data/decoration-assistant/backend
EnvironmentFile=/data/decoration-assistant/prod.env
Environment=PATH=/root/.nvm/versions/node/v24.15.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/data/decoration-assistant/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8002
Restart=on-failure
```

远端 `prod.env` 关键非敏感配置：

```text
IMAGE_BACKEND=codex
DATA_DIR=/data/decoration-assistant-data
CODEX_CMD=/root/.nvm/versions/node/v24.15.0/bin/codex
SERVE_STATIC_DIR=/data/decoration-assistant/frontend/dist
APP_VERSION=v1
WORKER_CONCURRENCY=10
IMAGE_SET_TURN_CONCURRENCY=1
IMAGE_SET_SESSION_CONCURRENCY=2
IMAGE_SET_GLOBAL_CONCURRENCY=4
MAX_TURN_RETRIES=1
TURN_TIMEOUT_SECONDS=600
MAX_UPLOAD_MB=20
WORKSPACE_TTL_DAYS=30
LOG_FORMAT=json
LOG_LEVEL=INFO
CORS_ORIGINS=https://v1-da-cx.ppixels.com
CODEX_REASONING_EFFORT=medium
```

`APP_AUTH_TOKEN` 存在但必须脱敏。

## 常见问题

- `Permission denied (publickey)`：优先确认是否误用了非 `root` 用户，或远端是否移除了 root 用户的 `authorized_keys`。
- 连接超时：先测 `nc -vz -G 8 47.251.185.234 22`，再判断是网络、安全组、防火墙还是服务器 SSH 服务问题。
- 主机指纹变化：停止操作，提示用户确认是否服务器重装或 IP 被复用；不要自动覆盖 `known_hosts`。
- `git dubious ownership`：不要急着 `git config --global --add safe.directory`；部署优先走本地 `rsync`，避免远端 Git 状态成为发布前置条件。
- `healthz app_server.alive=false`：先看 `journalctl -u da-v1.service -n 100 --no-pager`，重点关注 `codex app-server`、`CODEX_CMD`、`/root/.codex/auth.json` 和网络错误。
- 外部域名异常但本机 `8002` 正常：检查 `systemctl status caddy`、`/etc/caddy/Caddyfile`、Caddy 日志和 DNS；不要改 Python 服务。
