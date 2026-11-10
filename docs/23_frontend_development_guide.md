# 前端开发文档 + 任务单（队友 F 专用）

> 读者：负责前端的队友 F。
> 前提：**后端已经 17/17 全部实现并测试通过**（提交 `f76fde4`，契约 0.2.0）。
> 你不需要 mock 六个页面，也不需要等后端补齐接口——所有页面要的数据，接口都已经在返回。
> 本文档 = 工程怎么搭 + 每个页面怎么连 + 你要做的事怎么验收。
> 后端字段与错误码的完整说明见同目录 `22_backend_delivery_summary.md`。

---

## 0. 你手上已经有什么

| 资源 | 位置 | 用途 |
| --- | --- | --- |
| 权威契约 | `contracts/openapi.json` | 17 个操作、35 个 schema。**唯一真相**，不许改 |
| TypeScript SDK | `contracts/client.generated.ts` | 17 个与 operationId 同名的函数 + 全部类型。**不许手改** |
| 请求/响应快照 | `contracts/examples.json` | 29 个真实结构的假数据，写页面时直接抄 |
| 逐接口手册 | `docs/11_api_reference.md` | 每个字段的含义 |
| 页面对接表 | `docs/12_page_api_integration.md` | 页面 × 事件 × 接口 × 失败行为 |
| 后端总结 | `docs/22_backend_delivery_summary.md` | 字段、错误码、状态机、业务不变量 |
| 后端实现 | `backend/app/**` | 有疑问就读代码，以代码为准 |
| 导出样例 | `桌面/智能挑战赛/导出样例/` | PDF/CSV 真实产物，用于对照你要展示的数字 |

**当前状态**：`frontend/` 目录还不存在。第一步由你建工程（下面给完整命令与配置），
不要指望仓库里已经有一个能跑的前端骨架。

---

## 1. 开工（半小时内看到空壳跑起来）

### 1.1 拉代码

```bash
git clone https://github.com/lorry-create/multi-bill-ledger.git
cd multi-bill-ledger
git checkout task/T00-baseline
```

### 1.2 先把后端跑起来（你必须连真后端开发，不再走 mock）

```bash
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m app.migrate
python -m app.seed_demo --username demo_a --password 'DemoA@2026'
python -m uvicorn app.main:app --reload --port 8000
```

自检三件事，任何一件失败先解决再继续：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}

curl -i -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_a","password":"DemoA@2026"}'
# 200 + Set-Cookie: bill_session=... + {"user":{...},"csrf_token":"..."}
```

演示账号里有 `seed_demo` 灌入的合成账本（收入 10000 分、毛支出 4200、退款 500、净支出 3700、差额 6300），
所以月报页一打开就有数，不用先自己传账单。

### 1.3 建前端工程

```bash
cd ..                                   # 回到仓库根
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install
npm install vue-router@4 echarts
```

`frontend/vite.config.ts` 必须配代理（**不要**用 `http://127.0.0.1:8000` 直连）：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
```

为什么必须走代理：会话 Cookie 是 `HttpOnly + SameSite=Lax`，同源请求才会稳定带上。
直连 8000 会出现"登录成功了但下一个请求 401"这类查半天的问题。
代理之后 SDK 的 `baseUrl` 保持空字符串即可，不要调 `setApiBaseUrl`。

### 1.4 同步 SDK

```bash
mkdir -p frontend/src/api
python tools/generate_contract_artifacts.py          # 会把 SDK 同步到 frontend/src/api/client.generated.ts
python tools/generate_contract_artifacts.py --check  # CI 用，必须无漂移
```

`src/api/client.generated.ts` 的文件头写着 `DO NOT EDIT`，它是生成物。
**页面不许直接 import 它**——统一走 `src/api/index.ts` 这一层（见 2.2），
否则以后加统一错误处理或换 baseUrl 要改 20 个文件。

---

## 2. 工程结构与接口层

### 2.1 建议目录

```text
frontend/src/
  api/
    client.generated.ts     # 生成物，禁止手改
    index.ts                # 页面唯一入口：封装会话/CSRF/错误/下载
    types.ts                # 少量前端视图类型（不复制后端 DTO）
  stores/
    session.ts              # user + csrf_token（内存 + sessionStorage）
  composables/
    usePolling.ts           # 批次轮询
  utils/
    money.ts                # 分 ↔ 元（精确字符串）
    date.ts                 # 本地日期 / 月份
    labels.ts               # 枚举中文映射
  pages/
    LoginPage.vue
    ImportUploadPage.vue
    ImportConfirmPage.vue
    TransactionsPage.vue
    ReportPage.vue
    RulesPage.vue
  components/
    MoneyInput.vue
    CategorySelect.vue
    IssueBanner.vue
    ErrorAlert.vue
  router.ts
