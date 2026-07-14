# 泰山五项能力 API 调查文档

更新时间：2026-06-09

## 结论摘要

已通过 Taishan 前端静态资源确认 5 项能力对应的页面、接口域名、主要 API、请求方法、前端消费的返回结构。其中“业务日志查询”已在登录态下用纯 HTTP 实测成功；SQL 权限确认/申请、申请列表、受控 SQL 初始化、只读查询、结果获取和关闭会话已封装 CLI。SQL 真实响应字段仍需要在具体应用登录态下继续校准。

公共域名映射：

| host key | 实际域名 |
| --- | --- |
| `server` / `taishan` | `https://server-manager.wanmeixiangsu.cn` |
| `logcenter` | `https://logcenter.wanmeixiangsu.cn` |

## 能力总表

| 能力 | 页面/入口 | 页面 chunk | 主接口 |
| --- | --- | --- | --- |
| SQL执行记录查看 | `taishan.H0009`，`/#/sql-record` | `5797.10a28328.js` | `GET /api/admin/sql-exec/list.htm`、`GET /api/admin/sql-exec-record/list.htm` |
| SQL查询申请 | 组件入口，申请弹窗/申请列表 | `4056.eef7f66e.js`、公共 SQL chunk | `POST /api/admin/sql-query-approve/create.htm`、`GET /api/admin/sql-query-approve/list.htm` |
| 受控SQL查询 | `taishan.H0008`，`/#/sql-query` | `4044.93570727.js` | `POST /api/admin/sql/query.htm` |
| 业务日志查询 | `taishan.H0036`，`/#/business-logs` | `2486.1a087953.js` | `GET /api/admin/v2/biz-log/query-range.htm`、`POST /api/admin/v2/log/query.htm` |
| 访问日志查询 | `taishan.H0033`，`/#/logcenter` | `185.42671662.js` | `POST /api/admin/v2/log/query.htm` |

所有接口调用都需要登录态 Cookie。未带 Cookie 或 Cookie 不属于目标子系统时会跳转到 SSO 登录页，或返回“当前用户未登录”。

## 1. SQL执行记录查看

页面：

```text
https://taishan.wanmeixiangsu.cn/#taishan.H0009?id=<appId>&engName=<engName>
```

主要 API：

| API | 方法 | 用途 | 主要参数 |
| --- | --- | --- | --- |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/list.htm` | GET | SQL 执行申请/执行记录主列表 | `appId`、`dbname`、`username`、`status`、`execType`、分页参数 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec-record/list.htm` | GET | 某条执行单下的 SQL 明细记录 | `sqlExecId`、`exec=false`、分页参数 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/view-sql.htm` | GET | 查看 SQL 内容 | `id` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/download.htm?id=<id>` | GET | 下载 SQL | `id` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/execute.htm` | GET | 手动执行已审核记录 | `id` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/approve.htm` | GET | 审核 SQL 执行申请 | `id`、`status`、`approveRemark`、可选 `execTime` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/status.htm` | GET | 审批状态下拉 | 无/少量查询参数 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-exec/type.htm` | GET | 执行方式下拉 | 无/少量查询参数 |

前端消费的列表字段：

```json
{
  "itemList": [
    {
      "id": 0,
      "appName": "",
      "dbname": "",
      "username": "",
      "statusTime": 0,
      "statusName": "",
      "sqlType": "",
      "execType": 0,
      "execTypeName": "",
      "execLog": "",
      "execSuccess": true,
      "remark": "",
      "approveSystemId": ""
    }
  ],
  "total": 0
}
```

`sql-exec-record/list.htm` 明细字段：

```json
{
  "itemList": [
    {
      "id": 0,
      "content": "",
      "comment": "",
      "useTime": 0,
      "statusName": "",
      "updateRows": 0,
      "remark": "",
      "createTime": 0
    }
  ],
  "total": 0
}
```

## 2. SQL查询申请

入口不是独立一级页面，而是数据库查询前置流程/申请列表组件：

- 选择数据库时如果无权限，前端按错误码打开“申请数据库查询权限”弹窗。
- 申请列表组件标题为“SQL查询权限申请列表”。

主要 API：

