# 后端（H）差距分析：对照需求还缺什么

生成时间 2026-11-10，对照基线：`contracts/openapi.json` 0.2.0、`docs/03`、`docs/08`、`docs/11`、`docs/13`。
代码基线：分支 `task/T00-baseline`，HEAD `5ad4b30`。

本文只描述"需求要求但代码里没有"的部分，不重复已完成项。每条都给出可判定的验收口径，
避免"写完了"和"跑通了"混为一谈。

> **进展更新（2026-11-10 晚，CHG-003）**：第三节的三处隐蔽缺口已全部补齐——
> `X-Contract-Version` 中间件（`app/middleware.py`，四种状态码实测带）、
> 智能模块接口层（`app/intelligence/`，含纯规则 fallback）、
> 报表唯一口径（`app/services/reporting.py`，与 `seed_demo` 共用）。
> 补齐细节与实测数据见 `docs/20_intelligence_contract.md` 与 `docs/10` 的 CHG-003。
>
> **进展更新（2026-11-10 深夜，CHG-004）**：第二节的 13 个接口里 **5 个已实现**——
> `createImport` / `getImport` / `getImportOriginal` / `retryImport` / `confirmImport`
> （T02 导入中心整条闭环，含状态机、幂等、去重、单事务确认）。后端已实现 4 → **9**，
> 待实现 **8**：`listTransactions`、`patchTransaction`、`listRules`、`patchRule`、
> `getMonthlyReport`、`putBudget`、`exportTransactions`、`exportMonthlyPdf`。
> 实测：`unittest discover -s tests` 100 项通过；真实 uvicorn 走通「上传 202 → 轮询
> pending_review → 回读原件字节一致 → 确认 6 笔 → 同 request_id 重放结果一致」；
> 强杀进程重启后批次转 `failed(BATCH_INTERRUPTED)` 而非永久 processing。
> 详见 `docs/10` CHG-004。


---

## 一、总览

| 维度 | 需求 | 已完成 | 缺口 |
| --- | --- | --- | --- |
| HTTP 接口 | 17 | 4 | **13** |
| 逻辑表 | 7 + 会话表 1 | 8（全部建表） | 0（但 6 张表无任何读写代码） |
| 响应头约定 | 全部响应带 `X-Contract-Version` | **0** | 全缺 |
| 智能模块对接 | parse / classify / OCR / normalize | 0 | **全缺（adapter 层不存在）** |
| 原子事务 | 确认入账、纠错建规则、预算 upsert | 0 | 3 处全缺 |
| 幂等 | 确认接口同 ID 同体重放 | 0（字段已建） | 逻辑全缺 |
| 乐观锁 | 4 个接口需 version 校验 → 409 | 0（字段已建） | 全缺 |
| 导出 | CSV（防注入）+ 中文 PDF | 0 | 全缺 |
| 部署 | Compose 可跑、PG 迁移、备份恢复 | 骨架已写未验证 | 验证 + 备份脚本 |

按 docs/06 的任务卡，你的活儿是 **T00（已完）→ T02 → T05 → T08 → T10**。

---

## 二、接口级缺口（13 个）

| # | 接口 | operationId | 任务 | 难点，不是"写个 CRUD" |
| --- | --- | --- | --- | --- |
| 1 | `POST /api/imports` | createImport | T02 | multipart、10MiB/5MiB 双上限、413/415 区分、202 + `Location` + `Retry-After` |
| 2 | `GET /api/imports/{id}` | getImport | T02 | 状态机读取、草稿解密、`expires_at` 过期语义 |
| 3 | `GET /api/imports/{id}/original` | getImportOriginal | T02 | 解密原文件流、`Content-Disposition`、不可用时 503 |
| 4 | `POST /api/imports/{id}/retry` | retryImport | T02 | 仅 `failed` + 版本相符 → 202；否则 409 |
| 5 | `POST /api/imports/{id}/confirm` | confirmImport | T02 | **全项目最难的一个**，见第四节 |
| 6 | `GET /api/transactions` | listTransactions | T02 | 月份/类别/来源筛选、分页、金额解密后排序 |
| 7 | `PATCH /api/transactions/{id}` | patchTransaction | T05 | 乐观锁、改月份/类别须同步更新索引、记日志 |
| 8 | `GET /api/classification-rules` | listRules | T05 | 本人范围、只读 |
| 9 | `PATCH /api/classification-rules/{id}` | patchRule | T05 | 版本校验、停用不回溯已处理草稿 |
| 10 | `GET /api/reports/monthly` | getMonthlyReport | T08 | 确定性计算，不维护累计表，见第五节 |
| 11 | `PUT /api/budgets` | putBudget | T08 | 唯一键 upsert、拒 `pending`、金额可 0 |
| 12 | `GET /api/exports/transactions.csv` | exportTransactions | T08 | **CSV 公式注入防护** |
| 13 | `GET /api/exports/monthly.pdf` | exportMonthlyPdf | T08 | 中文字体嵌入、Linux 无字体即翻车 |