```

### 2.2 `src/api/index.ts` 该长什么样

页面只从这里 import。它负责三件 SDK 不管的事：注入 CSRF、把错误统一成可展示对象、把 Blob 变成下载。

```ts
import * as sdk from './client.generated'
export * from './client.generated'   // 类型可以透出，函数不要直接用

let csrfToken = sessionStorage.getItem('csrf') ?? ''

export function setCsrf(token: string) {
  csrfToken = token
  sessionStorage.setItem('csrf', token)
}
export function clearCsrf() {
  csrfToken = ''
  sessionStorage.removeItem('csrf')
}

/** 统一包装：写接口自动带 CSRF；401 交给调用方跳登录 */
async function call<T>(fn: (csrf?: string) => Promise<T>, needCsrf = false): Promise<T> {
  try {
    return await fn(needCsrf ? csrfToken : undefined)
  } catch (e) {
    throw normalizeError(e)
  }
}

export type AppError = { status: number; code: string; message: string; fields?: sdk.FieldError[]; currentVersion?: number }

function normalizeError(e: unknown): AppError {
  if (e instanceof sdk.ApiError) {
    return {
      status: e.status,
      code: e.payload.error.code,
      message: e.payload.error.message,
      fields: e.payload.error.details?.fields,
      currentVersion: e.payload.error.details?.current_version,
    }
  }
  return { status: 0, code: 'NETWORK_ERROR', message: '网络连接失败，请检查后端是否在运行' }
}

// —— 读接口 ——
export const health = () => call(() => sdk.health({}))
export const getSession = () => call(() => sdk.getSession({}))
export const getImport = (id: string) => call(() => sdk.getImport({ path: { id } }))
export const getImportOriginal = (id: string) => call(() => sdk.getImportOriginal({ path: { id } }))
export const listTransactions = (q: Parameters<typeof sdk.listTransactions>[0]['query']) =>
  call(() => sdk.listTransactions({ query: q }))
export const listRules = () => call(() => sdk.listRules({}))
export const getMonthlyReport = (month: string) => call(() => sdk.getMonthlyReport({ query: { month } }))
export const exportTransactions = (q: Parameters<typeof sdk.exportTransactions>[0]['query']) =>
  call(() => sdk.exportTransactions({ query: q }))
export const exportMonthlyPdf = (month: string) => call(() => sdk.exportMonthlyPdf({ query: { month } }))

// —— 写接口（自动带 CSRF）——
export const login = (username: string, password: string) =>
  call(() => sdk.login({ body: { username, password } }))
export const logout = () => call(() => sdk.logout({}), true)
export const createImport = (source: sdk.Source, method: sdk.IngestionMethod, file: File) =>
  call(() => sdk.createImport({ body: { source, ingestion_method: method, file } }), true)
export const retryImport = (id: string, expectedVersion: number) =>
  call(() => sdk.retryImport({ path: { id }, body: { expected_version: expectedVersion } }), true)
export const confirmImport = (id: string, body: sdk.ConfirmInput) =>
  call(() => sdk.confirmImport({ path: { id }, body }), true)
export const patchTransaction = (id: string, body: sdk.TransactionPatch) =>
  call(() => sdk.patchTransaction({ path: { id }, body }), true)
export const patchRule = (id: string, body: sdk.RulePatch) =>
  call(() => sdk.patchRule({ path: { id }, body }), true)
export const putBudget = (body: sdk.BudgetInput) => call(() => sdk.putBudget({ body }), true)

