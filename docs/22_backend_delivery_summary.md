# 后端交付总结（契约 0.2.0 · 17/17 收口）

> 面向读者的说明：这份文档是**后端"已经做完的东西"的完整清单**，用于评审、交接和前端对接。
> 字段与状态码全部按 `contracts/openapi.json` 0.2.0 与 `backend/app` 实际实现逐条核对过；
> 凡"契约声明了但实现未触发"的分支，在文中明确标注，不糊。
>
> | 项目 | 值 |
> | --- | --- |
> | 契约版本 | 0.2.0（`contracts/openapi.json`，17 operations / 35 schemas / 29 examples） |
> | 后端提交 | `f76fde4`（分支 `task/T00-baseline`） |
> | 分支提交链 | `06d643f` → `af025fd` → `65e432c` → `f76fde4` |
> | 接口完成度 | **17/17**，无占位、无 501、无 `TODO` 分支 |
> | 测试 | **162 项全过**（`cd backend && python -m unittest discover -s tests -v`） |
> | 数据存储 | 开发默认 SQLite（`backend/local-data/app.db`），生产 PostgreSQL（psycopg3） |
> | 文档日期 | 2026-11-10 |

---

## 1. 一句话结论

后端从"上传一份账单"到"导出一份中文 PDF 月报"的整条链路已经闭合，且每个破坏性分支
（重复入账、并发覆盖、越权读取、部分入账、公式注入）都有对应的实现约束和测试用例。
剩余工作全部在**前端页面、真实账单样本、截图 OCR、容器实跑**四件事上，不在后端接口上。

闭环的五个环节，逐环对应到接口：

```text
① 上传      POST /api/imports                 202 + Location + Retry-After
② 解析分类  （后台 worker，非 HTTP）           uploaded → processing
③ 确认入账  POST /api/imports/{id}/confirm     草稿 → 已确认交易（事务 / 幂等 / 去重）
④ 列表纠错  GET/PATCH /api/transactions        版本控制 + remember_rule
⑤ 规则反馈  GET/PATCH /api/classification-rules 第五环，停用后新交易回落通用规则
   ↓
   月报/预算/导出  GET /api/reports/monthly、PUT /api/budgets、GET /api/exports/*
```

---

## 2. 交付范围（模块 × 契约 × 代码 × 测试）

| 模块 | 契约操作 | 主要代码 | 测试文件（项数） |
| --- | --- | --- | --- |
| 健康检查 | `GET /health` | `routers/health.py` | `test_t00_smoke.py`（13） |
| 认证与会话 | `login` `getSession` `logout` | `routers/auth.py`、`deps.py`、`security.py` | `test_t00_smoke.py` |
| 导入中心 | `createImport` `getImport` `getImportOriginal` `retryImport` `confirmImport` | `routers/imports.py`、`services/imports.py`(870 行)、`services/worker.py`、`services/dedupe.py` | `test_imports_api.py`（26） |
| 账单列表与纠错 | `listTransactions` `patchTransaction` | `routers/transactions.py`、`services/transactions.py` | `test_ledger_api.py`（38） |
| 个人规则 | `listRules` `patchRule` | `routers/rules.py`、`services/rules.py` | `test_rules_and_exports.py`（24） |
| 月报 | `getMonthlyReport` | `routers/reports.py`、`services/reporting.py` | `test_reporting.py`（18） |
| 预算 | `putBudget` | `routers/budgets.py`、`services/budgets.py` | `test_reporting.py` |
| 导出 | `exportTransactions` `exportMonthlyPdf` | `routers/exports.py`、`services/exporting.py`(417 行) | `test_rules_and_exports.py` |
| 智能模块（解析/分类） | 非 HTTP，内部接口 | `intelligence/base.py`、`fallback.py`、`tables.py`、`rules.py`、`normalize.py` | `test_intelligence.py`（43） |
| 公共设施 | — | `contracts.py`(生成)、`errors.py`、`middleware.py`、`crypto.py`、`config.py`、`http_utils.py` | 各测试共用 |

**162 = 13 + 26 + 38 + 43 + 18 + 24**（其中 18 含预算用例，24 含 A07 全闭环用例）。

---

## 3. 十分钟跑起来

```bash
# 1) 依赖
python -m pip install -r backend/requirements-dev.txt

# 2) 建表
cd backend
python -m app.migrate                # --check 只校验；--sql 导出 PostgreSQL DDL

# 3) 造演示账号 + 合成账本（金额与 fixtures 逐项核对，不一致直接非 0 退出）
python -m app.seed_demo --username demo_a --password 'DemoA@2026'
python -m app.seed_demo --username demo_b --password 'DemoB@2026'

# 4) 起服务
python -m uvicorn app.main:app --reload --port 8000
```

- 交互式文档：<http://127.0.0.1:8000/docs>（这是**已实现部分**的自描述，权威契约仍是 `contracts/openapi.json`）
- 健康检查：`GET http://127.0.0.1:8000/health` → `{"status":"ok"}`；数据库不可用时 503 `DB_UNAVAILABLE`
- 前端联调地址：后端 `127.0.0.1:8000`，前端 `127.0.0.1:5173`，Vite 代理 `/api` 与 `/health`
- 生产必填：`APP_ENV=production` 时必须显式提供 `SESSION_SECRET` 与 `DATA_ENCRYPTION_KEY`，缺失直接启动失败（不允许悄悄用默认值）

