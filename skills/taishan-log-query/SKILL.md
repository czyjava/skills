---
name: taishan-log-query
description: 通过泰山 logcenter 纯 HTTP 查询日志时使用。适用于用户要求查看某个服务、某个环境的业务日志或访问日志，按 server、warning、error 过滤业务日志，按 host/path/method/status 过滤访问日志，或需要输出完整日志接口请求和响应；不得依赖浏览器登录态，必须使用 Cookie Header 调用接口。
---

# 泰山日志查询 Skill

## 使用原则

- 必须通过 HTTP 请求调用 logcenter，不依赖浏览器操作或浏览器登录态。
- Cookie 从环境变量 `TAISHAN_COOKIE` 或当前项目 `.agent-state/taishan-agent/cookie` 读取；输出时始终脱敏。
- Cookie 失效时先运行 `auth refresh-cookie`，由脚本打开 Chrome 等待扫码并自动保存，不要求用户手工粘贴。
- 飞书通知通过 `lark-cli` 发出；飞书 app 凭据和登录态由 `lark-cli` 自己管理，不写入本仓库。
- 默认输出简洁摘要和日志列表；用户要求“完整调用日志/完整响应”时加 `--full`。
- 日志正文可能包含用户 ID、URL、token 等敏感信息，输出前必须经过脚本脱敏。

## Cookie 自动刷新

当 logcenter 返回统一登录页、401、403 或提示 Cookie 失效时，运行：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py auth refresh-cookie
```

脚本会：

- 打开 Chrome 到泰山页面。
- 等待用户扫码完成登录。
- 从 Chrome 本地 Cookie 数据库读取并解密白名单 Cookie：默认只取 `__CLIENT_USER_TOKEN__`。
- 用 logcenter 业务日志接口校验 Cookie 可用。
- 保存到当前项目 `.agent-state/taishan-agent/cookie`，文件权限为 `0600`。

如果 Chrome 已经登录，也可以不打开浏览器，直接读取并校验：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py auth refresh-cookie --no-open
```

该能力依赖 macOS Chrome profile 和 Keychain 中的 `Chrome Safe Storage`，不会输出或提交 Cookie 明文。

## 业务日志

默认查询 `pixel-studio` 生产环境最近 60 分钟、返回 5 条：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-log-query
```

查询指定服务和环境：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-log-query \
  --app-id 83 \
  --service pixel-studio \
  --env production \
  --level warning \
  --minutes 30 \
  --limit 20
```

业务日志级别：

- `server`：映射到 Loki label `log_file_name="server"`。
- `warning`：映射到日志正文过滤 `|=\`WARN\``。
- `error`：映射到日志正文过滤 `|=\`ERROR\``。

## Error 日志巡检和飞书通知

查询最近 5 分钟业务 `error` 日志；如果没有日志，只输出 `notification.reason=no_error_logs`，不会发飞书：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
  --app-id 83 \
  --service pixel-studio \
  --env production \
  --feishu-user-id "$TAISHAN_FEISHU_USER_ID"
```

如果没有提前配置 `TAISHAN_FEISHU_USER_ID`，脚本会尝试用 `lark-cli contact +search-user --query '陈致远'` 查找 open_id；同名或查找失败时，改用显式 `--feishu-user-id`。

手动验证但不实际发消息：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
  --service pixel-studio \
  --env production \
  --feishu-user-id "$TAISHAN_FEISHU_USER_ID" \
  --dry-run
```

如果需要证明巡检一直在跑，可以加 `--send-ok`。无 error 时也会发一条“巡检正常”消息；有 error 时仍发送告警。自动化场景建议加 `--ok-interval-minutes 30`，让每 5 分钟巡检最多每 30 分钟发一次正常心跳：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
  --service pixel-studio \
  --env production \
  --send-ok \
  --ok-interval-minutes 30
