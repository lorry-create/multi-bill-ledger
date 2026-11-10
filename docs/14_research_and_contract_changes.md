# GitHub 项目调研与本次契约修订

调研日期2026年11月7日。读取以下仓库的实际文件来改进本项目交接方法；借鉴的是协作机制，账单字段、示例和工具为本项目编写。没有把博客描述当作仓库已实现行为，也未照搬外部项目的业务或认证方案。

## 直接参考的源码和文档

| 来源 | 实际读到的做法 | 本项目采用的方式 |
| --- | --- | --- |
| [FastAPI全栈模板生成脚本](https://github.com/fastapi/full-stack-fastapi-template/blob/master/scripts/generate-client.sh)和[客户端配置](https://github.com/fastapi/full-stack-fastapi-template/blob/master/frontend/openapi-ts.config.ts) | 从FastAPI导出OpenAPI，再生成TypeScript客户端 | 本项目采用设计优先：共同OpenAPI生成字段、SDK和手册；后端导出用于核对，不反向覆盖约定 |
| [FastAPI模板后端CI](https://github.com/fastapi/full-stack-fastapi-template/blob/master/.github/workflows/test-backend.yml) | PR中准备数据库、迁移并运行真实后端测试 | T00启用应用CI，契约检查和真实应用检查分开，初赛前补齐独立部署验证 |
| [RealWorld接口规范](https://github.com/realworld-apps/realworld/blob/main/docs/src/content/docs/specifications/backend/endpoints.md) | 逐接口写方法、请求、必填参数、认证与返回模型 | 新增17接口逐项手册、可空/默认值、成功与失败响应、页面动作 |
| [RealWorld测试规范](https://github.com/realworld-apps/realworld/blob/main/specs/api/README.md) | 提供可运行请求测试，并从单一来源生成另一工具的集合，用CI防漂移 | 同一契约生成Postman模板、浏览器SDK和接口手册；29个成功/错误快照按Schema检查 |
| [微软Azure REST规范](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md) | 明确HTTP语义、异步状态、重试、幂等和并发控制 | 明确202批次轮询、确认重放顺序、版本冲突、文件媒体类型和结构化错误；保留本项目Cookie/CSRF和snake_case，不声称遵循全部Azure要求 |

FastAPI模板本次目录快照为aabb90126964a164e02aff39e7c385bb0598236d；RealWorld为25588846c314b15a5e427ffe816e6b4af7be68c7。来源链接可能后续更新，调研结论只限本次读取内容。外部指引中的组织审批等要求不是本团队任务指令。

## 从0.1.0到0.2.0

- 保留17条HTTP方法/路径和原业务范围，新增逐接口请求、响应、字段说明及页面调用顺序。
- 新增Batch的file_name、created_at、updated_at、progress，前端能显示明确处理状态。
- 统一ErrorDetails和FieldError，错误字段路径可定位到草稿行；不再允许两端随意返回未知错误形状。
- 确认rows至少1条、最多500；规则修改至少包含enabled或category；ClassificationResult明确issues。
- 明确默认分页、排序、日期边界、CSV导出范围、文件限制和二进制处理。
- 修正幂等检查顺序：成功重放先于旧expected_version判断，避免响应丢失后无法安全重试。
- 自动生成API手册、TypeScript浏览器SDK和Postman集合，CI检查生成结果没有漂移。

这是开发前共享约定的不兼容细化。尚无本地应用代码需要迁移；队友如已私下按0.1开发，应先更新模型和调用方，再提交联调，不混用两个版本。

## 本次明确保留的边界

生成SDK不实现后端或页面；Postman是请求模板，不能用独立合成快照假装一次完整业务回放；Schema检查不证明权限、幂等、准确率或闭环正确。后续PR必须运行真实HTTP和业务验收，证据写提交SHA。