/** 二进制下载：SDK 已返回 Blob，这里触发浏览器保存 */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
```

### 2.3 SDK 函数签名速查

所有函数第一个参数是 `{ path?, query?, body? }`，写接口第二个参数传 CSRF：

| 函数 | 参数 | 返回 |
| --- | --- | --- |
| `health` | — | `{status:"ok"}` |
| `login` | `{body:{username,password}}` | `Session` |
| `getSession` | — | `Session` |
| `logout` | — | `undefined`（204） |
| `createImport` | `{body:{source, ingestion_method, file: Blob}}` | `Batch` |
| `getImport` | `{path:{id}}` | `Batch` |
| `getImportOriginal` | `{path:{id}}` | `Blob` |
| `retryImport` | `{path:{id}, body:{expected_version}}` | `Batch` |
| `confirmImport` | `{path:{id}, body:ConfirmInput}` | `ConfirmResult` |
| `listTransactions` | `{query?:{date_from,date_to,category,source,flow_type,page,page_size}}` | `TransactionPage` |
| `patchTransaction` | `{path:{id}, body:{expected_version, changes, remember_rule?}}` | `Transaction` |
| `listRules` | — | `RuleList` |
| `patchRule` | `{path:{id}, body:{expected_version, enabled?, category?}}` | `ClassificationRule` |
| `getMonthlyReport` | `{query:{month}}` | `MonthlyReport` |
| `putBudget` | `{body:{month,category,amount_fen}}` | `Budget` |
| `exportTransactions` | `{query?:{...同列表，不含分页}}` | `Blob` |
| `exportMonthlyPdf` | `{query:{month}}` | `Blob` |

SDK 已经做了这些，你不用再写：拼 URL、编码路径参数、`credentials:'include'`、`Content-Type`、
FormData 组装、204 返回 `undefined`、二进制返回 `Blob`、非 2xx 转 `ApiError`、
成功状态码与契约不符时抛 `UNEXPECTED_STATUS`。

---

## 3. 全局规则（写每一页之前先背下来）

### 3.1 会话与 CSRF

1. 应用启动 → `getSession()`：成功则存 `user` + `setCsrf(csrf_token)`；401 跳 `/login`。
2. 登录成功 → 同样 `setCsrf(response.csrf_token)`。**token 只放内存 + sessionStorage，不写 localStorage**（退出/关标签即失效）。
3. 任何请求返回 401 `AUTH_REQUIRED` → `clearCsrf()` + 跳登录（不要弹 toast 了事）。
4. 返回 403 `CSRF_INVALID` → 重新 `getSession()` 刷新 token，**自动重试一次**；再失败跳登录。
5. 退出 → `logout()`（必须带 CSRF）→ 无论成功失败都清本地状态并跳登录。
6. 一个容易踩的细节：SDK 在**没有 CSRF token 时抛的是普通 `Error`（"CSRF token required"），不是 `ApiError`**。
   所以启动必须先 `getSession()`；如果你看到 `NETWORK_ERROR` 但网络明明正常，先怀疑 token 没设上。

### 3.2 错误处理映射（照这张表写，不要自己发挥）

| HTTP | code | 页面行为 |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` / `AUTH_INVALID` / `ACCOUNT_DISABLED` | 前两个跳登录；`AUTH_INVALID` 在登录页内联提示"账号或密码不正确" |
| 403 | `CSRF_INVALID` | 刷新 token 重试一次 |
| 404 | `RESOURCE_NOT_FOUND` | 提示"记录不存在或已被删除"，回列表页；**不要说"无权限"** |
| 409 | `VERSION_CONFLICT` | 弹「内容已被修改」：展示 `details.current_version`，提供「重新加载」，禁止自动覆盖提交 |
| 409 | `BATCH_STATE_CONFLICT` | 刷新批次详情/列表，按 `message` 告诉用户原因（已确认过 / 只有失败批次能重试 / 草稿已过期） |
| 409 | `IDEMPOTENCY_CONFLICT` | 说明"这次提交内容与上次不同"，生成新 `request_id` 后允许重提 |
| 413 | `UPLOAD_TOO_LARGE` | 上传区红字：文件 10MiB / 图片 5MiB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 提示支持 PNG/JPEG/CSV/XLSX 且需平台原样导出 |
| 422 | `VALIDATION_ERROR` | 遍历 `details.fields`：有 `row_id` 的高亮该草稿行并滚到可见；无 `row_id` 的定位到表单字段 |
| 429 | `LOGIN_LOCKED` | 按 `details.retry_after_seconds` 倒计时禁用登录按钮 |
| 503 | `SERVICE_UNAVAILABLE` / `EXPORT_UNAVAILABLE` | 页面保留数据，提示稍后重试，给「重试」按钮 |
| 500 | `INTERNAL_ERROR` | 通用错误提示 + 重试入口，不展示原始信息 |

