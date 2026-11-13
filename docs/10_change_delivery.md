# 变更和交付记录模板

共享约定改变时，同步改变文档、接口、实现调用方和验收，不用群聊口头决定替代仓库版本。当前契约为 0.2.0。新增可选字段可升小版本；删除、改名、类型或语义不兼容需要显式记录迁移与三方同步，不偷偷保留多个不同标准。

## 共同约定变更

```text
变更编号和日期：
提出人及任务：
现契约版本和建议版本：
问题及实际证据：
建议的最小改动：
影响的接口、调用方、数据迁移和测试：
需要同步的人员与实施顺序：
队长决定和对应提交：
```

当前初版建立需求、共享接口、金额口径、角色边界和任务依赖；OCR 提供方、模型名、实际服务器限制待真实验证后补充。初版不表示三名成员已经完成阅读或同意具体实现。

## 每个任务 PR 的交付

```text
任务 ID 与需求 ID：
契约版本与公共文档提交：
分支与最新提交 SHA：
完成的行为和受影响模块：
依赖和实际连接的接口：
运行环境和启动方法：
实际执行的测试命令与结果：
用户操作步骤及证据：
真实提供方、测试替身或合成样本标记：
已知问题、未测项和回退方法：
需要队长检查的验收项：
```

## 队长验收记录

```text
任务、PR、测试日期、验收人：
被测 head SHA 和契约版本：
配置和数据来源，不写真实凭据：
验收编号 A01 等：
输入与步骤：
预期：
实际与证据文件：
通过或失败及缺陷级别：
未覆盖项：
最终决定：待修复／已验收
合并后的 main SHA 与集成复核：
```

记录实际完成，不把计划日期、AI 回答或一次绿色文档检查当验收。真实截图和数据证据仅在授权和脱敏范围内存放；即使私有仓库也不提交密钥或原始个人账单。

## 2026年11月7日 0.2.0修订

根据用户要求，把功能级交接补为逐接口设计与页面调用。新增批次元信息、结构化错误、明确类别和分类issues，修正重放顺序；生成手册、TypeScript调用代码和Postman模板；增加标准与样例校验。影响H/F/D模型和调用，详细来源与变更见14。当前没有已实现本地应用，旧版私下开发代码应先更新共同模型。

## 2026年11月10日 CHG-001：运行环境统一为 Python 3.13 系列

```text
变更编号和日期：CHG-001 / 2026-11-10
提出人及任务：罗镓裕（队长），T00 基础工程骨架
现契约版本和建议版本：契约 0.2.0 不变（本变更不改变任何接口、字段或语义）
问题及实际证据：原 AGENTS 第 8 行、03 T00 交付项写"目标 Python 3.12"，CI 写 python-version '3.12'，
  但三人手上都没有 3.12。队长机实测（逐路径执行 python --version）：
    C:/Users/lenovo/.workbuddy/binaries/python/versions/3.13.12/python.exe        -> Python 3.13.14
    C:/Users/lenovo/.workbuddy/binaries/python/versions/3.13.12.old.38000/python.exe -> Python 3.13.14
    D:/Drivers/python/python.exe                                                  -> Python 3.13.7
  注意：托管解释器的目录名仍是 3.13.12，但已自动升级为 3.13.14，目录名不可作为版本依据，
  必须以 python --version 的输出为准（这一点写进 T00 前置检查，避免队友核对时误判）。
  已在 3.13.14 上实际执行 tools/gen_pydantic_models.py：生成 backend/app/contracts.py 共 463 行、39 个导出符号；
  负向用例 7 项全部被拒绝（字符串金额、浮点金额、越界类别、零金额、非 CNY、非法流向、非法来源）；
  --check 幂等通过。pydantic 2.14 可用，FastAPI/Starlette/psycopg 在 3.13 无已知阻塞。
建议的最小改动：不锁死 patch 版本，统一到 3.13 系列，基线 3.13.14、下限 3.13.7。
  AGENTS 第 8 行改为"Python 3.13 系列"，03 T00 同步，CI python-version 改为 '3.13'（由 setup-python 取该系列
  最新补丁），使 CI 与本地同属一个次版本，避免把 patch 写死后本地满足、CI 拉不到或反之的环境漂移。
影响的接口、调用方、数据迁移和测试：接口无影响；三人克隆后须用 3.13.x 创建虚拟环境并提交实际锁文件
  （jsonschema 4.23.0 / openapi-spec-validator 0.7.2 已在 3.13 验证可跑；pydantic 2.x 支持 3.13）；
  无数据迁移。回归口径：contract-check.yml 全部步骤全绿，其中步骤 5（Pydantic 模型漂移）为新增校验。
需要同步的人员与实施顺序：1) 队长改 AGENTS/03/CI 并推送（本记录随同一次提交）；
  2) F、D 拉取后重建 venv，回执 python --version 与锁文件变更；
  3) 若任一方在 3.13 上遇到 OCR 或数据库驱动实际阻塞，按 AGENTS 原文"先说明再共同调整"处理，不得单方降级到 3.12。
队长决定和对应提交：已决定统一 Python 3.13 系列（用户 2026-11-10 确认）。提交 SHA 由队长推送后回填本行。
```