主要环境变量（`backend/app/config.py`，模板见 `.env.example`）：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `DATABASE_URL` | sqlite `backend/local-data/app.db` | 生产用 `postgresql+psycopg://...` |
| `SESSION_SECRET` / `DATA_ENCRYPTION_KEY` | 开发自动生成到 `local-data/dev_secrets.json` | 会话签名 / 敏感字段 AES-GCM 密钥 |
| `SESSION_TTL_HOURS` | 12 | 会话有效期 |
| `COOKIE_SECURE` | 生产为 true | Cookie 是否仅 HTTPS |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCK_SECONDS` | 5 / 60 | 账号级登录限流 |
| `UPLOAD_MAX_FILE_BYTES` / `UPLOAD_MAX_IMAGE_BYTES` | 10MiB / 5MiB | 导入上限 |
| `BATCH_DEADLINE_SECONDS` / `BATCH_DRAFT_TTL_HOURS` | 300 / 24 | 批次处理期限 / 草稿保留 |
| `EXPORT_MAX_ROWS` | 50000 | 单次 CSV 导出行数上限 |
| `PDF_FONT_PATH` | 空=自动搜索 | 中文字体（容器内为 `wqy-zenhei.ttc`） |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许的前端源 |

---

## 4. 全局通信约定

### 4.1 鉴权与 CSRF

| 项目 | 约定 |
| --- | --- |
| 会话载体 | Cookie `bill_session`（`HttpOnly`、`SameSite=Lax`、`Path=/`，生产加 `Secure`），服务端只存 token 指纹 |
| CSRF | 登录/`GET /api/auth/me` 返回 `csrf_token`；**所有写请求**（POST/PUT/PATCH/DELETE）必须带请求头 `X-CSRF-Token` |
| 读接口 | 只校验会话（`require_session`） |
| 写接口 | 校验会话 + CSRF（`require_csrf`），缺或不匹配 → 403 `CSRF_INVALID` |
| 登录限流 | 同一账号连续失败 5 次锁 60 秒 → 429 `LOGIN_LOCKED`，`details.retry_after_seconds` + `Retry-After` 头 |
| 账号不可用 | 401 `ACCOUNT_DISABLED` |

注意 Cookie 属性 `SameSite=Lax` 意味着**必须同源访问后端**。开发期用 Vite 代理到 8000，
不要把 `setApiBaseUrl` 指向另一个端口去裸跑跨源，否则会话时有时无。

### 4.2 统一错误结构

所有非 2xx（含框架产生的 422）都是同一个信封，前端**只能按 `code` 分支**，不得匹配中文文案：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请修正标红的字段后重试",
    "details": {
      "fields": [
        {"field": "rows[0].transaction.amount_fen", "row_id": "row-3", "code": "INVALID_AMOUNT", "message": "金额必须为正整数分"}
      ],
      "current_version": 3,
      "retry_after_seconds": 42
    }
  }
}
```

`details` 三个字段都可缺省；`fields[].row_id` 为 `null` 表示不是草稿行的错误。

### 4.3 错误码总表（实现实际会返回的）

| code | HTTP | 触发场景 | 前端该做什么 |
| --- | --- | --- | --- |
| `AUTH_REQUIRED` | 401 | 无 Cookie / 会话过期 / 被删 | 清本地会话，跳登录页 |
| `AUTH_INVALID` | 401 | 账号或密码错误 | 提示"账号或密码不正确"，保留用户名 |
| `ACCOUNT_DISABLED` | 401 | 账号被停用 | 提示联系管理员 |
| `LOGIN_LOCKED` | 429 | 失败次数超限 | 按 `details.retry_after_seconds` 倒计时禁用按钮 |
| `CSRF_INVALID` | 403 | 缺/错 `X-CSRF-Token` | 重新 `getSession` 取新 token 后重试一次；仍失败则跳登录 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在**或不属于本人** | 提示不存在；不要显示"无权限"（会泄露存在性） |
| `VERSION_CONFLICT` | 409 | `expected_version` 落后 | 用 `details.current_version` 提示并重新拉取，禁止自动覆盖 |
| `BATCH_STATE_CONFLICT` | 409 | 批次状态不允许该操作（非 failed 重试、非 pending_review 确认、已确认过再确认、草稿过期） | 刷新批次；按 `message` 给用户解释 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 `request_id` 提交了不同请求体 / 快照损坏 | 生成新 `request_id` 重新提交（内容改动后必须换 ID） |
| `VALIDATION_ERROR` | 422 | 参数/字段不合法（含 `DATE_RANGE_REVERSED`、`FILENAME_MISSING`、`RULE_PATCH_EMPTY`、导出行数超限） | 逐条定位到字段，`fields[].row_id` 高亮对应草稿行 |
| `UPLOAD_TOO_LARGE` | 413 | 文件超 10MiB / 图片超 5MiB | 提示上限并让用户重选 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 扩展名不支持，或内容与扩展名不符（魔数校验） | 提示支持 PNG/JPEG/CSV/XLSX，要求用平台原样导出 |
| `PAYLOAD_TOO_LARGE` / `UNSUPPORTED_MEDIA_TYPE` | 413/415 | 框架层拦截，语义同上 | 同上 |
| `SERVICE_UNAVAILABLE` | 503 | 数据库不可用、原文件解密失败 | 提示稍后重试，保留当前页面与输入 |
| `EXPORT_UNAVAILABLE` | 503 | PDF 字体/渲染依赖缺失 | 提示导出暂不可用，页面数据仍然正常 |
| `DB_UNAVAILABLE` | 503 | `/health` 探活失败 | 部署/运维侧信号 |
| `INTERNAL_ERROR` | 500 | 未捕获异常、交易密文损坏 | 提示"服务异常"，可重试；不展示堆栈 |

