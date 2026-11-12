# 团队代码推送接入说明（队长 / 队友各看一半）

> 适用仓库：`https://github.com/lorry-create/multi-bill-ledger`（public，默认分支 `main`，后端代码在 `task/T00-baseline`）
> 目标：让队友 F 在自己电脑上改 `frontend/` 并能 `git push` 上来，不改到别人的东西。

---

## 一、先搞清楚一件事：public ≠ 可推送

| 动作 | 是否需要对仓库授权 |
| --- | --- |
| 浏览器看代码、`git clone`、`git pull` | 不需要，public 仓库人人可读 |
| `git push` 到本仓库任何分支 | **需要**，必须被加为协作者（或持有 write 权限的凭据） |
| 提 PR（不改本仓库） | 不需要，fork 到自己名下再 PR 即可 |

所以「授权」这一步无法绕过，只能由你在 GitHub 上点。

---

## 二、队长操作：三种授权方式，先选一种

### 方式 A：添加协作者（推荐，3 人小队最省事）

1. 浏览器打开 `https://github.com/lorry-create/multi-bill-ledger`
2. 点 **Settings**（仓库自己的 Settings，不是个人账号的）
3. 左栏 **Collaborators and teams** → 点绿色按钮 **Add people**
4. 输入队友的 **GitHub 用户名**（或他注册邮箱）→ 角色选 **Write** → **Add \<name\> to this repository**
5. 队友会收到邮件 + GitHub 通知，**必须他自己点接受**：
   `https://github.com/lorry-create/multi-bill-ledger/invitations`
   或邮件里的 **View invitation → Accept invitation**

权限角色怎么选：

| 角色 | 能做什么 | 选不选 |
| --- | --- | --- |
| Read | 只能看 | 不给，clone 本来就能 |
| Triage / Maintain | 管 issue、管设置 | 不需要 |
| **Write** | 推代码到分支（含 main，除非开了保护） | **给这个** |
| Admin | 能删仓库、改设置 | **绝对不给**，包括队友 |

> 邀请发出后状态是 `Pending invite`，队友没接受之前他 push 依然 403。这一步最容易漏，一定要催他点接受。

### 方式 B：Fork + Pull Request（不想给推送权限时用）

队友 fork 到自己名下 → 推到自己仓库 → 向 `task/T00-baseline` 开 PR → 你点合并。
好处是他永远不会写坏主仓库；坏处是每轮改动都要你手动合一次，3 人小队没必要。

### 方式 C：Deploy Key（兜底，不推荐）

仓库 Settings → **Deploy keys** → Add deploy key → 勾 **Allow write access**，队友把 SSH 公钥贴上来。
问题：这是「机器级」凭据，不是你队友的个人身份，谁拿到这把钥匙都能推，**审计上分不清是谁提交的**。除非队友实在没有 GitHub 账号，否则别用。

---

## 三、队友操作：从他电脑上跑通第一条 push

### 1. 前置

- 有 GitHub 账号（没有就先注册），并已接受邀请
- 装了 Git（Windows 装 Git for Windows 自带凭据管理器 Git Credential Manager）
- 装了 Node.js 18+（跑 Vite）

### 2. 克隆并切到开发分支

```bash
git clone https://github.com/lorry-create/multi-bill-ledger.git
cd multi-bill-ledger

# 代码在 task/T00-baseline，不在 main
git checkout task/T00-baseline
```

### 3. 设成本人身份（必须，否则提交记录全是别人的名字）

```bash
git config user.name  "F的昵称"
git config user.email "F的邮箱"
git config --get user.name   # 回读确认
```

### 4. 第一次 push 怎么过认证

**推荐：用 HTTPS + 浏览器登录（凭据管理器自动存）**

```bash
git push origin task/T00-baseline
```

第一次会弹出一个窗口让你 **Sign in with your browser**，用**你自己的 GitHub 账号**登录并授权一次，之后本机就记住，不再问。

**备选：用 SSH**

```bash
ssh-keygen -t ed25519 -C "F的邮箱"           # 一路回车
cat ~/.ssh/id_ed25519.pub                     # 复制这段公钥
# 粘到 GitHub → Settings → SSH and GPG keys → New SSH key
git remote set-url origin git@github.com:lorry-create/multi-bill-ledger.git
```

### 5. 红线：不要把 token 拼进 remote 地址

```bash
# ❌ 千万别这么干
git remote set-url origin https://ghp_xxxxxxxx@github.com/lorry-create/multi-bill-ledger.git
```

`git remote -v`、报错日志、截图、录屏都会把这个 token 原样打出来，一旦泄露要立刻去
GitHub → Settings → Developer settings → Personal access tokens 撤销。**这个项目已经踩过一次。**

---

## 四、三个人怎么改不打架

### 目录归属（硬约定）

