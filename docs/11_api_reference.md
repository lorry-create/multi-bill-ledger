# 前后端接口开发手册

契约版本 0.2.0。本文由 contracts/openapi.json 和 contracts/examples.json 自动生成；修改源契约后重新生成，避免手写两份字段。

这里的HTTP示例为独立合成快照；不是一段连续的真实数据库记录。multipart文件和二进制内容为占位说明，业务应用尚待实现。

## 公共调用规则

- 开发后端 http://127.0.0.1:8000，前端 http://127.0.0.1:5173；Vite代理 /api 和 /health。Compose对外默认8080。浏览器SDK默认同源相对地址；Postman的baseUrl按实际环境调整。
- 登录后浏览器自动保存HttpOnly Cookie bill_session。登录和me的JSON提供csrf_token；除登录外的写请求设置X-CSRF-Token。不要在JavaScript读取Set-Cookie，也不要把Cookie当请求JSON字段。
- 普通请求application/json；文件上传使用FormData，浏览器自动生成multipart boundary，不手动设置Content-Type。文件下载读Blob，204不调用response.json()。
- 所有成功和失败响应带X-Contract-Version。金额使用整数分，日期时间带时区，统一枚举，错误读error.code。具体语义见02。
- 缺省查询参数与显式null不同。JSON可空字段在模型中标null，未提供PATCH字段保持旧值；未知请求字段应拒绝。列表空结果为items:[]，报表空月返回全月0值。

## 接口总表

| 编号 | 方法和路径 | SDK函数 | 页面动作 | 任务 |
| --- | --- | --- | --- | --- |
| API01 | `GET /health` | `health` | 公共：启动检查 | T00 |
| API02 | `POST /api/auth/login` | `login` | 登录页：点击登录 | T00 |
| API03 | `GET /api/auth/me` | `getSession` | 所有受保护页面：首次加载或刷新 | T00 |
| API04 | `POST /api/auth/logout` | `logout` | 导航栏：点击退出 | T00 |
| API05 | `POST /api/imports` | `createImport` | 导入中心：上传文件或截图 | T02/T03/T06 |
| API06 | `GET /api/imports/{id}` | `getImport` | 导入确认页：读取批次或轮询 | T02/T03/T07 |
| API07 | `GET /api/imports/{id}/original` | `getImportOriginal` | 导入确认页：查看原图或原文件 | T02/T07 |
| API08 | `POST /api/imports/{id}/retry` | `retryImport` | 导入失败页：点击重试 | T02/T07 |
| API09 | `POST /api/imports/{id}/confirm` | `confirmImport` | 导入确认页：点击确认入账 | T02/T03/T07 |
| API10 | `GET /api/transactions` | `listTransactions` | 账单页：列表初始化和筛选翻页 | T02/T03 |
| API11 | `PATCH /api/transactions/{id}` | `patchTransaction` | 账单编辑弹窗：保存修改或记住分类 | T05/T07 |
| API12 | `GET /api/classification-rules` | `listRules` | 个人规则页：读取本人规则 | T05/T07 |
| API13 | `PATCH /api/classification-rules/{id}` | `patchRule` | 个人规则页：修改类别或停用 | T05/T07 |
| API14 | `GET /api/reports/monthly` | `getMonthlyReport` | 月报页：选月份、修改后刷新 | T08/T09 |
| API15 | `PUT /api/budgets` | `putBudget` | 预算弹窗：保存分类月预算 | T08/T09 |
| API16 | `GET /api/exports/transactions.csv` | `exportTransactions` | 账单页：导出当前筛选结果 | T08/T09 |
| API17 | `GET /api/exports/monthly.pdf` | `exportMonthlyPdf` | 月报页：导出当前月报 | T08/T09 |

## API01 必要依赖健康检查

`GET /health`

GET /health 检查应用和数据库，200表示必要依赖就绪；不返回密钥或账单。

前端导出函数：`health`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T00。

认证：无需会话。

请求体：无。

### 请求示例

```http
GET /health HTTP/1.1
Host: 127.0.0.1:8000
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "status": "ok"
}
```

响应模型：`object`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 503 | SERVICE_UNAVAILABLE | 保留用户输入并提示稍后手动重试。 |

## API02 登录并设置HttpOnly会话Cookie

`POST /api/auth/login`

校验账号密码与同源Origin，成功设置HttpOnly会话Cookie并返回CSRF token。401表示账号或密码错误。

前端导出函数：`login`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T00。

认证：无需会话。

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `username` | `string` | 是 | minLength=1。登录账号名称；不是GitHub协作者身份。 |
| `password` | `string` | 是 | minLength=1。账号密码，只用于登录请求，不回显、不记录。 |

### 请求示例

```http
POST /api/auth/login HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json
```

JSON请求正文：

```json
{
  "username": "demo_a",
  "password": "<本机演示账号密码>"
}
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
Set-Cookie: bill_session=synthetic-cookie; HttpOnly; SameSite=Lax
```

```json
{
  "user": {
    "id": "user_demo_a",
    "username": "demo_a"
  },
  "csrf_token": "synthetic-csrf-token"
}
```

响应模型：`Session`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_INVALID | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |
| 429 | RATE_LIMITED | 按Retry-After或details重试等待，限制次数。 |

错误示例：HTTP 401