补充口径：`VALIDATION.md` 中"捆绑 Python 3.12.14"记录的是 0.2.0 文档校验当时实际使用的解释器，属历史证据，不修改、不追溯；自 T00 起新增的代码与 CI 一律以 Python 3.13 系列为准。若后续有人在新机器上装出 3.13 之外的版本，按本变更"不得单方降级"处理，而不是默默继续。

## 2026年11月10日 CHG-002：T00 骨架落地，新增会话表与登录锁定字段

```text
变更编号和日期：CHG-002 / 2026-11-10
提出人及任务：罗镓裕（队长），T00 基础工程骨架
现契约版本和建议版本：契约 0.2.0 不变。本变更不改变任何接口路径、请求/响应字段或状态码，
  只把"文档里已经约定的东西"变成可运行的服务，并补齐会话与限流的持久化位置。
问题及实际证据：契约声明了 cookieAuth（bill_session）与 csrfAuth（X-CSRF-Token），docs/13 的表清单
  却没有会话表，登录限流也没有落点。若不落库，登出无法立即失效、加副本后限流失效
  （评分项的"高可用"正好要求多副本）。
  实测证据（本机 Python 3.13.14 + SQLite）：
    python -m app.migrate            -> [OK] 建表完成（8 张），迁移 001 已记录，checksum c64a885bf3a0
    python -m app.migrate --check    -> [OK] 8 张表齐全，迁移 001 校验通过
    python -m app.seed_demo ...      -> 入库 6 笔 + 预算 2 条；解密回读后
                                       收入 100.00 / 支出 42.00 / 退款 5.00 / 净支出 37.00 /
                                       收支差额 63.00，与 fixtures.expected 逐项一致
    python -m unittest discover -s tests -> 9 项全部通过（含 429 锁定、CSRF 403、422 转 error.details.fields）
    python tools/check_implemented_contract.py -> 已实现 4 个接口字段一致，待实现 13 个
建议的最小改动：
  1) docs/13 表清单新增 user_sessions（只存 token 摘要与 csrf 值，登出即删行）；
  2) users 增加 failed_login_count、locked_until，使登录锁定在多副本下依然生效；
  3) 后端只实现 /health 与 /api/auth/{login,me,logout} 共 4 个 operation，其余 13 个留给 T01/T02；
  4) 表结构以 ORM 模型为唯一来源，DDL 由 python -m app.migrate --sql 导出到
     backend/migrations/001_init.sql，避免手写 SQL 与模型漂移；
  5) 新增 tools/check_implemented_contract.py，在 CI 里只比对"已声明的 operation"，
     未实现的不算失败，因此可以随开发进度一直跑。
影响的接口、调用方、数据迁移和测试：
  - 接口：已实现的 4 个与契约字段完全一致；未实现的 13 个仍是 T01/T02 范围，前端不得先行对接。
  - 调用方：F 可用 /api/auth/* 打通登录态与 CSRF；D 不受影响（intelligence 层接口未变）。
  - 数据迁移：新增表与列，属首次建表，无历史数据需要搬迁；--drop 在生产环境被拒绝。
  - 测试：backend/tests/test_t00_smoke.py 为新增回归，CI 增加"契约漂移"与"冒烟测试"两步。
需要同步的人员与实施顺序：1) 队长推送 backend/ 与 docs 变更；
  2) F 按 docs/17 的窄卡先做 mock，再切真接口，注意写请求必须回传 csrf_token；
  3) D 不需要等本变更，按 docs/18 直接做解析与分类；4) 三人各自拉取后跑一次
     python -m unittest discover -s tests，确认本地环境一致。
队长决定和对应提交：已决定按上述最小改动落地（用户 2026-11-10 "b 和 a 同时做"）。
  已推送：`5ad4b30`（分支 task/T00-baseline），代码提交 `c4a79f5`、`26fa275` 为其前置。
```

已知边界（不要误读为已完成）：T00 只做骨架，**没有**实现上传、预览确认、交易列表、规则、报表、导出这 13 个接口；也没有接入 DeepSeek 与 OCR。真实账单样本仍为零，这是 T01 的前置条件。

## 2026年11月10日 CHG-003：补契约响应头、智能模块接口层与报表唯一口径

