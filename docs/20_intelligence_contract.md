# 智能模块对接说明与本次补齐记录

日期 2026-11-10。对应变更 CHG-002（见 `docs/10_change_delivery.md`）。
本文给两个人看：**D**（按这里的签名实现解析与分类）、**F**（知道哪些错误码要展示）。

---

## 一、本次补的三件事

| 项 | 问题 | 现在 |
| --- | --- | --- |
| `X-Contract-Version` 响应头 | docs/11 第 12 行是硬要求，18 处响应示例都带，代码里一处没有 | `app/middleware.py` 纯 ASGI 中间件，200/401/404/422 实测全带 |
| 智能模块接口层 | `backend/app/intelligence/` 目录根本不存在，D 无法对接 | `app/intelligence/` 落地，含协议、异常、纯规则实现、工厂 |
| 报表口径复用 | `seed_demo` 自己算一遍，接口将来再算一遍，两套必然分叉 | `app/services/reporting.py` 唯一口径，两处共用 |

---

## 二、代码结构

```
backend/app/
├── middleware.py              # X-Contract-Version（所有响应）
├── intelligence/
│   ├── base.py                # 协议、异常、错误码、结果校验
│   ├── normalize.py           # 商户名标准化（NFKC + 折叠空白 + casefold）
│   ├── rules.py               # 通用关键词分类（最长匹配）
│   ├── tables.py              # 字节 → 二维表（编码/表头/尾部行三处坑）
│   ├── fallback.py            # 纯规则实现（满足协议，可被 D 替换）
│   └── factory.py             # 按配置选实现，不自动降级
├── services/reporting.py      # 月度报表唯一口径
└── tools/parse_probe.py       # 人工核对工具
```

---

## 三、D 要实现的四个方法

后端只通过 `app.intelligence.IntelligenceProvider` 协议调用，**不 import D 的任何模块**。
D 的实现放在 `backend/app/intelligence/deepseek.py`（或另行约定），只要满足：

```python
class DeepSeekIntelligence:
    name = "deepseek"

    def parse_bill_file(self, data: bytes, filename: str, source: str) -> ParseResult: ...
    def recognize_bill_image(self, data: bytes, mime_type: str, source: str) -> ParseResult: ...
    def normalize_merchant(self, raw: str) -> str: ...
    def classify_transactions(
        self,
        rows: list[TransactionDraft],
        rules: list[ClassificationRule],
        use_llm: bool = False,
    ) -> list[ClassificationResult]: ...
```

然后在 `.env` 里写 `INTELLIGENCE_PROVIDER=app.intelligence.deepseek:DeepSeekIntelligence`。
**配置错会启动即失败，不会静默退回规则实现**——否则分类来源标着 `general_rule`
却让人以为走了模型，准确率报表全错。

三条硬约束：

1. **`ParseResult` 里的 `rows` 必须是 `TransactionDraft`**，字段定义只认 `app/contracts.py`
   （由 `contracts/openapi.json` 生成）。不要自己另定义字段。
2. **分类结果每个 `row_id` 恰好一项**。数量不符、重复、未知 row_id 一律在
   `assert_one_result_per_row` 里被拒（`MODEL_OUTPUT_INVALID`）。错配会把甲商户的类别
   写到乙头上，比分类失败严重得多。
3. **不要写库**。`parse` / `classify` 只读，入账由后端在事务里做（docs/13）。

### 异常

整体失败时抛 `IntelligenceFailure(code)`，只接受这六个代码：

| code | 何时用 | 用户看到的文案 |
| --- | --- | --- |
| `UNSUPPORTED_TEMPLATE` | 表头找不到、格式不认识 | 无法识别该账单模板… |
| `INVALID_FILE` | 文件损坏、编码无法识别 | 文件内容不合法或已损坏 |
| `OCR_UNAVAILABLE` | OCR 服务挂了或没配 | 截图识别服务当前不可用 |
| `OCR_FIELD_MISSING` | 截图关键字段缺 | 截图中缺少必要字段 |
| `MODEL_TIMEOUT` | 模型 20 秒超时（重试 1 次后） | 智能分类服务响应超时 |
| `MODEL_OUTPUT_INVALID` | 模型返回结构不合法 | 智能分类返回结果不符合约定格式 |

