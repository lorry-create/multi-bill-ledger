# 归账前端

Vue 3 + TypeScript + Vite。页面通过 `src/api/client.generated.ts` 调用仓库 OpenAPI 0.2.0 契约。开发代理把 `/api` 和 `/health` 转到 `http://127.0.0.1:8000`。

```powershell
cd web
npm ci
npm run dev
```

默认连接真实后端。若只需要查看界面，可在本机创建 `.env.local`：

```text
VITE_USE_MOCK=true
```

然后重新运行 `npm run dev`。演示模式的数据来自 `contracts/examples.json` 的**独立合成快照**，不代表后端已处理真实账单；任意非空账号密码仅用于本地界面预览。演示模式不生成真实 PDF，也没有原始文件。不要用演示模式的数字作为联调证据。

页面：登录、导入、逐笔确认、账单筛选和修正、月报与预算、个人分类规则。真实模式的写请求通过生成 SDK 发送 CSRF token，金额在表单中精确转为整数分。账单页的筛选和页码保存在地址栏，CSV 和 Excel 均导出筛选范围内的全部账单。

修正账单时可查看已保存版本，下载可用的导入原件，并对照能唯一匹配的导入草稿。契约 0.2.0 仅提供账单列表查询，版本冲突时按支付平台分页查找同一交易 ID。按 ID 直接查询和逐次修改记录需要后端接口支持。

```powershell
npm run typecheck
npm run build
```

接口契约变更后运行 `python tools/generate_contract_artifacts.py` 重新生成 SDK，前端不手改生成文件。当前后端已实现 19 个接口。本地真实 HTTP 联调覆盖 CSV／XLSX 导入、截图离线 OCR、逐笔确认和规则反馈。修正类别后，可从入账完成页保存商户规则，后续同平台交易优先使用该规则。月报可导出 PDF。截图 OCR 默认启用，DeepSeek 分类需在后端单独配置 API Key。