```text
变更编号和日期：CHG-003 / 2026-11-10
提出人及任务：罗镓裕（队长），T00 收口 → T02 前置
现契约版本和建议版本：契约 0.2.0 不变。本变更不新增/修改任何路径、字段或状态码，
  补的是"契约要求但代码没有"的三处地基，以及一批前端要用到的 Issue 机器码（仅新增取值，
  不破坏既有结构）。
问题及实际证据（对照原文逐条核查，不是凭印象）：
  1) docs/11 第 12 行写明「所有成功和失败响应带 X-Contract-Version」，全文 18 处响应示例均带
     该头；实际在 backend/ 全文搜索零命中。属契约违规，且是 T00 就该有的。
  2) docs/13「智能模块接口」规定 D 提供 parse_bill_file / recognize_bill_image /
     normalize_merchant / classify_transactions 及 IntelligenceFailure（6 个错误码），
     但 backend/app/intelligence/ 目录不存在。后果具体：D 写完后端不知道 import 哪里、
     catch 什么异常；后端写 T02 只能先硬编码假解析，等 D 交付再推翻重写。
  3) seed_demo.py 自带一套 _totals；将来 GET /api/reports/monthly 必然再写一套。
     docs/13 明确"报告不维护另一套容易过期的累计总数"，两套实现迟早分叉且无人第一时间发现。
建议的最小改动：
  1) 新增 app/middleware.py：纯 ASGI 中间件写 X-Contract-Version。用纯 ASGI 而非
     BaseHTTPMiddleware，后者会额外包 task，影响 CSV/PDF 流式响应与后台任务时机。
     CORS 增补 expose_headers，否则浏览器 JS 读不到该头。
  2) 新增 app/intelligence/：base.py（协议 + IntelligenceFailure + assert_one_result_per_row）
     / normalize.py / rules.py / tables.py / fallback.py / factory.py。
     fallback 是**纯规则确定性实现**，不叫 mock——解析与金额是真的，只是分类用关键词，
     classification_source 如实写 general_rule。目的是 D 未到位时后端能先打通闭环，
     且模型超时时业务仍可运行（docs/08 A06 禁止伪成功）。
  3) 新增 app/services/reporting.py：compute_totals + build_monthly_report 为唯一口径，
     seed_demo 改为调用它。
  4) 新增 app/tools/parse_probe.py：真实账单人工核对工具（A02 要求逐笔核对条数金额）。
  5) 新增 fixtures/real_format_samples/：两份**格式仿真、数据全合成**的支付宝/微信导出件，
     用于验证编码（GBK / UTF-8 BOM）、表头不在首行、全角括号列名、尾部说明行等真实坑。
  6) backend/requirements.txt 增加 openpyxl（契约允许 XLSX 上传）。
  7) 智能模块实现通过 INTELLIGENCE_PROVIDER 选择，配置错则启动失败——故意不支持
     "自动降级"，否则分类来源会撒谎。
实测证据（本机 Python 3.13.14）：
  python -m unittest discover -s tests -v   -> 74 项全部通过
      其中 test_intelligence 43 项、test_reporting 18 项、test_t00_smoke 13 项
  curl -i /health                            -> 200 + x-contract-version: 0.2.0
  curl -i /api/auth/me                       -> 401 + x-contract-version: 0.2.0
  curl -i /api/nope                          -> 404 + x-contract-version: 0.2.0
  curl -i -X POST /api/auth/login（缺字段）  -> 422 + x-contract-version: 0.2.0
  python -m app.tools.parse_probe 支付宝样本 -> 6 条草稿，跳过 2 行（关闭/0 元），合计 支出 2665.00
  python -m app.tools.parse_probe 微信样本   -> 6 条草稿，0 条问题，合计 支出 398.50
  python -m app.seed_demo --username demo_a  -> 与 fixtures.expected 逐项一致（改用共用口径后未回归）
  python tools/check_implemented_contract.py -> 已实现 4 个，待实现 13 个
影响的接口、调用方、数据迁移和测试：
  - 接口：17 个操作的数量与字段均未变；已实现的 4 个新增响应头。
  - F：需要知道 401/422 等错误响应也带 X-Contract-Version；写请求仍必须带 X-CSRF-Token。
    Issue 机器码清单见 docs/20 第四节，前端按 code 判断，不要按中文文案判断。
  - D：按 docs/20 第三节实现四个方法即可被后端调用，禁止另定义字段、禁止写库。
  - 数据迁移：无。本变更不新增表、不改列。
  - 测试：新增 tests/test_intelligence.py、tests/test_reporting.py；
    test_t00_smoke.py 增加 4 项响应头断言。CI 的 unittest discover 自动覆盖，无需改 workflow。
需要同步的人员与实施顺序：1) 队长推送本变更；2) D 读 docs/20 第三节后开工，实现类名报给队长
  以更新 INTELLIGENCE_PROVIDER；3) F 读 docs/20 第四节确认 Issue 码；4) 三人拉取后跑
  python -m unittest discover -s tests，期望 74 项通过。
队长决定和对应提交：已决定按上述改动落地（用户 2026-11-10 "请你按照思路进行对应的代码的编写"）。
  已推送：`ca831fa`（响应头）、`0cfbc0b`（智能模块层）、`dc4c3bf`（报表口径与文档），
  分支 task/T00-baseline，HEAD 为 `dc4c3bf`。
```

已知边界（不要误读）：本次**没有**新增任何业务接口，13 个仍是 T02/T05/T08 范围。
fallback **不做 OCR**（抛 `OCR_UNAVAILABLE`，不返回空结果假装成功），也**不会**把分类来源
标成 `deepseek`。真实账单样本仍为零，`fixtures/real_format_samples` 是格式仿真件，不能代替
A02 的真实文件核对。


---

## CHG-004（2026-11-10 晚）：T02 导入中心 5 个接口 + 批次状态机

契约版本不变（0.2.0），**不改任何字段与状态码语义**，只是把契约里已声明的
5 个操作真正实现出来。后端已实现接口从 4 个升到 9 个，待实现 8 个。

### 改了什么

1. `app/routers/imports.py`：`POST /api/imports`、`GET /api/imports/{id}`、
   `GET /api/imports/{id}/original`、`POST /api/imports/{id}/retry`、
   `POST /api/imports/{id}/confirm`。
