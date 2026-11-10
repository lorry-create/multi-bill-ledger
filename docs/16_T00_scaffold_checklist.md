# T00 骨架落地清单（状态：已完成并实测，2026-11-10 14:55）

写这份清单的原因很直接：`docs/04` 和 `docs/05` 两份任务书质量够高，但队友当天 clone 下来会发现：

- F 没有 `frontend/` 工程，也没有 `frontend/src/api/`，拿不到 `client.generated.ts`，五个页面无从落笔；
- D 没有 `backend/app/contracts.py`，无法 `from app.contracts import ParseResult`，只能自己造一遍字段，直接违反 AGENTS 第 7 条。

所以 **T00 不是"队长自己的第一张卡"，它是两个队友的开工许可**。骨架不做完就催队友开工，他们只能写空页面和自造 DTO，后面全部要返工。

## 一、当前状态：能启动、能登录、能拿到共用模型

| 项目 | 实测结果 | 复现命令 |
| --- | --- | --- |
| 建表 | 8 张表，`schema_migrations` 记录 001，checksum `c64a885bf3a0` | `python -m app.migrate` |
| 结构校验 | 表齐全 + checksum 一致，重复执行幂等 | `python -m app.migrate --check` |
| 演示数据 | 6 笔合成账 + 2 条预算；解密回读合计与 `fixtures.expected` 完全一致 | `python -m app.seed_demo --username demo_a --password ...` |
| 端到端 | 9 个 unittest 全过（登录、CSRF、422 结构、429 锁定、登出失效） | `python -m unittest discover -s tests -v` |
| 契约对齐 | 已实现 4 / 17 个接口，字段与 `contracts/openapi.json` 一致 | `python ../tools/check_implemented_contract.py` |
| 共用模型 | 463 行、39 个符号，7 项负向用例全部拒绝 | `python ../tools/gen_pydantic_models.py --check` |

已实现接口：`GET /health`、`POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout`。
**其余 13 个接口仍未实现**，不要误读为"后端做完了"。

## 二、五步复现（新机器从零到能登录）

```bash
export PATH="/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:$PATH"
python --version            # 期望 3.13.x，本机实测 3.13.14；不要看目录名

cd 团队协作开发包
python -m venv .venv && source .venv/Scripts/activate
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY          # 本机代理会卡住 pip
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r backend/requirements-dev.txt

python tools/gen_pydantic_models.py                # 生成 backend/app/contracts.py
cd backend
python -m app.migrate                              # 建表 + 记录版本
python -m app.seed_demo --username demo_a --password 你的密码   # 导入合成数据并核对金额
python -m unittest discover -s tests -v            # 9 项应全绿
python -m uvicorn app.main:app --reload --port 8000
```

另开一个终端验证：

```bash
curl -s http://127.0.0.1:8000/health                      # {"status":"ok"}
curl -s -c c.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_a","password":"你的密码"}'          # 返回 user + csrf_token
curl -s -b c.txt http://127.0.0.1:8000/api/auth/me        # 同一会话可读回
```

写请求（登出、后续所有 POST/PATCH/PUT）必须带 `X-CSRF-Token: <csrf_token>`，否则返回 `403 CSRF_INVALID`。

## 三、实际目录树

```text
multi-bill-ledger/
├── backend/
│   ├── app/
│   │   ├── contracts.py        # 生成物，禁止手改
│   │   ├── config.py           # 环境变量；开发密钥落 local-data/dev_secrets.json
│   │   ├── crypto.py           # AES-256-GCM 字段加密 + HMAC 去重摘要
│   │   ├── security.py         # scrypt 密码哈希、令牌、恒定时间比较
│   │   ├── db.py               # 引擎、会话工厂、UTC 时间工具
│   │   ├── models.py           # 8 张表（含 user_sessions、schema_migrations）
│   │   ├── errors.py           # 统一 Error 结构；422 转 error.details.fields
│   │   ├── deps.py             # 登录态、CSRF 校验
│   │   ├── main.py             # create_app；只挂 health + auth
│   │   ├── migrate.py          # 建表 / --check / --sql / --drop
│   │   ├── seed_demo.py        # 导入合成数据并机器核对金额
│   │   └── routers/{health,auth}.py
│   ├── migrations/001_init.sql # 由模型导出的 PostgreSQL DDL（评审可读）
│   ├── tests/test_t00_smoke.py # 9 项回归，不占端口
│   ├── requirements.txt / requirements-dev.txt / Dockerfile
│   └── local-data/             # 开发 SQLite 与开发密钥，已被 .gitignore 排除
├── frontend/                   # 仍为空，由 F 建（docs/17）
├── docker-compose.yml          # PostgreSQL + api，命名卷，健康检查
├── contracts/  tools/  docs/  fixtures/   # 已有
```