契约里 `login` 声明了 403 `CSRF_INVALID` 分支，**当前实现未对登录做 Origin 校验**，
所以这个分支实际不会触发。前端不必为登录单独写 403 处理（统一兜底即可）。

### 4.4 金额、时间、月份

| 约定 | 说明 |
| --- | --- |
| 金额 | 一律 **CNY 整数分**，字段名统一带 `_fen`。不存在浮点元。`amount_fen ≥ 1`（交易）；预算 `amount_fen ≥ 0` |
| 时间 | ISO 8601 **必须带时区**（如 `2026-11-08T12:00:00+08:00`）；无时区的时间在确认/纠错时返回 422 `TIME_WITHOUT_TIMEZONE` |
| 归月 | 按 `Asia/Shanghai` 自然日归一，落库为 `month_index = YYYY-MM` |
| 月份参数 | 字符串 `YYYY-MM`，服务端正则限定月份为 01–12；接口**不静默默认当月**，缺了就 422 |
| 日期筛选 | `date_from`/`date_to` 是**上海自然日**且两端包含；`date_from > date_to` → 422 `DATE_RANGE_REVERSED`（`fields[].field = "date_from"`） |
| 报表口径 | `net_expense_fen = gross_expense_fen - refund_fen`；`balance_fen = income_fen - net_expense_fen`（**是收支差额，不是账户余额**） |

### 4.5 响应头

| 头 | 出现位置 | 说明 |
| --- | --- | --- |
| `X-Contract-Version: 0.2.0` | 所有业务响应 | 前端可比对 SDK 版本；被直接返回的进程级 500 可能没有 |
| `Location: /api/imports/{id}` | `createImport` / `retryImport` 202 | 建议直接跳转 |
| `Retry-After: 1` | 同上 | 首次轮询间隔秒 |
| `Retry-After` | 429 `LOGIN_LOCKED` | 锁定剩余秒 |
| `Content-Disposition` | 导出、原文件 | RFC 5987 中文文件名（`filename*=UTF-8''...`） |
| `Cache-Control: private, no-store` | 原文件 | 账单原件禁止进浏览器缓存 |

---

## 5. 枚举字典

前端需要中文映射的都在这里，代码值不要翻译、不要自己造。

| 枚举 | 值 | 中文建议 |
| --- | --- | --- |
| `Source` 平台 | `alipay` / `wechat` | 支付宝 / 微信 |
| `IngestionMethod` 采集方式 | `file` / `screenshot` | 导出文件 / 账单截图 |
| `Category` 类别（含待分类） | `dining` `transport` `shopping` `salary` `housing` `entertainment` `health` `education` `other` `pending` | 餐饮 交通 购物 工资 居住 娱乐 医疗 教育 其他 待分类 |
| `ResolvedCategory`（预算/规则用） | 同上**不含** `pending` | 预算与规则不接受"待分类" |
| `FlowType` 资金事件 | `income` `expense` `refund` `transfer` `repayment` | 收入 支出 退款 内部转账 还款 |
| `ClassificationSource` 分类来源 | `user_rule` `general_rule` `deepseek` `manual` `pending` | 个人规则 通用规则 AI 模型 用户手动 待分类 |
| `BatchStatus` 批次状态 | `uploaded` `processing` `pending_review` `completed` `failed` | 已上传 处理中 待确认 已完成 失败 |
| `duplicate_status` 去重状态 | `unique` `duplicate` `suspected` | 唯一 / 明确重复 / 疑似重复 |
| `Transaction.status` | 固定 `confirmed` | 只有已确认交易会出现在列表和报表 |

`Issue.code`（草稿行/批次上的机器码，前端按码分支）：

| code | 出现在 | 含义 |
| --- | --- | --- |
| `AMOUNT_MISSING` / `INVALID_AMOUNT` | 行 | 金额缺失 / 格式非法 |
| `TIME_MISSING` / `INVALID_TIME` | 行 | 时间为空 / 解析失败 |
| `FLOW_TYPE_UNKNOWN` | 行 | 收/支方向无法判断 |
| `MERCHANT_MISSING` | 行 | 商户为空（可入账，但不能建个人规则） |
| `CATEGORY_UNCERTAIN` | 行 | 规则未命中，待用户选 |
| `ROW_UNPARSABLE` | 行 | 整行无法解析 |
| `DUPLICATE_SUSPECTED` | 行 | 文件内疑似重复 |
| `DUPLICATE_EXISTING` | 行 | 与库中已入账记录撞去重摘要（`duplicate_status` 已是 `duplicate`） |
| `ROWS_SKIPPED` | 批次（`row_id` 为 null） | 跳过了 N 行关闭/0 元/说明行 |
| `NO_ROWS_PARSED` | 批次 | 文件可读但没有可入账交易 |
| `DRAFT_UNREADABLE` | 批次 | 草稿密文解不开（密钥更换/损坏） |
| `BATCH_TIMEOUT` / `BATCH_INTERRUPTED` | 批次 | 超 300 秒 / 服务重启中断（可重试） |
| `BATCH_EXPIRED` / `CRYPTO_FAILED` | 批次 | 草稿超过 24 小时 / 原件解不开（需重新上传） |
| `UNSUPPORTED_TEMPLATE` `INVALID_FILE` `OCR_UNAVAILABLE` `OCR_FIELD_MISSING` `MODEL_TIMEOUT` `MODEL_OUTPUT_INVALID` | 批次 | 智能模块抛出的失败（可重试） |