2. `app/services/imports.py`：批次状态机、幂等、去重、确认入账的单事务实现。
3. `app/services/worker.py`：后台批次执行器（线程 + 条件 UPDATE 原子认领 + 超时巡检 + 重启恢复）。
4. `app/services/dedupe.py`：去重摘要与月份归属的唯一口径（处理阶段与确认阶段共用同一算法）。
5. `app/config.py` 新增 6 个可调项（全部有安全默认值，不设也能跑）：
   `UPLOAD_MAX_FILE_BYTES`(10MiB) / `UPLOAD_MAX_IMAGE_BYTES`(5MiB) /
   `BATCH_DEADLINE_SECONDS`(300) / `BATCH_DRAFT_TTL_HOURS`(24) /
   `IMPORT_WORKER_ENABLED`(true) / `IMPORT_WORKER_POLL_SECONDS`(0.5)。
6. `app/main.py`：注册路由；lifespan 里启动/停止 worker（取不到智能实现则**启动即失败**，
   不自动降级）；`strip_unreachable_422` 摘掉纯字符串路径参数端点里"永不可能发生"的 422 声明。
7. `tools/check_implemented_contract.py`：带请求体的端点若多出契约未写的 422，记 `[注意]`
   而不是失败（见下方"契约待补"）。

### 状态机与事务（照 docs/13 实现，逐条对应）

```
uploaded → processing → pending_review → completed
                ↓              ↓
              failed ←─────────┘（failed 可 retry 回到 uploaded）
```

- **认领**用条件 UPDATE（`WHERE status='uploaded'`，`rowcount==1` 才算抢到），不是读后改，
  多进程下不会重复处理同一批次。
- **确认入账**顺序固定：① 查幂等（同 `request_id` 同体 → 解密返回当时快照；同 ID 异体 → 409
  `IDEMPOTENCY_CONFLICT`）② 校验 `pending_review` + 未过期 ③ 校验 `expected_version`
  ④ 逐行重校验（未知 `row_id`、无时区时间、空商户、疑似重复未显式允许 → 422 且整体回滚）
  ⑤ 算去重摘要、撞唯一约束的行跳过计数 ⑥ 写 `transactions` ⑦ 批次转 `completed` + version+1
  ⑧ 存加密响应快照供重放。
- 去重摘要**包含事件性质**（`flow_type`）：`SYN-ORDER-1` 那种"同订单一笔支出 + 一笔退款"
  不会被误合并。没有可靠事件号时退化为内容指纹（平台 + 方向 + 上海时区自然日 + 金额 +
  标准化商户 + 说明），不冒充唯一事件号。
- `SELECT FOR UPDATE` 只在 PostgreSQL 生效；SQLite 下 SQLAlchemy 自动省略该子句（本地开发库），
  已写进代码注释。

### 实测证据（本机 Python 3.13.14）

| 命令/场景 | 实测结果 |
| --- | --- |
| `python -m unittest discover -s tests` | **100 项全部通过**（新增 `tests/test_imports_api.py` 26 项） |
| 真实 uvicorn 全链路（127.0.0.1:8011） | 登录 200 → 上传 `202` + `Location: /api/imports/<id>` + `Retry-After: 1` → 第 3 次轮询转 `pending_review`（6 条草稿）→ 原文件回读 1577 字节、`text/csv`、与上传字节完全一致 → 确认 `created_count=6` → 同 `request_id` 重放响应逐字段相同 → 批次 `completed` v4 |
| 重启恢复（真实进程） | 人为把批次置 `processing` → 强杀进程 → 重启 → `GET` 返回 `failed` v3 + `BATCH_INTERRUPTED`「服务重启中断了本次处理，请点击重试」，retry 通道打开 |
| `python tools/check_implemented_contract.py` | 已实现 **9** 个接口，字段与契约一致；待实现 8 个；1 条 `[注意]`（retry 的 422，见下） |
| 边界 | 超限 → 413；`.pdf` → 415；PDF 改名 `.csv`（魔数不符）→ 415；0 字节 → 422 `EMPTY_FILE`；别人的批次 → 404；`pending_review` 批次 retry → 409 `BATCH_STATE_CONFLICT`；旧版本 confirm → 409 `VERSION_CONFLICT` 且回带 `current_version` |

### 三条需要全员知道的约定

1. **草稿有效期 24 小时**（`BATCH_DRAFT_TTL_HOURS`）。契约里有 `Batch.expires_at` 但没写时长，
   这里定为 24h：过期后 `confirm` 返回 409 `BATCH_STATE_CONFLICT`「批次草稿已过期，请重新上传」，
   `GET` 仍可读，不会突然消失。要改时长请一起调这个环境变量，别在代码里另写一份。
2. **疑似重复必须显式允许**。草稿 `duplicate_status=suspected` 若 `allow_suspected_duplicate=false`，
   确认返回 422 且 `details.fields[].code=SUSPECTED_DUPLICATE_NOT_ALLOWED`——不静默入账，
   也不静默丢弃。F 需要在确认页对这类行弹二次确认再置 true。
3. **新增 Issue 机器码**（后端产生，已补进 docs/20 第四节）：`DUPLICATE_EXISTING`、
   `NO_ROWS_PARSED`、`DRAFT_UNREADABLE`；批次级失败码 `BATCH_TIMEOUT`、`BATCH_INTERRUPTED`、
   `BATCH_EXPIRED`、`CRYPTO_FAILED`。

