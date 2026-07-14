---
name: taishan-app-info
description: 通过泰山系统查询指定应用信息时使用。适用于用户给出泰山应用 ID、engName、登录后 URL，或要求查看像素工坊等 wanmeixiangsu 泰山应用的部署、域名、资源、K8S、数据库连接概览；必须保护 Cookie、token、密码、数据库凭据等敏感信息。
---

# 泰山应用信息查询 Skill

## 使用原则

- 默认使用中文输出应用摘要。
- Cookie、token、密码、数据库连接串等敏感值不得写入日志、知识库、commit 或最终回答。
- 如果读取到泰山登录后 URL，先用脚本解析并脱敏，不直接展示原始 URL。
- 如果需要直接调用 HTTP 接口，Cookie 从环境变量 `TAISHAN_COOKIE` 或当前项目 `.agent-state/taishan-agent/cookie` 读取。
- 真实执行时不得依赖浏览器登录态；Agent 环境可能没有浏览器，必须由脚本发起 HTTP 请求。

## 快速流程

0. 查看当前 Skill 支持的能力：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py capabilities
   ```

1. 如果用户提供登录后 URL，运行：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py summarize-url --url '<登录后URL>'
   ```

2. 如果用户提供 Cookie，先安全保存：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py auth set-cookie
   ```

   按提示粘贴完整 `Cookie` Header 值。脚本会保存到当前项目 `.agent-state/taishan-agent/cookie` 并设置 `0600` 权限。

   如果不想手工粘贴 Cookie，可以让脚本打开 Chrome 等待扫码并自动保存：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py auth refresh-cookie
   ```

   该命令默认只从 Chrome 读取 `__CLIENT_USER_TOKEN__`，会先用 logcenter 校验通过再写入本机私有文件。

3. 如果已确认应用详情接口模板，设置：

   ```bash
   export TAISHAN_APP_DETAIL_URL_TEMPLATE='https://example/api/app/detail?id={id}'
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py fetch-app --id 83
   ```

4. 使用五个内置能力之一生成接口 URL 或发起查询：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py capability-url \
     --capability SQL执行记录查看 \
     --id 83 \
     --eng-name pixel-studio \
     --template 'https://example/api/sql/records?appId={id}&engName={engName}'
   ```

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py capability-fetch \
     --capability 业务日志查询 \
     --id 83 \
     --eng-name pixel-studio \
     --param keyword=error
   ```

5. 业务日志查询已经确认真实接口，可直接纯 HTTP 调用并查看脱敏后的请求和响应：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-log-query \
     --app-id 83 \
     --service pixel-studio \
     --env production \
     --level warning \
     --minutes 60 \
     --limit 5
   ```

   该命令会请求 `https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/query-range.htm`，Cookie 只通过 Header 发送，输出时固定显示为 `[REDACTED]`。

   最近 5 分钟 error 日志巡检可直接调用；只有查到日志才会通过 `lark-cli` 发飞书。飞书消息只发送同类异常聚合摘要，不发送异常原文：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
     --app-id 83 \
     --service pixel-studio \
     --env production \
     --feishu-user-id "$TAISHAN_FEISHU_USER_ID"
   ```

   调试飞书集成时先加 `--dry-run`。`TAISHAN_LARK_CLI` 可配置为 `lark-cli` 或 `npx @larksuite/cli@latest`；未配置 `TAISHAN_FEISHU_USER_ID` 时会尝试按姓名 `陈致远` 搜索接收人。

   如果需要定期证明巡检仍在运行，可以加 `--send-ok`。无 error 时也会发送“巡检正常”消息，有 error 时仍发送告警。自动化里建议加 `--ok-interval-minutes 30`，避免每 5 分钟都发正常消息：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
     --app-id 83 \
     --service pixel-studio \
     --env production \
     --send-ok \
     --ok-interval-minutes 30
   ```

   如果要把巡检结果交给通用排障 Agent，增加 `--project` 和 `--event-output`。该文件只包含脱敏后的统一事件，可继续交给 Incident Router：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py biz-error-monitor \
     --app-id 83 \
     --service pixel-studio \
     --env production \
     --project pixel-studio \
     --event-output /tmp/taishan-pixel-studio-error-event.json

   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/agents/incident-router/scripts/incident_router_agent.py route \
     --input /tmp/taishan-pixel-studio-error-event.json \
     --threshold 1 \
     --dedupe-window-minutes 30
   ```

   访问日志使用同一个 logcenter Cookie，但走独立接口：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py access-log-query \
     --service pixel-studio \
     --env production \
     --host pixel-studio.ppixels.com \
     --minutes 60 \
     --limit 5
   ```

6. 如果接口模板缺失，才使用浏览器登录泰山并打开页面做接口发现：

   ```text
   https://taishan.wanmeixiangsu.cn/#taishan.H0001?id=<应用ID>
   ```

   页面跳转后，读取当前 URL，用 `summarize-url` 解析脱敏结果。

## SQL 查询闭环

这些命令通过 `server-manager.wanmeixiangsu.cn` 的 Taishan 接口执行，不依赖浏览器登录态。所有请求都从 `TAISHAN_COOKIE` 或当前项目 `.agent-state/taishan-agent/cookie` 读取 Cookie，输出时脱敏。

1. 查询应用可选数据库，拿到数据库 `index`：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-dbs \
     --app-id 83
   ```

