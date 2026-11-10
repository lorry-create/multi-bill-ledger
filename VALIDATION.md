# 0.2版交接包检查记录

日期2026年11月7日，契约版本0.2.0。业务应用尚未实现；下列本地验证不表示已启动后端或完成真实闭环。

## 已执行检查

- 基础检查：本地引用、接口operationId、路径参数、文档相对链接及六笔合成账本预期一致；错误金额和坏引用会被拒绝。
- 标准校验：使用openapi-spec-validator 0.7.2校验OpenAPI 3.1契约，包含17个HTTP操作和35个共享模型。
- 示例校验：使用jsonschema 4.23.0校验17个成功和12个错误快照的参数、正文、响应媒体类型及文档头；金额为0的422请求明确标为预期非法输入。
- 负向验证：字符串金额和缺失csrf_token会被Schema校验拒绝。
- 生成一致性：生成器--check核对API手册、SDK和Postman均与源契约相同。
- 类型检查：TypeScript 5.7.3的strict/noEmit通过，包含缺查询、金额字符串、中文类别、缺版本、pending预算等应被拒绝的编译期示例。
- 调用层：Node内置测试用fetch替身覆盖查询、Cookie请求配置、CSRF、FormData、204、409、Blob、异常成功状态、登录和非JSON错误，9项通过、0失败。未执行真实网络请求或身份认证。
- 工作流：两个工作流YAML能解析，并核对只读contents权限。远端Actions尚未运行，不能据此宣称GitHub CI已通过。
- 新版ZIP完成后核对清单和CRC；临时依赖不包含在交付包中。

## 2026 年 11 月 10 日补充：共用模型生成器

新增 `tools/gen_pydantic_models.py`，从 `contracts/openapi.json` 生成 `backend/app/contracts.py`，解决 H 与 D 必须共用同一份模型、又容易手工抄错的问题。本机实际执行结果：

- 生成 463 行、39 个导出符号（7 个枚举 + 32 个模型，含 `MonthlyReportExpenseByCategoryItem` 等内联子模型），契约版本 0.2.0。
- 导入校验通过；`amount_fen` 等金额字段生成为 `StrictInt`，`"2300"` 与 `2300.0` 均被拒绝。
- 负向用例 7 项全部拒绝：字符串金额、浮点金额、越界类别、零金额、非 CNY、非法流向、非法来源。
- 语义断言通过：`BudgetStatus` 允许负净支出（-5000），`pending` 不能作为预算类别，`2026-13` 月份被拒，内联枚举自动复用顶层枚举。
- `--check` 重复执行一致，可作为 CI 漂移检查；`contract-check.yml` 已加入 "Reject Pydantic model drift" 步骤。

仍需开发后验证：生成的模型与 FastAPI 实际路由的 `response_model` 是否一致、序列化后的 JSON 是否与 `examples.json` 快照逐字段相等。本次只证明"模型可导入、约束生效、与契约文本一致"，不表示后端接口已实现。

## 2026 年 11 月 10 日补充：T00 骨架实测

| 命令 | 实测结果 |
| --- | --- |
| `python -m app.migrate` | 8 张表建成，`schema_migrations` 记录 001，checksum `c64a885bf3a0` |
| `python -m app.migrate --check` | 表齐全、checksum 一致，重复执行幂等 |
| `python -m app.migrate --sql` | 导出 152 行 PostgreSQL DDL 到 `backend/migrations/001_init.sql` |
| `python -m app.seed_demo` | 6 笔合成账 + 2 条预算；重复执行 6 笔全跳过（幂等）；解密回读合计与 `fixtures.expected` 完全一致（收入 100.00／支出 42.00／退款 5.00／净支出 37.00／收支差额 63.00） |
| `python -m unittest discover -s tests -v` | 9 项通过：health、未登录 401、错误密码、账号不存在同码、422→`error.details.fields`、登录成功与 Cookie 属性、CSRF 403、登出 204 且会话立即失效、429 锁定 |
| `tools/check_implemented_contract.py` | 已实现 4 个接口字段与契约一致；待实现 13 个 |
| 手动 HTTP 复核 | 22 项断言全过（含 `Retry-After` 头、未知路径 404 也走统一 Error） |