### 契约待补（不阻塞，但要一起定）

`retryImport` 的请求体 `RetryInput.expected_version` 是必填正整数，格式非法时后端确实返回 422，
但契约的 retry 只列了 401/403/404/409。这是契约漏写，不是实现写错。为不改版本号、不逼 F 重新
生成 SDK，本次在检查工具里记 `[注意]`。**建议 0.2.x 补上这一个响应码**，由 H 与 F 一起拍板，
走共同变更流程后再改 `contracts/openapi.json` 并重新生成 SDK。

### 已知限制（写清楚，别当成已完成）

- **重启恢复假设单进程**。启动时会把所有 `processing` 批次判 `failed(BATCH_INTERRUPTED)`。
  如果以后要跑多个后端副本，必须改成"按 `started_at` 超时"（`worker.sweep()` 已经是这种写法，
  复用它即可），否则副本 A 启动会杀掉副本 B 正在跑的批次。
- **平台错标不回写**。用户把支付宝文件标成微信时，解析器能按表头认出来并照常解析，
  但 `Batch.source` 仍以用户声明为准，去重也按声明平台计算。是否需要回写成真实平台，
  等真实账单样本到了再定（真实样本目前仍为零，这是全队最大外部依赖）。
- **截图链路未通**。`ingestion_method=screenshot` 走的是 `recognize_bill_image`，
  当前 fallback 抛 `OCR_UNAVAILABLE` → 批次 `failed`，原因如实回显。上传、限额、魔数校验已就绪，
  D 的 OCR 一到位即可用。
- **原件存在库里**（`encrypted_original`，AES-GCM）。10MiB 上限下可接受，PostgreSQL 靠 TOAST 消化；
  若以后放宽限额，要改成对象存储 + 独立密钥，别继续往行里塞。

---

## CHG-005（2026-11-10 晚）：账单列表/纠错、月报、预算 4 个接口 + 5 处契约偏差修正

契约版本不变（0.2.0），**没有改任何字段名或状态码语义**。已实现接口从 9 个升到
**13 个**，待实现 4 个（分类规则 2 个、导出 2 个）。

### 一、新增的 4 个接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/transactions` | 按日期/类别/平台/流向筛选 + 分页，只返回本人已确认交易 |
| `PATCH /api/transactions/{id}` | 改字段；显式改类别标 manual；`remember_rule` 同时沉淀个人规则 |
| `GET /api/reports/monthly` | 月报，直接调 `services/reporting`，不重复计算 |
| `PUT /api/budgets` | 按（用户, 月份, 类别）覆盖写入，始终 200 |

新增文件：`services/transactions.py`、`services/budgets.py`、`routers/transactions.py`、
`routers/reports.py`、`routers/budgets.py`、`tests/test_ledger_api.py`（38 项）。

### 二、核对字段时发现的 5 个真实偏差（这才是本轮最该记的部分）

**1. 错误码名字和契约不一致 —— 前端所有错误分支都会失效。**