2. 每次查询前先确认权限；已有有效权限会跳过申请，没有权限才提交申请：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-permission-ensure \
     --app-id 83 \
     --db-index 2 \
     --apply-hours 2 \
     --remark '应用问题排查：确认任务状态'
   ```

   申请时长最长 12 小时；超过 12 小时会被脚本拒绝。调试请求但不实际提交时加 `--dry-run`；只检查权限不提交申请时加 `--no-apply`。

3. 申请后查看是否通过：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-query-apply-list \
     --app-id 83 \
     --db-name pixel_studio_db \
     --limit 20
   ```

   返回列表中的 `status` / `statusName` / `expireTime` 用于判断审批状态和权限有效期；审批未通过前不得绕过权限继续查询。

4. 审批通过后初始化受控 SQL 查询会话：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-init \
     --app-id 83 \
     --db-index 2
   ```

   保存返回的 `uuid`。

5. 执行受控只读 SQL 查询：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-query \
     --uuid '<uuid>' \
     --sql 'select id, status from task where id = 123'
   ```

   `SELECT` 会自动补 `LIMIT 100`；也可用 `--max-rows` 调整上限。只允许 `SELECT` / `SHOW` / `EXPLAIN`，禁止写 SQL、DDL、多语句和文件读写类 SQL。只做安全检查不实际查询时加 `--dry-run`。

6. 如果接口返回异步查询上下文，用结果命令继续取结果：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-query-result \
     --uuid '<uuid>' \
     --param queryId='<queryId>'
   ```

7. 排查结束关闭会话：

   ```bash
   python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-close \
     --uuid '<uuid>'
   ```

SQL 查询结果默认只输出摘要和脱敏后的行数据；需要真实响应结构排查时加 `--full`，仍会脱敏 Cookie、token、密码、手机号、邮箱等敏感字段。

如果明确需要手动提交申请，也可以直接调用：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py sql-query-apply \
  --app-id 83 \
  --db-index 2 \
  --apply-hours 2 \
  --remark '应用问题排查：确认任务状态'
```

## 五项能力

| 能力 | key | 接口模板环境变量 | 当前路由 |
| --- | --- | --- | --- |
| SQL执行记录查看 | `sql-exec-records` | `TAISHAN_SQL_EXEC_RECORD_URL_TEMPLATE` | `taishan.H0009` |
| SQL查询申请 | `sql-query-apply` | `TAISHAN_SQL_QUERY_APPLY_URL_TEMPLATE` | `taishan.H0008` 前置申请流程 |
| 受控SQL查询 | `controlled-sql-query` | `TAISHAN_CONTROLLED_SQL_QUERY_URL_TEMPLATE` | `taishan.H0008` |
| 业务日志查询 | `biz-log-query` | `TAISHAN_BIZ_LOG_QUERY_URL_TEMPLATE` | `taishan.H0036` |
| 访问日志查询 | `access-log-query` | `TAISHAN_ACCESS_LOG_QUERY_URL_TEMPLATE` | `taishan.H0033` |

接口模板支持 `{id}`、`{engName}` 以及 `--param key=value` 传入的任意占位符。所有占位符都会做 URL 编码。

如果只需要打开页面，可使用：

```bash
python3 /Users/chenzhiyuan/.agents/skills/taishan-app-info/scripts/taishan_app_agent.py capability-page \
  --capability SQL执行记录查看 \
  --id 83 \
  --eng-name pixel-studio
```

