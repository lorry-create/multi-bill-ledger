# 第一次分工与联调操作

开发人员拿到本包后按下面执行，不再从一句功能描述重新设计接口。

## 开发前共同读取

所有人读README、01需求、02语义、11接口手册、12页面调用。H另读13数据库与模块；D读取13的DTO交接；F使用contracts/client.generated.ts。三人确认相同契约版本0.2.0和同一文档提交SHA。

后端未就绪时，F可以按contracts/examples.json的明确标记合成响应开发页面；最终验收必须切换真实后端。不要把测试样例URL用作真实数据来源或宣称模型已调用。

## H 后端第一批

T00实现登录、me、logout、health、共用模型、数据库迁移和加密回读。第二批T02实现createImport/getImport/confirmImport/listTransactions，再接D的classify及OCR。H用response_model约束输出，以OpenAPI和29个样例验证实际返回，不只让路由返回随意字典。

## F 前端第一批

从生成SDK导入login/getSession/createImport/getImport/confirmImport/listTransactions。先完成登录→上传→预览确认→账单列表。接口状态、required和nullable按11，按12处理Cookie/CSRF、409及轮询。先完成这条可验收路径，再做预算图表和导出。

## D 智能模块第一批

按13的四个Python函数和DTO完成parse_bill_file与通用规则，再接DeepSeek和OCR。文件原始行、草稿row_id、分类结果一一对应。让H直接导入函数，而不是再启动一个独立端口服务。

## 联调顺序

1. H在8000提供真实服务，F在5173配置代理；两人先验证登录Cookie、CSRF和me。
2. H/D准备一个对应已支持平台模板的合成或授权脱敏小文件，确认条数、金额和标注；将验证数据范围写明，不能假定任意CSV都支持。
3. 用上传响应id查询批次，确认status=pending_review和最新version；F修正字段后构造ConfirmInput。
4. 按原request_id同体重试确认，验证不重复；修改请求体仍用同ID，验证409；用旧version编辑，验证409。
5. 列表取得实际id/version，修正分类并记住；新文件中另一笔交易命中个人规则。
6. seed_demo用于六笔合成报表口径验收。上传联调和六笔seed预期是独立数据场景，不能混在一起后仍断言6300分。
7. 图表、预算和导出按真实后端统计核对，最后执行08的权限、异常和干净部署验收。

## Postman怎么用

导入contracts/postman_collection.json，填写baseUrl、username和本机演示password。先运行login，脚本保存csrfToken；浏览器Cookie与Postman Cookie不同，Postman自行保存其登录Cookie。

运行createImport时在form-data选择本机文件和正确source；随后getImport查询。确认body里的row_id、expected_version及完整字段必须按实际草稿替换。确认成功后会记录transactionId。listRules会取首项ruleId供修改示例，使用前核对是否目标规则。retryImport只在批次确实failed时运行。

集合含独立场景操作，不能直接点击全部运行就认为完整业务通过。集合脚本只做基本成功状态和变量提取；业务不变量仍按08验证，HTTP正文可按契约Schema校验。不要在同步到公共空间的Postman环境保存真实密钥或个人账单。

## CI对齐

每个PR执行契约标准校验、请求响应示例Schema验证、生成文件漂移检查和SDK类型检查。T00实现应用后再启用后端、前端与数据库测试。后端的真实HTTP测试至少覆盖29例对应的状态形状，并增加08要求的幂等、权限、退款、反馈和恢复断言。

验收记录必须写实际SHA。PR修改接口时，同一个PR更新OpenAPI、examples、生成物、两端和测试，H/F/D共同检查受影响部分。远端仓库当前只有原README，是否上传此新版基线由仓库实际提交确认；本包生成不代表已推送。
