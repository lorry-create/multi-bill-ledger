# multi-bill-ledger

多源账单导入与个人财务管理。当前开发交接包版本为0.2.0，日期2026年11月7日。目标在11月19日前完成初赛核心闭环，20日提交。业务服务和页面尚未实现。

## 先看接口设计

| 开发时要找的内容 | 文件 |
| --- | --- |
| 17个接口的方法、URL、参数、必填字段、请求和成功失败响应 | [前后端接口手册](docs/11_api_reference.md) |
| 每个页面调用哪个函数、怎样轮询、确认、纠错和刷新 | [页面对接说明](docs/12_page_api_integration.md) |
| 后端表结构、事务、幂等及D模块的函数输入输出 | [数据库与模块设计](docs/13_database_module_design.md) |
| 前后端共同的机器契约 | [OpenAPI](contracts/openapi.json) |
| 自动生成的字段类型与浏览器HTTP调用函数 | [TypeScript SDK](contracts/client.generated.ts) |
| 17个成功和12个失败请求响应快照 | [合成示例](contracts/examples.json) |
| 可导入Postman的逐接口请求模板 | [Postman集合](contracts/postman_collection.json) |
| 按角色开始和完成第一轮真实联调 | [首次联调操作](docs/15_first_integration_handoff.md) |
| **今天从哪开工（T00 骨架半天落地）** | [T00 骨架落地清单](docs/16_T00_scaffold_checklist.md) |
| **F 今天做什么** | [F 首日开工卡](docs/17_F_first_day_card.md) |
| **D 今天做什么** | [D 首日开工卡](docs/18_D_first_day_card.md) |

共用 Pydantic 模型由契约生成，不要手写：`python tools/gen_pydantic_models.py` 产出 `backend/app/contracts.py`，`--check` 已接入 CI 防漂移。

## 三人分工与读取顺序

全员先读AGENTS、[需求](docs/01_requirements.md)、[业务约定](docs/02_contract.md)、11接口手册和12调用顺序，再读自己的任务书。

| 人员 | 职责 | 任务书 |
| --- | --- | --- |
| 你 H | 后端、模型、数据库、统计、导出、部署和集成验收 | [队长后端](docs/03_captain_backend.md) |
| 队友 A F | 前端页面、统一SDK、交互和图表 | [前端](docs/04_frontend.md) |
| 队友 B D | 文件解析、OCR、DeepSeek和规则匹配的Python模块 | [数据与AI](docs/05_data_ai.md) |

日期、依赖、修改范围和验收在[T00至T11任务卡](docs/06_tasks_schedule.md)。先完成T00的共同模型、登录、运行环境和真实接口；页面草图、样本和纯函数可按依赖提前并行。每次让AI读整个仓库的公共约定，只完成一张当前任务卡。[开工提示词](docs/09_ai_prompts.md)已同步新版必读内容。

## 共同契约怎样保持一致

```text
OpenAPI + examples
    → 生成逐接口手册、TypeScript SDK、Postman
    → H按模型实现，F使用SDK，D返回统一DTO
    → PR检查契约、示例、生成漂移和SDK
    → 真实HTTP、浏览器闭环和部署验收
```

OpenAPI定义路径字段，02/12/13定义业务约束，examples定义独立合成快照。不要手改生成文件，也不要让后端导出覆盖设计契约来掩盖偏差。接口变更需[变更说明](docs/10_change_delivery.md)，同一PR更新受影响两端和测试。

F在T00创建frontend/src/api目录后，生成器会把同一份SDK同步至frontend/src/api/client.generated.ts，--check同时检查它。三人用同一契约版本与提交SHA，避免依赖各自旧ZIP。

## 现在可以执行的检查

```powershell
python -m pip install -r tools/requirements-contract.txt
python tools/check_contract.py --self-test
python tools/validate_examples.py --self-test
python tools/generate_contract_artifacts.py --check
```

本地已执行OpenAPI标准、29例Schema、生成一致性、TypeScript严格检查和9项fetch替身调用测试，结果见[检查记录](VALIDATION.md)。完整TypeScript与Node测试命令在.github/workflows/contract-check.yml；远端Actions尚未运行。静态例子和替身不是实际业务服务，真实权限、金额事务、OCR模型和部署仍需后续验证。

## GitHub协作

仓库：https://github.com/lorry-create/multi-bill-ledger 。已确认private且当前连接可读；本次读取仍只有原项目README。本次本地修订未上传远端、创建PR或邀请队友。

你邀请队友接受Collaborator访问，上传新版文档基线，队友克隆同一仓库。任务分支开发、PR提交、Actions检查、你拉取具体SHA测试、验收合并main。步骤和套餐限制见[GitHub指南](docs/07_github_review.md)。真实账单、密钥不入Git；[合成账本](fixtures/synthetic_ledger.json)只用于口径测试。

## 修订依据和历史

已实际读取FastAPI全栈模板、RealWorld和微软REST规范，采用逐接口示例、共同类型生成和PR契约检查，来源见[调研与修订](docs/14_research_and_contract_changes.md)。此前0.1版ZIP仅作历史，此次0.2替代开发交接内容；未把任何业务任务标记为已完成。