## 已确认接口

详细接口清单和前端消费的返回结构见 `/Users/chenzhiyuan/.agents/skills/taishan-app-info/docs/taishan-api-capabilities.md`。核心接口：

- SQL执行记录查看：`server/api/admin/sql-exec/list.htm`、`server/api/admin/sql-exec-record/list.htm`、`server/api/admin/sql-exec/view-sql.htm`。
- SQL查询申请：`server/api/admin/sql-query-approve/create.htm`、`server/api/admin/sql-query-approve/list.htm`、`server/api/admin/sql-query-approve/approve.htm`。
- 受控SQL查询：`server/api/admin/sql/init.htm`、`server/api/admin/sql/query.htm`、`server/api/admin/sql/get-result.htm`。
- 业务日志查询：`logcenter/api/admin/v2/biz-log/query-range.htm`、`logcenter/api/admin/v2/biz-log/label-values.htm`、`logcenter/api/admin/v2/log/query.htm`。
- 访问日志查询：`logcenter/api/admin/v2/log/query-column-list.htm`、`logcenter/api/admin/v2/log/query.htm`、`logcenter/api/admin/v2/log/download.htm`。

## 通用排障 Agent 接入

- 项目元信息放在 `configs/projects.example.json`，本机可复制为 `~/.config/wmxs-agent/projects.json` 后添加更多项目。
- 监控脚本只负责查询日志、发飞书和写统一事件；不读取业务代码、不访问数据库、不自动修复。
- 运行态文件统一放在当前项目 `.agent-state/`，不要放到用户级 `~/.config`。
- `/Users/chenzhiyuan/.agents/skills/taishan-app-info/agents/incident-router/scripts/incident_router_agent.py route` 会按问题族写入 `.agent-state/wmxs-agent/incident-ledger.json` 和汇总报告。
- 同一问题族重复出现时只更新次数、时间窗口和样本，不再重复触发新的排障 prompt。
- 只有新增问题族会在 `.agent-state/wmxs-agent/incidents/` 写入 `*.json` 和 `*.prompt.md`，后续由 Hub/人工统一决定是否启动排障 Agent。
- Troubleshooting Agent 第一阶段只能分析、给方案并提 issue；不得自动改代码、提交或推送，除非用户明确要求进入修复阶段。
- 进入修复阶段时，必须从远程 `origin/master` 新建修复分支；解决后推送分支，向远程 `origin/test` 发 MR，并把 MR 链接发给用户。
- 自动闭环先使用 `/Users/chenzhiyuan/.agents/skills/taishan-app-info/agents/incident-router/scripts/incident_router_agent.py next-issue --project <项目名> --limit <N>` 批量认领新增问题族。认领前必须检查 GitLab 现有 Issue 是否已覆盖同类问题；已有覆盖时只回写 `duplicate`/`issueUrl`，不得重复创建 Issue。确实未覆盖时才创建 GitLab Issue；每个 Issue 仍只对应一个问题族。
- Issue 创建成功并回写 `issueUrl` 后，使用 `next-fix --project <项目名> --limit <M>` 并行认领多个已有 Issue 的问题族进入修复；每个修复线程只处理一个 familyKey。
- `next-fix` 只处理已有 Issue 的问题族；没有 `issueUrl` 时返回 `issue_required`，不得创建修复分支或修改代码。

## 输出要求

- 优先输出：应用 ID、中文名、英文名、类型、环境、域名、内部域名、项目 ID、Git 项目 ID、资源规格、状态、标签、负责人、最近更新人和更新时间。
- 数据库、K8S、环境变量等信息只输出结构性摘要；字段值如命中 `password`、`token`、`secret`、`cookie`、`authorization`、`pwd` 必须显示为 `[REDACTED]`。
- 接口返回未登录、401 或 403 时，提示用户 Cookie 失效，需要重新扫码或提供新 Cookie。

## 当前已知

- 泰山外层入口：`https://taishan.wanmeixiangsu.cn/`
- 公共框架配置：`https://admin-appstore.wanmeixiangsu.cn/base2/framework.config.json`
- 框架静态配置不包含登录后的应用菜单；真实应用对象会在登录后路由参数 `app` 中出现。
- 已验证应用 `id=83` 对应 `pixel-studio / 像素工坊`，但不得保存或输出原始路由中的敏感配置。