| 位置 | 原来写 | 契约要求 | 后果 |
| --- | --- | --- | --- |
| 所有 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` | `AUTH_REQUIRED` | 前端 `if (code === 'AUTH_REQUIRED') 跳登录` 永远不命中，401 时页面卡住 |
| 所有 403 | `CSRF_TOKEN_INVALID` | `CSRF_INVALID` | CSRF 失效时的重取令牌逻辑不触发 |
| 所有 422 | `VALIDATION_FAILED` | `VALIDATION_ERROR` | 表单标红逻辑不触发，用户只看到"提交失败" |
| 登录失败 | `INVALID_CREDENTIALS` | `AUTH_INVALID` | 登录页无法区分"密码错"与其他错误 |

已全部改为契约值（`app/deps.py`、`app/errors.py`、`app/routers/auth.py`），并同步
7 处测试断言。`docs/16` 第 53 行原文写的 `CSRF_TOKEN_INVALID` 是笔误，一并修正。
**这是 T00 遗留问题，不影响已有数据的正确性，但会让 F 的页面调试多绕好几天。**

**2. 422 的 OpenAPI 文档结构与实际返回不一致。**
实现层早就把 `RequestValidationError` 转成了 `{"error": {...}}`，但 FastAPI 生成的
OpenAPI 仍在按默认的 `{"detail": [...]}` 描述 422。F 如果按文档生成类型，422 分支
拿到的字段全是 `undefined`。已在 `main.py` 加 `normalize_error_schema()` 统一指向
`Error`，检查工具不再报 `缺字段 ['error']，多字段 ['detail']`。

**3. 新路由必须显式声明非 2xx 响应，否则生成的 SDK 里没有错误分支。**
`responses={401: _ERR, 403: _ERR, ...}` 逐个补上。契约声明了但实现没声明时，检查
工具会报 `[注意] 契约声明但暂未实现的响应码`——那不是"没实现"，而是"文档没写"，
两者都要改。

**4. 入账时没保存分类来源，列表接口无法如实返回。**
契约里 `Transaction.classification_source` 和 `classification_reason` 都是必填，但 T02
入账时只存了 `TransactionInput`（8 个字段），这两项根本没落库。补齐方式：
- 确认入账时把草稿的分类来源一并写入加密区；
- 用户确认时改了类别的，标 `manual` + "用户确认时修正分类"；
- 同时存入 `ingestion_method`，避免列表为了一个字段去 join 批次表。

存量记录（CHG-004 之前入账的）没有这两项，接口**如实返回 `pending` + "该记录入账时
未保存分类来源"**，不拿当前规则补记一个当时并不存在的来源。目前真实数据为零，
这条影响范围就是 `seed_demo` 的历史副本。

**5. 合并 patch 时枚举没转字符串，会把 `"Category.dining"` 写进加密区。**
`_merge_changes()` 原来只处理 `datetime`，`Category`/`FlowType` 枚举原样塞回载荷。
结果：分类统计整块归到"未知类别"，而且因为脏值在加密区里，SQL 也查不出来——
属于"不报错但数据悄悄坏掉"的那类 bug。已统一取 `.value`（`tests` 里
`test_patch_remember_rule_creates_personal_rule` 抓到了它）。

### 三、三个有意为之的设计决定（别当成漏了）

1. **编辑后不重算 `dedupe_digest`。** 它标识的是"这次导入的哪一行"，不是内容哈希。
   用户改完金额就重算，等于把原记录的去重身份换掉，同一份账单再导入一次会重新
   进账——比"改错了改回来"危险得多。
2. **`spent_fen` 用净支出，可以为负。** 某类别只发生退款时 `spent_fen = -5`，
   符合契约"退款跨月时可以为负"和"这个月还能花多少"的直觉（A10）。
3. **提交内容与原值完全相同时 `version` 不递增。** 改了又改回原值不该让前端手里的
   `expected_version` 失效。但 `remember_rule=true` 时即使交易字段没变，规则照建
   ——用户点的就是"记住商户"，不能因为类别本来就对而静默吞掉。

### 四、实测证据（本机 Python 3.13.14）

| 命令/场景 | 实测结果 |
| --- | --- |
| `python -m unittest discover -s tests` | **138 项全部通过**（100 + 新增 38） |
| `python tools/check_implemented_contract.py` | 已实现 **13** 个，字段与契约一致；待实现 4 个；1 条 `[注意]`（retryImport 的 422，仍待 0.2.x 补） |
| 真实 uvicorn（127.0.0.1:8021，seed_demo 6 笔） | 列表 6 条倒序正确（16:00→09:00）；`category=dining`→2、`source=alipay`→3、单日 11-08→6；`page=2&page_size=2`→total 仍 6；反向区间→422 `DATE_RANGE_REVERSED` |
| 月报口径 | 收入 100.00 / 毛支出 42.00 / 退款 5.00 / 净支出 37.00 / 差额 63.00，与 `seed_demo` 独立核对结果逐项一致；日趋势 30 天全给出，仅 11-08 有值 |
| 纠错联动 | 把 `dining 30.00` 改为 `transport` 并记住商户 → 200、`manual`、v1→v2；月报分类构成立刻变 `[transport 30, other 12]`，毛支出仍 42.00（改类别不改金额）；`?category=transport` 立即查得到 |
| 乐观锁 | 用旧 `expected_version=1` 再改 → 409 `VERSION_CONFLICT`，`details.current_version=2` |
| 预算 | `PUT` 覆盖同一 ID 不新建；`pending` 类别 → 422；`amount_fen=0` 允许；`dining` 预算 50 元、当月只剩 5 元退款 → `spent_fen=-5.00`、`remaining=55.00` |

### 五、已知限制（写清楚，不当成已完成）

- **列表和月报是全量解密后在内存里过滤、排序、分页。** 因为日期、金额、商户都在
  加密区，SQL 层只能过滤月份/类别/流向/平台这些明文索引列。个人规模（万级以内）
  没问题；数据量再涨要改成独立存储或加明文日期索引，**不能**假装能在加密列上
  SQL 排序。这是任务书第四节「接口字段和数据库的加密存储表示不同」里明确的取舍。
- **个人规则匹配是 O(规则数) 次解密。** 规则表没有明文商户列（匹配条件本身是敏感
  信息，docs/13 要求保护）。规则通常几十条，可接受；上千条要另想办法。
- **`import_batch_id` 在批次被删除后返回空串。** 契约该字段不可空，又没有"未知"的
  表示法，只能给空串。F 不要拿它做"是否来自导入"的判断。
- **金额精度只到分，不接受更多小数位**，这是契约 0.2.0 的既定口径，本轮没动。

---

## CHG-006（2026-11-10 夜）：规则读写 + 两个导出，契约 17/17 全部落地

**契约版本不变（0.2.0），没有改任何字段名、状态码或错误码语义。**
后端已实现接口从 13 个升到 **17 个，待实现 0 个**。这是后端功能面的收口提交。

### 一、新增的 4 个接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/classification-rules` | 本人全部规则（**含已停用**），按 `source` 再 `merchant_normalized` 升序 |
| `PATCH /api/classification-rules/{id}` | 改类别或停用/启用；停用**不重写**历史交易 |
| `GET /api/exports/transactions.csv` | 与筛选范围一致的账单 CSV，不限分页，防公式注入 |
| `GET /api/exports/monthly.pdf` | 与月报同口径的中文 PDF，字体真嵌入 |

