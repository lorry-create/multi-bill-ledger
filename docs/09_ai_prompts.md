# AI 开工和审查提示词

先克隆仓库或将整个文档包提供给 AI。只发送一段任务描述而不给公共约定和现有代码，容易生成接口不兼容的独立版本。以下提示词适用于不同 AI 开发工具，不依赖自动识别某一种说明文件；要求 AI 实际读取文件并报告已读内容。

## 队长首次工程任务

```text
你在 multi-bill-ledger 仓库开发。先读 README.md、AGENTS.md、docs/01_requirements.md、docs/02_contract.md、contracts/openapi.json、docs/03_captain_backend.md、docs/06_tasks_schedule.md 的 T00，以及 docs/08_acceptance.md。
本次只完成 T00。先检查现有文件，复述公共接口、目录归属和依赖，再开始实现。保留已有内容，不另建重复系统。
落实基础前后端、共用模型、数据库迁移、认证与隔离、加密回读、Compose 骨架、合成数据初始化和真实应用 CI。应用命令必须能运行，不能以文档检查替代功能测试。
不得上传真实密钥或账单，不自动推 main 或合并。完成后给出实际命令与输出、契约一致性、改动文件和未解决问题；未运行的检查明确写未运行。
```

## 队友 A 当前任务

```text
你负责本仓库前端。先读 README.md、AGENTS.md、docs/01_requirements.md、docs/02_contract.md、contracts/openapi.json、docs/04_frontend.md、docs/08_acceptance.md 和 docs/06_tasks_schedule.md 的 T03。
本次只实现 T03。检查 T00 已合并，T02 哪些接口可用；依赖未就绪时说明，不另造后端。早期合成样例明确标记，交付时接真实接口。
只改 frontend 与本任务证据。金额传整数分，写操作带 CSRF；确认幂等、缺字段、错误、重复和筛选按契约处理。运行真实 typecheck、lint、build 和相关交互验证。
提交功能分支并准备 PR 说明，不擅自改契约或推 main。输出改动、已连接接口、实际验证和阻塞项。
```

## 队友 B 当前任务

```text
你负责本仓库数据与 AI。先读 README.md、AGENTS.md、docs/01_requirements.md、docs/02_contract.md、contracts/openapi.json、docs/05_data_ai.md、docs/08_acceptance.md 和 docs/06_tasks_schedule.md 的 T01。
本次只实现 T01，样本收集和解析。检查 T00 共用模型，按 parse_bill_file 接口返回 ParseResult，不建 API 或数据库。只改 backend/app/intelligence、对应 tests 和任务证据。
真实样本在 data/private 不提交；Git 使用合成 fixture。逐个平台验证编码表头、金额、交易号、坏行，给队长可调用示例与真实支持范围。
缺样本或依赖写阻塞，不伪造真实解析或模型调用。完成后给实际命令、测试结果、限制和 PR 交付内容，不直接推 main。
```

后续任务把 T03 或 T01 换成当前已认领任务号，同时换成对应任务卡的范围和验收，不能沿用旧任务的允许目录。

## 队长审查提示词

```text
请审查当前 PR，先确认 PR 号、最新 head SHA、任务 ID 和契约版本，再读对应需求、接口、任务书和验收项。
先只读审查 diff，核对金额、状态、用户隔离、去重、规则反馈、模型故障和受影响调用方，区分阻塞缺陷与次要建议。给可定位文件与行号，不按代码量评分。
随后在独立 review 环境用合成数据运行相关测试和受影响用户流程。不能连接我的真实账单数据库或把凭据带入待审代码。
结果写明实际命令、预期和实际、SHA、未测项，说明是否满足任务验收。不要自动批准、合并或声称测试通过。若我再要求修复，才按缺陷范围修改。
```

## 单个缺陷修复提示词

```text
修复验收记录中的一个明确失败：提供任务号、输入、期望、实际和提交 SHA。
先读对应契约与相关调用方，定位根因，做最小完整修复，并增加能捕获该失败的有意义检查。不得删除测试或放宽断言来变绿。修复后重跑受影响检查，报告结果，不擅自合并。
```

## 0.2版所有角色提示词追加要求

请先读取docs/11_api_reference.md、docs/12_page_api_integration.md、docs/13_database_module_design.md和contracts/examples.json。接口名、字段、成功状态、错误code和分页按它们实现，SDK导出函数名与operationId相同。

前端先创建web/src/api目录，运行生成器生成SDK并使用，禁止手写另一套请求字段。后端用共同Pydantic模型和response_model，并通过真实请求校验。D严格返回规定DTO。任何不够用的字段先提交共同变更，不能各自临时改协议。
