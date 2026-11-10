# GitHub 协作和队长审查

目标仓库 https://github.com/lorry-create/multi-bill-ledger 。2026 年 11 月 7 日复核已为 private，当前 GitHub 连接仍可访问；本次检查到的远端文件为标题 README。队友是否已获得访问需各自接受邀请并验证。

## 私有仓库访问

私有仓库可以邀请两位队友成为 Collaborators。接受邀请后能读写、克隆、推送分支和创建 PR，免费个人账号也支持。你保留所有者身份，各人使用自己的 GitHub 账号；AI 工具需要访问私有仓库时也要在各自账号上授权该仓库。

当前不必重复修改可见性。你在 Settings 的 Collaborators 或管理访问入口邀请两位队友的 GitHub 用户名。让队友分别打开仓库、克隆、推送测试分支并开 PR，验证实际访问，而非只验证邀请已发出。后续复核可见性的设置路径为 Settings → General → Danger Zone → Change repository visibility。

私有可见性不等于 main 分支受保护。个人私有仓库的协作者有写权限，不能声称他们天生只能推功能分支。GitHub Free 的私有仓库不具备文档中列出的全部受保护分支能力；Pro 等套餐才支持相应私有保护。以实际设置页和官方说明为准。

若账号支持，要求所有 main 变更经 PR、至少一个批准、应用 CI 成功、讨论解决，禁止 force push。应用 CI 未启用或尚未跑出检查名时，不把文档检查冒充应用检查。若账号不支持，使用明确的人工规则：队友不直推 main、由你验收合并；这是团队约定，不能描述为技术强制。你自己的 PR 让队友交叉检查。

## 第一次把文档放入仓库

当前远端已有 README，不能用无关本地历史强推覆盖。推荐先克隆现有仓库，再把本包的内容复制进克隆根目录，在 docs/team-baseline 分支提交。新版 README 保留了远端原有项目名和中文介绍。

以下为你执行的步骤说明，本包没有自动执行远端上传、可见性修改、邀请或合并。克隆路径由你选择；不要把真实账单所在整个桌面目录作为 Git 仓库。

```powershell
git clone https://github.com/lorry-create/multi-bill-ledger.git
Set-Location multi-bill-ledger
git switch -c docs/team-baseline
```

将团队协作开发包内的 README、AGENTS、VALIDATION、docs、contracts、fixtures、tools、.github、.env.example、.gitignore 复制到此目录；包含以点开头的文件。不要把 ZIP 本身、比赛原始文件或个人账单一起复制。先检查差异再暂存：

```powershell
python tools/check_contract.py
git status --short
git diff
git add README.md AGENTS.md VALIDATION.md docs contracts fixtures tools .github .env.example .gitignore
git diff --cached --stat
git diff --cached
git commit -m "docs: add team development contracts and handoff"
git push -u origin docs/team-baseline
```

在 GitHub 打开 Pull requests → New pull request，base 为 main，compare 为 docs/team-baseline。审阅文件和 Contract checks，确认基线后合并。再让队友克隆或更新 main；把文档基线的提交 SHA 写入任务卡。

## 常用概念

| 概念 | 本项目用途 |
| --- | --- |
| Issue | 一张可验收任务卡，标题包含 T00 等任务号 |
| Branch | 该任务的开发分支 |
| Commit SHA | 唯一确定测试过哪个版本的编号 |
| Pull Request 或 PR | 请求队长审查并合并代码 |
| Actions | 自动运行约定的检查、测试和构建 |

## 队友每天的工作

从干净工作区更新 main，认领一个依赖已满足的任务，创建任务分支，例如 feat/T03-import-ui 或 feat/T04-classification。旧分支已有未提交修改时先妥善提交或处理，不使用强制清理命令。

```powershell
git status --short
git switch main
git pull --ff-only origin main
git switch -c feat/T03-import-ui
```

把对应提示词交给 AI，让它读仓库和任务卡、实现、验证，再人工检查差异。按实际改动路径暂存，提交并推送功能分支；在网页开 PR 指向 main，申请你审查。分支未完成时可频繁推送或开 Draft PR，状态写开发中，不误报完成。

同步 main 的新公共契约时，在自己的任务分支合并 origin/main 并解决冲突，重新测试；不要自行 force push。不能用聊天中的旧 ZIP 替换仓库最新契约。

## 队长随时审查和测试

网页依次看任务描述、Files changed、Checks 和验证证据。Actions 的日志可查实际测试命令；绿色 Contract checks 证明契约、合成样例和SDK的约定检查，不能代替真实应用验收。待 T00 启用 App CI 后，backend-tests 和 frontend-build 才分别表明对应命令通过。

本地建议单独克隆一份 review 目录，避免切换 PR 时影响自己的未提交代码。GitHub CLI 为可选工具，当前本机未检测到 gh；可安装并登录后使用，或用下方 Git 方式。

```powershell
git clone https://github.com/lorry-create/multi-bill-ledger.git multi-bill-ledger-review
Set-Location multi-bill-ledger-review
git fetch origin pull/12/head:review/pr-12
git switch review/pr-12
git rev-parse HEAD
```

12 是示例 PR 号，替换为实际值。之后该 PR 有新提交时使用一个新 review 分支或明确同步后再测，并记录最新 SHA，不复用旧报告。若已安装 GitHub CLI，也可用 gh pr checkout 12。

T00 和 T10 应将以下约定实现为可运行命令，当前文档包本身不能启动业务系统：

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests --junitxml=test-results/backend.xml
Set-Location frontend
npm ci
npm run typecheck
npm run lint
npm run build
```

完整业务验收从仓库根目录用独立 review 配置运行 Docker Compose，使用合成账单和测试凭据，不加载个人真实数据库。H 应提供 .env.review 的生成说明、APP_PORT=18080 和如下可验证入口：

```powershell
docker compose -p billledger-review --env-file .env.review up --build -d
```

项目名隔离只有在 Compose 未使用固定容器名或全局固定卷名时才有效，H 必须验证。不要在不明目标上执行清卷命令。先测试 08 的受影响验收项，再做关键闭环，记录 SHA 和结果。

GitHub 能让你随时看代码、PR 和 CI；上传代码不会自动产生可公开访问的 Web 演示站。初赛采用本地或指定服务器运行；公网 PR 预览要额外配置部署，当前不承诺。

## 合并和交付

没有阻塞缺陷、受影响测试通过、实际页面验证完成、共同约定同步后，你在 GitHub 合并 PR，main 再跑集成检查。保留分支合并记录和测试 SHA。任何合并方式均保留原 PR 的可追踪信息；不把所有开发伪造成最终一次提交。

## 官方参考

- [私有仓库邀请协作者](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)
- [个人仓库权限](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)
- [仓库可见性设置](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
- [受保护分支和套餐范围](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [本地检出 PR](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/checking-out-pull-requests-locally)
- [Actions 工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
