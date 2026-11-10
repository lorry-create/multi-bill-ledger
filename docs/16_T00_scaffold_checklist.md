# T00 骨架落地清单（目标：半天内让 F 和 D 能开工）

写这份清单的原因很直接：`docs/04` 和 `docs/05` 两份任务书质量够高，但队友今天 clone 下来会发现：

- F 没有 `frontend/` 工程，也没有 `frontend/src/api/`，拿不到 `client.generated.ts`，五个页面无从落笔；
- D 没有 `backend/app/contracts.py`，无法 `from app.contracts import ParseResult`，只能自己造一遍字段，直接违反 AGENTS 第 7 条。

所以 **T00 不是"队长自己的第一张卡"，它是两个队友的开工许可**。在这份骨架上花的两小时，等于把两条并行开发线解锁。骨架不做完就催队友开工，他们只能写空页面和自造 DTO，后面全部要返工。

## 已经替你做完的部分

`tools/gen_pydantic_models.py` 已新增并实测通过，直接从 `contracts/openapi.json` 生成 `backend/app/contracts.py`：

| 项目 | 实测结果 |
| --- | --- |
| 生成规模 | 463 行、39 个导出符号（7 个枚举 + 32 个模型，含内联子模型） |
| 契约对齐 | 35 个 schema 全覆盖，`CONTRACT_VERSION = "0.2.0"` |
| 负向校验 | 字符串金额、浮点金额、越界类别、零金额、非 CNY、非法流向、非法来源 **7 项全部拒绝** |
| 金额严格性 | `*_fen` 字段生成为 `StrictInt`，`"2300"` 与 `2300.0` 都不接受，避免静默转换 |
| 枚举一致性 | 内联枚举自动复用同名顶层枚举，`flow_type` 与 `status` 不会出现两种写法 |
| 幂等 | `--check` 重复执行输出一致，可直接进 CI |
| CI | `contract-check.yml` 已加 "Reject Pydantic model drift" 一步 |

这解决了 D 最容易被卡住的点：**他拿到的是可直接 import 的共用模型，而不是一份需要自己抄的字段表。**

## 前置检查（5 分钟，别跳过）

```bash
export PATH="/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:$PATH"

docker version --format '{{.Server.Version}}'   # 有输出才走 Compose 起 PostgreSQL
python --version                                 # 期望 3.13.x；本机实测 3.13.14
node --version                                   # 目标 22.x
```

两个结论要当场记下来，写进当天的同步记录：

1. **团队统一 Python 3.13 系列，不再装 3.12**（变更记录见 `docs/10_change_delivery.md` CHG-001，AGENTS 第 8 行、03 T00、CI 均已同步）。下限 3.13.7，基线 3.13.14。FastAPI + SQLAlchemy + psycopg 在 3.13 上没问题，锁文件以实际安装为准。
   **看版本要看 `python --version` 的输出，不要看安装目录名**：本机托管解释器目录仍叫 `versions/3.13.12`，`--version` 实际输出 `3.13.14`（已被自动升级）。按目录名判断会把版本记错，写进同步记录就是假证据。把 `--version` 的实际输出连同 node 版本一起记进当天同步记录。
2. **Docker 若不可用**，今天先用 SQLite 把 `/health` 和登录跑通，但要在同步记录里写明"临时"，并在 **11 月 12 日前**切回 PostgreSQL。不要拖到 11 月 16 日部署那天才发现数据库换不过来。

## 目标目录树

```text
multi-bill-ledger/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── contracts.py          # 生成物，禁止手改
│   │   ├── config.py             # 环境变量读取，密钥从这里进
│   │   ├── db.py                 # 引擎与会话
│   │   ├── main.py               # FastAPI 实例，/health
│   │   ├── api/                  # H：路由（先只挂 health + auth）
│   │   ├── services/             # H：入账、统计、导出
│   │   ├── models/               # H：数据库映射
│   │   └── intelligence/         # D 的工作区，今天建空目录即可
│   ├── tests/
│   │   ├── integration/          # H
│   │   └── intelligence/         # D
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── api/                  # 生成 SDK 落位处，建好目录生成器才会同步
│   │   ├── pages/
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts            # /api 代理到 8000
├── deploy/
│   └── docker-compose.yml
├── contracts/                    # 已有
├── tools/                        # 已有，新增 gen_pydantic_models.py
├── docs/                         # 已有
└── fixtures/synthetic_ledger.json
```

## 六步执行

### 步骤 1 · 生成共用模型（2 分钟）

```bash
cd 团队协作开发包     # 实际仓库根目录
python tools/gen_pydantic_models.py            # 生成 backend/app/contracts.py
python tools/gen_pydantic_models.py --check    # 应输出 OK，生成物与契约一致
```

验收：`backend/app/contracts.py` 存在且 463 行左右；`CONTRACT_VERSION == "0.2.0"`。

### 步骤 2 · 后端最小可跑（30 分钟）