```json
{
  "error": {
    "code": "AUTH_INVALID",
    "message": "账号或密码错误",
    "details": {}
  }
}
```

错误示例：HTTP 429

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "登录请求过于频繁",
    "details": {
      "retry_after_seconds": 30
    }
  }
}
```

## API03 获取当前用户及CSRF token

`GET /api/auth/me`

读取当前用户及CSRF token。浏览器保存Cookie，JavaScript不读取Set-Cookie。

前端导出函数：`getSession`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T00。

认证：本人会话Cookie。

请求体：无。

### 请求示例

```http
GET /api/auth/me HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "user": {
    "id": "user_demo_a",
    "username": "demo_a"
  },
  "csrf_token": "synthetic-csrf-token"
}
```

响应模型：`Session`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |

错误示例：HTTP 401

```json
{
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "请先登录",
    "details": {}
  }
}
```

## API04 退出并清除会话

`POST /api/auth/logout`

校验CSRF后清除会话Cookie；204没有JSON正文，前端清空用户和CSRF状态。

前端导出函数：`logout`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T00。

认证：本人会话Cookie。写请求必须CSRF。

请求体：无。

### 请求示例

```http
POST /api/auth/logout HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
```

### 成功响应

HTTP状态：`204`。

```http
X-Contract-Version: 0.2.0
Set-Cookie: bill_session=; Max-Age=0; HttpOnly; SameSite=Lax
```

响应无正文；SDK返回undefined。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |

## API05 上传文件或截图，异步解析分类为待确认草稿

`POST /api/imports`

multipart上传source、ingestion_method、file，返回202和批次。请求仅创建批次，不自动确认入账。文件10MiB、图片5MiB，PNG/JPEG/CSV/XLSX。

前端导出函数：`createImport`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T03/T06。

认证：本人会话Cookie。写请求必须CSRF。

### 请求体

媒体类型：`multipart/form-data`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `source` | `Source` | 是 | 见共享模型定义。 |
| `ingestion_method` | `IngestionMethod` | 是 | 见共享模型定义。 |
| `file` | `string` | 是 | format=binary。见共享模型定义。 |

### 请求示例

```http
POST /api/imports HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: multipart/form-data
```

字段值示例（上传接口表示FormData字段，不是JSON上传）：

```json
{
  "source": "wechat",
  "ingestion_method": "file",
  "file": "<用户选择的本机CSV文件>"
}
```

### 成功响应

HTTP状态：`202`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
Location: /api/imports/batch_demo_01
Retry-After: 2
```

```json
{
  "id": "batch_demo_01",
  "version": 1,
  "source": "wechat",
  "ingestion_method": "file",
  "status": "processing",
  "rows": [],
  "issues": [],
  "progress": {
    "current": 0,
    "total": null
  },
  "file_name": "synthetic_bill.csv",
  "created_at": "2026-11-08T12:00:00+08:00",
  "updated_at": "2026-11-08T12:00:00+08:00"
}
```

响应模型：`Batch`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 413 | UPLOAD_TOO_LARGE | 提示缩小文件，不原样重试。 |
| 415 | UNSUPPORTED_MEDIA_TYPE | 提示支持的文件类型。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

错误示例：HTTP 413

```json
{
  "error": {
    "code": "UPLOAD_TOO_LARGE",
    "message": "文件超过10MiB",
    "details": {}
  }
}
```

错误示例：HTTP 415

```json
{
  "error": {
    "code": "UNSUPPORTED_MEDIA_TYPE",
    "message": "不支持该文件类型",
    "details": {}
  }
}
```

## API06 读取本人批次状态、草稿和问题

`GET /api/imports/{id}`

读取本人批次。首次1秒后轮询，之后每2秒；pending_review、completed或failed停止。120秒仍处理中暂停自动轮询并允许手动刷新；不能由前端自行判失败。

前端导出函数：`getImport`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T03/T07。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

请求体：无。

### 请求示例

```http
GET /api/imports/batch_demo_01 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "id": "batch_demo_01",
  "version": 2,
  "source": "wechat",
  "ingestion_method": "file",
  "status": "pending_review",
  "rows": [
    {
      "source_transaction_id": "SYN-HTTP-001",
      "occurred_at": "2026-11-08T12:00:00+08:00",
      "amount_fen": 2300,
      "currency": "CNY",
      "flow_type": "expense",
      "merchant": "示例餐馆",
      "description": "合成午餐账单",
      "category": "dining",
      "row_id": "row_demo_01",
      "classification_source": "general_rule",
      "classification_reason": "商户命中餐饮规则",
      "duplicate_status": "unique",
      "issues": []
    }
  ],
  "issues": [],
  "progress": {
    "current": 1,
    "total": 1
  },
  "file_name": "synthetic_bill.csv",
  "created_at": "2026-11-08T12:00:00+08:00",
  "updated_at": "2026-11-08T12:00:00+08:00"
}
```

响应模型：`Batch`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |

