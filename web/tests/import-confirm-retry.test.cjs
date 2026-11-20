const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const ts = require("typescript");
const { parse } = require("vue/compiler-sfc");

test("重试确认直接重放丢失响应的原请求", async () => {
  const source = readFileSync(require.resolve("../src/pages/ImportConfirm.vue"), "utf8");
  const script = parse(source).descriptor.scriptSetup.content;
  const ast = ts.createSourceFile("ImportConfirm.ts", script, ts.ScriptTarget.ES2022, true);
  const confirm = ast.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === "confirm",
  );
  assert.ok(confirm);
  const { outputText } = ts.transpileModule(confirm.getText(ast), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });

  const ref = (value) => ({ value });
  const draft = { row_id: "row-1", duplicate_status: "unique", category: "dining" };
  const occurredAt = "2026-11-19T10:00:00+08:00";
  const calls = [];
  let prechecks = 0;
  const context = {
    crypto: webcrypto,
    active: true,
    route: { params: { id: "batch-1" } },
    batch: ref({ id: "batch-1", source: "wechat", rows: [draft], version: 3 }),
    selected: ref([
      {
        row: draft,
        occurred_at: occurredAt,
        amount: "12.34",
        flow_type: "expense",
        merchant: "瑞幸咖啡",
        description: "",
        category: "dining",
      },
    ]),
    busy: ref(false),
    ready: ref(true),
    invalid: ref([]),
    hasUnallowedSuspectedSelected: ref(false),
    error: ref(""),
    notice: ref(""),
    dupCheckNotice: ref(""),
    dupModalOpen: ref(false),
    rowErrors: ref({}),
    confirmed: ref(null),
    fromLocalInput: (value) => value,
    parseYuan: () => 1234,
    csrf: () => "test-token",
    withCsrfRetry: (send) => send(),
    errorText: (error) => error.message,
    load: async () => {},
    runDuplicatePrecheck: async () => {
      prechecks++;
      if (calls.length) throw Object.assign(new Error("BATCH_STATE_CONFLICT"), { status: 409 });
      return null;
    },
    api: {
      confirmImport: async (request) => {
        calls.push(structuredClone(request));
        if (calls.length === 1) throw new Error("入账后响应丢失");
        return { created_count: 1, duplicate_count: 0, ignored_count: 0, transaction_ids: ["txn-1"] };
      },
    },
  };
  const handler = new Function(
    ...Object.keys(context),
    `let retryPayload = null;\n${outputText}\nreturn confirm;`,
  )(...Object.values(context));

  await handler();
  assert.equal(context.error.value, "入账后响应丢失");
  await handler();

  assert.equal(prechecks, 1);
  assert.equal(calls.length, 2);
  assert.ok(calls[0].body.request_id);
  assert.deepEqual(calls[1], calls[0]);
  assert.deepEqual(context.confirmed.value.transactionIds, ["txn-1"]);
  assert.match(context.notice.value, /已入账 1 笔/);
});
