# 队长和后端开发任务书

你负责接口、数据库、用户隔离、入账、纠错持久化、报表、部署和集成验收。你也用 AI 开发，但每次让 AI 执行当前任务卡，并亲自确认实际输出。

必读 README、AGENTS、01、02、contracts/openapi.json、06、07、08。顺序为 T00 → T02 → T05，同时在接口稳定后做 T08，最后 T10 和 T11。F 和 D 的依赖就绪后当天接入，不等全部完成。

## T00 首要交付

- 建立 backend、frontend、共用模型、配置、迁移、演示数据初始化，Python 3.13 系列、Node 22 起步并提交实际依赖锁定结果。
- 两个仅用于演示的用户，密码经成熟哈希；实现登录、me、logout、CSRF 和资源归属基础校验。初始化命令不能默认创建生产弱口令。
- 建立 /health、数据库连接、加密回读、Docker Compose 骨架，数据库使用项目命名卷，不写固定 container_name。
- 与前端负责人共同建立 package.json、package-lock.json 和 typecheck、lint、build 脚本；requirements-dev.txt 包含运行依赖和必要测试依赖。
- 规定 backend 工作目录，python -m app.seed_demo 仅导入 fixtures 合成账单；pytest 在独立测试库运行。
- 将 .github/workflows/app-ci.yml.example 按实际工程核对后改为 app-ci.yml，首次 CI 通过不能靠跳过缺失测试。
- 完成一个真实 /health 或认证测试和一个前端构建；输出启动、测试命令。此后其他人拉取这一基线。

## 集成职责

T02 调 D 的 parse、classify 和 OCR 接口，自己负责状态、超时恢复、鉴权、重复确认和数据库原子性。T05 保存交易修改、日志和规则，不让 D 的模块直接写库。T08 用后端确定性计算统一报表，输出 CSV 和可在 Linux 打开的中文 PDF；让 F 直接使用汇总数字。

T10 落实数据加密、用户隔离、备份恢复、干净部署；确保图片、PDF、字体和其他运行资源不依赖开发者个人目录。真实 DeepSeek 配置可以缺失，但必须显示规则或待确认路径，不伪造成功。

## 每个 PR 如何验收

1. 检查任务号、契约版本、diff 和依赖；确认无越界修改和真实数据。
2. 查看 Actions，分清文档检查、单元测试、数据库测试和前端构建。
3. 在独立 review 克隆目录拉取 PR 最新 head，记录 SHA。用合成数据运行受影响功能；关键闭环按 08 复核。
4. 保存输入、预期、实际、命令、环境、SHA 和失败项。PR 更新后重新确认新 SHA，旧结果不自动适用于新代码。
5. 通过后合并，再检验 main 的集成结果。你自己的 PR 由另一名队员交叉检查，避免完全自审。

你每天查看 PR 和任务板，记录实际完成而非预计完成。代码上传只是已推送，尚不代表已验收。功能分支可频繁推送，main 保持最近一次已经验收的集成版本。

## 新版接口交接要求

开工先读11的全部HTTP接口和13的数据/事务设计，按contracts/openapi.json建立共同Pydantic请求与response_model。不要只参考功能描述后自行定义返回字典。先交付health、login、getSession、logout；再按任务接批次、确认、查询、纠错、报表和导出。

交付时执行tools/validate_examples.py、生成器--check和真实HTTP测试；Schema静态检查不代替鉴权和事务测试。F创建frontend/src/api目录后，生成器会同步SDK至该目录，CI检查是否漂移。你修改契约时同步生成物和两个调用端。