**异常 message 里不许出现密钥、文件内容或用户明文**——它会进日志、进响应、进截图。
`IntelligenceFailure.__init__` 会拒绝未登记的 code，这条防线在代码里而不只靠自觉。

---

## 四、Issue 代码表

`Issue` 挂在草稿行上，`code` 是**给前端做逻辑判断**的稳定机器码，`message` 只是给人看的。
F 端不要按中文文案判断（docs/11 明确）。

| code | 含义 | 前端该做什么 |
| --- | --- | --- |
| `AMOUNT_MISSING` | 该行金额空或无法解析，**未生成草稿** | 提示"有 N 行未识别"，不显示为空行 |
| `INVALID_AMOUNT` | 金额格式非法（契约示例已有此码） | 高亮金额字段，要求重填 |
| `TIME_MISSING` | 时间为空 | 要求补时间（否则无法归月） |
| `INVALID_TIME` | 时间有值但解析不了 | 同上，并显示原值 |
| `FLOW_TYPE_UNKNOWN` | 收/支方向判断不出 | 要求选择收入/支出，否则不能确认 |
| `MERCHANT_MISSING` | 商户名为空 | 允许确认，但建立个人规则前必须补 |
| `CATEGORY_UNCERTAIN` | 规则没命中，待用户选 | 显示类别选择器，默认 pending |
| `ROW_UNPARSABLE` | 整行无法解析 | 建议用户检查该行或改用 CSV 重导 |
| `DUPLICATE_SUSPECTED` | 同文件内重复单号 | 默认不勾选，让用户决定 |
| `ROWS_SKIPPED` | `row_id` 为 null 的汇总提示，如"已跳过 2 行关闭交易" | 顶部提示条，不进列表 |

`ROWS_SKIPPED` 这个码存在的意义：让"文件里 30 条、界面 28 条"有明确解释，
而不是让用户以为丢账。

### 4.1 由后端（导入服务）产生的码（CHG-004 新增）

以下三个不是 D 的解析器产出，而是 `app/services/imports.py` 在处理/读取批次时加的。
D 不要重复造；F 同样按 code 判断。

| code | 含义 | 前端该做什么 |
| --- | --- | --- |
| `DUPLICATE_EXISTING` | 该行与库里已入账交易撞去重摘要，`duplicate_status` 已置 `duplicate` | 默认不勾选，提示"已入账，确认时会跳过" |
| `NO_ROWS_PARSED` | 文件能打开但没有任何可入账交易 | 显示空状态 + 建议检查导出范围 |
| `DRAFT_UNREADABLE` | 批次草稿/失败原因解密失败（密钥更换或密文损坏） | 引导重新上传，不要说"文件格式错误" |

批次**整体失败**时没有草稿，只有一条 `row_id` 为 null 的 Issue，code 取自下表：

| code | 含义 | 能否重试 |
| --- | --- | --- |
| `UNSUPPORTED_TEMPLATE` / `INVALID_FILE` / `OCR_UNAVAILABLE` / `OCR_FIELD_MISSING` / `MODEL_TIMEOUT` / `MODEL_OUTPUT_INVALID` | 智能模块抛出的失败（docs/13 的六个最小集合） | 能（`POST /api/imports/{id}/retry`） |
| `BATCH_TIMEOUT` | 超过 `BATCH_DEADLINE_SECONDS`（默认 300 秒）仍未结束 | 能 |
| `BATCH_INTERRUPTED` | 服务重启中断了处理 | 能 |
| `BATCH_EXPIRED` | 批次草稿超过 `BATCH_DRAFT_TTL_HOURS`（默认 24 小时） | 不能，重新上传 |
| `CRYPTO_FAILED` | 服务端解不开原文件（密钥变更/密文损坏） | 不能，重新上传 |

