// 演示数据仅来自 contracts/examples.json 的独立合成快照；不是实际后端记录。
import examples from "../../../contracts/examples.json";
import * as SDK from "./client.generated";

type Case = { case_id: string; response: { body?: unknown } };
const cases = examples.cases as Case[];
function sample<T>(name: string): T {
  return structuredClone(
    cases.find((c) => c.case_id === name)?.response.body,
  ) as T;
}
let session: SDK.Session | null = null;
const demoSessionKey = "ledger-demo-session";
let batch: SDK.Batch | null = null;
let transactions = sample<SDK.TransactionPage>(
  "listTransactions_success",
).items;
let rules = sample<SDK.RuleList>("listRules_success").items;
const initialReport = sample<SDK.MonthlyReport>("getMonthlyReport_success");
const budgetRecords = new Map<string, SDK.Budget>();
for (const item of initialReport.budgets) {
  const id = `demo_budget_${initialReport.month}_${item.category}`;
  budgetRecords.set(id, {
    id,
    month: initialReport.month,
    category: item.category,
    amount_fen: item.budget_fen,
  });
}
const wait = () => new Promise((resolve) => setTimeout(resolve, 350));

type TransactionFilters = NonNullable<
  SDK.OperationArgs["exportTransactions"]["query"]
>;
const shanghaiDate = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const csvColumns = [
  "occurred_at",
  "source",
  "flow_type",
  "category",
  "amount_fen",
  "currency",
  "merchant",
  "description",
  "classification_source",
  "source_transaction_id",
] as const satisfies readonly (keyof SDK.Transaction)[];

function matchingTransactions(query: TransactionFilters) {
  return transactions
    .filter((item) => {
      if (query.category && item.category !== query.category) return false;
      if (query.source && item.source !== query.source) return false;
      if (query.flow_type && item.flow_type !== query.flow_type) return false;
      if (!query.date_from && !query.date_to) return true;
      const day = shanghaiDate.format(new Date(item.occurred_at));
      return (
        (!query.date_from || day >= query.date_from) &&
        (!query.date_to || day <= query.date_to)
      );
    })
    .sort((a, b) => {
      const timeDifference =
        Date.parse(b.occurred_at) - Date.parse(a.occurred_at);
      if (timeDifference || a.id === b.id) return timeDifference;
      return a.id < b.id ? 1 : -1;
    });
}

function csvCell(value: string | number | null) {
  if (typeof value === "number") return String(value);
  const text = value ?? "";
  const safeText = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safeText)
    ? `"${safeText.replaceAll('"', '""')}"`
    : safeText;
}