**只能按 `code` 分支，不许匹配中文 `message`。** `message` 是给人看的，随时可能改文案。

### 3.3 金额：全程整数分，只在显示层转元

```ts
// utils/money.ts
/** 分 → 元字符串，永远两位小数。不要用 /100 后直接 toFixed 之外的浮点运算 */
export function fenToYuan(fen: number | null | undefined): string {
  if (fen === null || fen === undefined) return '—'
  const sign = fen < 0 ? '-' : ''
  const abs = Math.abs(fen)
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}

/** 用户输入的元 → 分。用字符串解析，不许 Number(x) * 100（0.1+0.2 那套会差 1 分） */
export function yuanToFen(input: string): number | null {
  const text = input.trim().replace(/[¥,，\s]/g, '')
  if (!/^-?\d+(\.\d{0,2})?$/.test(text)) return null
  const negative = text.startsWith('-')
  const [intPart, decPart = ''] = text.replace('-', '').split('.')
  const fen = Number(intPart) * 100 + Number(decPart.padEnd(2, '0'))
  if (!Number.isSafeInteger(fen)) return null
  return negative ? -fen : fen
}
```

规则：金额输入框 `type="text"`（不是 `number`，避免 `1e3`、尾随小数被浏览器改造）；
失焦时校验并回填标准格式；`amount_fen` 提交时必须是 `≥1` 的整数（交易）/`≥0`（预算）。

### 3.4 日期与月份

- 日期筛选值用**本地日期** `YYYY-MM-DD`，不要 `new Date().toISOString().slice(0,10)`（那是 UTC，晚上 8 点后会差一天）。
- 月份 `YYYY-MM` 由 `<input type="month">` 直接给，或自己格式化。
- 交易时间展示用 `Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', ...})`。
- 提交 `occurred_at` 时必须带时区：`2026-11-08T12:00:00+08:00`。
  用 `new Date(localString)` 后 `.toISOString()` 会转成 UTC（`...Z`），语义正确、后端也接受；
  但如果手动拼字符串，务必带 `+08:00`，否则 422 `TIME_WITHOUT_TIMEZONE`。

### 3.5 枚举中文映射（直接抄）

```ts
// utils/labels.ts
export const CATEGORY_LABEL: Record<string, string> = {
  dining: '餐饮', transport: '交通', shopping: '购物', salary: '工资', housing: '居住',
  entertainment: '娱乐', health: '医疗', education: '教育', other: '其他', pending: '待分类',
}
export const SOURCE_LABEL = { alipay: '支付宝', wechat: '微信' } as const
export const FLOW_LABEL = {
  income: '收入', expense: '支出', refund: '退款', transfer: '内部转账', repayment: '还款',
} as const
export const CLASSIFICATION_LABEL = {
  user_rule: '个人规则', general_rule: '通用规则', deepseek: 'AI 模型', manual: '用户手动', pending: '待分类',
} as const
export const STATUS_LABEL = {
  uploaded: '已上传', processing: '解析中', pending_review: '待确认', completed: '已完成', failed: '失败',
} as const
export const RULE_CATEGORIES = ['dining','transport','shopping','salary','housing','entertainment','health','education','other'] as const
```

`RULES_CATEGORIES` 里**没有 `pending`**：规则和预算都不接受"待分类"，下拉框别把它列进去。

---

## 4. 六个页面规格

路由建议：`/login`、`/`（重定向到 `/transactions`）、`/import`、`/import/:id`、`/transactions`、`/report`、`/rules`。
除 `/login` 外都要求已登录（路由守卫调 `getSession()` 一次即可，结果缓存在 store）。

### 4.1 登录页 `/login` — 接口：`login`、`getSession`

| 项 | 规格 |
| --- | --- |
| 元素 | 账号、密码、登录按钮、错误提示区 |
| 成功 | `setCsrf` → 跳 `/transactions` |
| 失败 | 401 `AUTH_INVALID` 内联"账号或密码不正确"；429 显示倒计时"请 X 秒后重试"并禁用按钮；0 网络错误显示"后端未启动" |
| 细节 | 回车提交；提交中按钮 loading 且防重复点击；密码框 `autocomplete="current-password"` |
| 演示账号 | `demo_a` / `demo_b`（密码由队长设定），两个账号的数据必须互相看不到 |

### 4.2 导入中心 `/import` — 接口：`createImport`