| API | 方法 | 用途 | 主要参数 |
| --- | --- | --- | --- |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-query-approve/create.htm` | POST | 创建数据库查询权限申请 | `appId`、`index`、`applyHours`、`remark` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-query-approve/list.htm` | GET | 查询权限申请列表 | `approveSystemId`、`appId`、`address`、`dbName`、`status`、`createUserName`、`approveUserName`、分页参数 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-query-approve/approve.htm` | GET | 审核查询权限申请 | `id`、`pass`、`applyHours`、`approveRemark` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-query-approve/submit-oa.htm` | POST | 提交 OA 审批 | 路径/查询参数 `id` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql-query-record/list-history.htm` | POST | 查询历史 SQL 记录 | 与查询上下文相关 |

前端消费的申请列表字段：

```json
{
  "itemList": [
    {
      "id": 0,
      "appName": "",
      "domain": "",
      "address": "",
      "dbName": "",
      "remark": "",
      "status": 0,
      "statusName": "",
      "expireTime": 0,
      "createUserName": "",
      "approveUserName": "",
      "approveSystemId": "",
      "applyHours": 0,
      "createTime": 0,
      "updateTime": 0
    }
  ],
  "total": 0
}
```

创建申请成功时前端只依赖 `getData()` 成功返回；失败时会读取 `errorCode` 和 `message`，其中 `13000` 会触发打开申请列表。

## 3. 受控SQL查询

页面：

```text
https://taishan.wanmeixiangsu.cn/#taishan.H0008?id=<appId>&uuid=<uuid>&db=<dbName>&appId=<appId>&index=<dbIndex>&env=<env>&address=<dbAddress>
```

进入前置流程：

| API | 方法 | 用途 | 主要参数/返回 |
| --- | --- | --- | --- |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/dbs.htm` | GET | 查询应用可选数据库 | `appId`；返回数据库选项数组 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/init.htm` | POST | 初始化受控 SQL 查询会话 | `appId`、`index`；成功后返回 `uuid` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/init-directly.htm` | POST | 直接初始化查询会话 | 查询上下文 |

查询页 API：

| API | 方法 | 用途 | 主要参数 |
| --- | --- | --- | --- |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/tables.htm` | GET | 查询表列表 | `uuid` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/columns.htm` | GET | 查询表字段 | `uuid`、表名 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/query.htm` | POST | 执行受控 SQL 查询 | `uuid`、`sql` |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/get-result.htm` | POST | 获取异步查询结果 | 查询任务上下文 |
| `https://server-manager.wanmeixiangsu.cn/api/admin/sql/close.htm` | GET | 关闭查询会话 | `uuid` |

`sql/query.htm` 前端消费结构：

```json
{
  "columns": [
    {
      "title": "",
      "dataIndex": "",
      "key": ""
    }
  ],
  "dataSource": [
    {}
  ],
  "rows": [],
  "execTime": 0,
  "message": "",
  "finished": true
}
```

说明：字段名来自查询结果动态生成，前端会把结果追加到 `results` 列表；实际字段随 SQL 返回列变化。

## 4. 业务日志查询

页面：

```text
https://taishan.wanmeixiangsu.cn/#taishan.H0036?id=<appId>&engName=<engName>&groupId=<groupId>&env=<production|test>
```

主要 API：

| API | 方法 | 用途 | 主要参数 |
| --- | --- | --- | --- |
| `https://logcenter.wanmeixiangsu.cn/grafana/api/datasources/153/resources/label/log_file_name/values` | GET | 查询日志文件名枚举 | Grafana/Loki 标签参数 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/query-range.htm` | GET | 查询业务日志列表 | `_r`、`end`、`limit`、`query`、`start`、`taishanId`、`_` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/label-values.htm` | GET | 查询业务日志标签值 | `group`、`appId`、`name` 等 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query.htm` | POST | 查询日志列表 | `app_name`、`groupId`、`profile`、`start`、`end`、`q`、分页/方向参数 |
| `wss://logcenter.wanmeixiangsu.cn/loki/api/v1/tail?tenantId=fake&query=<query>` | WebSocket | 实时日志 tail | Loki query 字符串 |

已实测请求示例：

```text
GET https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/query-range.htm?_r=<随机数>&end=<纳秒时间戳>&limit=200&query=<URL编码后的Loki查询>&start=<纳秒时间戳>&taishanId=83&_=<随机数>
```

`query` 示例：

```text
{infra_type="app",profile="production",app_name="pixel-studio"}
```