新增文件：`app/services/rules.py`、`app/services/exporting.py`、`app/routers/rules.py`、
`app/routers/exports.py`、`app/http_utils.py`、`backend/tests/test_rules_and_exports.py`（24 项）。

### 二、闭环第五环终于闭合（这是本轮真正的目的）

之前的状态：用户能"记住商户"，新交易也能命中规则，但**规则停不掉**——
`patchRule` 不存在，docs/08 A07 四步只能走三步，等于反馈闭环是假闭合。

现在 A07 四步在真实 HTTP 全链路下逐条验证通过（`test_a07_full_loop`）：

```
导入「瑞幸咖啡」→ 通用规则判 dining (general_rule)
  → 用户改成 transport + 记住商户 → manual，规则落库 (wechat / 瑞幸咖啡 / transport)
  → 再导入同商户新交易 → transport (user_rule)   ← 个人规则优先
  → 停用规则 → 第三笔回落 dining (general_rule)   ← 停用真的生效
  → 已入账的前两笔类别不变                        ← 停用不重写历史
```

### 三、五个值得记下的实现决定

**1. `enabled` 以明文列为唯一真相，加密区只做同步。**
`classification_rules.enabled` 是明文布尔列——导入时要在 SQL 层筛 `enabled IS TRUE`，
不可能为它解密整张表。加密区里也存了一份 `enabled`（历史遗留），写入时同步，
但**读取一律以明文列为准**，避免两处水位漂移时不知道该信谁。

**2. 空 patch 必须由服务层拦。**
契约用 `anyOf` 要求"至少提供 enabled 或 category"，但 Pydantic 模型两个字段都是
`Optional`，空请求能过模型校验。不补这条检查，`{"expected_version": 1}` 会被当成
"什么都没改"悄悄返回 200。现在返回 422 `VALIDATION_ERROR` + 字段码 `RULE_PATCH_EMPTY`。

**3. CSV 导出的筛选与列表**共用同一份实现**。**
`filtered_rows()` 从 `list_transactions` 里抽出来，导出调它、列表也调它。
导出若自己再写一套筛选，迟早出现"页面 12 条、CSV 15 条"这种谁也说不清的问题
（docs/08 A11 明确要求两者一致）。导出只是"不分页地取全量"，筛选逻辑零复制。

**4. CSV 防公式注入不是可选项。**
以 `=` `+` `-` `@` `\t` `\r` 开头的文本单元格，Excel 打开时当公式执行——
商户名里塞一句 `=cmd|'/c calc'!A1` 就能在别人机器上跑命令。导出时统一前置单引号，
`=1+1` 变成 `'=1+1`。金额列是整数分，不是文本，不加引号也不受影响。
已用四个恶意商户名逐条验证，同时验证正常商户（"永辉超市"）不会被误加引号。

**5. PDF 找不到中文字体就 503，不输出方块。**
契约本来就声明了 503 `EXPORT_UNAVAILABLE` 这个分支，这不是"没做完"的借口，
而是"渲染依赖缺失时的正确行为"。所以：
- `pdf_font_path` 留空时按内置候选列表搜索（Windows 找 simhei/msyh，Linux 找文泉驿）；
- 全部找不到 → 503，日志说明原因；
- 找到就**真嵌入**（PDF 里能查到 `FontFile2` 与 `ToUnicode`，不是只设了个字体名）。

容器里特意装 `fonts-wqy-zenhei` 而不是 `fonts-noto-cjk`：**reportlab 只能嵌
TrueType 轮廓，Noto CJK 是 CFF/OTF，加载会直接失败**。这个坑不写下来下一个人一定踩。

### 四、实测证据（本机 Python 3.13.14，真实 uvicorn，非只有 TestClient）

| 命令/场景 | 实测结果 |
| --- | --- |
| `python -m unittest discover -s tests` | **162 项全部通过**（138 + 新增 24） |
| `python tools/check_implemented_contract.py` | 已实现 **17** 个，字段与契约一致；**待实现 0**；1 条 `[注意]`（retryImport 的 422，仍待 0.2.x 补） |
| 规则列表 | 空库返回 `{"items": []}`；含停用项时按 `(source, merchant_normalized)` 升序；他人规则不出现 |
| 规则修改 | 停用 200 且 `version` 1→2；重新启用 200 且 →3；改类别 200；空 patch 422 `RULE_PATCH_EMPTY`；`category=pending` 422；旧版本 409 `VERSION_CONFLICT` + `current_version: 2`；他人规则 404；无 CSRF 403 `CSRF_INVALID` |
| CSV 导出（真实进程） | 200、`text/csv; charset=utf-8`、`Content-Disposition` 含 RFC5987 中文名；819 字节；**首 3 字节为 UTF-8 BOM**；表头 10 列含 `amount_fen`；6 条数据行 |
| CSV 范围一致性 | `category=dining` 时列表 `total=1`、CSV 数据行 1，**逐数一致**；`page=1&page_size=1` 仍导出 3 行（不被分页截断） |
| CSV 防注入 | `=1+1`/`+SUM(A1)`/`-2+3`/`@SUM(1)` 四种商户名全部被前置单引号；`永辉超市` 未被误加 |
| PDF 导出（真实进程） | 200、`application/pdf`、19,681 字节；`%PDF-` 开头；含 `FontFile2` 与 `ToUnicode`；字体为 `AAAAAA+SimHei` 子集 |
| PDF 内容（pymupdf 提取 + 渲染核对） | 中文完整可读：「2026 年 11 月收支月报」「收支合计」「支出分类构成」「每日支出趋势」「预算执行」；数字 100.00 / 42.00 / 5.00 / 37.00 / 63.00 与 `GET /api/reports/monthly` 逐项相同；分类名显示「交通/购物/餐饮」而不是 `transport/shopping/dining` |
| PDF 字体缺失 | 清空候选列表 → 503 `EXPORT_UNAVAILABLE`，日志写明"找不到可嵌入的中文字体" |
| 未登录 | CSV 与 PDF 都是 401 `AUTH_REQUIRED` |