| 项 | 规格 |
| --- | --- |
| 元素 | 平台选择（支付宝/微信）、采集方式（文件/截图）、拖拽或选择文件、上传按钮 |
| 前端预校验 | 文件：`.csv/.xlsx`；截图：`.png/.jpg/.jpeg`；大小 10MiB / 5MiB（预校验只为体验，服务端仍会校验） |
| 成功 | 202 → 记下 `batch.id` 与 `batch.version` → 跳 `/import/:id` |
| 失败 | 413/415/422 按 3.2 表提示；不要自己判"上传失败"就清空选择 |
| 细节 | 上传中显示进度态（`fetch` 拿不到 upload progress 就显示 indeterminate，别做假进度条） |

### 4.3 确认页 `/import/:id` — 接口：`getImport`、`getImportOriginal`、`confirmImport`、`retryImport`

这是整个作品最核心的一页，评审会用 A03/A04/A05/A07 打这一页。

**状态机与展示**

| `status` | 页面 |
| --- | --- |
| `uploaded` / `processing` | 进度条（用 `progress.current/total`，`total` 为 null 时用 indeterminate）+ "解析中，请稍候" |
| `pending_review` | 显示草稿表格 + 原件对照 + 确认按钮 |
| `completed` | 显示"已入账 X 条"结果 + 去账单页/月报页的入口，确认按钮禁用 |
| `failed` | 显示 `issues[0].code` 对应文案 + 「重试」按钮（`retryImport`，带当前 `version`） |

**轮询**：首次 1 秒，之后每 2 秒；到 `pending_review/completed/failed` 停止；
累计 120 秒仍在处理 → 停止自动轮询 + 显示「继续等待/手动刷新」。
组件 `onUnmounted` 必须清掉定时器。

```ts
// composables/usePolling.ts 关键形态：用 setTimeout 递归，别用 setInterval（会重叠请求）
let timer: number | undefined
let elapsed = 0
async function tick() {
  const batch = await getImport(id)
  apply(batch)
  if (['pending_review', 'completed', 'failed'].includes(batch.status)) return
  elapsed += elapsed === 0 ? 1000 : 2000
  if (elapsed > 120_000) { paused.value = true; return }
  timer = window.setTimeout(tick, elapsed === 1000 ? 1000 : 2000)
}
```

**表格列**（草稿 `TransactionDraft`）：勾选 | 行问题 | 时间 | 金额（分→元） | 收支方向 | 商户 | 说明 | 类别 | 分类来源 | 重复状态。

**必须遵守的交互规则**

1. `duplicate_status === 'duplicate'`：默认**不勾选**且禁选，行尾提示"已入账，确认时会跳过"。
2. `duplicate_status === 'suspected'`：默认不勾选，勾选时弹确认框"疑似重复，仍作为新交易入账？"；
   用户同意后该行 `allow_suspected_duplicate = true`，否则不提交该行的 `true`（后端会 422 `SUSPECTED_DUPLICATE_NOT_ALLOWED`）。
3. `occurred_at`、`amount_fen`、`flow_type` 任一为空/`pending` 时**不允许勾选**，行内提示补全。
4. 行内编辑后本地状态与草稿分离：提交时构造 `TransactionInput`（八个字段全给，不能把缺字段原样丢回去）。
5. 确认按钮点击后 → `disabled`，防止连点（服务端也幂等，但别让用户看到两次成功）。
6. `request_id` 的生成与复用：

```ts
// 点确认时生成一次，并记住"这次提交的序列化内容"
let pendingSnapshot: { requestId: string; bodyJson: string } | null = null

function buildRequest(): ConfirmInput { /* 从选中行构造 */ }

async function onConfirm() {
  const body = buildRequest()
  const json = JSON.stringify(body)
  if (!pendingSnapshot || pendingSnapshot.bodyJson !== json) {
    // 内容变了（或首次）→ 换新 ID
    pendingSnapshot = { requestId: crypto.randomUUID(), bodyJson: json }
  }
  try {
    const result = await confirmImport(id, { ...body, request_id: pendingSnapshot.requestId })
    // created_count / duplicate_count / ignored_count 三个数都显示
  } catch (e) {
    // 网络错误：用同一 pendingSnapshot 重试，不允许换 ID
  }
}
```

