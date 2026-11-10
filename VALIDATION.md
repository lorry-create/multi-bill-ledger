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

## 仍需开发后验证

真实HTTP返回、Pydantic模型与契约匹配、数据库事务和权限、实际平台格式、OCR和DeepSeek效果、浏览器完整交互、Linux部署与恢复。Postman集合是请求模板，独立快照不能当作一键连续业务回放。

本次读取的远端仍是原README；修订没有上传、创建Issue或PR、邀请或启用远端CI。远端是否通过必须看实际运行及被测SHA。

## 本地环境

使用捆绑Python 3.12.14、项目临时目录中的Schema校验库和TypeScript编译器，未替换系统Python。T00仍需落实三人解释器、应用依赖锁和启动命令。生成SDK和检查工具是交接辅助，不是账单业务实现。

注：上述 3.12.14 是 0.2.0 文档校验当时的解释器，属历史记录不追溯。自 T00 起团队统一 Python 3.13 系列（CHG-001，见 docs/10_change_delivery.md）：共用模型生成器已在 3.13.14 实测通过，含 463 行/39 符号生成、7 项负向用例与 --check 幂等。
