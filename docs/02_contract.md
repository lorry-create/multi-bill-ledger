# 共同接口和业务约定

版本 0.2.0。接口路径、必填字段、响应和枚举以 contracts/openapi.json 为准；本文约束语义和模块交接。后端先形成共用模型，前端和智能模块均按此使用。

## 目录归属

```text
backend/app/contracts.py       H 共同模型
backend/app/api/               H HTTP 与认证
backend/app/services/          H 入账 纠错 统计 导出
backend/app/models/            H 数据库及加密映射
backend/app/intelligence/      D 文件解析 OCR 分类 纯匹配
backend/tests/intelligence/    D 模块测试
backend/tests/integration/     H 数据库 权限与 HTTP 测试
frontend/                     F 页面 类型与交互
contracts/                    H 维护 三方评审
deploy/                       H 部署和资源
docs/evidence/                各人 仅合成或授权脱敏证据
data/private/                 本机真实数据 Git 忽略
```

H 不重复实现 D 的解析器，D 不建独立后端服务器或数据库。F 的测试样例仅用于早期界面开发，接上后端后不以静态样例假装真实请求成功。

## 字段和类别

所有金额是 CNY 的正整数分，预算为非负整数分；接口不接受浮点元。时间为带时区 ISO 8601，日期筛选按 Asia/Shanghai。原平台交易号必须是字符串。

source 为 alipay 或 wechat；ingestion_method 为 file 或 screenshot，不能用 OCR 替代平台字段。类别固定为 dining 餐饮、transport 交通、shopping 购物、salary 工资、housing 居住、entertainment 娱乐、health 医疗、education 教育、other 其他、pending 待确认。

flow_type 为 income、expense、refund、transfer、repayment；解析草稿可为 null，确认入账前必须明确。分类可以 pending，但金额、时间、流向不能缺失。classification_source 为 user_rule、general_rule、deepseek、manual、pending，必须反映实际来源。

## 认证和错误

采用同源 HttpOnly 会话 Cookie bill_session。GET /api/auth/me 返回当前用户和 CSRF token；除登录外，写请求带 X-CSRF-Token 并在后端验证。部署 HTTPS 时 Cookie Secure；开发用前端代理，避免随意放开带凭据跨域。两位队友使用自己被邀请的 GitHub 身份，不能共用队长账号或令牌。

成功直接返回契约对象，不再另加 data 包装。错误统一为 error 对象，含 code、message、details。401 为未登录，403 为 CSRF 或禁止操作，404 用于不存在或不属于当前用户的资源，409 为版本或幂等冲突，422 为字段校验，503 为服务暂不可用。FastAPI 默认校验错误需适配本结构。

## 导入与确认

POST /api/imports 接收 multipart 的 source、ingestion_method、file，返回 202 和批次。批次状态 uploaded → processing → pending_review → completed；失败为 failed。处理包含解析、校验、分类并生成草稿，未确认不进入报表。重启中断的任务可恢复或标 failed 提供重试说明，不能永久显示处理中。

初赛默认文件不超过 10 MiB、图片不超过 5 MiB、文件不超过 500 个交易候选行；这些为开发约定，11 月 8 日可按实测通过变更流程调整。支持 PNG/JPEG、CSV/XLSX；不承诺任意银行模板、旧 XLS、PDF 或压缩包。

草稿保留 row_id 和字段缺失、解析错误、重复提示。缺失金额或日期必须用户补齐；截图没有年份不自动无提示地补当前年。对同一截图多条交易返回多个草稿。

确认请求包含 request_id、批次 expected_version 和最终确认的 rows。每行含 row_id 与完整 TransactionInput，allow_suspected_duplicate 默认 false。前端可取消不入账行。服务端重新验证所有数据；本次确认在单一事务中完成，失败不部分入账。相同用户、批次、request_id 和相同请求体重放返回原结果；同 request_id 不同请求体返回 409。已完成批次用新 request_id 再确认返回 409。明确重复自动跳过并计数，疑似重复必须用户显式选择才允许新增。

稳定交易号按用户、平台、交易号、事件性质判重。支付与退款共享订单号时仍是不同事件。没有交易号或跨来源疑似同笔时标疑似，不因同金额同时间自动删除。错误行和略过记录要向用户说明。

## 统计与反馈

当月收入 I 排除退款和内部转账；毛支出 E 排除转账与还款；退款 R 按实际发生月单列。净支出 E−R，收支差额 I−E+R。收支差额不等于银行余额。饼图用毛支出，日趋势分别展示收入、支出、退款。

