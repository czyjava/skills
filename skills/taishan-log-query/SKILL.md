---
name: taishan-log-query
description: 通过 WMXS 泰山 Agent API 查询业务日志和访问日志。适用于按应用、时间窗口、日志级别、路径或状态码排查线上异常；必须在 mucang-server 使用项目根目录 ./wmxs taishan，禁止切换到其它认证或接口链路。
---

# 泰山日志查询

## 硬性边界

- 默认在远程服务器 `mucang-server` 执行。
- 固定工作目录为 `/data/projects/wmxs/wm-dev-server`。
- 唯一入口是 `./wmxs taishan biz-log` 和 `./wmxs taishan access-log`。
- 底层只允许调用 `/api/agent/**`，认证材料由服务 bootstrap 配置读取，禁止打印或复制。
- Agent 能力不可用、认证失败或返回结构异常时，将对应证据标记为 `unavailable` 并保留脱敏错误摘要，不得改走其它链路。
- 日志正文和查询结果必须脱敏，不输出用户标识、认证材料、手机号、邮箱、身份证或完整请求参数。

## 查询前确认

必须确认：

1. 项目和服务名。
2. 环境，例如 `production` 或 `test`。
3. 泰山 `appId`，优先从远程项目目录中的项目配置实时确认。
4. 精确时间窗口；“最近 N 分钟”也应记录最终的开始和结束时间。
5. 查询目标：业务异常、访问异常，或两者都查。

不要沿用未验证的历史 `appId` 或环境配置。

## 业务日志

查询最近 10 分钟的 ERROR 日志：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan biz-log \
     --app-id=83 \
     --minutes=10 \
     --query=ERROR \
     --page=1 \
     --limit=100'
```

使用固定毫秒时间窗复查：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan biz-log \
     --app-id=83 \
     --start=1784269208805 \
     --end=1784269808805 \
     --query=ERROR \
     --page=1 \
     --limit=100'
```

业务异常判断优先使用日志正文中的真实格式化级别，例如 ` - ERROR - `、` - WARN - `，并结合异常栈和业务失败语义。不要仅因普通 INFO 文本中出现 `error=null` 或 `errorCount=0` 就判定为异常。

## 访问日志

查询最近 10 分钟的 HTTP 5xx：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan access-log \
     --app-id=83 \
     --minutes=10 \
     --query="status in [500 599]" \
     --page=1 \
     --limit=100'
```

访问异常至少记录：时间、host、method、path、status、upstreamStatus、requestTime 和脱敏 traceId。

## 过滤与分页校验

- 每次都检查返回中的 `filterWarning`。
- 查询 ERROR 却返回普通 INFO，或查询 5xx 却返回 2xx 时，不得据此宣称“无异常”。
- 过滤失效但时间窗和分页仍有效时，可以固定同一组 `start` / `end`，逐页拉取后在本地对脱敏结果进行严格筛选。
- 分页必须记录扫描页数、行数、最早和最晚时间；末页仍达到 `limit` 时，标记为“覆盖不完整”。
- 只要发现一条真实异常即可确认“存在异常”；精确异常总数只有在完整覆盖且去重后才能报告。
- 业务日志与访问日志结论冲突时，分别报告两个证据面，不得互相覆盖。

## 结果输出

默认输出：

- 应用、环境、`appId` 和精确时间窗口。
- 业务日志与访问日志各自的查询状态。
- 已确认的问题族和少量脱敏样本。
- 扫描页数、行数、是否完整覆盖。
- 五类证据中的日志状态：`collected` 或 `unavailable`，以及原因。
- Agent 查询能力本身暴露的过滤、分页或字段解析问题。

不要输出完整日志列表或大段堆栈。