---

## 6. 接口总表（17 个）

图例：鉴权列 **读** = 只需会话，**写** = 会话 + `X-CSRF-Token`，**无** = 公开。

| # | 方法 | 路径 | operationId | 鉴权 | 成功 | 错误码 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `/health` | `health` | 无 | 200 `{status:"ok"}` | 503 `DB_UNAVAILABLE` |
| 2 | POST | `/api/auth/login` | `login` | 无 | 200 `Session` | 401 `AUTH_INVALID`/`ACCOUNT_DISABLED`、422、429 `LOGIN_LOCKED` |
| 3 | GET | `/api/auth/me` | `getSession` | 读 | 200 `Session` | 401 `AUTH_REQUIRED` |
| 4 | POST | `/api/auth/logout` | `logout` | 写 | 204 无正文 | 401、403 `CSRF_INVALID` |
| 5 | POST | `/api/imports` | `createImport` | 写 | 202 `Batch` | 413、415、422 |
| 6 | GET | `/api/imports/{id}` | `getImport` | 读 | 200 `Batch` | 404 |
| 7 | GET | `/api/imports/{id}/original` | `getImportOriginal` | 读 | 200 二进制 | 404、503 |
| 8 | POST | `/api/imports/{id}/retry` | `retryImport` | 写 | 202 `Batch` | 404、409 `BATCH_STATE_CONFLICT`/`VERSION_CONFLICT` |
| 9 | POST | `/api/imports/{id}/confirm` | `confirmImport` | 写 | 200 `ConfirmResult` | 404、409（三种）、422 |
| 10 | GET | `/api/transactions` | `listTransactions` | 读 | 200 `TransactionPage` | 422 |
| 11 | PATCH | `/api/transactions/{id}` | `patchTransaction` | 写 | 200 `Transaction` | 404、409、422、500 |
| 12 | GET | `/api/classification-rules` | `listRules` | 读 | 200 `RuleList` | 401 |
| 13 | PATCH | `/api/classification-rules/{id}` | `patchRule` | 写 | 200 `ClassificationRule` | 404、409、422 `RULE_PATCH_EMPTY` |
| 14 | GET | `/api/reports/monthly` | `getMonthlyReport` | 读 | 200 `MonthlyReport` | 422 |
| 15 | PUT | `/api/budgets` | `putBudget` | 写 | 200 `Budget` | 422 |
| 16 | GET | `/api/exports/transactions.csv` | `exportTransactions` | 读 | 200 `text/csv` | 422、503 |
| 17 | GET | `/api/exports/monthly.pdf` | `exportMonthlyPdf` | 读 | 200 `application/pdf` | 422、503 `EXPORT_UNAVAILABLE` |

---

## 7. 逐接口：请求与返回字段

> 通用：所有 `id` 都是服务端生成的字符串，前端原样使用，不解析、不拼接。
> 「必填」指响应中一定存在；请求体字段未标可选即必填。

### 7.1 `GET /health`

响应 200：

```json
{"status": "ok"}
```

真的执行 `SELECT 1`，不是无条件 ok。容器编排与部署验证读这个点。

### 7.2 认证

**`POST /api/auth/login`** 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `username` | string | 账号 |
| `password` | string | 密码，只用于本次请求 |

