---
name: taishan-db-query
description: 通过 WMXS 泰山 Agent API 执行受控只读数据库查询。适用于数据库索引确认、权限检查以及 SELECT、SHOW、EXPLAIN 取证；必须在 mucang-server 使用项目根目录 ./wmxs taishan，并遵守最长 12 小时临时权限限制。
---

# 泰山数据库查询

## 硬性边界

- 默认在远程服务器 `mucang-server` 执行。
- 固定工作目录为 `/data/projects/wmxs/wm-dev-server`。
- 唯一入口是 `./wmxs taishan sql-dbs`、`sql-permissions` 和 `sql-execute`。
- 底层只允许调用 `/api/agent/**`，认证材料由服务 bootstrap 配置读取，禁止打印或复制。
- 只允许 `SELECT`、`SHOW`、`EXPLAIN`；禁止写 SQL、DDL、多语句、存储过程、文件读写和批量导出。
- 查询结果必须脱敏，最多展示 20 行必要样本。
- Agent 能力不可用或权限不满足时，将数据库证据标记为 `unavailable`，不得改走其它链路。

## 查询前确认

必须确认：

1. 项目、环境和查询目的。
2. 泰山 `appId`，必须从远程项目配置实时确认。
3. 数据库索引；多个数据库时不得猜测。
4. 表名、时间字段、状态语义必须由设计文档和当前代码交叉确认。
5. SQL 具备时间或主键范围，并设置合理 `LIMIT`。

## 数据库与权限检查

查询数据库索引：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan sql-dbs --app-id=83'
```

查询当前权限：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan sql-permissions \
     --app-id=83 \
     --page=1 \
     --limit=100'
```

权限必须同时满足：应用和数据库匹配、状态有效、未过期。

## 临时权限门禁

- 新建临时权限最长只能为 12 小时。
- 只能审批当前任务由统一工作流创建的申请，不得审批无关申请。
- 执行前必须确认当前 `./wmxs taishan sql-execute` 能证明新建权限时长不超过 12 小时。
- 如果实现中硬编码了更长时长，或命令没有可靠的时长约束能力，立即停止，不得调用 `sql-execute`。
- 已有有效权限可以复用，但仍需记录权限状态和到期时间。

## 执行只读 SQL

将一条经过校验的 SQL 写入独立临时文件，再执行完整工作流：

```bash
ssh mucang-server \
  'cd /data/projects/wmxs/wm-dev-server && \
   ./wmxs taishan sql-execute \
     --app-id=83 \
     --db-index=0 \
     --sql-file=/tmp/wmxs-order-count.sql \
     --task-id=verify-pixel-orders-20260717 \
     --remark="核对最近十分钟订单和支付成功数量" \
     --max-rows=20 \
     --timeout-seconds=30'
```

SQL 示例：

```sql
SELECT
  COUNT(*) AS order_count,
  SUM(CASE WHEN paid_time IS NOT NULL THEN 1 ELSE 0 END) AS paid_count
FROM t_order
WHERE place_time >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
  AND place_time < NOW()
  AND sandbox = 0
  AND test_user = 0
LIMIT 20
```

如果 SQL 返回异步结果，必须由统一工作流完成等待；无论成功失败，都必须确认查询会话已关闭。

## SQL 安全检查

允许：

```sql
SELECT id, order_status FROM t_order WHERE id = 123 LIMIT 20;
SHOW TABLES;
SHOW COLUMNS FROM t_order;
EXPLAIN SELECT id FROM t_order WHERE id = 123 LIMIT 1;
```

禁止：

```sql
INSERT ...
UPDATE ...
DELETE ...
DROP ...
ALTER ...
TRUNCATE ...
CREATE ...
REPLACE ...
GRANT ...
REVOKE ...
CALL ...
SELECT ... INTO OUTFILE
```

## 结果输出

默认输出：

- 应用、环境、`appId`、数据库索引和权限状态。
- 脱敏 SQL 摘要与精确时间窗口。
- 返回行数和最多 20 行必要脱敏样本。
- 查询会话是否关闭。
- 数据库证据状态：`collected` 或 `unavailable`，以及原因。

无法安全执行时，数值结论写 `unknown`，不得写成 `0`。
