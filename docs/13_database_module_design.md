# 后端数据和智能模块设计

本说明定义逻辑表、事务和模块交接，配合OpenAPI 0.2.0使用。H实现数据库与服务，D仅实现intelligence模块。物理索引和库版本由T00实际验证，不把本文当作已经执行的迁移。

## 逻辑表结构

主键用UUID，HTTP中作为字符串返回。所有用户数据通过user_id关联，外键及服务校验同时确保同一用户归属。时间列用带时区类型，逻辑amount_fen为正整数，预算为非负整数。

| 表 | 关键列和约束 | 明文与加密范围 |
| --- | --- | --- |
| users | id PK；username唯一；password_hash；created_at；is_active | 密码成熟慢哈希，不可逆明文存储 |
| import_batches | id；user_id FK；source；ingestion_method；status；version；progress_current/total；created_at/updated_at；started_at；expires_at | filename、原文件、草稿、issues和幂等响应内容加密；仅必要状态/索引明文 |
| transactions | id；user_id；import_batch_id；version；month_index；source；flow_type；category；status；created_at/updated_at | 精确时间、金额、交易号、商户、说明、分类依据进入encrypted_payload；必要类别月份流向索引保留并说明泄露范围 |
| classification_rules | id；user_id；source；version；enabled；created_at/updated_at | merchant_normalized和规则内容加密；仅在本人少量规则中解密匹配，禁止建明文商户库 |
| correction_logs | id；user_id；transaction_id；created_at；是否建立规则 | 修改前后值和原因加密，不能日志打印原文 |
| budgets | id；user_id；month；category；updated_at；同人月份类别唯一 | 预算amount_fen加密或同一认证加密payload |

批次只允许一次成功确认。可在import_batches存confirmation_request_id、request_body_digest、encrypted_confirm_result，实现同ID同体重放和同ID异体拒绝；若拆独立幂等表，也必须有用户/批次/请求ID唯一约束及事务。不能仅用进程内字典。

交易去重的稳定标识应在用户、平台、事件性质范围内比较。可使用带独立密钥的HMAC摘要建立唯一索引，原号加密；同订单多次部分退款不能仅用订单号一刀切，需源退款事件号或待人工确认。截图无可靠事件号时只做疑似重复。H与D依据真实样本约定字段来源，未验证的平台情况不得强行合并。

## 必须原子执行的操作

| 操作 | 单一事务中的步骤 | 并发或失败处理 |
| --- | --- | --- |
| 确认入账 | 锁本人批次；先查幂等重放；版本/状态校验；逐行重校验；去重；写交易；标completed及版本；保存确认响应 | 任一行不合法全回滚；网络响应丢失可按原request_id重放 |
| 修正并记住规则 | 锁本人交易；核验version；更新加密值及月份/类别索引；记日志；建立或更新个人规则；version递增 | 其他会话旧版本返回409，不能部分建立规则却未修改交易 |
| 停用规则 | 本人范围读取、核版本、更新enabled、version递增 | 仅影响后续分类，已处理草稿不自动覆盖；用户要新规则须重新处理失败批次或新建批次 |
| 设置预算 | 按用户月份类别唯一键upsert，验证类别非pending和金额非负 | 重复PUT保存相同值，结果仍200 |

报告不维护另一套容易过期的累计总数。初赛个人数据量下，按用户和月份取已确认记录、解密并确定性计算。交易月份或类别修正时同步更新索引。不得把“收支差额”写成银行余额。

## 智能模块接口

共用DTO在backend/app/contracts.py由H维护，字段与11的共享模型一致。D导入这些模型，所有结果按row_id关联。

| 函数 | 输入 | 返回 | 可产生的副作用 |
| --- | --- | --- | --- |
| parse_bill_file | bytes、filename、source | ParseResult，rows为TransactionDraft，issues为Issue | 解析只读，不写数据库 |
| recognize_bill_image | bytes、mime_type、source | 同上，未知字段null；首次识别保留 | 可调用所选OCR，不能直接入账 |
| normalize_merchant | 商户字符串 | NFKC、trim、合并空白、casefold后的字符串 | 无 |
| classify_transactions | list[TransactionDraft]、本人list[ClassificationRule]、use_llm布尔 | list[ClassificationResult]，每输入row_id恰好一项，含issues | 可调用DeepSeek；不改金额时间，不写库 |

ParseResult和ClassificationResult均是数据，不包含HTTP Response、数据库Session或前端组件。D遇到坏行用Issue返回；文件整体无法解析时抛项目自定义IntelligenceFailure，含code和安全message，由H转批次failed。先约定最小错误代码 UNSUPPORTED_TEMPLATE、INVALID_FILE、OCR_UNAVAILABLE、OCR_FIELD_MISSING、MODEL_TIMEOUT、MODEL_OUTPUT_INVALID；不抛含密钥或原文件的异常文本。

类别判断只改变分类字段及issues。个人规则和通用规则均未命中时才调用模型；每次调用超时20秒、最多1次重试，最多2个并发调用，整体批次期限300秒；以真实服务特性需要调整时走共同变更。模型输出的row_id缺失、重复或未知不能错配，相关行回pending。

## HTTP处理层

H的API层负责认证、CSRF、请求模型校验、资源归属、HTTP状态和Error结构；服务层负责业务事务；数据层负责加密持久化；intelligence负责解析分类。FastAPI请求和response_model必须与契约字段一致，默认422错误需要统一转换为error.details.fields。

T00输出的/openapi.json用来检查真实路径和模型是否对齐，不能直接用后端新导出覆盖设计契约以掩盖漂移。契约变更先经文档说明，同一PR更新两端、例子、生成SDK和测试。