---

## 五、fallback 能做什么、不能做什么

**能做**（已实测，见 `tests/test_intelligence.py` 43 项）：

- 支付宝 / 微信 CSV 与 XLSX；GBK 与 UTF-8 BOM；表头在任意前 40 行
- 金额 `¥1,234.56` → 整数分（Decimal，无浮点漂移）
- 时间五种格式，带 `+08:00`
- 跳过交易关闭行、0 元订单、尾部说明行，并给出 `ROWS_SKIPPED`
- 同订单号在文件内重复 → `DUPLICATE_SUSPECTED`
- 通用关键词分类（约 120 词），个人规则优先
- 平台标错时按内容识别

**不能做**：

- 截图 OCR（抛 `OCR_UNAVAILABLE`，不返回空结果假装成功）
- 模型分类（`use_llm` 被忽略，来源**永远不会**标成 `deepseek`）
- 跨文件去重（那是后端 `dedupe_digest` 的职责）

---

## 六、真实账单怎么核对

```bash
cd backend
python -m app.tools.parse_probe ../data/private/alipay_2026-10.csv --source alipay
```

打印条数、每笔金额、流向、类别、问题清单，以及按流向合计。
**与平台页面显示的条数和金额逐项比对**，不一致就不要导入。

真实账单放 `data/private/`（`.gitignore` 已排除，永不进仓库）。
核对记录写进 `docs/21_parse_verification.md`（有真实样本后建）。

---

## 七、报表口径（后端唯一实现）

`app/services/reporting.py`：

| 概念 | 定义 | 容易搞错的地方 |
| --- | --- | --- |
| 收入 | `flow_type=income` 求和 | 不含退款、不含内部转账 |
| 毛支出 | `flow_type=expense` 求和 | 含已退款的原交易（钱确实付出去过） |
| 退款 | `flow_type=refund` 求和 | 是净支出的**减项**，不是收入 |
| 净支出 | 毛支出 − 退款 | 可以为负（跨月退款） |
| 收支差额 | 收入 − 净支出 | **不是账户余额**，字段说明和 UI 都不许混 |
| 分类构成 | 按类别汇总**毛支出** | 退款不回冲，否则饼图加起来不等于毛支出 |
| 预算已用 | 该类别**净支出** | 退款要回到预算里，才符合"这月还能花多少" |

验收值见 `docs/08` A09/A10，已固化为 `tests/test_reporting.py` 18 项断言。

---

## 八、当前接口进度

| 已实现 | 数量 |
| --- | --- |
| `/health`、`/api/auth/login`、`/api/auth/me`、`/api/auth/logout` | 4 |
| 导入中心 5 个：`createImport`、`getImport`、`getImportOriginal`、`retryImport`、`confirmImport`（CHG-004） | 5 |
| 账单与报表 4 个：`listTransactions`、`patchTransaction`、`getMonthlyReport`、`putBudget`（CHG-005） | 4 |
| 个人规则 2 个：`listRules`、`patchRule`（CHG-006） | 2 |
| 导出 2 个：`exportTransactions`、`exportMonthlyPdf`（CHG-006） | 2 |

`python tools/check_implemented_contract.py` 可随时核对已实现部分与契约是否漂移。
截至 CHG-006：**已实现 17 个、字段与契约一致，待实现 0 个**。后端功能面收口，
剩余工作全部在前端页面、真实账单样本、OCR 接入与部署验证上。

分类来源的落库约定（CHG-005）：确认入账时把草稿的 `classification_source` /
`classification_reason` 一并写入加密区，用户改了类别则标 `manual`。存量记录缺这两项
时接口如实返回 `pending` 加说明，**不会**用当前规则补记一个当时并不存在的来源。