---

## 三、三处"文档写了、代码里没有"的隐蔽缺口

这三条比"少写几个接口"危险，因为它们不在任何清单上，只有对照原文才看得出来。

### 3.1 `X-Contract-Version` 响应头，一处都没实现

`docs/11` 第 12 行写的是**硬要求**：

> 所有成功和失败响应带 X-Contract-Version。

全文 18 处响应示例都带这个头。当前 `backend/` 全文搜索零命中。

**修法**：一个中间件，读 `contracts.CONTRACT_VERSION` 写进所有响应，`/health` 也包含。
**验收**：`curl -i` 任意接口（含 401/409/422 错误响应）都能看到 `X-Contract-Version: 0.2.0`。
**代价**：约 20 行、半小时。这是本次分析里性价比最高的一条。

### 3.2 智能模块 adapter 层不存在

`docs/13`「智能模块接口」一节规定了 D 必须提供的四个函数：

```
parse_bill_file(bytes, filename, source) -> ParseResult
recognize_bill_image(bytes, mime_type, source) -> ParseResult
normalize_merchant(str) -> str
classify_transactions(list[TransactionDraft], list[ClassificationRule], bool) -> list[ClassificationResult]
```

还有一条异常约定：文件整体不可解析时抛 `IntelligenceFailure(code, safe_message)`。

但 `backend/app/intelligence/` **目录不存在**，`IntelligenceFailure` 也没有定义。后果是：

- D 按 `docs/05` 写完了函数，后端却不知道 import 哪里、catch 什么异常；
- 后端写 T02 时只能先硬编码一个假解析，等 D 交付再推翻重写；
- 两边各写一套 `Issue` 构造逻辑，字段含义逐渐分叉。

**修法**：先落一层 `intelligence/base.py`：

1. 定义 `IntelligenceFailure`（含 `UNSUPPORTED_TEMPLATE` / `INVALID_FILE` / `OCR_UNAVAILABLE` / `OCR_FIELD_MISSING` / `MODEL_TIMEOUT` / `MODEL_OUTPUT_INVALID` 六个最小代码）
2. 用 `Protocol` 或 ABC 固定上面四个签名，D 的实现只要满足协议即可
3. 提供 `fallback.py`：一个**纯规则、零外部依赖**的确定实现（支付宝/微信 CSV 都能解析、关键词分类），保证 D 未到位或 OCR 挂掉时闭环仍能跑
4. `factory.py` 按 `ALLOW_TEST_DOUBLES` / 环境变量选择真实实现或 fallback，**不允许静默回退到假成功**，必须把 `classification_source` 写成 `general_rule` 而不是 `llm`

这一条是架构上最值钱的决定：**它让你不依赖 D 也能先打通闭环**，D 到了只是替换实现。
11/19 如果 OCR 没成，你还有东西可交。

### 3.3 幂等与状态机：字段建了，逻辑为零

`import_batches` 表已经有 `confirmation_request_id`、`request_body_digest`、
`encrypted_confirm_result` 三列，但没有任何代码读写它们。`docs/11` API09 的要求是三条独立规则：

| 情形 | 要求结果 |
| --- | --- |
| 同 `request_id` + 同请求体 | 返回**原始 200 结果**（重放，不重复入账） |
| 同 `request_id` + 不同请求体 | `409 IDEMPOTENCY_CONFLICT` |
| 已完成批次 + 新 `request_id` | `409 BATCH_STATE_CONFLICT` |
| `expected_version` 不符 | `409 VERSION_CONFLICT` |