错误示例：HTTP 404

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "资源不存在",
    "details": {}
  }
}
```

## API07 鉴权读取原文件或原图供对照

`GET /api/imports/{id}/original`

鉴权流式返回原文件。前端以Blob预览图片，不能将其当JSON或可公开访问的静态URL。

前端导出函数：`getImportOriginal`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T07。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

请求体：无。

### 请求示例

```http
GET /api/imports/batch_demo_01/original HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="synthetic_bill.csv"
```

```text
<原图或文件的二进制内容>
```
以上仅说明文件载荷，不能据此声称文件已生成。

响应模型：`string`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |
| 503 | SERVICE_UNAVAILABLE | 保留用户输入并提示稍后手动重试。 |

## API08 仅对失败批次进行可追踪重试

`POST /api/imports/{id}/retry`

仅failed且版本相符才能重试；返回202、新版本与processing。该接口不重新确认已完成批次，旧版本或其他状态返回409。

前端导出函数：`retryImport`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T07。

认证：本人会话Cookie。写请求必须CSRF。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |

### 请求示例

```http
POST /api/imports/batch_demo_01/retry HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: application/json
```

JSON请求正文：

```json
{
  "expected_version": 3
}
```

### 成功响应

HTTP状态：`202`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
Location: /api/imports/batch_demo_01
Retry-After: 2
```

```json
{
  "id": "batch_demo_01",
  "version": 4,
  "source": "wechat",
  "ingestion_method": "file",
  "status": "processing",
  "rows": [],
  "issues": [],
  "progress": {
    "current": 0,
    "total": null
  },
  "file_name": "synthetic_bill.csv",
  "created_at": "2026-11-08T12:00:00+08:00",
  "updated_at": "2026-11-08T12:00:00+08:00"
}
```

响应模型：`Batch`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |
| 409 | VERSION_CONFLICT, BATCH_STATE_CONFLICT | 按error.code区分版本、幂等或状态冲突；重新读取后由用户确认。 |

错误示例：HTTP 409

```json
{
  "error": {
    "code": "BATCH_STATE_CONFLICT",
    "message": "只有失败批次能够重试",
    "details": {}
  }
}
```

## API09 重新校验后在事务中幂等确认入账

`POST /api/imports/{id}/confirm`

pending_review批次才能确认。同request_id同请求体返回原200结果，先检查幂等记录再检查旧版本；同ID异体或已完成批次新ID返回409。全部选中行同事务，不部分入账。

前端导出函数：`confirmImport`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T03/T07。

认证：本人会话Cookie。写请求必须CSRF。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `request_id` | `string` | 是 | format=uuid。确认操作的UUID。同一次网络重试复用同一ID和请求体。 |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `rows` | `array[ConfirmRow]` | 是 | minItems=1; maxItems=500。草稿或本次选中的确认行；处理中的批次可为空数组。 |

### 请求示例

```http
POST /api/imports/batch_demo_01/confirm HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: application/json
```

JSON请求正文：

```json
{
  "request_id": "30fd9d73-08f4-4947-911c-64d32ce24d00",
  "expected_version": 2,
  "rows": [
    {
      "row_id": "row_demo_01",
      "transaction": {
        "source_transaction_id": "SYN-HTTP-001",
        "occurred_at": "2026-11-08T12:00:00+08:00",
        "amount_fen": 2300,
        "currency": "CNY",
        "flow_type": "expense",
        "merchant": "示例餐馆",
        "description": "合成午餐账单",
        "category": "dining"
      },
      "allow_suspected_duplicate": false
    }
  ]
}
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "batch_id": "batch_demo_01",
  "created_count": 1,
  "duplicate_count": 0,
  "ignored_count": 0,
  "transaction_ids": [
    "txn_demo_01"
  ]
}
```

响应模型：`ConfirmResult`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |
| 409 | VERSION_CONFLICT, IDEMPOTENCY_CONFLICT, BATCH_STATE_CONFLICT | 按error.code区分版本、幂等或状态冲突；重新读取后由用户确认。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

错误示例：HTTP 403

```json
{
  "error": {
    "code": "CSRF_INVALID",
    "message": "会话校验失败，请刷新后重试",
    "details": {}
  }
}
```

错误示例：HTTP 409

```json
{
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "同一request_id不能提交不同内容",
    "details": {}
  }
}
```