```

飞书 error 告警只发送同类异常聚合摘要，不发送异常原文。重复出现的同一问题族由 Incident Router 更新 `.agent-state/wmxs-agent/incident-ledger.json` 和报告，不应每次重复触发排障。

当某个问题族进入排障闭环时，先提 issue；真正修复必须从远程 `origin/master` 新建修复分支，完成后向远程 `origin/test` 发 MR，并把 MR 链接发给用户。

自动分期闭环由两步驱动：

1. `incident_router_agent.py next-issue --project <项目名> --limit <N>`：批量认领新增问题族；认领前必须检查 GitLab 现有 Issue 是否已经覆盖同类问题，已有覆盖时只回写 `duplicate`/`issueUrl`，不得重复创建 Issue；确实未覆盖时才创建 GitLab Issue。每个 Issue 仍只对应一个问题族，不得改代码。
2. `incident_router_agent.py next-fix --project <项目名> --limit <M>`：并行认领已有 `issueUrl` 的问题族进入修复；每个修复线程只处理一个 familyKey，没有 Issue 时返回 `issue_required`。

同一个 familyKey 不重复创建 Issue 或修复线程；语义相同但 familyKey 不同的问题也必须先复用已有 Issue，不得重复创建。不同未覆盖问题族可以同时创建 Issue，也可以并行修复。

飞书相关配置：

- `TAISHAN_LARK_CLI`：可选，默认 `lark-cli`；也可以设置为 `npx @larksuite/cli@latest`。
- `TAISHAN_FEISHU_USER_ID`：推荐，陈致远的飞书 open_id。
- `TAISHAN_FEISHU_CHAT_ID`：可选，如果要发到群聊而非个人。
- `TAISHAN_FEISHU_USER_NAME`：可选，未配置 open_id 时用于搜索用户，默认 `陈致远`。
- `TAISHAN_FEISHU_AS`：可选，默认 `bot`，也可设为 `user`。

真实接口：

```text
GET https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/query-range.htm
```

## 访问日志

访问日志和业务日志共用 logcenter Cookie，但接口和参数格式不同。访问日志至少要指定 `--host`、`--query` 或 `--profile-id` 之一。

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py access-log-query \
  --service pixel-studio \
  --env production \
  --host pixel-studio.wanmeixiangsu.cn,pixel-studio.ppixels.com,pixel-studio.wmxs-inc.cn \
  --minutes 30 \
  --limit 20
```

精确复现控制台时间窗口：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py access-log-query \
  --service pixel-studio \
  --host pixel-studio.wanmeixiangsu.cn,pixel-studio.ppixels.com,pixel-studio.wmxs-inc.cn \
  --start-time '2026-06-09 18:35:12' \
  --end-time '2026-06-09 18:50:19' \
  --limit 25
```

可按路径、方法、状态码继续过滤：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py access-log-query \
  --service pixel-studio \
  --host pixel-studio.wanmeixiangsu.cn,pixel-studio.ppixels.com,pixel-studio.wmxs-inc.cn \
  --path /api/open/order \
  --method POST \
  --status 500
```

真实接口：

```text
POST https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query.htm
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
```

核心参数：

```text
appName=<service>
startTime=<YYYY-MM-DD HH:mm:ss>
endTime=<YYYY-MM-DD HH:mm:ss>
q=<访问日志查询条件>
page=<页码>
limit=<条数>
```

Host 条件按前端格式生成：

```text
has(["pixel-studio.wanmeixiangsu.cn","pixel-studio.ppixels.com","pixel-studio.wmxs-inc.cn"],request_host)
```

## 通用参数

- `--service` / `--eng-name`：服务英文名，例如 `pixel-studio`。
- `--env`：环境标签，例如 `production`、`test`；业务日志会用于 Loki `profile`。
- `--minutes`：向前查询多少分钟，默认 `60`。
- `--lag-seconds`：默认时间窗口距离当前时间的延迟秒数，访问日志默认 `180`，用于避开最新索引边界。
- `--start-time` / `--end-time`：精确时间窗口，格式 `YYYY-MM-DD HH:mm:ss`。
- `--limit`：展示日志条数；访问日志后端按前端习惯至少请求 `25` 条，再在摘要中截断展示。
- `--full`：输出完整接口响应和 stats。