注意顺序：**先查幂等记录，再查版本**。反了就会出现"重放被当成版本冲突"。
且这三条必须在一个事务里，`docs/13` 明确禁止用进程内字典。

---

## 四、confirmImport 的事务清单（最该照着写的一条）

`docs/13`「必须原子执行的操作」第一行，拆成可执行步骤：

```
BEGIN
  1. SELECT ... FOR UPDATE 本人批次（其他人拿到 404，不是 403，避免探测）
  2. 查幂等：request_id 命中 → 比对 body_digest → 相同则解密返回旧结果，不同则 409
  3. 校验 status == pending_review 且 version == expected_version，否则 409
  4. 逐行重新校验：金额>0、货币 CNY、类别合法、时间带时区、row_id 在批次内
     任何一行不合法 → 整体 422，全回滚，不允许部分入账
  5. 逐行算 dedupe_digest → 撞唯一约束的行跳过（计为 duplicate）
  6. 写 transactions（金额等进 encrypted_payload，索引列明文）
  7. 批次 status=completed、version+1
  8. 存 encrypted_confirm_result + request_id + body_digest
COMMIT
```

五条容易漏的细节：

- 第 1 步用 `SELECT FOR UPDATE`（SQLite 不支持，本地测试用一个互斥锁代替，**要在代码注释里写明差异**）
- 第 4 步"全回滚"意味着不能边校验边插入
- 第 5 步去重摘要的 `parts` 必须包含**事件性质**：`SYN-ORDER-1` 那笔支出和退款同订单号，只用订单号会误删其一
- 第 8 步存的是**明文响应快照再加密**，重放时原样返回，不重新计算
- 任何异常路径都要保证批次不留在 `processing`（A12 要求）

---

## 五、报表口径（A09/A10 是硬指标）

`docs/08` 指定 fixtures 的期望值，单位分：

| 指标 | 值 |
| --- | --- |
| 收入 I | 10000 |
| 支出 E | 4200 |
| 退款 R | 500 |
| 净支出 | 3700 |
| 收支差额 | 6300 |

现状：`seed_demo.py` 已经能算出这套数字并逐项核对，**但没有任何接口把它暴露出去**。
`getMonthlyReport` 要做的就是复用同一套计算逻辑（建议把 `seed_demo` 里的 `_totals` 抽成
`services/reporting.py`，让两边共用，避免"核对过的一套"和"接口用的另一套"不一致）。

预算口径（A10）：餐饮预算 2000、净支出 2500 → `spent_fen=2500, remaining_fen=-500, over_fen=500`；
购物预算 1500、净支出 1200 → `remaining_fen=300, over_fen=0`；**预算为 0 时前端不除零**，后端只需如实返回 0。

三条纪律：
1. 不建累计汇总表，每次按用户+月份取已确认记录解密计算（`docs/13` 明确）
2. "收支差额"不得写成"银行余额"
3. 退款计入 `net_expense` 的减项，不是收入

---

## 六、导出

**CSV**：`docs/08` A11 要求"不触发表格公式"。凡以 `= + - @ \t \r` 开头的单元格，
前置单引号或包成 `'...'`；UTF-8 **带 BOM**，否则 Excel 打开中文乱码；
列顺序与页面表头一致；导出范围必须与筛选参数一致。

**PDF**：真正的坑不是生成 PDF，是**中文字体**。
Linux 容器里通常没有中文字体，ReportLab 默认字体渲染中文就是方块。
两种做法：
- 仓库内自带一份开源中文字体（如思源黑体子集，注意许可证要能随包分发），`Dockerfile` 里 COPY 进去
- 或干脆降级：先出"可打印 HTML"，浏览器打印成 PDF（省一天，但 `docs/11` 契约里这个接口还是得在）

---

## 七、优先级与工作量

剩余约 9 天 × 4 小时 ≈ 36 人时。下表合计约 48 人时，**必须砍掉 12 小时以上**。