错误示例：HTTP 422

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请修正金额字段",
    "details": {
      "fields": [
        {
          "field": "rows[0].transaction.amount_fen",
          "row_id": "row_demo_01",
          "code": "INVALID_AMOUNT",
          "message": "金额必须为正整数分"
        }
      ]
    }
  }
}
```

## API10 筛选并分页读取本人已确认交易

`GET /api/transactions`

只返回本人已确认交易。默认page=1、page_size=50；按occurred_at倒序再id倒序。日期两端均为上海自然日包含边界；不传日期则查本人全部记录。

前端导出函数：`listTransactions`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T02/T03。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `date_from` | query | `string` | 否 | 包含该上海自然日，需与date_to保持先后顺序。 |
| `date_to` | query | `string` | 否 | 包含该上海自然日，服务端按下一日零点开区间计算。 |
| `category` | query | `Category` | 否 | 可选类别代码。 |
| `source` | query | `Source` | 否 | 可选平台代码。 |
| `flow_type` | query | `FlowType` | 否 | 可选资金事件性质。 |
| `page` | query | `integer` | 否 | 默认1。 |
| `page_size` | query | `integer` | 否 | 默认50，最大100。 |

请求体：无。

### 请求示例

```http
GET /api/transactions?date_from=2026-11-01&date_to=2026-11-30&source=wechat&page=1&page_size=50 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "items": [
    {
      "source_transaction_id": "SYN-HTTP-001",
      "occurred_at": "2026-11-08T12:00:00+08:00",
      "amount_fen": 2300,
      "currency": "CNY",
      "flow_type": "expense",
      "merchant": "示例餐馆",
      "description": "合成午餐账单",
      "category": "dining",
      "id": "txn_demo_01",
      "version": 1,
      "source": "wechat",
      "ingestion_method": "file",
      "import_batch_id": "batch_demo_01",
      "classification_source": "general_rule",
      "classification_reason": "商户命中餐饮规则",
      "status": "confirmed"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

响应模型：`TransactionPage`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

## API11 修改交易并可选择建立个人商户规则

`PATCH /api/transactions/{id}`

expected_version必填；未提交字段不变。显式更改类别标manual，未提交category则保留原类别及来源。remember_rule只在非空商户和非pending类别时生效。账单、规则、日志及索引原子更新。

前端导出函数：`patchTransaction`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T05/T07。

认证：本人会话Cookie。写请求必须CSRF。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `changes` | `object` | 是 | 需要修改的字段；未提交字段保持原值。显式null只允许在契约可空字段。 |
| `remember_rule` | `boolean` | 否 | default=False。true时同时建立或更新个人商户分类规则，默认false。 |

### 请求示例

```http
PATCH /api/transactions/txn_demo_01 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: application/json
```

JSON请求正文：

```json
{
  "expected_version": 1,
  "changes": {
    "category": "shopping"
  },
  "remember_rule": true
}
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "source_transaction_id": "SYN-HTTP-001",
  "occurred_at": "2026-11-08T12:00:00+08:00",
  "amount_fen": 2300,
  "currency": "CNY",
  "flow_type": "expense",
  "merchant": "示例餐馆",
  "description": "合成午餐账单",
  "category": "shopping",
  "id": "txn_demo_01",
  "version": 2,
  "source": "wechat",
  "ingestion_method": "file",
  "import_batch_id": "batch_demo_01",
  "classification_source": "manual",
  "classification_reason": "用户手动修正分类",
  "status": "confirmed"
}
```

响应模型：`Transaction`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |
| 409 | VERSION_CONFLICT | 按error.code区分版本、幂等或状态冲突；重新读取后由用户确认。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

错误示例：HTTP 409

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "记录已被其他操作修改",
    "details": {
      "current_version": 2
    }
  }
}
```

## API12 读取本人规则

`GET /api/classification-rules`

返回本人全部规则，包括已停用项，按source再merchant_normalized升序。

前端导出函数：`listRules`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T05/T07。

认证：本人会话Cookie。

请求体：无。

### 请求示例

```http
GET /api/classification-rules HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "items": [
    {
      "id": "rule_demo_01",
      "version": 1,
      "source": "wechat",
      "merchant_normalized": "示例餐馆",
      "category": "shopping",
      "enabled": true
    }
  ]
}
```

响应模型：`RuleList`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |

## API13 修改或停用规则，不改写历史账单

`PATCH /api/classification-rules/{id}`

至少提供enabled或category，携带expected_version；已停用规则可重新启用。停用不重写历史交易。

前端导出函数：`patchRule`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T05/T07。

认证：本人会话Cookie。写请求必须CSRF。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | path | `string` | 是 | 从列表或创建结果取得的资源ID。 |

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `enabled` | `boolean` | 否 | 个人规则是否启用，停用仅影响后续自动分类。 |
| `category` | `ResolvedCategory` | 否 | 明确的类别代码，不接受pending。 |

### 请求示例

```http
PATCH /api/classification-rules/rule_demo_01 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: application/json
```

JSON请求正文：

```json
{
  "expected_version": 1,
  "enabled": false
}
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "id": "rule_demo_01",
  "version": 2,
  "source": "wechat",
  "merchant_normalized": "示例餐馆",
  "category": "shopping",
  "enabled": false
}
```

响应模型：`ClassificationRule`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 404 | RESOURCE_NOT_FOUND | 提示资源不可用，不泄露别的用户资源。 |
| 409 | VERSION_CONFLICT | 按error.code区分版本、幂等或状态冲突；重新读取后由用户确认。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

## API14 按上海时区汇总月份并返回预算情况

`GET /api/reports/monthly`

month必填。返回统一汇总、分类毛支出、全月日趋势和预算。列表/图表/导出共用相同口径，空月返回0与完整日期序列。

前端导出函数：`getMonthlyReport`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T08/T09。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `month` | query | `string` | 是 | 指定月份YYYY-MM；必填。 |

请求体：无。

### 请求示例

```http
GET /api/reports/monthly?month=2026-11 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "month": "2026-11",
  "totals": {
    "income_fen": 10000,
    "gross_expense_fen": 4200,
    "refund_fen": 500,
    "net_expense_fen": 3700,
    "balance_fen": 6300
  },
  "expense_by_category": [
    {
      "category": "dining",
      "amount_fen": 3000
    },
    {
      "category": "shopping",
      "amount_fen": 1200
    }
  ],
  "daily_trend": [
    {
      "date": "2026-11-01",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-02",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-03",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-04",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-05",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-06",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-07",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-08",
      "income_fen": 10000,
      "gross_expense_fen": 4200,
      "refund_fen": 500,
      "net_expense_fen": 3700
    },
    {
      "date": "2026-11-09",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-10",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-11",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-12",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-13",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-14",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-15",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-16",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-17",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-18",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-19",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-20",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-21",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-22",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-23",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-24",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-25",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-26",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-27",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-28",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-29",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    },
    {
      "date": "2026-11-30",
      "income_fen": 0,
      "gross_expense_fen": 0,
      "refund_fen": 0,
      "net_expense_fen": 0
    }
  ],
  "budgets": [
    {
      "category": "dining",
      "budget_fen": 2000,
      "spent_fen": 2500,
      "remaining_fen": -500,
      "over_fen": 500
    },
    {
      "category": "shopping",
      "budget_fen": 1500,
      "spent_fen": 1200,
      "remaining_fen": 300,
      "over_fen": 0
    }
  ]
}
```

响应模型：`MonthlyReport`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

## API15 按本人月份类别设置或更新预算

`PUT /api/budgets`

按当前用户、month、category唯一键创建或覆盖预算，始终200。category不接受pending；金额为0时前端不计算百分比除法。

前端导出函数：`putBudget`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T08/T09。

认证：本人会话Cookie。写请求必须CSRF。

### 请求体

媒体类型：`application/json`。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `month` | `string` | 是 | pattern=^\d{4}-(0[1-9]|1[0-2])$。YYYY-MM，接口不静默默认当前月份。 |
| `category` | `ResolvedCategory` | 是 | 明确的类别代码，不接受pending。 |
| `amount_fen` | `integer` | 是 | minimum=0。分类月预算，非负整数分；与交易金额的正整数要求不同。 |

### 请求示例

```http
PUT /api/budgets HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
X-CSRF-Token: synthetic-csrf-token
Content-Type: application/json
```

JSON请求正文：

```json
{
  "month": "2026-11",
  "category": "dining",
  "amount_fen": 2000
}
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/json
```

```json
{
  "id": "budget_demo_01",
  "month": "2026-11",
  "category": "dining",
  "amount_fen": 2000
}
```

响应模型：`Budget`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 403 | CSRF_INVALID | 刷新会话/CSRF或提示拒绝，不自动重放修改。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |

## API16 导出与筛选范围一致的本人账单CSV

`GET /api/exports/transactions.csv`

导出所有筛选结果，不限当前分页，不接受page/page_size。UTF-8 CSV，文本单元格防公式注入，金额字段明确amount_fen。

前端导出函数：`exportTransactions`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T08/T09。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `date_from` | query | `string` | 否 | 包含该上海自然日，需与date_to保持先后顺序。 |
| `date_to` | query | `string` | 否 | 包含该上海自然日，服务端按下一日零点开区间计算。 |
| `category` | query | `Category` | 否 | 可选类别代码。 |
| `source` | query | `Source` | 否 | 可选平台代码。 |
| `flow_type` | query | `FlowType` | 否 | 可选资金事件性质。 |

请求体：无。

### 请求示例

```http
GET /api/exports/transactions.csv?date_from=2026-11-01&date_to=2026-11-30&source=wechat HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: text/csv
Content-Disposition: attachment; filename="ledger.csv"
```

```text
source,amount_fen,flow_type,category
wechat,2300,expense,dining