export const mock = {
  async login() {
    await wait();
    session = sample<SDK.Session>("login_success");
    globalThis.sessionStorage?.setItem(demoSessionKey, "true");
    return session;
  },
  async getSession() {
    await wait();
    if (
      !session &&
      globalThis.sessionStorage?.getItem(demoSessionKey) === "true"
    ) {
      session = sample<SDK.Session>("login_success");
    }
    if (!session) throw new Error("演示会话尚未建立");
    return session;
  },
  async logout() {
    session = null;
    globalThis.sessionStorage?.removeItem(demoSessionKey);
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
  async resolveImportMissing(args: SDK.OperationArgs["resolveImportMissing"]) {
    await wait();
    const current = batch ?? sample<SDK.Batch>("getImport_success");
    const year = args.body.default_year ?? 2026;
    const rows = current.rows.map((row) => ({
      ...row,
      occurred_at: row.occurred_at ?? `${year}-11-06T16:53:00+08:00`,
      issues: row.issues.filter((i) => i.code !== "TIME_MISSING"),
    }));
    batch = {
      ...current,
      version: current.version + 1,
      rows,
      issues: rows.flatMap((r) => r.issues),
    };
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
    const filtered = matchingTransactions(q);
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
    const current = transactions[index];
    if (!current) {
      throw new SDK.ApiError(404, {
        error: {
          code: "RESOURCE_NOT_FOUND",
          message: "资源不存在",
          details: {},
        },
      });
    }
    if (args.body.expected_version !== current.version) {
      throw new SDK.ApiError(409, {
        error: {
          code: "VERSION_CONFLICT",
          message: "记录已被其他操作修改",
          details: { current_version: current.version },
        },
      });
    }
    const item = {
      ...current,
      ...args.body.changes,
      version: current.version + 1,
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
  async getMonthlyReport(
    args: SDK.OperationArgs["getMonthlyReport"],
  ): Promise<SDK.MonthlyReport> {
    const month = args.query.month;
    const [year, number] = month.split("-").map(Number);
    const monthLength = new Date(year, number, 0).getDate();
    const daily_trend = Array.from({ length: monthLength }, (_, index) => ({
      date: `${month}-${String(index + 1).padStart(2, "0")}`,
      income_fen: 0,
      gross_expense_fen: 0,
      refund_fen: 0,
      net_expense_fen: 0,
    }));
    const totals = {
      income_fen: 0,
      gross_expense_fen: 0,
      refund_fen: 0,
      net_expense_fen: 0,
      balance_fen: 0,
    };
    const gross = new Map<SDK.Category, number>();
    const net = new Map<SDK.Category, number>();
    for (const item of transactions) {
      const date = shanghaiDate.format(new Date(item.occurred_at));
      if (date.slice(0, 7) !== month) continue;
      const day = daily_trend[Number(date.slice(-2)) - 1];
      const amount = item.amount_fen;
      if (item.flow_type === "income") {
        day.income_fen += amount;
        totals.income_fen += amount;
      } else if (item.flow_type === "expense") {
        day.gross_expense_fen += amount;
        totals.gross_expense_fen += amount;
        gross.set(item.category, (gross.get(item.category) ?? 0) + amount);
        net.set(item.category, (net.get(item.category) ?? 0) + amount);
      } else if (item.flow_type === "refund") {
        day.refund_fen += amount;
        totals.refund_fen += amount;
        net.set(item.category, (net.get(item.category) ?? 0) - amount);
      }
      day.net_expense_fen = day.gross_expense_fen - day.refund_fen;
    }
    totals.net_expense_fen = totals.gross_expense_fen - totals.refund_fen;
    totals.balance_fen = totals.income_fen - totals.net_expense_fen;
    const budgets = [...budgetRecords.values()]
      .filter((item) => item.month === month)
      .map((item) => {
        const spent_fen = net.get(item.category) ?? 0;
        const remaining_fen = item.amount_fen - spent_fen;
        return {
          category: item.category,
          budget_fen: item.amount_fen,
          spent_fen,
          remaining_fen,
          over_fen: Math.max(0, -remaining_fen),
        };
      });
    return {
      month,
      totals,
      daily_trend,
      budgets,
      expense_by_category: [...gross].map(([category, amount_fen]) => ({
        category,
        amount_fen,
      })),
    };
  },
  async putBudget(args: SDK.OperationArgs["putBudget"]) {
    const { month, category } = args.body;
    const id = `demo_budget_${month}_${category}`;
    const budget = { ...args.body, id };
    budgetRecords.set(id, budget);
    return { ...budget };
  },
  async exportTransactions(args: SDK.OperationArgs["exportTransactions"]) {
    const rows = matchingTransactions(args.query ?? {}).map((transaction) =>
      csvColumns.map((column) => csvCell(transaction[column])).join(","),
    );
    const csv = [csvColumns.join(","), ...rows].join("\r\n");
    return new Blob(["\uFEFF", csv, "\r\n"], {
      type: "text/csv;charset=utf-8",
    });
  },
  async exportMonthlyPdf() {
    return new Blob(["合成演示不提供 PDF，请连接真实后端导出。"], {
      type: "text/plain",
    });
  },
  async checkImportDuplicates(
    args: SDK.OperationArgs["checkImportDuplicates"],
  ): Promise<SDK.DuplicateCheckResult> {
    const page = await this.listTransactions({
      query: { page: 1, page_size: 100 },
    });
    const existing = page.items;
    return {
      batch_id: args.path.id,
      version: args.body.expected_version,
      rows: args.body.rows.map((row) => {
        const day = row.occurred_at ? row.occurred_at.slice(0, 10) : "";
        const hitExact = existing.find(
          (tx) =>
            (row.source_transaction_id &&
              tx.source_transaction_id === row.source_transaction_id) ||
            (tx.occurred_at.slice(0, 10) === day &&
              row.amount_fen !== null &&
              tx.amount_fen === row.amount_fen &&
              tx.merchant.trim() === row.merchant.trim()),
        );
        if (hitExact) {
          return {
            row_id: row.row_id,
            duplicate_status: "duplicate",
            reason: "与演示账本中已有记录一致",
            matched_summary: `${hitExact.occurred_at.slice(0, 10)} ${hitExact.merchant} ¥${(hitExact.amount_fen / 100).toFixed(2)}`,
          };
        }
        return {
          row_id: row.row_id,
          duplicate_status: "unique",
          reason: "",
          matched_summary: "",
        };
      }),
    };
  },
};