**原件对照**：`getImportOriginal` 返回 Blob。图片用 `URL.createObjectURL` 显示，切换批次或离开页面时 `revokeObjectURL`；
CSV/XLSX 原件不要尝试在页面里渲染，给"下载原件"即可（同样用 Blob + `a[download]`）。
**不要**把 Blob 当 JSON 解析，也不要试图用 URL 猜一个静态地址。

### 4.4 账单页 `/transactions` — 接口：`listTransactions`、`patchTransaction`、`exportTransactions`

| 项 | 规格 |
| --- | --- |
| 筛选 | 日期区间（`date_from`/`date_to`，两端包含）、类别、平台、收支方向；改动即重查（第 1 页） |
| 分页 | `page` 从 1 开始，`page_size` 默认 50、上限 100；显示 `total` 与总页数 |
| 表格列 | 时间、平台、方向、类别、商户、金额、分类来源、操作 |
| 编辑弹窗 | 可改时间、金额、方向、商户、说明、类别；提交 `changes` 只放**改动过的**字段 + `expected_version` |
| 记住商户 | 弹窗内复选框"记住该商户的分类"→ `remember_rule: true`，文案要说明"影响之后的新交易，不改历史" |
| 成功后 | 用返回的 `Transaction` 原地更新该行（新 `version`），并刷新月报缓存 |
| 409 | 弹"记录已被修改"，展示 `details.current_version`，给「重新加载」 |
| 空数据 | 空状态 + "去导入账单"入口，不是报错 |
| 导出 | 用**当前筛选对象**（去掉 `page/page_size`）调 `exportTransactions`，`saveBlob(blob, '账单导出.csv')` |

日期区间前端要防 `date_from > date_to`（后端会 422 `DATE_RANGE_REVERSED`），选完就校验。

### 4.5 月报页 `/report` — 接口：`getMonthlyReport`、`putBudget`、`exportMonthlyPdf`

| 项 | 规格 |
| --- | --- |
| 月份切换 | `<input type="month">`，值直接作为 `month`；**不要**默认空值，初始化为本月 |
| 汇总卡 | 收入 `income_fen`、毛支出 `gross_expense_fen`、退款 `refund_fen`、净支出 `net_expense_fen`、收支差额 `balance_fen`（文案必须写"收支差额"，**不能写"余额"**） |
| 饼图 | `expense_by_category`（`{category, amount_fen}`），类别中文用 `CATEGORY_LABEL` |
| 趋势图 | `daily_trend` 已含全月每一天（无交易日为 0），直接画折线，**不要前端补齐日期** |
| 预算区 | `budgets` 每项显示 `budget_fen`/`spent_fen`/`remaining_fen`/`over_fen`；`over_fen > 0` 标红；`budget_fen === 0` 时**不计算百分比**（显示"未设预算"或"—"） |
| 设置预算 | 选类别 + 输入元 → `yuanToFen` → `putBudget({month, category, amount_fen})` → 成功后重新 `getMonthlyReport(month)`，不要本地手改数字 |
| 数字来源 | **所有数字只来自接口**，前端不许自己做第二套汇总（评审会拿页面数字和 PDF 对） |
| 导出 PDF | `exportMonthlyPdf(month)` → `saveBlob(blob, \`收支月报_${month}.pdf\`)`；503 时提示"导出暂不可用"，页面数据照常显示 |
| 无数据月 | 接口返回 0 与完整日期序列，如实显示 0；**不要捏造环比**（没有上月数据就不要写"较上月 +12%"） |

### 4.6 规则页 `/rules` — 接口：`listRules`、`patchRule`

| 项 | 规格 |
| --- | --- |
| 列表 | 平台、商户（`merchant_normalized`，展示时说明这是标准化键）、类别、状态、操作 |
| 操作 | 「停用/启用」→ `patchRule(id, {expected_version, enabled})`；「改类别」→ `patchRule(id, {expected_version, category})` |
| 排序 | 接口已按 `source` + `merchant_normalized` 排好，前端保持原序 |
| 文案 | 停用要写清"只影响之后的新交易，已入账的历史不变"；不要写"已删除" |
| 空状态 | "还没有个人规则：在账单页修改分类并勾选记住商户后，会出现在这里" |
| 409 | 刷新列表后重试（规则列表通常很短，直接重拉即可） |

`enabled` 与 `category` 至少给一个，两个都不给会 422 `RULE_PATCH_EMPTY`——所以「停用」按钮必须明确带 `enabled: false`。