```
以上仅说明文件载荷，不能据此声称文件已生成。

响应模型：`string`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |
| 503 | SERVICE_UNAVAILABLE | 保留用户输入并提示稍后手动重试。 |

## API17 导出与月报同口径的中文PDF

`GET /api/exports/monthly.pdf`

month必填，返回中文PDF二进制，与同月份月报数字相同。字体和渲染依赖随部署包提供。

前端导出函数：`exportMonthlyPdf`。后端负责人H；智能处理由D模块提供，前端负责人F。对应任务：T08/T09。

认证：本人会话Cookie。

### 路径和查询参数

| 参数 | 位置 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- | --- |
| `month` | query | `string` | 是 | 指定月份YYYY-MM；必填。 |

请求体：无。

### 请求示例

```http
GET /api/exports/monthly.pdf?month=2026-11 HTTP/1.1
Host: 127.0.0.1:8000
Cookie: bill_session=<浏览器自动携带的会话>
```

### 成功响应

HTTP状态：`200`。

```http
X-Contract-Version: 0.2.0
Content-Type: application/pdf
Content-Disposition: attachment; filename="ledger-2026-11.pdf"
```

```text
<PDF二进制内容，不是JSON>
```
以上仅说明文件载荷，不能据此声称文件已生成。

响应模型：`string`。逐字段见文末共享模型。

### 失败和前端处理

| HTTP | 错误代码或含义 | 前端动作 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 回登录或展示登录失败，不循环重试。 |
| 422 | VALIDATION_ERROR | 映射details.fields至对应字段，修正后提交。 |
| 503 | EXPORT_UNAVAILABLE | 保留用户输入并提示稍后手动重试。 |

错误示例：HTTP 503

```json
{
  "error": {
    "code": "EXPORT_UNAVAILABLE",
    "message": "报表导出暂不可用，请稍后重试",
    "details": {}
  }
}
```

## 共享数据模型

下列定义由接口契约生成。表中的必填表示字段必须出现；允许null时仍可能是必填。日期、金额、版本和规则的跨字段限制还须执行02的业务约定。

### Source

共享模型 Source；HTTP请求与响应均遵守本定义。

类型：`alipay / wechat`。


### IngestionMethod

共享模型 IngestionMethod；HTTP请求与响应均遵守本定义。

类型：`file / screenshot`。


### Category

共享模型 Category；HTTP请求与响应均遵守本定义。

类型：`dining / transport / shopping / salary / housing / entertainment / health / education / other / pending`。


### FlowType

共享模型 FlowType；HTTP请求与响应均遵守本定义。

类型：`income / expense / refund / transfer / repayment`。


### ClassificationSource

共享模型 ClassificationSource；HTTP请求与响应均遵守本定义。

类型：`user_rule / general_rule / deepseek / manual / pending`。


### BatchStatus

共享模型 BatchStatus；HTTP请求与响应均遵守本定义。

类型：`uploaded / processing / pending_review / completed / failed`。


### Error

共享模型 Error；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `error` | `object` | 是 | error字段，类型和必填性如下。 |


### User

共享模型 User；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | 服务端资源标识，前端原样使用，不自行拼接。 |
| `username` | `string` | 是 | 登录账号名称；不是GitHub协作者身份。 |


### LoginInput

共享模型 LoginInput；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `username` | `string` | 是 | minLength=1。登录账号名称；不是GitHub协作者身份。 |
| `password` | `string` | 是 | minLength=1。账号密码，只用于登录请求，不回显、不记录。 |


### Session

共享模型 Session；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `user` | `User` | 是 | 当前登录用户，不包含密码或服务端密钥。 |
| `csrf_token` | `string` | 是 | 前端保存在会话状态，写请求放入X-CSRF-Token，退出后清除。 |


### Issue

共享模型 Issue；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `row_id` | `string / null` | 是 | 本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。 |
| `field` | `string / null` | 是 | 字段路径，例如rows[0].amount_fen或amount_fen。 |
| `code` | `string` | 是 | 稳定的机器错误代码，前端不能按中文message判断逻辑。 |
| `message` | `string` | 是 | 面向用户的说明文本。 |


### TransactionInput

共享模型 TransactionInput；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `source_transaction_id` | `string / null` | 是 | 可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。 |
| `occurred_at` | `string` | 是 | format=date-time。带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。 |
| `amount_fen` | `integer` | 是 | minimum=1。CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。 |
| `currency` | `"CNY"` | 是 | 初赛只接受CNY，不自动换汇。 |
| `flow_type` | `FlowType` | 是 | 收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。 |
| `merchant` | `string` | 是 | maxLength=500。商户原始展示名称；建立个人规则要求非空。 |
| `description` | `string` | 是 | maxLength=2000。交易说明，空说明用空字符串。 |
| `category` | `Category` | 是 | 固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。 |


### TransactionDraft

共享模型 TransactionDraft；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `source_transaction_id` | `string / null` | 是 | 可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。 |
| `occurred_at` | `string / null` | 是 | format=date-time。带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。 |
| `amount_fen` | `integer / null` | 是 | minimum=1。CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。 |
| `currency` | `"CNY"` | 是 | 初赛只接受CNY，不自动换汇。 |
| `flow_type` | `income / expense / refund / transfer / repayment / None` | 是 | 收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。 |
| `merchant` | `string` | 是 | maxLength=500。商户原始展示名称；建立个人规则要求非空。 |
| `description` | `string` | 是 | maxLength=2000。交易说明，空说明用空字符串。 |
| `category` | `Category` | 是 | 固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。 |
| `row_id` | `string` | 是 | 本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。 |
| `classification_source` | `ClassificationSource` | 是 | 实际分类来源，不得将规则或测试替身标成deepseek。 |
| `classification_reason` | `string` | 是 | 供用户查看的简短分类依据，不是准确率或概率。 |
| `duplicate_status` | `unique / duplicate / suspected` | 是 | unique可正常选中，duplicate明确重复会跳过，suspected需要人工判断。 |
| `issues` | `array[Issue]` | 是 | 解析、识别或分类的字段问题；空数组表示暂无问题。 |


### ParseResult

共享模型 ParseResult；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `rows` | `array[TransactionDraft]` | 是 | 草稿或本次选中的确认行；处理中的批次可为空数组。 |
| `issues` | `array[Issue]` | 是 | 解析、识别或分类的字段问题；空数组表示暂无问题。 |


### ClassificationResult

共享模型 ClassificationResult；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `row_id` | `string` | 是 | 本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。 |
| `category` | `Category` | 是 | 固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。 |
| `classification_source` | `ClassificationSource` | 是 | 实际分类来源，不得将规则或测试替身标成deepseek。 |
| `classification_reason` | `string` | 是 | 供用户查看的简短分类依据，不是准确率或概率。 |
| `issues` | `array[Issue]` | 是 | 解析、识别或分类的字段问题；空数组表示暂无问题。 |


### Transaction

共享模型 Transaction；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `source_transaction_id` | `string / null` | 是 | 可靠的源交易或退款事件标识；只有共用订单号且无法区分事件时为null并标疑似，不冒充唯一事件号。 |
| `occurred_at` | `string` | 是 | format=date-time。带时区的交易时间，按Asia/Shanghai归属日期月份；草稿未知可为null。 |
| `amount_fen` | `integer` | 是 | minimum=1。CNY整数分，不是浮点元；草稿可未知，确认必须为正整数。 |
| `currency` | `"CNY"` | 是 | 初赛只接受CNY，不自动换汇。 |
| `flow_type` | `FlowType` | 是 | 收入、支出、退款、内部转账、还款；草稿可未知，确认前必须明确。 |
| `merchant` | `string` | 是 | maxLength=500。商户原始展示名称；建立个人规则要求非空。 |
| `description` | `string` | 是 | maxLength=2000。交易说明，空说明用空字符串。 |
| `category` | `Category` | 是 | 固定类别代码；pending可作为未分类桶，但建立个人规则不接受pending。 |
| `id` | `string` | 是 | 服务端资源标识，前端原样使用，不自行拼接。 |
| `version` | `integer` | 是 | minimum=1。资源当前版本。写操作通过 expected_version 防止覆盖新修改。 |
| `source` | `Source` | 是 | 账单所属支付平台，与采集方式分开。 |
| `ingestion_method` | `IngestionMethod` | 是 | file为导出文件，screenshot为账单截图。 |
| `import_batch_id` | `string` | 是 | 交易来源批次ID。 |
| `classification_source` | `ClassificationSource` | 是 | 实际分类来源，不得将规则或测试替身标成deepseek。 |
| `classification_reason` | `string` | 是 | 供用户查看的简短分类依据，不是准确率或概率。 |
| `status` | `"confirmed"` | 是 | BatchStatus为批次状态；交易status为confirmed，草稿不进入报表。 |


### Batch

共享模型 Batch；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | 服务端资源标识，前端原样使用，不自行拼接。 |
| `version` | `integer` | 是 | minimum=1。资源当前版本。写操作通过 expected_version 防止覆盖新修改。 |
| `source` | `Source` | 是 | 账单所属支付平台，与采集方式分开。 |
| `ingestion_method` | `IngestionMethod` | 是 | file为导出文件，screenshot为账单截图。 |
| `status` | `BatchStatus` | 是 | BatchStatus为批次状态；交易status为confirmed，草稿不进入报表。 |
| `rows` | `array[TransactionDraft]` | 是 | 草稿或本次选中的确认行；处理中的批次可为空数组。 |
| `issues` | `array[Issue]` | 是 | 解析、识别或分类的字段问题；空数组表示暂无问题。 |
| `progress` | `Progress` | 是 | 处理进度，仅供展示，不决定是否可确认。 |
| `file_name` | `string` | 是 | 经过鉴权后展示的原文件名，不能当作服务器磁盘路径。 |
| `created_at` | `string` | 是 | format=date-time。资源创建时间，带时区ISO 8601。 |
| `updated_at` | `string` | 是 | format=date-time。最后状态更新时间，带时区ISO 8601。 |


### ConfirmRow

共享模型 ConfirmRow；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `row_id` | `string` | 是 | 本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。 |
| `transaction` | `TransactionInput` | 是 | 该行最终入账字段，后端重新校验。 |
| `allow_suspected_duplicate` | `boolean` | 是 | default=False。仅用户明确确认疑似重复仍为新交易时设true。 |


### ConfirmInput

共享模型 ConfirmInput；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `request_id` | `string` | 是 | format=uuid。确认操作的UUID。同一次网络重试复用同一ID和请求体。 |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `rows` | `array[ConfirmRow]` | 是 | minItems=1; maxItems=500。草稿或本次选中的确认行；处理中的批次可为空数组。 |


### ConfirmResult

共享模型 ConfirmResult；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `batch_id` | `string` | 是 | 本次确认对应的批次。 |
| `created_count` | `integer` | 是 | minimum=0。本次真正新增的交易数。 |
| `duplicate_count` | `integer` | 是 | minimum=0。本次提交选中行里被明确判重而跳过的行数。 |
| `ignored_count` | `integer` | 是 | minimum=0。该批次草稿中未在本次确认请求提交的行数。 |
| `transaction_ids` | `array[string]` | 是 | 本次新增交易ID；重放确认返回相同数组。 |


### RetryInput

共享模型 RetryInput；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |


### TransactionPatch

共享模型 TransactionPatch；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `changes` | `object` | 是 | 需要修改的字段；未提交字段保持原值。显式null只允许在契约可空字段。 |
| `remember_rule` | `boolean` | 否 | default=False。true时同时建立或更新个人商户分类规则，默认false。 |


### TransactionPage

共享模型 TransactionPage；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `items` | `array[Transaction]` | 是 | 当前列表项，空结果用空数组。 |
| `total` | `integer` | 是 | minimum=0。列表中为筛选后的总数；Progress中为候选行总数，可未知。 |
| `page` | `integer` | 是 | minimum=1。页码从1开始，默认1。 |
| `page_size` | `integer` | 是 | minimum=1。每页默认50，范围1至100。 |


### ClassificationRule

共享模型 ClassificationRule；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | 服务端资源标识，前端原样使用，不自行拼接。 |
| `version` | `integer` | 是 | minimum=1。资源当前版本。写操作通过 expected_version 防止覆盖新修改。 |
| `source` | `Source` | 是 | 账单所属支付平台，与采集方式分开。 |
| `merchant_normalized` | `string` | 是 | minLength=1。按本项目标准化步骤得到的精确匹配键，仅对本人和该平台有效。 |
| `category` | `ResolvedCategory` | 是 | 明确的类别代码，不接受pending。 |
| `enabled` | `boolean` | 是 | 个人规则是否启用，停用仅影响后续自动分类。 |


### RuleList

共享模型 RuleList；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `items` | `array[ClassificationRule]` | 是 | 当前列表项，空结果用空数组。 |


### RulePatch

共享模型 RulePatch；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `expected_version` | `integer` | 是 | minimum=1。提交编辑前最后读取的资源版本，冲突返回409和最新版本。 |
| `enabled` | `boolean` | 否 | 个人规则是否启用，停用仅影响后续自动分类。 |
| `category` | `ResolvedCategory` | 否 | 明确的类别代码，不接受pending。 |


### BudgetInput

共享模型 BudgetInput；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `month` | `string` | 是 | pattern=^\d{4}-(0[1-9]|1[0-2])$。YYYY-MM，接口不静默默认当前月份。 |
| `category` | `ResolvedCategory` | 是 | 明确的类别代码，不接受pending。 |
| `amount_fen` | `integer` | 是 | minimum=0。分类月预算，非负整数分；与交易金额的正整数要求不同。 |


### Budget

共享模型 Budget；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `id` | `string` | 是 | 服务端资源标识，前端原样使用，不自行拼接。 |
| `month` | `string` | 是 | pattern=^\d{4}-(0[1-9]|1[0-2])$。YYYY-MM，接口不静默默认当前月份。 |
| `category` | `ResolvedCategory` | 是 | 明确的类别代码，不接受pending。 |
| `amount_fen` | `integer` | 是 | minimum=0。保存后的分类月预算，非负整数分。 |


### BudgetStatus

共享模型 BudgetStatus；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `category` | `ResolvedCategory` | 是 | 明确的类别代码，不接受pending。 |
| `budget_fen` | `integer` | 是 | minimum=0。该类别当月预算，非负整数分。 |
| `spent_fen` | `integer` | 是 | 类别当月净支出，退款跨月时可以为负。 |
| `remaining_fen` | `integer` | 是 | 预算减当月净支出，可以为负。 |
| `over_fen` | `integer` | 是 | minimum=0。max(0,净支出减预算)。 |


### Totals

共享模型 Totals；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `income_fen` | `integer` | 是 | minimum=0。当月收入，不含退款和内部转账。 |
| `gross_expense_fen` | `integer` | 是 | minimum=0。当月毛支出，不含内部转账和还款。 |
| `refund_fen` | `integer` | 是 | minimum=0。按退款实际发生月计入的退款。 |
| `net_expense_fen` | `integer` | 是 | 毛支出减退款，可以为负。 |
| `balance_fen` | `integer` | 是 | 本期收支差额=收入减毛支出加退款，不是账户余额。 |


### MonthlyReport

共享模型 MonthlyReport；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `month` | `string` | 是 | pattern=^\d{4}-(0[1-9]|1[0-2])$。YYYY-MM，接口不静默默认当前月份。 |
| `totals` | `Totals` | 是 | 统一口径汇总，前端不重新做另一套计算。 |
| `expense_by_category` | `array[object]` | 是 | 分类毛支出构成，仅返回毛支出大于0的类别；用于饼图。 |
| `daily_trend` | `array[object]` | 是 | 该月每个自然日按日期升序返回，无交易日各项为0。 |
| `budgets` | `array[BudgetStatus]` | 是 | 该月已设置预算的类别，按类别代码稳定排序。 |


### FieldError

共享模型 FieldError；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `field` | `string` | 是 | 字段路径，例如rows[0].amount_fen或amount_fen。 |
| `row_id` | `string / null` | 是 | 本批次内稳定的草稿行标识，确认和分类按它关联，不能依赖数组顺序。 |
| `code` | `string` | 是 | 稳定的机器错误代码，前端不能按中文message判断逻辑。 |
| `message` | `string` | 是 | 面向用户的说明文本。 |


### ErrorDetails

共享模型 ErrorDetails；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `fields` | `array[FieldError]` | 否 | 逐字段错误列表，row_id为null表示非草稿字段。 |
| `current_version` | `integer` | 否 | minimum=1。发生版本冲突时可返回当前版本；不存在此信息时省略。 |
| `retry_after_seconds` | `integer` | 否 | minimum=1。限流等待秒数；不存在此信息时省略。 |


### Progress

共享模型 Progress；HTTP请求与响应均遵守本定义。

| 字段 | 类型 | 必填 | 约束和含义 |
| --- | --- | --- | --- |
| `current` | `integer` | 是 | minimum=0。已处理的候选行数。 |
| `total` | `integer / null` | 是 | minimum=0。列表中为筛选后的总数；Progress中为候选行总数，可未知。 |


### ResolvedCategory

用于个人规则和预算的明确类别，不接受pending。

类型：`dining / transport / shopping / salary / housing / entertainment / health / education / other`。


## 维护步骤

1. 先修改OpenAPI和合成请求响应示例，再运行生成器。
2. 两端用生成类型和调用入口，CI验证示例与生成文件没有漂移。
3. 后端实现后还要执行真实HTTP和业务验收；静态契约通过不保证功能已实现。