响应 200 `Session`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user.id` | string | 用户 ID |
| `user.username` | string | 账号 |
| `csrf_token` | string | 写请求的 `X-CSRF-Token`，前端存内存/会话状态，退出后清除 |

副作用：`Set-Cookie: bill_session=...; HttpOnly; SameSite=Lax; Path=/`，`Cache-Control: no-store`。

**`GET /api/auth/me`** → 200 同上 `Session`。页面启动第一件事就是它：拿到 `user` 与 `csrf_token`；
401 即跳登录。

**`POST /api/auth/logout`** → 204 无正文（SDK 返回 `undefined`），服务端删会话行并 `delete_cookie`。
即使会话已失效，前端也应清本地状态。

### 7.3 导入中心（5 个）

**`POST /api/imports`**（`multipart/form-data`）

| 表单字段 | 类型 | 说明 |
| --- | --- | --- |
| `source` | `alipay` \| `wechat` | 账单所属平台 |
| `ingestion_method` | `file` \| `screenshot` | `file` 只收 `.csv/.xlsx`；`screenshot` 只收 `.png/.jpg/.jpeg` |
| `file` | 二进制 | 上限：文件 10MiB、图片 5MiB；会做魔数校验（CSV 需可解码为 UTF-8/GB18030，XLSX 需 `PK`，PNG/JPEG 需对应文件头） |

响应 **202**，`Batch` 全量结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 批次 ID |
| `version` | int | 批次版本，写操作用 `expected_version` |
| `source` | `Source` | 平台 |
| `ingestion_method` | `IngestionMethod` | 采集方式 |
| `status` | `BatchStatus` | 初始为 `uploaded` |
| `rows` | `TransactionDraft[]` | 处理中为空数组 |
| `issues` | `Issue[]` | 批次级问题，空数组表示暂无 |
| `progress.current` / `progress.total` | int / int\|null | 已处理行数 / 候选总数（可未知） |
| `file_name` | string | 净化后的文件名（只留文件名本身） |
| `created_at` / `updated_at` | ISO8601 | 带时区 |

`TransactionDraft`（草稿行，注意有 5 个字段允许为 `null`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `row_id` | string | 批次内稳定行标识；确认按它关联，**不要依赖数组下标** |
| `source_transaction_id` | string\|null | 源交易号，可能缺失 |
| `occurred_at` | string\|null | 交易时间；null 表示未识别出 |
| `amount_fen` | int\|null | 金额（分）；null 表示未识别出 |
| `currency` | `"CNY"` | 固定 |
| `flow_type` | `FlowType`\|null | null 表示方向未知，确认前必须明确 |
| `merchant` | string | 商户原始名称，可为空串 |
| `description` | string | 说明，空说明为空串 |
| `category` | `Category` | 可为 `pending` |
| `classification_source` | `ClassificationSource` | 真实来源，不会伪造 `deepseek` |
| `classification_reason` | string | 简短依据，给用户看 |
| `duplicate_status` | `unique`\|`duplicate`\|`suspected` | `duplicate` 确认时会被跳过 |
| `issues` | `Issue[]` | 该行的问题 |

**`GET /api/imports/{id}`** → 200 同一个 `Batch`。轮询用：首次 1 秒，之后 2 秒；
`pending_review`/`completed`/`failed` 停止；120 秒仍处理中则暂停自动轮询、给"手动刷新"，
**不能由前端自行判失败**（服务端 300 秒才转 `failed`）。别人的批次 → 404。

**`GET /api/imports/{id}/original`** → 200 二进制流，`Content-Type` 按真实类型（图片 `inline`、文件 `attachment`），
`Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff`。前端用 Blob + `URL.createObjectURL`
预览，**必须 `revokeObjectURL`**；这是唯一能拿到原图的途径，没有公开静态 URL。

**`POST /api/imports/{id}/retry`** 请求体 `{"expected_version": 3}` → 202 `Batch`（`version` 已 +1，状态回 `processing`）。
仅 `failed` 且未过期可重试，否则 409：`BATCH_STATE_CONFLICT`（状态不对/已过期）或 `VERSION_CONFLICT`（版本旧）。

**`POST /api/imports/{id}/confirm`** 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `request_id` | uuid 字符串 | 幂等键。**同一份请求体重试必须复用**；内容一改就必须换新 ID |
| `expected_version` | int | 从最近一次 `getImport` 拿到的 `version` |
| `rows` | `ConfirmRow[]` | 本次勾选入账的行 |
| `rows[].row_id` | string | 必须是本批次里的行 |
| `rows[].transaction` | `TransactionInput` | 该行最终字段（用户修正后的） |
| `rows[].allow_suspected_duplicate` | bool | 仅当用户明确"疑似重复仍要入账"时 `true` |

`TransactionInput`（确认用，全部必填、不可为 null）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `source_transaction_id` | string\|null | 无可靠事件号时可 null |
| `occurred_at` | ISO8601 | **必须带时区**，否则 422 `TIME_WITHOUT_TIMEZONE` |
| `amount_fen` | int | ≥ 1 |
| `currency` | `"CNY"` | 只有 CNY |
| `flow_type` | `FlowType` | 必须明确 |
| `merchant` | string | 不能为空（422 `MERCHANT_REQUIRED`） |
| `description` | string | 可空串 |
| `category` | `Category` | 允许 `pending` |

响应 200 `ConfirmResult`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | string | 本次确认的批次 |
| `created_count` | int | 真正新增条数 |
| `duplicate_count` | int | 明确重复被跳过条数 |
| `ignored_count` | int | 草稿里**没提交**的行数 |
| `transaction_ids` | string[] | 本次新增交易 ID，幂等重放返回**同一数组** |

语义要点：先查幂等记录、再查版本（反了会让重放被判成冲突）；全部选中行同事务，任何一行不合法整体 422，
**不会部分入账**。同一 `request_id` 同体 → 原样返回当时快照；同 ID 不同体 → 409 `IDEMPOTENCY_CONFLICT`；
已确认批次用新 ID → 409 `BATCH_STATE_CONFLICT`。

### 7.4 账单（2 个）

**`GET /api/transactions`** 查询参数（全部可选）：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `date_from` / `date_to` | `YYYY-MM-DD` | 上海自然日，两端包含 |
| `category` | `Category` | 含 `pending` |
| `source` | `Source` | 平台 |
| `flow_type` | `FlowType` | 资金事件 |
| `page` | int ≥ 1 | 默认 1 |
| `page_size` | int 1–100 | 默认 50，超 100 直接 422 |

响应 200 `TransactionPage`：`items: Transaction[]`、`total`（筛选后总数）、`page`、`page_size`。
排序：`occurred_at` 倒序，再 `id` 倒序（稳定）。只返回本人 `confirmed` 交易。

`Transaction` 字段（20 个）：`id`、`version`、`source`、`ingestion_method`、`import_batch_id`、`status`（恒 `"confirmed"`）、
`source_transaction_id`、`occurred_at`、`amount_fen`、`currency`、`flow_type`、`merchant`、`description`、`category`、
`classification_source`、`classification_reason`。

**`PATCH /api/transactions/{id}`** 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `expected_version` | int | 必填，来自列表项 `version` |
| `changes` | object | 只提交要改的字段；未提交的保持原值 |
| `changes.occurred_at` | ISO8601 | 必须带时区（422 `TIME_WITHOUT_TIMEZONE`） |
| `changes.amount_fen` | int ≥ 1 | |
| `changes.currency` | `"CNY"` | |
| `changes.flow_type` | `FlowType` | |
| `changes.merchant` | string ≤500 | |
| `changes.description` | string ≤2000 | |
| `changes.category` | `Category` | 显式改类别会把来源改成 `manual`、理由写成"用户手动修正分类" |
| `changes.source_transaction_id` | string\|null | |
| `remember_rule` | bool，默认 false | true 时同时建立/更新本人商户规则 |

返回 200 整条 `Transaction`（`version` 已 +1）。
规则细节：`remember_rule` 只在「商户非空 且 类别不是 `pending`」时生效，否则静默跳过而不报错；
**提交内容与原值完全相同且没有新规则时，`version` 不变**（改了又改回不该让前端手里的版本失效）。
索引列（`month_index`/`category`/`flow_type`）在同一事务内跟着改，所以筛选与报表立刻同步。

### 7.5 个人规则（2 个）

**`GET /api/classification-rules`** → 200 `RuleList{ items: ClassificationRule[] }`，按 `source` 再 `merchant_normalized` 升序，
**包含已停用项**（否则用户无法重新启用）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 规则 ID |
| `version` | int | 乐观锁版本 |
| `source` | `Source` | 只对本人 + 该平台生效 |
| `merchant_normalized` | string | 标准化后的商户匹配键（不是原始商户名） |
| `category` | `ResolvedCategory` | 不含 `pending` |
| `enabled` | bool | 停用只影响后续自动分类，**不重写历史账单** |

**`PATCH /api/classification-rules/{id}`** 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `expected_version` | int | 必填 |
| `enabled` | bool，可选 | 停用/启用 |
| `category` | `ResolvedCategory`，可选 | 改类别 |

`enabled` 与 `category` **至少给一个**，都缺 → 422 `RULE_PATCH_EMPTY`。返回 200 单条 `ClassificationRule`。

### 7.6 月报

**`GET /api/reports/monthly?month=2026-11`**（`month` 必填）→ 200 `MonthlyReport`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `month` | string | 回显 |
| `totals.income_fen` | int | 当月收入（不含退款与内部转账） |
| `totals.gross_expense_fen` | int | 当月毛支出（不含内部转账与还款） |
| `totals.refund_fen` | int | 按退款实际发生月计入 |
| `totals.net_expense_fen` | int | 毛支出 − 退款，可为负 |
| `totals.balance_fen` | int | 收入 − 净支出（**不是账户余额**） |
| `expense_by_category` | `[{category, amount_fen}]` | 仅返回毛支出 > 0 的类别，按类别声明顺序排；饼图直接用 |
| `daily_trend` | `[{date, income_fen, gross_expense_fen, refund_fen, net_expense_fen}]` | **全月每一天**都返回，无交易日各项为 0 |
| `budgets` | `BudgetStatus[]` | 该月已设预算的类别，按类别代码排序；没设预算则为空数组 |

整月现算，不建汇总表；列表、图表、CSV/PDF 导出共用这一份口径。

### 7.7 预算

**`PUT /api/budgets`** 请求体（唯一键：用户 + `month` + `category`，存在即覆盖，始终 200）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `month` | `YYYY-MM` | 必填 |
| `category` | `ResolvedCategory` | 不接受 `pending` |
| `amount_fen` | int ≥ 0 | 0 是合法值（前端显示占比时不要除以 0） |

响应 200 `Budget{id, month, category, amount_fen}`。**没有 GET 预算接口**：预算随月报返回，避免两个视图不同步。

`BudgetStatus`：`category`、`budget_fen`、`spent_fen`（该类别当月**净**支出，退款会减回去）、
`remaining_fen`（可负）、`over_fen`（`max(0, spent - budget)`）。

### 7.8 导出（2 个，都是二进制，不是 JSON）

**`GET /api/exports/transactions.csv`** 查询参数与列表页同构（`date_from`/`date_to`/`category`/`source`/`flow_type`），
**不接受 `page`/`page_size`**：导出全部筛选结果。

- `Content-Type: text/csv; charset=utf-8`
- 编码 **UTF-8 带 BOM**（Excel 双击不乱码；程序解析请用 `utf-8-sig`）
- 列顺序固定 10 列：`occurred_at, source, flow_type, category, amount_fen, currency, merchant, description, classification_source, source_transaction_id`
- 金额列写**整数分**，不写元
- 文本单元格防公式注入：以 `=` `+` `-` `@` `\t` `\r` 开头的值前置一个单引号
- 超 `EXPORT_MAX_ROWS`（默认 5 万行）→ 422，不悄悄截断
- 文件名：`账单导出_{date_from}_{date_to}.csv`，无筛选时 `账单导出_{YYYYMMDD}.csv`

**`GET /api/exports/monthly.pdf?month=2026-11`** → `application/pdf`，数字与同月月报**完全一致**（不重新汇总）。
中文字体真嵌入（`FontFile2` + `ToUnicode`）；字体缺失时 503 `EXPORT_UNAVAILABLE`，绝不输出方块 PDF 冒充成功。
文件名：`收支月报_{YYYY-MM}.pdf`。

> 依赖提醒：PDF 走 `reportlab`（`backend/requirements.txt` 已声明，CHG-007 补齐）。
> 干净环境必须装齐 `requirements-dev.txt` 再跑测试，否则 PDF 三例会失败——那是缺依赖，不是代码问题。

已生成的真实样例（可直接打开眼验）：`桌面/智能挑战赛/导出样例/收支月报_2026-11.pdf`、`收支月报_预览.png`、`账单导出_全部.csv`。

---

## 8. 业务不变量（评审最爱问的部分）

### 8.1 批次状态机

```text
uploaded ──(worker 原子认领)──> processing ──> pending_review ──(confirm 成功)──> completed
    │                              │
    └──────────┬───────────────────┘
               └──> failed ──(retry, version+1)──> processing
