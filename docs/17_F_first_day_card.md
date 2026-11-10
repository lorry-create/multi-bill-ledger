# F · 首日开工卡（11 月 10 日晚 — 11 月 11 日）

> 这张卡替代 `docs/04_frontend.md` 作为**今天的执行依据**。04 是完整任务书，覆盖六个页面；今天只做三个。原因：初赛后只剩 9 个工作日，六页并行会全部做一半。先把「登录 → 上传 → 预览确认」这条主干打通，剩下三页（账单、月报、规则）在主干接上真实后端后按 04 继续。

## 今天的唯一目标

三个页面能点通，接口走 mock，明天切真后端不改页面结构。

```text
登录 → 上传文件 → 看到批次预览 → 逐行修正 → 确认入账（mock 返回成功）
```

## 开工前（10 分钟）

```bash
git clone <仓库地址> && cd multi-bill-ledger
git checkout task/T00-baseline
cd frontend
npm install
npm run dev          # 应能打开 5173 的空壳
```

确认三件事，缺任何一件立刻在群里说，不要自己绕：

1. `src/api/client.generated.ts` 存在，里面有 `login` / `getSession` / `createImport` / `getImport` / `confirmImport` / `listTransactions` 六个函数。
2. `vite.config.ts` 里 `/api` 代理指向 `http://127.0.0.1:8000`。
3. `contracts/examples.json` 打得开，里面 29 个 case 是你要抄的假数据来源。

## 只允许改这些文件

```text
frontend/src/pages/Login.vue
frontend/src/pages/ImportUpload.vue
frontend/src/pages/ImportConfirm.vue
frontend/src/api/mock.ts          # 新建
frontend/src/router.ts            # 新建或改
frontend/src/api/index.ts         # 新建：真实/mock 的切换层
frontend/src/styles/              # 样式
```

**禁止**改：`contracts/` 下任何文件、`client.generated.ts`、`backend/` 下任何文件、根 CI。发现接口不够用，按 `docs/10_change_delivery.md` 提变更说明，不要自己加后端没有的字段。

## mock 怎么写（这是今天最关键的技术决定）

新建 `src/api/mock.ts`，从 `contracts/examples.json` 抄 `createImport` / `getImport` / `confirmImport` 的**真实响应快照**，函数签名与 SDK 完全一致：

```ts
// src/api/index.ts —— 页面只 import 这里，不直接 import client.generated.ts
import * as real from './client.generated'
import * as mock from './mock'

export const api = import.meta.env.VITE_USE_MOCK === 'true' ? mock : real
```

这样明天切真后端只改 `.env.local` 一行，页面代码零改动。**不要**在页面里写 `if (import.meta.env.DEV) return fakeData`，那样切真实请求时要逐个页面改。

`.env.local`（不要提交）：

```text
VITE_USE_MOCK=true
```

mock 里每个返回值上方写一行注释标明来源，例如 `// 抄自 examples.json case: getImport_pending_review`。PR 里要能一眼看出哪些是假数据。

## 三个页面各自做什么

### 1. Login.vue

- 两个输入框 + 提交按钮；调用 `login`，成功后调 `getSession` 拿 `user` 和 `csrf_token`。
- 状态必须处理：提交中禁用按钮、401 显示"账号或密码错误"、网络错误显示可重试提示。
- 成功后跳到导入页。`csrf_token` 存内存即可（真后端会走 HttpOnly Cookie，前端只负责把 token 放进 `X-CSRF-Token` 头）。

### 2. ImportUpload.vue

- 平台选择（支付宝 / 微信）+ 文件选择（CSV / XLSX）+ 截图选择（PNG / JPEG）两组入口。
- 前端先拦：文件 > 10 MiB、图片 > 5 MiB 直接提示，不发请求。
- 调 `createImport`（multipart，字段 `source`、`ingestion_method`、`file`），拿到 202 和批次对象后跳确认页。
- 状态必须处理：上传进度、失败原因、"处理中"轮询 `getImport` 直到 `status = pending_review`。

### 3. ImportConfirm.vue

- 左右布局：左侧原图或文件名，右侧逐行草稿表格。
- 每行展示：时间、金额（**分转元显示**）、流向、商户、类别、分类来源、问题标记。
- 可编辑：金额、时间、商户、类别。
- **缺时间或金额或流向的行，禁止勾选确认**，按钮置灰并说明原因。
- 疑似重复（`duplicate_status = suspected`）的行默认不勾选，需要用户显式勾选才能入账。
- 确认按钮调 `confirmImport`，body 里带 `request_id`（用 `crypto.randomUUID()` 生成一次并存住）、`expected_version`、`rows`。**网络失败后重试必须复用同一个 `request_id` 和同样的 body**，改了内容就换新 ID。

## 今天就验收这四条

```bash
npm run build      # 必须通过
npm run typecheck  # 若脚本已存在
```

1. 三个页面截图，放进 `docs/evidence/F/`，文件名带日期。
2. 手动点通：登录 → 上传 → 预览 → 修正一行 → 确认成功。
3. 故意不填金额，确认按钮置灰，能截到图。
4. PR 描述里写明：哪些页面已连 mock、哪些还没做、明天要接哪几个真接口。

## 今天明确不做

月报页、图表、预算、规则页、PDF/CSV 导出、动效、暗色模式、移动端适配、国际化。

## 明天（11/11）预告

H 的 `T02` 接口就绪后，你只需要：把 `.env.local` 改成 `VITE_USE_MOCK=false`，用真实批次走一遍。若接口形状和 mock 不一致，**先报给队长，不要自己适配** —— 那是契约问题，不是你的页面问题。

## 一条纪律

页面显示"成功"不等于数据正确。确认入账后，一定去账单列表核对条数和金额，别只看绿色提示。`docs/12_page_api_integration.md` 里 409（版本冲突）和 401（会话过期）的处理顺序照抄，不要自己发明。
