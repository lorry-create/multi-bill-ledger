// 演示数据仅来自 contracts/examples.json 的独立合成快照；不是实际后端记录。
import examples from "../../../contracts/examples.json";
import type * as SDK from "./client.generated";

type Case = { case_id: string; response: { body?: unknown } };
const cases = examples.cases as Case[];
function sample<T>(name: string): T {
  return structuredClone(
    cases.find((c) => c.case_id === name)?.response.body,
  ) as T;
}
let session: SDK.Session | null = null;
let batch: SDK.Batch | null = null;
let transactions = sample<SDK.TransactionPage>(
  "listTransactions_success",
).items;
let rules = sample<SDK.RuleList>("listRules_success").items;
let report = sample<SDK.MonthlyReport>("getMonthlyReport_success");
const wait = () => new Promise((resolve) => setTimeout(resolve, 350));

export const mock = {
  async login() {
    await wait();
    session = sample<SDK.Session>("login_success");
    return session;
  },
  async getSession() {
    await wait();
    if (!session) throw new Error("演示会话尚未建立");
    return session;
  },
  async logout() {
    session = null;
  },
  async createImport(args: SDK.OperationArgs["createImport"]) {
    await wait();
    batch = sample<SDK.Batch>("getImport_success");
    batch.file_name = (args.body.file as File).name;
    batch.source = args.body.source;
    batch.ingestion_method = args.body.ingestion_method;
    return batch;
  },
  async getImport() {
    await wait();
    return batch ?? sample<SDK.Batch>("getImport_success");
  },
  async getImportOriginal() {
    return new Blob(["合成演示数据不包含原始文件"], { type: "text/plain" });
  },
  async retryImport() {
    batch = sample<SDK.Batch>("getImport_success");
    return batch;
  },
  async confirmImport(args: SDK.OperationArgs["confirmImport"]) {
    await wait();
    const result = sample<SDK.ConfirmResult>("confirmImport_success");
    if (batch) {
      batch.status = "completed";
      batch.version++;
    }
    const items = args.body.rows.map((row, i): SDK.Transaction => ({
      ...row.transaction,
      id: `demo_${i}_${Date.now()}`,
      version: 1,
      source: batch?.source ?? "wechat",
      ingestion_method: batch?.ingestion_method ?? "file",
      import_batch_id: batch?.id ?? "batch_demo_01",
      classification_source: "manual",
      classification_reason: "演示手动确认",
      status: "confirmed",
    }));
    transactions = [...items, ...transactions];
    return {
      ...result,
      created_count: items.length,
      transaction_ids: items.map((x) => x.id),
    };
  },
  async listTransactions(args: SDK.OperationArgs["listTransactions"]) {
    await wait();
    const q = args.query ?? {};
    const filtered = transactions.filter(
      (x) =>
        (!q.category || x.category === q.category) &&
        (!q.source || x.source === q.source) &&
        (!q.flow_type || x.flow_type === q.flow_type) &&
        (!q.date_from || x.occurred_at.slice(0, 10) >= q.date_from) &&
        (!q.date_to || x.occurred_at.slice(0, 10) <= q.date_to),
    );
    const page = q.page ?? 1,
      size = q.page_size ?? 50;
    return {
      items: filtered.slice((page - 1) * size, page * size),
      total: filtered.length,
      page,
      page_size: size,
    };
  },
  async patchTransaction(args: SDK.OperationArgs["patchTransaction"]) {
    const index = transactions.findIndex((x) => x.id === args.path.id);
    const item = {
      ...transactions[index],
      ...args.body.changes,
      version: transactions[index].version + 1,
      classification_source: "manual" as const,
    };
    transactions[index] = item;
    if (args.body.remember_rule && item.category !== "pending")
      rules.unshift({
        id: `demo_rule_${Date.now()}`,
        version: 1,
        source: item.source,
        merchant_normalized: item.merchant,
        category: item.category,
        enabled: true,
      });
    return item;
  },
  async listRules() {
    return { items: [...rules] };
  },
  async patchRule(args: SDK.OperationArgs["patchRule"]) {
    const i = rules.findIndex((x) => x.id === args.path.id);
    rules[i] = { ...rules[i], ...args.body, version: rules[i].version + 1 };
    return rules[i];
  },
  async getMonthlyReport(args: SDK.OperationArgs["getMonthlyReport"]) {
    if (args.query.month === report.month) return { ...report };
    const [year, month] = args.query.month.split("-").map(Number);
    const days = new Date(year, month, 0).getDate();
    return {
      month: args.query.month,
      totals: {
        income_fen: 0,
        gross_expense_fen: 0,
        refund_fen: 0,
        net_expense_fen: 0,
        balance_fen: 0,
      },
      expense_by_category: [],
      daily_trend: Array.from({ length: days }, (_, i) => ({
        date: `${args.query.month}-${String(i + 1).padStart(2, "0")}`,
        income_fen: 0,
        gross_expense_fen: 0,
        refund_fen: 0,
        net_expense_fen: 0,
      })),
      budgets: [],
    };
  },
  async putBudget(args: SDK.OperationArgs["putBudget"]) {
    const b = args.body;
    report.budgets = report.budgets
      .filter((x) => x.category !== b.category)
      .concat({
        category: b.category,
        budget_fen: b.amount_fen,
        spent_fen: 0,
        remaining_fen: b.amount_fen,
        over_fen: 0,
      });
    return { id: "demo_budget", ...b };
  },
  async exportTransactions() {
    return new Blob(["日期,商户,金额（分）\n2026-11-08,示例餐馆,2300"], {
      type: "text/csv;charset=utf-8",
    });
  },
  async exportMonthlyPdf() {
    return new Blob(["合成演示不提供 PDF，请连接真实后端导出。"], {
      type: "text/plain",
    });
  },
};