## 四、与原计划的四处差异（为什么改）

| 原计划 | 实际做法 | 理由 |
| --- | --- | --- |
| Alembic 初始迁移，只建 `users` 一张表 | 不引 Alembic，由 ORM 模型建 8 张表，`--sql` 导出 PG DDL | 8 张表互相有外键，只建 1 张后每次加表都要改已有表；checksum 能直接抓漂移。少一个生成器，少一处与模型不同步的地方 |
| argon2 或 bcrypt | 标准库 `hashlib.scrypt`（n=2^14, r=8, p=1） | 不额外引入需要编译的轮子；参数随记录存储，以后调参可平滑验证旧密码 |
| 密码写进 `docs/` 演示说明 | 密码只从命令行传入，不落仓库；未传则生成一次性随机密码并打印一次 | 仓库是 public，演示口令入仓等于公开 |
| `pytest` | 标准库 `unittest` | 队友不必先装测试框架；`python -m unittest` 直接能跑 |

## 五、T00 边界（今天不要往下做）

| 属于 T00（已完成） | 不属于 T00（别碰） |
| --- | --- |
| 目录、共用模型、`/health`、登录/me/logout、建表、演示数据、Compose 骨架、CI | 上传接口、解析器、分类、OCR、报表、图表、PDF、备份恢复 |

`/api/imports` 一旦动手就必须同时定状态机、幂等、去重，那是 T02 的完整工作量。现在队友可以并行：F 用 mock 打通三页，D 用共用模型写解析与分类。

## 六、交接给队友时发这两句

给 F：

> 后端骨架已推 `task/T00-baseline`，`/api/auth/login|me|logout` 和 `/health` 已经能跑，`docs/16` 里有 curl 复现。你先建 Vite 工程，今天只做登录、上传、预览确认三页，接口先走 `src/api/mock.ts`（照 `contracts/examples.json` 抄），明后天切真后端。**记得写请求带 `X-CSRF-Token`**。任务看 `docs/17_F_first_day_card.md`。

给 D：

> `backend/app/contracts.py` 已按契约生成，直接 `from app.contracts import ParseResult, TransactionDraft, ClassificationResult`，别另定义字段。你的工作区 `backend/app/intelligence/`。今天只做支付宝 CSV 解析 + 通用规则分类，20 条金额逐笔对齐。任务看 `docs/18_D_first_day_card.md`。

## 七、本机已知坑（踩过的）

| 现象 | 处理 |
| --- | --- |
| `dirname: command not found` 一片红 | 命令前 `export PATH="/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:$PATH"` |
| `pip install` 卡几分钟无输出或报 `No matching distribution` | `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`，并用阿里云镜像 |
| 传给 `python.exe` 的路径写成 `/c/...` | 改成 `C:/...`，Git Bash 会把 `/c` 变成 `c:\c` |
| `taskkill` 报无效参数 | 前面加 `MSYS_NO_PATHCONV=1` |
| 大 wheel 下载被守卫中断 | 从阿里云镜像 `curl -O` 直下，再 `pip install --no-index 本地.whl` |
| 改完代码不生效 | uvicorn 不带 `--reload`；重启前先 `netstat -ano | findstr :8000` 找到 PID 再 `taskkill /F /PID` |
| `autoflush=False` 时同事务查不到刚插入的行 | 核对逻辑放到提交后的新 session；不要靠 `flush()` 猜时序 |
