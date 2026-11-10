# D · 首日开工卡（11 月 10 日晚 — 11 月 11 日）

> 这张卡替代 `docs/05_data_ai.md` 作为**今天的执行依据**。05 覆盖解析、分类、OCR、实验报告四块；今天只做前两块的一半。原因：真实样本你还没导出来，OCR 选型会吃掉一整天。先把「真实文件 → 结构化草稿」这条最短路径跑通，H 才能接上 T02。

## 今天的唯一目标

一个真实支付宝 CSV，进去 20 条交易，金额与人工核对完全一致；再给它们打上通用规则分类。

```text
支付宝 CSV → parse_bill_file() → ParseResult(20 rows) → classify_transactions() → 20 条 ClassificationResult
```

## 开工前（30 分钟，今天最重要的半小时）

**这一步做不完，今天就别写代码。**

1. 在 Windows 电脑上打开支付宝，进入「账单」，用「导出账单」功能选最近 3 个月、CSV 格式，下载到本机。
2. 微信支付同理：我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单 → 用于个人对账 → 选 CSV。
3. 两份文件立刻复制到 `backend/data/private/`（该目录在 `.gitignore` 里，**永远不要提交**）。
4. 同时导出 3–5 张手机账单截图，放到同目录 `screenshots/`，今天不用，明天 OCR 用。
5. 在 `docs/evidence/D/` 建一个 `samples.md`，记录：平台、导出日期、时间范围、文件格式、条数、字段顺序、编码。

如果导出入口找不到或需要等邮件，**立刻在群里说**，改做微信那份，或先用 `fixtures/synthetic_ledger.json` 跑通代码结构、明天换真实样本。不要自己造一份假的"真实样本"。

## 你的工作区

```text
backend/app/intelligence/          # 只有你能改
backend/tests/intelligence/        # 只有你能改
backend/data/private/              # 本地真实数据，Git 忽略
docs/evidence/D/                   # 你的证据
```

**禁止**改：`backend/app/contracts.py`、`backend/app/api/`、`backend/app/models/`、`contracts/`。你需要新字段就提变更说明，不要另建一套 DTO。

## 今天第一件事：确认能用共用模型

```bash
cd backend
python -c "from app.contracts import ParseResult, TransactionDraft, ClassificationResult, Issue, Category, FlowType; print('ok')"
```

`contracts.py` 已从 OpenAPI 生成（463 行、39 个符号），金额字段是 `StrictInt` —— 传 `"2300"` 或 `2300.0` 会直接报错，这是有意的。**你的解析器必须产出整数分**，不要产出元。

## 要交付的两个函数

签名固定为 `docs/02_contract.md` 里的版本，不要改：

```python
def parse_bill_file(content: bytes, filename: str, source: str) -> ParseResult: ...
def classify_transactions(
    rows: list[TransactionDraft],
    personal_rules: list[ClassificationRule],
    *,
    use_llm: bool,
) -> list[ClassificationResult]: ...
```

### parse_bill_file 今天只做支付宝 CSV

处理顺序，一条都不能跳：

1. **编码**：先试 `utf-8-sig`，失败退 `gbk`，再失败报明确错误 —— 不要把乱码当成功。
2. **说明行**：支付宝导出前若干行是导出说明与表头，真实样本里数清楚第几行开始是数据，写进代码注释。
3. **金额**：`"23.00"` → `Decimal("23.00") * 100` → `int`。**禁止 `float`，禁止 `round()`**。带逗号的千分位先去掉。三位以上小数直接进 `issues`，不要静默截断。
4. **时间**：按 `Asia/Shanghai` 解析成带时区 `datetime`。缺年份、格式不认识 → `occurred_at = None` + `issues`，不要默认当前年。
5. **交易号**：保持字符串，哪怕是纯数字。`source_transaction_id` 一旦变 int 就会丢精度。
6. **流向**：根据支付宝的收/支字段映射到 `income` / `expense` / `refund` / `transfer` / `repayment`；认不出就 `None` 并进 `issues`，等用户确认。
7. **坏行**：进 `issues`，不要 `continue` 静默跳过，也不要让整批失败。

每行 `row_id` 用稳定规则生成（例如 `f"{source}-{行号}"`），**不要用 `uuid4()`** —— 重试时会变，破坏确认幂等。

### classify_transactions 今天只做通用规则层

顺序固定：个人规则 → 通用规则 → （DeepSeek，今天不接）→ `pending`。

```text
餐饮：麦当劳、肯德基、星巴克、瑞幸、美团、饿了么、外卖、餐厅、食堂
交通：滴滴、高德、地铁、公交、加油、停车、铁路、12306
购物：淘宝、天猫、京东、拼多多、超市、便利店、屈臣氏
居住：房租、物业、水费、电费、燃气、宽带
娱乐：电影、KTV、游戏、视频会员、音乐会员
医疗：医院、药房、药店、诊所、体检
教育：学费、书店、课程、培训、考试
其他：以上都不命中，但商户明确
待确认：商户为空或无法判断
```

- 命中必须写 `classification_source = general_rule` 和一句 `classification_reason`（例如"命中关键词：麦当劳"）。
- 一条都没命中 → `category = pending`、`classification_source = pending`、`reason` 说明"无规则命中且未启用模型"。
- **绝不能**把规则命中的结果标成 `deepseek`。
- `normalize_merchant` 用 `docs/02` 的规则：Unicode NFKC、首尾去空白、连续空白合并、casefold。H 建个人规则时用的是同一个函数，所以你这份实现会被 H 直接 import，命名和语义不要自己发挥。

## 今天就验收这五条

```bash
cd backend && pytest tests/intelligence -v
```

1. 真实支付宝 CSV 解析成功，条数与文件实际交易行数一致（把两个数字都写进 `docs/evidence/D/parsing.md`）。
2. 逐笔金额与支付宝页面显示完全一致，**单位为分**，列出对照表中的前 10 条。
3. 至少构造 3 个坏行（金额三位小数、缺日期、金额为空），全部进 `issues`，没有一行被静默丢弃。
4. 20 条分类结果里，`general_rule` 与 `pending` 分工清楚，抽查 5 条能说出理由。
5. PR 里贴出：一个正常输入的完整返回（JSON 截断到 2 条即可）、一个失败返回、运行命令。

## 今天明确不做

OCR、DeepSeek 真实调用、微信 XLSX（若支付宝 CSV 顺利，可以做微信 CSV 作为第二条）、指标统计、实验报告、RPA。

## 明天（11/11）预告

- 微信 CSV 或 XLSX 第二条解析器。
- 接 DeepSeek：先跑通一次结构化调用，把 JSON 校验、类别越界、超时重试写进去，**真实调用结果单独记一份证据**，不要和规则结果混在一起报准确率。
- OCR 选型今晚就可以查：目标环境是 Linux 容器，优先云端 API（腾讯云/百度 OCR 有免费额度），本地 PaddleOCR 作兜底。明天下午前必须定一个。

## 一条纪律

解析器报"成功"不等于数据对。你交出去的东西 H 会直接入库、统计、出报表，**金额错一分就是全链路错**。宁可让 3 行进 `issues` 待人工确认，也不要让 1 行带着浮点误差悄悄入库。