```

- 认领是 `UPDATE ... WHERE status='uploaded'` + `rowcount==1`，多进程不会重复处理同一批次
- `pending_review` 才可确认；`completed` 是新终态，再来新 `request_id` 一律 409
- 任何异常路径都给终态：**不存在永久 `processing`**（超 300 秒巡检查出 → `failed` + `BATCH_TIMEOUT`）
- 草稿保留 24 小时，过期确认 → 409 `BATCH_STATE_CONFLICT`（`BATCH_EXPIRED`）

### 8.2 幂等 / 乐观锁 / 去重

| 机制 | 实现 | 破坏它的后果 |
| --- | --- | --- |
| 确认幂等 | `request_id` + 请求体摘要（`body_digest`），先查幂等、再查版本；重放返回**当时存下的快照** | 重算会让"后来又改了数据"时数字变，就不是幂等 |
| 乐观锁 | 批次/交易/规则都有 `version`，写操作必须带 `expected_version`，不符 409 + `current_version` | 静默覆盖用户刚做的修改 |
| 去重 | `dedupe_digest` = 归一化后的商户 + 金额 + 日期 + **flow_type** + 源单号等；含 `flow_type` 是为了同一订单号的"支付 + 退款"两条不被一刀切 | 误删合法交易 / 重复入账 |
| 疑似重复 | 同单号但无法区分事件 → `duplicate_status=suspected`，必须用户显式 `allow_suspected_duplicate=true` | 静默跳过让用户以为记上了；静默入账则凭空多一笔 |
| 事务 | 确认入账全部选中行同事务；纠错改写 + 索引列 + 日志 + 规则同事务 | 部分入账、报表与明细不一致 |

### 8.3 纠错 → 规则 → 生效（闭环第五环）

```text
PATCH /api/transactions/{id}  {changes:{category:"dining"}, remember_rule:true}
   → 交易改类、来源标 manual、写纠错日志（前后值加密）、按 (本人, source, 标准化商户) 建/更新规则
   → 下一份账单导入时，worker 只把**本人**的启用规则传给分类器 → 命中即 classification_source=user_rule
   → PATCH /api/classification-rules/{id} {enabled:false} 停用 → 后续交易回落 general_rule，历史账单不动
