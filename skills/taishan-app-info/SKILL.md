---
name: taishan-app-info
description: 查询 WMXS 项目的泰山应用映射和 Agent 能力状态。适用于确认项目、环境、服务名、appId、域名及可用取证能力；默认在 mucang-server 读取实时项目配置，并且只允许后续调用 ./wmxs taishan 的 Agent 流程。
---

# 泰山应用信息

## 硬性边界

- 默认在远程服务器 `mucang-server` 执行。
- 项目配置和运行状态以 `/data/projects/wmxs/wm-dev-server` 的实时部署为准。
- 泰山取证只允许通过项目根目录 `./wmxs taishan` 调用 `/api/agent/**`。
- 认证材料由服务 bootstrap 配置读取，禁止打印、复制或写入任务产物。
- 不得因为某项 Agent 能力尚未覆盖，就切换到其它认证或接口链路。
- 无法通过 Agent 获取的信息标记为 `unavailable`，不得根据历史配置推断为当前事实。

## 查询目标

应用信息查询至少确认：

- 项目标识和显示名称。
- 服务名和环境。
- 泰山 `appId`。
- 业务域名。
- 日志指标名和默认日志窗口。
- 当前启用状态。
- 日志与数据库 Agent 能力是否可调用。

## 实时项目配置

优先从远程运行中的项目目录和管理配置读取项目映射。只展示目标项目的必要字段，不输出完整配置或认证材料。

Pixel Studio 的结果应区分生产与测试，例如：

```text
project=pixel-studio
service=pixel-studio
env=production
appId=<实时值>
domain=<实时值>
enabled=true
```

不得把测试环境 `appId` 当成生产环境使用，也不得沿用未重新验证的历史值。

## Agent 能力验证

确认根入口存在：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   sed -n "100,145p" ./wmxs'
```

当前标准能力包括：

- `biz-log`：业务日志。
- `access-log`：访问日志。
- `sql-dbs`：数据库索引。
- `sql-permissions`：只读查询权限状态。
- `sql-execute`：受控只读 SQL 工作流。

具体日志查询使用 `taishan-log-query`；数据库查询使用 `taishan-db-query`。

## 能力状态判断

- 命令成功且返回 `success=true`：能力可用。
- Agent 认证缺失、接口未覆盖、返回结构异常或安全门禁不满足：能力不可用。
- `appId`、环境或数据库索引不明确：先补齐配置证据，不执行后续查询。
- 只能证明配置存在时，不得宣称线上调用一定成功；必须以一次轻量实时查询验证。

## 输出格式

默认输出：

- 项目、服务、环境、`appId` 和域名。
- 配置来源和核验时间。
- 日志、访问日志、数据库索引、权限和受控 SQL 的能力状态。
- 每项状态为 `collected`、`not_applicable` 或 `unavailable`，并说明原因。
- 对当前任务有影响的能力缺口。

不要输出完整配置文件、认证材料、数据库连接信息或无关项目数据。