过程中发现并修正的两个真实缺陷：`/health` 的 `status` 因带默认值被 OpenAPI 标为可选（与契约 required 不符）；`/api/auth/login` 的 422 文档默认写成 FastAPI 的 `detail` 结构，而运行时返回契约的 `error` 结构。两处均已修，并由 `check_implemented_contract.py` 持续看守。

## 仍需开发后验证

真实平台导出格式（支付宝/微信真实账单仍为空）、OCR 效果、DeepSeek 分类效果、浏览器完整交互、Linux 部署与备份恢复演练。已实现 4 个接口的真实 HTTP 行为已在本机验证；其余 13 个接口尚未实现，不能声称已验证。

T00 基线已推送到远端 `task/T00-baseline` 分支；`main` 未改动。远端 Actions 尚未实跑，是否通过必须看实际运行及被测 SHA。

## 本地环境

使用捆绑Python 3.12.14、项目临时目录中的Schema校验库和TypeScript编译器，未替换系统Python。T00仍需落实三人解释器、应用依赖锁和启动命令。生成SDK和检查工具是交接辅助，不是账单业务实现。

注：上述 3.12.14 是 0.2.0 文档校验当时的解释器，属历史记录不追溯。自 T00 起团队统一 Python 3.13 系列（CHG-001，见 docs/10_change_delivery.md）：共用模型生成器已在 3.13.14 实测通过，含 463 行/39 符号生成、7 项负向用例与 --check 幂等。

## 2026 年 11 月 10 日补充：T02 导入中心实测（CHG-004）

| 命令/场景 | 实测结果 |
| --- | --- |
| `python -m unittest discover -s tests` | **100 项通过**（`test_imports_api` 26 + `test_intelligence` 43 + `test_reporting` 18 + `test_t00_smoke` 13） |
| `python tools/check_implemented_contract.py` | 已实现 **9** 个接口，字段与契约一致；待实现 8；1 条 `[注意]`：`retryImport` 的 422 为契约漏写（见 docs/10 CHG-004「契约待补」） |
| 真实 uvicorn（127.0.0.1:8011，临时 SQLite） | 上传微信样例 1577 字节 → `202` + `Location` + `Retry-After: 1`；第 3 次轮询 `pending_review`，6 条草稿，首行为「星巴克咖啡 3500 分 dining / general_rule」；`original` 回读 1577 字节、字节完全一致、`text/csv`；`confirm` 建 6 笔并返回 6 个 ID；同 `request_id` 重放响应逐字段相同；批次 `completed`、version 4 |
| 真实进程重启恢复 | 人为置 `processing` → `taskkill /F` → 重启 → 同一批次返回 `failed`（version 3）+ `BATCH_INTERRUPTED`，重试通道可用；不存在永久 processing |
| 上传边界（用例内） | 513KiB → 413 `UPLOAD_TOO_LARGE`；`.pdf` → 415；PDF 改名 `.csv` → 415；0 字节 → 422 `EMPTY_FILE`；`.png` 以 file 方式上传 → 415；`source=paypal` → 422 `VALIDATION_FAILED` |
| 批次边界（用例内） | 他人批次 → 404 `RESOURCE_NOT_FOUND`；`pending_review` 批次 retry → 409 `BATCH_STATE_CONFLICT`；旧 `expected_version` → 409 `VERSION_CONFLICT` 并回带 `current_version`；未知 `row_id` → 422 `UNKNOWN_ROW`；无时区时间 → 422 `TIME_WITHOUT_TIMEZONE`；过期草稿 → 409 |
| 幂等与去重（用例内） | 同 ID 同体重放 → 返回原结果且库内交易数不变；同 ID 改金额 → 409 `IDEMPOTENCY_CONFLICT`；已完成批次 + 新 ID → 409 `BATCH_STATE_CONFLICT`；同一文件重传 → 6 行全 `duplicate`，确认 `created_count=0` |

本轮未验证：真实平台账单（仍为零）、OCR、Docker/PostgreSQL 实跑、备份恢复、浏览器端页面交互。
`tests` 全部在临时 SQLite 上跑，不触碰 `backend/local-data/app.db`。