```

对应 `tests/test_rules_and_exports.py::test_a07_full_loop`，四步逐步断言。

---

## 9. 数据与安全

| 项目 | 做法 |
| --- | --- |
| 敏感明细 | 金额、商户、说明、分类来源等整段 `AES-GCM` 加密存 `encrypted_payload`；表上只留 `month_index`、`category`、`flow_type`、`source`、`status`、`version`、`enabled` 这些**已知泄露面**的明文索引列（`docs/13` 已声明） |
| 原文件 | 同样加密存库，只能通过鉴权接口解密回传，没有静态目录、没有可猜 URL |
| 密码 | bcrypt 哈希；用户不存在时也做等价慢哈希，防时序探测账号是否存在 |
| 会话 | 只存 token 指纹 + CSRF；过期会话登录时顺带清理 |
| 归属性 | 所有资源按 `user_id` 过滤；访问他人资源一律 **404**（403 等于承认"这个 ID 存在"） |
| 日志 | 纠错前后值进加密区；未捕获异常只记服务端日志，响应不泄露路径/SQL/密钥 |
| CSV | 防公式注入（见 7.8） |
| 密钥 | 开发期自动生成并落盘 `local-data/dev_secrets.json`（已 gitignore）；生产必须环境变量注入，缺失启动即失败 |

---

## 10. 测试与验证证据

```bash
cd backend
python -m pip install -r requirements-dev.txt   # 含 reportlab（PDF）、httpx（TestClient）
python -m unittest discover -s tests -v         # 162 项
python -m app.seed_demo --username demo_a --password '...'   # 与 fixtures expected 逐项核对
```

| 覆盖点 | 用例位置 |
| --- | --- |
| 未登录 401、他人资源 404、CSRF 缺失 403、登录限流 429 | `test_t00_smoke.py` |
| 上传 413/415（含魔数不符）、轮询状态流转、retry 409、confirm 幂等与 409 三态 | `test_imports_api.py` |
| 筛选/分页/日期边界、纠错版本冲突、remember_rule、索引与报表同步 | `test_ledger_api.py` |
| fixtures 口径 I=10000 / E=4200 / R=500 / 净支出 3700 / 差额 6300、跨月退款、0 预算 | `test_reporting.py` |
| A07 四步闭环、规则停用回落、CSV 表头/BOM/防注入、PDF 中文可提取 | `test_rules_and_exports.py` |
| 解析容错：GBK/UTF-8 BOM、表头漂移、关闭行跳过、金额 Decimal 无浮点漂移、分类来源诚实 | `test_intelligence.py` |

验收用例（`docs/08` A01–A14）与后端对应情况：

| 用例 | 后端状态 |
| --- | --- |
| A01 越权隔离 | 已实现并有测试（404 策略） |
| A02 两平台真实文件 | **待真实样本**（能力有，证据缺，见第 11 节） |
| A03 二次导入 / 重试 / 改内容冲突 | 已实现并有测试 |
| A04 同额合法交易、支付退款共单号 | 已实现并有测试 |
| A05 截图缺字段 | 接口与字段具备，OCR 未接（`OCR_UNAVAILABLE`） |
| A06 四种来源诚实性 | 已实现并有测试 |
| A07 反馈闭环四步 | 已实现并有测试（`test_a07_full_loop`） |
| A08 版本冲突与索引同步 | 已实现并有测试 |
| A09 fixtures 金额 | 通过（seed_demo 与测试双验） |
| A10 预算超支与 0 预算 | 已实现并有测试 |
| A11 导出与页面一致、中文 PDF | 已实现并实测（样例文件在桌面） |
| A12 重启/超时/密钥错误 | 后端侧已实现（`BATCH_INTERRUPTED`/`BATCH_TIMEOUT`/`CRYPTO_FAILED`）；断网与限流需实跑录证 |
| A13 存储/日志/仓库检查 | 已实现（加密 + 密钥分离 + gitignore） |
| A14 干净 Linux 启动 | **未实跑**（Dockerfile/compose 齐备，待执行） |

---

## 11. 已知边界与未完成项（不藏在正文里）

| 项目 | 现状 | 归属 |
| --- | --- | --- |
| 前端页面 | `frontend/` 目录**尚不存在**，六个页面零代码 | 队友 F（规格见 `docs/23`） |
| 真实平台账单 | 仓库内只有合成 fixtures，**真实账单 0 份**；A02 与"技术数据时间可行性"缺唯一硬证据 | 队长本人导出 |
| 截图 OCR | 未接入，上传截图会得到 `OCR_UNAVAILABLE` 失败批次（诚实失败，不假装成功） | 队友 D |
| Docker / 干净 Linux | `Dockerfile`、`docker-compose.yml`、字体配置齐备但未实跑；`app-ci.yml.example` 未启用 | 队长（下一步建议项） |
| PostgreSQL 实跑 | 代码按 SQLAlchemy 通用写法，迁移可导出 PG DDL（`python -m app.migrate --sql`），但只在 SQLite 实跑过 | 队长 |
| 大文件性能 | 日期区间过滤与排序在**解密后内存**完成（个人量级万条以内可接受）；量级再涨需独立明文日期索引 | 技术债，已在代码注释声明 |
| 真实 DeepSeek 分类 | 当前 `INTELLIGENCE_PROVIDER=fallback-rules`，来源永不会标 `deepseek`（诚实） | 队友 D |

---

## 12. 变更记录（CHG）

| 编号 | 内容 | 位置 |
| --- | --- | --- |
| CHG-002 | T00 骨架与统一契约产物 | `docs/10` |
| CHG-003 | 报表唯一口径抽取 | `docs/10` |
| CHG-004 | 分类来源持久化 + 后端新增三个 Issue 码 | `docs/10`、`docs/20` |
| CHG-005 | 5 处错误码与契约对齐（`AUTH_REQUIRED`/`CSRF_INVALID`/`VALIDATION_ERROR`/`AUTH_INVALID`） | `docs/10` |
| CHG-006 | 补齐 `listRules`/`patchRule` 与两个导出，契约 17/17 收口；`filtered_rows` 抽公共；`RULE_PATCH_EMPTY` | `docs/10` |
| CHG-007 | 补 `reportlab` 依赖声明（此前漏声明会让干净环境 PDF 导出永久 503）；新增交付文档 22/23；装齐依赖后 162 项全过 | `docs/10` |

---

## 13. 给评审的一句话总结

后端以 OpenAPI 为唯一契约（生成 Pydantic 模型与 TypeScript SDK，CI 检查漂移），
17 个操作全部实现并配套 162 项测试；金额全程整数分、时间全程带时区、
敏感明细全程加密、写操作全程乐观锁 + 幂等键，越权一律 404；
导出与页面共用同一份筛选与汇总实现，因此不存在"页面 12 条、导出 15 条"。