预算按类别当月净支出计算，spent_fen 可因跨月退款为负；over_fen=max(0,spent−budget)，remaining_fen=budget−spent。使用比例的展示可下限为 0，但不能把实际净支出改成 0。预算为 0 时不除以 0，直接显示金额与是否超支。合成样本有手工预期供三方核对。

PATCH 交易携带 expected_version，防止旧页面覆盖新修改。修改账单、必要的加密索引、纠错日志和个人规则在同一事务保存。只有 remember_rule=true 才建立规则，要求类别和商户明确。分类手工改动标为 manual；下一笔规则命中标为 user_rule。记住规则不等于训练模型。

规则精确匹配当前用户、source 与标准化商户；标准化用 Unicode NFKC、首尾去空白、连续空白合并、casefold。不要自行做跨平台别名合并。每个匹配键只有一个当前规则；更新提高 version。停用不批量覆盖已确认历史账单，只影响后续自动分类。字段更改若影响重复判断要复核，不静默吞记录。

## D 交给 H 的 Python 接口

下列模型在 backend/app/contracts.py 由 H 建立并与 OpenAPI 对齐，D 导入共用模型。H 在调用前限定用户范围，D 不负责数据库事务。

```python
parse_bill_file(content: bytes, filename: str, source: str) -> ParseResult
recognize_bill_image(content: bytes, mime_type: str, source: str) -> ParseResult
normalize_merchant(value: str) -> str
classify_transactions(rows: list[TransactionDraft], personal_rules: list[ClassificationRule], *, use_llm: bool) -> list[ClassificationResult]
```

ParseResult 含 rows 和 issues；每个草稿用独立 row_id，缺失字段为 null。ClassificationResult 含 row_id、category、classification_source、classification_reason。分类按个人规则、通用规则、DeepSeek、pending 顺序返回；rule 和 LLM 不修改原始金额时间。服务超时、空输出、无效类别等返回待确认及 issue，不能编造成功。具体同步或异步执行由 H 的批次任务层安排，函数边界保持一致。

分类结果与输入 row_id 一一对应，不得遗漏、重复或把模型返回顺序当作交易关联。对缺失、未知或重复 row_id 的模型输出，回退为相关记录待确认并给出问题，不能错配到其他交易。

DeepSeek 输入仅含所需脱敏字段，输出经 JSON 和业务字段校验。批量大小、有限重试、耗时和 token 用量留记录；CI 用测试替身，真实调用另留脱敏证据。OCR 仅实现一个实际验证过的主提供方，资源和字体需能在目标 Linux 环境获取或随包提供。

## 存储保护

H 负责 users、import_batches、transactions、classification_rules、correction_logs、budgets 及必要迁移。敏感字段和保留文件用成熟认证加密库；必要的用户、月份、类别、状态索引可保留，文档准确写明保护范围。规则匹配字段和纠错前后值也应保护。初赛个人小规模数据可按用户读取后解密过滤、汇总，避免额外明文商户表。

密钥、API token 不存进 Git 或镜像；持久化卷和密钥分别备份。CSV 处理公式注入风险；原图和导出经鉴权响应，不放公共静态目录。事务、唯一约束及幂等记录由 H 实现，不能只依赖前端禁用按钮。

## 逐接口手册和对接入口

完整HTTP字段、请求和响应见[11接口手册](11_api_reference.md)；页面调用顺序见[12对接说明](12_page_api_integration.md)；数据库事务与智能模块交接见[13设计](13_database_module_design.md)。HTTP方法和路径以OpenAPI为准，SDK函数名与operationId完全一致。

批次新增file_name、created_at、updated_at、progress。ClassificationResult新增issues，所有结果仍按row_id关联。错误details现在固定为可选fields、current_version、retry_after_seconds，不能随意加其他形状。

文件与图像上传限制在契约固定为10MiB/5MiB及500行；调整需同步两端和契约。列表默认page=1/page_size=50，稳定按时间和id倒序；导出不带分页、覆盖全部筛选记录。

确认时先核验已完成的同请求幂等重放，再判断expected_version与状态。否则会导致成功响应丢失后重试被旧版本拒绝。完整状态与检查次序见12和13。

源去重标识必须能区分实际支付或退款事件；同订单多次部分退款无法从现有字段区分时标疑似并由用户确认，不直接合并。分类规则和预算使用ResolvedCategory，不接受pending。