### 五、CSV 列定义（给 F 与后续导出）

```
occurred_at, source, flow_type, category, amount_fen, currency,
merchant, description, classification_source, source_transaction_id
```

- `amount_fen` 是**整数分**，不是元；列名带 `_fen` 就是为了让下游不用猜。
- 文件编码是 **UTF-8 带 BOM**：不加 BOM 时 Excel 双击打开中文商户名会乱码。
  **程序化解析请用 `utf-8-sig` 解码**，否则第一列名会带一个不可见字符。
- 时间列是 ISO 8601 带偏移（`2026-11-08T16:00:00+08:00`），不是本地化字符串。
- 导出不按 `page/page_size` 截断，传了也忽略。

### 六、已知限制（写清楚，别当成已完成）

- **CSV 导出是全量解密后在内存里筛**。个人规模（万级以内）没问题；`EXPORT_MAX_ROWS`
  默认 5 万行，超限返回 422 并提示缩小日期范围，**不悄悄截断**。数据量再涨要改成
  流式解密或独立存储，不能在加密列上假装能 SQL 排序。
- **PDF 只有单页、不分页**。分类/预算/趋势条目多时会挤在一页里；真实数据若类别很多
  要加分页逻辑。目前 `reportlab` 没有做 platypus 流式排版，是刻意选简单方案。
- **PDF 的"可视化"只有分类横向条形图**，没有饼图。任务书要求饼图/柱状图主要在
  **页面端**（`expense_by_category` / `daily_trend` 都已提供数据，F 用 ECharts 画即可）；
  PDF 作为纸质附件，条形图已够表达构成。
- **规则排序需要解密全部规则**（商户名在加密区）。几十条无感，上千条要另想办法。
- **`_upsert_rule` 重新"记住"会把已停用规则重新启用并 `version+1`**。这是用户主动
  操作，语义上正确（"记住商户"就是要求它生效），但 F 的规则页如果正开着同一规则，
  会拿到 409，应刷新而不是重试。

---

## CHG-007（2026-11-10 夜）：补 `reportlab` 依赖声明 + 交付文档 22/23

**契约版本不变（0.2.0），不改任何接口、字段、状态码。** 这是"后端收尾文档化"时
发现的依赖缺口修复，加上给评审与 F 的两份交付文档。

### 一、修了什么

`services/exporting.py` 依赖 `reportlab` 生成月报 PDF，但 `backend/requirements.txt`
**漏了这一行**。后果很具体：干净环境（尤其 `Dockerfile` 只 `pip install -r requirements.txt`）
里 `GET /api/exports/monthly.pdf` 会永久返回 503 `EXPORT_UNAVAILABLE`——
本该是"字体/渲染依赖临时缺失"的诚实失败，变成"部署包少一个依赖"的常态故障。

- 已在 `backend/requirements.txt` 补 `reportlab>=4.0,<5`（放在 `openpyxl` 之后，带注释说明用途）。
- 本机安装 `reportlab 4.5.1` 后重跑全量测试：**162 项 OK**（此前 159 通过 3 失败，失败项正是 PDF 三例）。
- `Dockerfile` 无需改动：它本来就 `COPY requirements.txt` 后整体安装，补了声明即生效。

### 二、新增文档

| 文件 | 用途 |
| --- | --- |
| `docs/22_backend_delivery_summary.md` | 后端交付总结：17 个接口的请求/返回字段、枚举字典、错误码总表、业务不变量、测试证据、已知边界 |
| `docs/23_frontend_development_guide.md` | 前端开发文档 + 任务单：工程搭建、接口层封装、六个页面规格、A07 演示链路、F-01~F-12 任务与验收 |

两份文档的字段与错误码均按 `contracts/openapi.json` 0.2.0 与 `backend/app` 实现逐条核对，
"契约声明但实现未触发"的分支（如 `login` 的 403）已在文中标注，不做修饰。

### 三、给 F 的三条硬约束（写进 23，这里再强调一次）

1. **必须走 Vite 代理**。会话 Cookie 是 `HttpOnly + SameSite=Lax`，直连 8000 端口会出现
   "登录成功、下一请求 401"。
2. **错误只能按 `error.code` 分支**，不许匹配中文 `message`。
3. **金额全程整数分**：`Number(x) * 100` 会差 1 分，必须用字符串解析转换。