| 目录 | 谁改 | 其他人 |
| --- | --- | --- |
| `frontend/` | F | 队长、D 不碰 |
| `backend/` | 队长 | F、D 不碰，有问题提 issue 或微信说 |
| `contracts/` | 队长 | **所有人都别手改**，它由 `tools/` 生成 |
| `docs/` | 各自改自己相关的那份 | 别大改别人的 |
| `fixtures/`、`tools/` | 队长 | 只读 |

### 分支约定（二选一，队内统一）

**方案 1：F 在自己的分支上干，队长合**
```bash
git checkout -b feat/frontend        # 从 task/T00-baseline 切出
# ...开发...
git push -u origin feat/frontend     # 推上去后开 PR 到 task/T00-baseline
```
好处：F 一天推十次也不会影响你后端联调。

**方案 2：都直推 `task/T00-baseline`**
每天开工前先 `git pull --rebase`，改完立刻推。人少时更快，但要求纪律。

### 每次 push 前固定三行

```bash
git pull --rebase origin task/T00-baseline   # 先同步，避免 non-fast-forward
git status                                    # 看清自己要提交什么
git add frontend && git commit -m "feat(frontend): 登录页接通 /api/auth/login"
```

> 别用 `git add -A` / `git add .` 在仓库根目录扫全量——容易把本地临时文件、
> `backend/local-data/`、日志一起提上去。只 `git add` 你自己那个目录。

---

## 五、报错对照表（队友 push 失败时先查这张表）

| 报错关键字 | 真实原因 | 处理 |
| --- | --- | --- |
| `remote: Permission to lorry-create/multi-bill-ledger.git denied to <xxx>` | ① 不是协作者 ② 邀请没接受 ③ 本机登录的是另一个 GitHub 账号 | 先确认邀请已 Accept；再 `git config --get user.email` 核对；还不行就清凭据重登（见下行） |
| `Authentication failed` / `Support for password authentication was removed` | 用了账号密码，或凭据是旧的 | Windows：控制面板 → 凭据管理器 → Windows 凭据 → 删掉 `git:https://github.com` → 重新 push，走浏览器登录 |
| `! [rejected] ... (non-fast-forward)` | 远端有你没有的提交 | `git pull --rebase origin task/T00-baseline` 后再 push |
| `fatal: refusing to merge unrelated histories` | 他不是 clone 的，是 `git init` 后自己连上来的 | 删掉本地目录，重新 `git clone` |
| `error: src refspec ... does not match any` | 分支名打错 / 还没 commit | `git branch --show-current` 看当前分支；`git log --oneline -1` 确认有提交 |
| `GH001: Large files detected` / 文件超 100MB | 把 `node_modules`、`*.zip`、视频提上去了 | `git reset --soft HEAD~1` 撤回这次提交，检查 `.gitignore` 后重来 |
| push 卡住不动、没提示 | 代理 / 网络 | 关掉 VPN 或代理重试；`git config --global --unset http.proxy` |

`.gitignore` 里已经排掉：`node_modules/`、`frontend/dist/`、`.env*`（保留 `.env.example`）、`local-data/`、`*.zip`。所以前端初始化完直接 `git add frontend` 是安全的。

---

## 六、给 F 的第一天检查清单

- [ ] 已接受 GitHub 邀请（`Pending invite` 变成 `Collaborator`）
- [ ] `git clone` 成功，`git checkout task/T00-baseline` 后 `ls` 能看到 `backend/`、`contracts/`、`docs/`
- [ ] `git config user.name` / `user.email` 是**他自己**的
- [ ] 建 `frontend/` 脚手架（`npm create vite@latest frontend -- --template react-ts`），`npm run dev` 能起来
- [ ] 按 `docs/23_frontend_development_guide.md` 配好 `vite.config.ts` 的 `/api` 代理到 `http://127.0.0.1:8000`
- [ ] 起后端：`cd backend && python -m uvicorn app.main:app --reload --port 8000`
- [ ] 前端页面上能打到 `GET /api/health` 返回 200
- [ ] 做一次空提交推送成功：`git commit --allow-empty -m "chore: 接入验证" && git push`

最后一条通过，就说明权限链路彻底通了，后面只剩写页面的事。

---

## 七、队长这边的两个待办（会影响队友能不能直接开工）

1. **`main` 还停在 15 个提交之前**。队友 clone 后默认在 `main` 上，看到的是一份旧代码。
   两个选择：把 `task/T00-baseline` 快进合并到 `main`（推荐，队友零学习成本），
   或者明确要求所有人 `git checkout task/T00-baseline`。
2. **分支保护没开**。任何人（含 Write 角色）都能强推 `main`。人少时问题不大，
   但如果要留证据给评审，建议演示前保持现状、演示后别再让人碰 `main`。