---

## 5. 三条必须真跑通的流程

### 5.1 上传 → 确认入账

```text
/import 选 alipay + file + 账单.csv
  → createImport 202（记 id/version）
  → /import/:id 轮询 getImport（1s、2s…，120s 上限）
  → status=pending_review，显示草稿与 issues
  → 用户修正金额/时间/类别，勾选行
  → confirmImport {request_id, expected_version, rows[]}
  → 200 ConfirmResult：显示 created_count / duplicate_count / ignored_count
  → 跳 /transactions 能看到新记录，/report 数字跟着变
```

### 5.2 纠错 → 记住商户 → 新交易命中 → 停用（A07，评审必看）

```text
① /transactions 改一笔的类别（不勾记住）
   → patchTransaction {changes:{category}, remember_rule:false}
   → /rules 页面**没有**新规则
② 再改一笔同类，勾"记住该商户"
   → patchTransaction {changes:{category}, remember_rule:true}
   → /rules 出现该商户规则（enabled=true）
③ 导入另一份含该商户的新账单
   → 草稿行的 classification_source = 'user_rule'，分类理由显示"个人规则"
④ /rules 停用该规则
   → patchRule {expected_version, enabled:false}
   → 再导入，该商户回落 'general_rule'，历史已入账记录保持原样
```

这条链是"业务闭环 30 分"的核心证据，做的时候顺手截四张图存证。

### 5.3 版本冲突与导出

```text
两个标签页打开同一笔交易 → A 页改金额保存成功 → B 页用旧 version 保存
  → 409 VERSION_CONFLICT（details.current_version=新版本）
  → B 页弹提示、重新加载，用户确认后再改，不自动覆盖

/transactions 筛选 11 月 + 餐饮 → 页面显示 N 条、合计金额
  → 导出 CSV → 打开核对：行数一致、金额一致、中文不乱码
  → /report 导出 PDF → 打开：数字与页面完全一致、中文无方块
```

---

## 6. 任务拆分（你负责的三张卡，拆成可交付的小步）

对应 `docs/06` 的 **T03 / T07 / T09**。按顺序做，每完成一格提交一次 PR。

### P0 · 主干（先做这些，做不完不影响其他部分上线）

| # | 任务 | 交付物 | 验收 |
| --- | --- | --- | --- |
| F-01 | 工程骨架 | Vite + TS + router + 代理 + `api/index.ts` + `utils/*` | `npm run build` 通过；`getSession` 在浏览器里返回 200 |
| F-02 | 登录页 + 路由守卫 | `LoginPage.vue`、session store、401 拦截 | 错误密码看到 `AUTH_INVALID` 文案；未登录访问任何页跳 `/login` |
| F-03 | 导入中心 | `ImportUploadPage.vue` | 上传 CSV 得 202 并跳转；上传 `.txt` 看到 415 提示；超限文件看到 413 |
| F-04 | 确认页（列表 + 轮询 + 状态） | `ImportConfirmPage.vue` | 轮询到 `pending_review` 自动停；`failed` 显示原因与重试按钮；离开页面无残留定时器 |
| F-05 | 确认页（行编辑 + 幂等提交） | 同上 | 缺金额/时间的行不能勾选；连点两次确认只产生一批记录；断网重试复用 `request_id` |
| F-06 | 账单页（筛选 + 分页 + 空状态） | `TransactionsPage.vue` | 日期/类别/平台/方向筛选生效；`total` 与页数正确；空结果显示空状态不报错 |
| F-07 | 账单页（编辑 + 记住商户 + 409） | 编辑弹窗、`MoneyInput.vue` | 金额 12.34 元 → `amount_fen=1234`；改类别后 `classification_source` 变 `manual`；409 有明确提示 |

### P1 · 报表与反馈（主干通了再做）

| # | 任务 | 交付物 | 验收 |
| --- | --- | --- | --- |
| F-08 | 月报页（汇总 + 饼图 + 趋势） | `ReportPage.vue` + echarts | 五个汇总数字与 `seed_demo` 口径一致（10000/4200/500/3700/6300 分）；趋势含全月天数 |
| F-09 | 预算设置与超支 | 预算弹窗 + `putBudget` | 餐饮预算 2000 分、购物 1500 分时，超支/剩余与 A10 一致；0 预算不崩 |
| F-10 | 规则页 | `RulesPage.vue` | 列表含停用项；停用后新导入回落 `general_rule`；隔离（demo_b 看不到 demo_a 的规则） |
| F-11 | 导出 | 两个导出按钮 + `saveBlob` | CSV 用 Excel 打开中文正常、行数与筛选一致；PDF 数字与页面一致、中文无方块 |
| F-12 | 原件对照 | 确认页原图/原件面板 | 图片正常显示；切换批次后旧 objectURL 已 revoke |