```bash
python -m venv .venv
source .venv/Scripts/activate          # Windows Git Bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY   # 本机代理会卡住 pip
pip install -i https://mirrors.aliyun.com/pypi/simple/ \
  fastapi "uvicorn[standard]" sqlalchemy alembic "psycopg[binary]" \
  pydantic-settings python-multipart cryptography pytest httpx
pip freeze > backend/requirements.txt
```

`backend/app/main.py` 只做三件事：创建 app、注册 `/health`、返回契约里 `health` 操作定义的响应形状。

```bash
cd backend && uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

验收：`/health` 返回 200，字段形状与 `contracts/examples.json` 里 `health` 的 case 一致；**不返回密钥和交易内容**。

### 步骤 3 · 前端工程 + SDK 落位（30 分钟）

```bash
cd ..
npm create vite@latest frontend -- --template vue-ts
cd frontend && npm install
mkdir -p src/api                      # 必须先建，生成器才往这里同步
cd .. && python tools/generate_contract_artifacts.py
python tools/generate_contract_artifacts.py --check
```

`vite.config.ts` 加同源代理，避免带凭据跨域：

```ts
server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } }
```

验收：`frontend/src/api/client.generated.ts` 里有 19 个导出函数；`npm run build` 通过。

### 步骤 4 · 数据库与迁移骨架（40 分钟）

**有 Docker：**

```bash
docker run -d --name ledger-pg -e POSTGRES_PASSWORD=devonly -p 5432:5432 postgres:16
```

**无 Docker：** 今天先 `DATABASE_URL=sqlite:///./dev.db`，同步记录里标明临时。

建 `alembic` 初始迁移，只建 `users` 一张表（其余表等 T02 再迁，不要一次建完六张表然后没人敢改）。

验收：`alembic upgrade head` 成功；重启后表还在。

### 步骤 5 · 演示用户与 seed_demo（20 分钟）

```bash
cd backend && python -m app.seed_demo     # 只导入 fixtures/synthetic_ledger.json 六笔合成账目
```

两个演示用户，密码走成熟哈希（argon2 或 bcrypt），**初始化命令不允许默认创建弱口令**。把账号写进 `docs/` 的演示说明，不要写进仓库明文配置文件。

验收：两个用户能登录；`GET /api/auth/me` 返回 `user` 和 `csrf_token`；用户 A 访问用户 B 的资源返回 404。

### 步骤 6 · 推分支 + 发通知（10 分钟）

```bash
git checkout -b task/T00-baseline
git add backend/app/contracts.py tools/gen_pydantic_models.py .github/workflows/contract-check.yml
git commit -m "T00: 共用模型生成器与最小骨架"
git push -u origin task/T00-baseline
```

PR 描述里必须写：任务号 T00、契约版本 0.2.0、实际执行的命令与结果、哪些是骨架哪些还没实现。

## T00 今天就做到这里，不要往下做

| 属于 T00 | 不属于 T00（今天别碰） |
| --- | --- |
| 目录、共用模型、`/health`、登录/me/logout、迁移骨架、演示用户、seed_demo、Compose 骨架、CI 跑通 | 上传接口、解析器、分类、OCR、报表、图表、PDF、加密、备份恢复 |

理由：`/api/imports` 一旦动手就必须同时定状态机、幂等、去重，那是 T02 的完整工作量。今天只交付"能启动、能登录、能拿到共用模型"，队友就能并行。

## 交接给队友时发这两句

给 F：

> 骨架已推 `task/T00-baseline`。你 clone 后 `cd frontend && npm i && npm run dev`，`src/api/client.generated.ts` 里 19 个函数直接用。今天只做登录、上传、预览确认三页，接口先走 `src/api/mock.ts`，明后天切真后端。任务看 `docs/17_F_首日开工卡.md`。

给 D：

> 骨架已推 `task/T00-baseline`。`backend/app/contracts.py` 已按契约生成，直接 `from app.contracts import ParseResult, TransactionDraft, ClassificationResult`，别另定义字段。你的工作区 `backend/app/intelligence/`，测试在 `backend/tests/intelligence/`。今天只做支付宝 CSV 解析 + 通用规则分类，任务看 `docs/18_D_首日开工卡.md`。

## 本机已知坑（踩过的）

| 现象 | 处理 |
| --- | --- |
| `dirname: command not found` 一片红 | 命令前 `export PATH="/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:$PATH"` |
| `pip install` 卡几分钟无输出或报 `No matching distribution` | `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`，并用阿里云镜像 |
| 传给 `python.exe` 的路径写成 `/c/...` | 改成 `C:/...`，Git Bash 会把 `/c` 变成 `c:\c` |
| `taskkill` 报无效参数 | 前面加 `MSYS_NO_PATHCONV=1` |
| 大 wheel 下载被守卫中断 | 从阿里云镜像 `curl -O` 直下，再 `pip install --no-index 本地.whl` |