实测返回结构：

```json
{
  "success": true,
  "errorCode": 0,
  "message": null,
  "data": {
    "status": "success",
    "data": {
      "resultType": "streams",
      "result": [
        {
          "stream": {
            "app_name": "pixel-studio",
            "cluster": "simple-production",
            "infra_type": "app",
            "service_name": "k8s-tomcat",
            "profile": "production",
            "log_file_name": "server",
            "job": "k8s-tomcat",
            "pod_id": "pixel-studio-...",
            "detected_level": "info",
            "dc": "cn-hangzhou"
          },
          "values": [
            "1780993380845000000",
            "[2026-06-09 16:23:00.845] ... 日志正文 ..."
          ]
        }
      ],
      "stats": {
        "summary": {
          "totalEntriesReturned": 200,
          "totalLinesProcessed": 1745,
          "totalBytesProcessed": 857057
        }
      }
    }
  }
}
```

业务日志页面会把 `start/end` 转成纳秒时间戳：`1e6 * Date.getTime()`。

## 5. 访问日志查询

页面：

```text
https://taishan.wanmeixiangsu.cn/#taishan.H0033?id=<appId>&engName=<engName>&domainName=<domain>
```

主要 API：

| API | 方法 | 用途 | 主要参数 |
| --- | --- | --- | --- |
| `https://logcenter.wanmeixiangsu.cn/_/profile` | GET | 当前登录用户/角色 | 无 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query-column-list.htm` | GET | 查询可用查询字段 | `appName` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/agg-column-list.htm` | GET | 查询可聚合字段 | `appName` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/count-by-app.htm` | POST | 查询总日志数 | `appName`、`startTime`、`endTime`、`q` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/interval-query.htm` | POST | 查询时间分布 | `appName`、`startTime`、`endTime`、`q`、可选聚合窗口 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/column-agg-query.htm` | POST | 查询字段 TopN 聚合 | `appName`、`columnName`、`topN`、`startTime`、`endTime`、`q` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query.htm` | POST | 查询访问日志列表 | `appName`、`startTime`、`endTime`、`q`、`page`、`limit` |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/api-list.htm` | POST | 查询接口路径候选 | `hosts`、搜索参数 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/metadata/list-datasource.htm` | GET | 查询数据源/集群列表 | 无 |
| `https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/download.htm?<query>` | GET | 下载日志 | 查询参数同当前筛选 |

`log/query.htm` 前端消费结构：

```json
{
  "data": [
    {
      "logTime": 0,
      "logData": "{}",
      "request_host": "",
      "request_path": "",
      "status": 0,
      "method": "",
      "cost": 0
    }
  ],
  "paging": {
    "total": 0,
    "page": 1,
    "limit": 10
  }
}
```

访问日志页面会把 `logData` 当 JSON 字符串解析，并按用户选择字段生成 `displayLogData`。

访问日志与业务日志同属 logcenter，复用同一 Cookie。差异是访问日志的 `log/query.htm` 使用：

```text
POST application/x-www-form-urlencoded;charset=UTF-8
```

其中 `q` 由前端 `getQueryStr(queryList)` 生成，Host 条件的真实形态为：

```text
has(["pixel-studio.wanmeixiangsu.cn","pixel-studio.ppixels.com","pixel-studio.wmxs-inc.cn"],request_host)
has(["pixel-studio.wanmeixiangsu.cn","pixel-studio.ppixels.com","pixel-studio.wmxs-inc.cn"],request_host) and request_path = /api/open/order
```

## 证据来源

- `https://admin-appstore.wanmeixiangsu.cn/taishan/framework.config.json`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/index.6bed7bdf.js`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/5797.10a28328.js`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/4044.93570727.js`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/4056.eef7f66e.js`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/2486.1a087953.js`
- `https://admin-appstore.wanmeixiangsu.cn/taishan/js/185.42671662.js`

## 待继续实测的内容

业务日志和访问日志已经使用 Cookie Header 完成真实 HTTP 调用校准。SQL权限确认/申请、申请列表、受控SQL初始化、只读查询、结果获取、关闭会话已经封装到 `taishan_app_agent.py`；如果后续要补齐真实响应样例，仍需用已保存的本机 Cookie 发起请求，并在输出时脱敏 Cookie、token、SQL 内容、密码、数据库凭据。