### P2 · 打磨（有剩余时间再做，别提前做）

- 骨架屏、Toast 统一、金额千分位、键盘可达性（Tab 顺序、Enter 提交）
- 交易表格列宽与移动端降级（≥1280px 桌面优先，比赛演示用投影）
- 页脚展示契约版本 `0.2.0`（`CONTRACT_VERSION` 来自 SDK）

### 明确不在你范围内

- 前端不动 `contracts/`、`backend/`、根 CI；接口不够用时按 `docs/10_change_delivery.md` 提变更，不许自己在前端加后端不返回的字段
- 不做 OCR、不做分类算法、不做数据库（分别是 D 与后端的事）
- 不做用户注册、改密码、账号管理（初赛范围没有）

---

## 7. 交付要求（每次 PR 都要）

1. 标题带任务号：`feat(T03): 导入确认页行编辑与幂等提交`
2. 描述里写：契约版本 `0.2.0`、受影响页面、`npm run build` 与 `vue-tsc --noEmit` 的真实输出
3. 附截图：受影响页面的正常态 + 至少一个错误态（409 或 422 最好）
4. 说明哪些交互**已经连真实后端**、哪些还是前端假数据（不许含混）
5. 不提交 `node_modules`、`.env`、真实账单文件、任何密钥

分支：`task/T03-frontend`、`task/T07-frontend`、`task/T09-frontend`，一个任务一个 PR，等队长验收后再合并。

---

## 8. 常见坑（这些坑都有人在真实项目里踩过）

| 现象 | 原因 | 解法 |
| --- | --- | --- |
| 登录成功，但下一次请求 401 | 直连 8000 端口跨源，Cookie 没带上 | 用 Vite 代理，`baseUrl` 保持空 |
| 所有写请求 403 `CSRF_INVALID` | 忘了传第二个参数，或用了 `getSession` 之前保存的旧 token | 写接口一律 `await fn(..., csrfToken)`；403 时刷新 token 重试一次 |
| 上传 415 但文件明明是对的 | 扩展名对、内容不符（比如把 xls 改名成 xlsx） | 提示用户"用平台原样导出"；前端只做扩展名预校验 |
| 页面金额差 1 分 | `Number('12.34') * 100 = 1233.9999...` | 用 `yuanToFen` 字符串解析 |
| 日期筛选少一天 | 用了 `toISOString()` 取 UTC 日期 | 用本地 `YYYY-MM-DD` |
| 确认后列表没变 | 只改了本地状态 | 重新 `listTransactions` + `getMonthlyReport` |
| 导出下载下来是 JSON 错误 | 导出失败时返回的是 `Error` JSON，但被当文件保存 | 捕获 `ApiError` 走错误提示；成功后才是 Blob |
| PDF 打开是方块字 | 后端字体缺失（返回 503）或拿旧文件 | 503 时提示重试；容器部署由队长配 `PDF_FONT_PATH` |
| 轮询把浏览器打满 | `setInterval` 叠加请求 | 用 `setTimeout` 递归 + 组件卸载清理 |
| 图片预览内存泄漏 | 没 `revokeObjectURL` | 切换/卸载时统一 revoke |
| 分页请求 422 | `page_size` 传了 200 | 上限 100，默认 50 |
| 预算页除以 0 | `budget_fen === 0` | 显示"—"或"未设预算"，不算百分比 |
| 中文文案判断错误类型 | 按 `message` 做分支 | 只能按 `code` |

---

## 9. 一句话验收标准

打开比赛演示机，从 `demo_a` 登录开始，不刷新页面、不开 DevTools，
能在 5 分钟内连续完成：上传账单 → 修正并确认入账 → 在账单页改一笔分类并记住商户 →
导入第二份账单看到"个人规则"命中 → 停用该规则 → 月报数字与 PDF 一致 → 导出 CSV 用 Excel 打开无乱码。
做到这一步，前端的 30 + 25 分就有了实证。