| 优先级 | 事项 | 估计 | 说明 |
| --- | --- | --- | --- |
| **P0-1** | `X-Contract-Version` 中间件 | 0.5h | 契约硬要求，一行都不许缺 |
| **P0-2** | `intelligence` adapter + fallback | 3h | 解锁 D 的对接，也给自己兜底 |
| **P0-3** | 批次状态机 + 后台执行 + 中断恢复 | 5h | A12 |
| **P0-4** | createImport / getImport / getImportOriginal / retryImport | 8h | T02 入口 |
| **P0-5** | confirmImport（含幂等 + 去重 + 原子） | 8h | 全项目核心，A03/A04 |
| **P0-6** | listTransactions | 3h | F 的列表页依赖 |
| **P1-1** | getMonthlyReport + putBudget | 5h | A09/A10，评分表里"统计分析"整块 |
| **P1-2** | exportTransactions.csv | 2h | 便宜，必做 |
| **P1-3** | patchTransaction + 纠错日志 | 5h | A07/A08 |
| **P1-4** | listRules / patchRule | 3h | 可与 P1-3 合并做 |
| **P2-1** | exportMonthlyPdf | 5h | **第一个砍**：先出可打印 HTML，接口用 503 明确未就绪 |
| **P2-2** | Docker 实跑 + PG 迁移验证 | 3h | 不可省，但可压到 2h |
| **P2-3** | 备份恢复脚本 + 密钥有效性验证 | 2h | A13，纯脚本无 UI |
| **P2-4** | app-ci.yml 启用 | 1h | 模板已在，改名 + 核对路径 |

**砍法建议**：P2-1 砍掉或降级（省 5h），`getImportOriginal` 简化为直接解密回传不做出图预览（省 2h），
`patchRule` 只支持 `enabled` 开关不支持改匹配模式（省 2h），规则接口与交易接口同批做（省 2h）。
合计省 11h，压到 37h，刚好卡在产能线上——**没有余量，所以任何一天塌方都要当天砍功能**。

---

## 八、可以直接勾的验收清单

后端自测（每条都要能在本地跑出来）：

- [ ] `curl -i http://127.0.0.1:8000/health` 返回 200 且带 `X-Contract-Version: 0.2.0`
- [ ] 401 / 409 / 422 响应也带该头
- [ ] 未登录访问 13 个新接口 → 全部 401，不是 404
- [ ] 用户 B 用 A 的 batch_id / transaction_id → 404（不是 403，避免存在性探测）
- [ ] 上传 11MiB 文件 → 413；上传 `.pdf` → 415；上传 0 字节 → 422
- [ ] 同一文件二次上传 → 不重复入账，重复行计入 `duplicate_status`
- [ ] 同 `request_id` 重放确认 → 返回同一份结果，库内交易数不变
- [ ] 同 `request_id` 改金额 → 409 `IDEMPOTENCY_CONFLICT`
- [ ] `expected_version` 落后 → 409 `VERSION_CONFLICT` 且返回最新 version
- [ ] 确认过程中杀掉进程 → 重启后批次不是永久 `processing`
- [ ] fixtures 的月度报表 = I 10000 / E 4200 / R 500 / 净 3700 / 差 6300
- [ ] 餐饮预算 2000 对净支出 2500 → over 500；购物 1500 对 1200 → 剩 300
- [ ] 导出 CSV 用 Excel 打开中文不乱码，`=1+1` 这类商户名不执行
- [ ] `tools/check_implemented_contract.py` 显示 17/17 已实现且字段一致

---

## 九、和排期的对齐

`11月20日初赛开发执行计划_v2.md` 里后端的节点是：

| 日期 | 该完成的 | 本文对应的条目 |
| --- | --- | --- |
| 11/10 晚 | T00 收口（已完）+ 补 `X-Contract-Version` | P0-1 |
| 11/11 | adapter + 状态机 + 上传 4 接口 | P0-2/3/4 |
| 11/12 | confirmImport 打通，真实 20 条入库 | P0-5 |
| 11/13 | 列表 + 报表 + 预算 | P0-6、P1-1 |
| 11/14 | 交易纠错 + 规则 + CSV 导出 | P1-2/3/4 |
| 11/15 | 功能冻结，只修缺陷 | — |
| 11/16–17 | 部署、备份、PDF（有余量才做） | P2 |

**最该盯的一天是 11/12**：如果那天 confirmImport 没打通真实数据，后面所有"统计、导出、报表"都建立在沙子上。
