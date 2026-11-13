<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  Sparkles,
  X,
} from "@lucide/vue";
import { api, isDemo } from "../api";
import type {
  Batch,
  Category,
  ConfirmInput,
  FlowType,
  TransactionDraft,
} from "../api";
import type {
  DuplicateBatchMatch,
  DuplicateRowMatch,
} from "../api/client.generated";
import {
  categories,
  classificationSources,
  download,
  flows,
  fromLocalInput,
  parseYuan,
  sources,
  toLocalInput,
} from "../format";
import { csrf, errorText, withCsrfRetry } from "../session";

type Editable = {
  row: TransactionDraft;
  selected: boolean;
  occurred_at: string;
  amount: string;
  flow_type: FlowType | null;
  merchant: string;
  description: string;
  category: Category;
  allow_suspected_duplicate: boolean;
};

function isRowComplete(r: {
  occurred_at: string;
  amount: string;
  flow_type: FlowType | null;
  merchant: string;
}) {
  return (
    !!r.occurred_at &&
    parseYuan(r.amount) !== null &&
    !!r.flow_type &&
    !!r.merchant.trim()
  );
}

const route = useRoute(),
  router = useRouter(),
  batch = ref<Batch | null>(null),
  rows = ref<Editable[]>([]),
  busy = ref(false),
  error = ref(""),
  notice = ref(""),
  originalUrl = ref(""),
  originalLoadedFor = ref<string | null>(null),
  originalLoading = ref(false),
  originalZoomed = ref(false),
  rowErrors = ref<Record<string, string[]>>({}),
  elapsed = ref(0),
  resolveOpen = ref(false),
  resolveBusy = ref(false),
  resolveYear = ref<number | null>(new Date().getFullYear()),
  resolveInstruction = ref(""),
  resolveError = ref(""),
  promptAutoShownFor = ref<string>(""),
  dupModalOpen = ref(false),
  dupModalHint = ref(""),
  dupAutoWarnedFor = ref<string>(""),
  dupCheckBusy = ref(false),
  dupCheckNotice = ref(""),
  dupModalItems = ref<
    Array<{
      row_id: string;
      index: number;
      merchant: string;
      occurred_at: string;
      amount: string;
      duplicate_status: "duplicate" | "suspected";
      reason: string;
      matched_summary: string;
    }>
  >([]);
let active = true;
let timer: ReturnType<typeof setTimeout> | undefined;
let retryPayload: ConfirmInput | null = null;
const ready = computed(() => batch.value?.status === "pending_review");
const selected = computed(() => rows.value.filter((r) => r.selected));
const dupBatchMatch = computed<DuplicateBatchMatch | null>(
  () => batch.value?.duplicate_match ?? null,
);
const dupCounts = computed(() => {
  let dup = 0;
  let sus = 0;
  for (const item of rows.value) {
    if (item.row.duplicate_status === "duplicate") dup += 1;
    else if (item.row.duplicate_status === "suspected") sus += 1;
  }
  return { dup, sus, total: dup + sus };
});
const hasUnallowedSuspectedSelected = computed(() =>
  selected.value.some(
    (x) =>
      x.row.duplicate_status === "suspected" && !x.allow_suspected_duplicate,
  ),
);
const missingTimeRows = computed(() =>
  rows.value.filter((r) => !r.occurred_at),
);
const missingYearCount = computed(
  () =>
    batch.value?.rows.filter((row) =>
      row.issues.some(
        (i) =>
          i.code === "TIME_MISSING" && i.message.includes("缺少具体年份"),
      ),
    ).length ?? 0,
);
const uncertainCatCount = computed(
  () => rows.value.filter((r) => r.category === "pending").length,
);
const quickYears = computed(() => {
  const y = new Date().getFullYear();
  return [y, y - 1, y - 2];
});
const statusLabel: Record<Batch["status"], string> = {
  uploaded: "等待处理",
  processing: "识别中",
  pending_review: "等待确认",
  completed: "已完成",
  failed: "处理失败",
};
const invalid = computed(() =>
  selected.value.filter((r) => !isRowComplete(r)),
);
function draftToEditable(row: TransactionDraft): Editable {
  const occurred_at = toLocalInput(row.occurred_at);
  const amount = row.amount_fen === null ? "" : (row.amount_fen / 100).toFixed(2);
  const flow_type = row.flow_type;
  const merchant = row.merchant;
  return {
    row,
    selected:
      row.duplicate_status === "unique" &&
      isRowComplete({ occurred_at, amount, flow_type, merchant }),
    occurred_at,
    amount,
    flow_type,
    merchant,
    description: row.description,
    category: row.category,
    allow_suspected_duplicate: false,
  };
}
async function loadOriginalPreview(b: Batch) {
  if (
    isDemo ||
    b.ingestion_method !== "screenshot" ||
    !["pending_review", "completed", "failed"].includes(b.status) ||
    originalLoadedFor.value === b.id ||
    originalLoading.value
  ) {
    return;
  }
  originalLoading.value = true;
  originalLoadedFor.value = b.id;
  try {
    const blob = await api.getImportOriginal({ path: { id: b.id } });
    if (!active || String(route.params.id) !== b.id) return;
    if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
    originalUrl.value = URL.createObjectURL(blob);
  } catch {
    originalLoadedFor.value = null;
  } finally {
    if (active) originalLoading.value = false;
  }
}
function fill(b: Batch, preserve = false) {
  const prevStatus = batch.value?.status;
  const canPreserve =
    preserve &&
    prevStatus === "pending_review" &&
    rows.value.length > 0 &&
    rows.value.length === b.rows.length;
  batch.value = b;
  if (!canPreserve) rows.value = b.rows.map(draftToEditable);
  loadOriginalPreview(b);
}
async function load(preserve = false, resetTimeout = false) {
  const batchId = String(route.params.id);
  clearTimeout(timer);
  timer = undefined;
  if (resetTimeout) elapsed.value = 0;
  try {
    const b = await api.getImport({ path: { id: batchId } });
    if (!active || String(route.params.id) !== batchId) return;
    error.value = "";
    fill(b, preserve);
    if (
      b.status === "pending_review" &&
      promptAutoShownFor.value !== b.id &&
      b.rows.some((row) => !row.occurred_at)
    ) {
      promptAutoShownFor.value = b.id;
      openResolveModal();
    } else if (
      b.status === "pending_review" &&
      dupAutoWarnedFor.value !== b.id &&
      (b.duplicate_match ||
        b.rows.some((row) => row.duplicate_status !== "unique"))
    ) {
      dupAutoWarnedFor.value = b.id;
      openDupModalFromCurrent(
        b.duplicate_match
          ? "检测到当前上传与历史导入文件/截图重复，请核对以下已存在或疑似重复的账单记录。"
          : "系统检测到本批次包含此前已录入或疑似重复的账单，请确认后再入账。",
      );
    }
    if (["uploaded", "processing"].includes(b.status) && elapsed.value < 120) {
      const wait = elapsed.value ? 2000 : 1000;
      timer = setTimeout(() => {
        elapsed.value += wait / 1000;
        load(false);
      }, wait);
    }
  } catch (e) {
    if (active) error.value = errorText(e);
  }
}
function onConfirmKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (originalZoomed.value) {
    originalZoomed.value = false;
    return;
  }
  if (dupModalOpen.value && !busy.value) {
    dupModalOpen.value = false;
    return;
  }
  if (resolveOpen.value && !resolveBusy.value) {
    resolveOpen.value = false;
  }
}
watch(
  () => route.params.id,
  (next, prev) => {
    if (!next || next === prev) return;
    clearTimeout(timer);
    timer = undefined;
    elapsed.value = 0;
    retryPayload = null;
    batch.value = null;
    rows.value = [];
    error.value = "";
    notice.value = "";
    dupCheckNotice.value = "";
    rowErrors.value = {};
    resolveOpen.value = false;
    dupModalOpen.value = false;
    dupAutoWarnedFor.value = "";
    promptAutoShownFor.value = "";
    originalZoomed.value = false;
    originalLoadedFor.value = null;
    if (originalUrl.value) {
      URL.revokeObjectURL(originalUrl.value);
      originalUrl.value = "";
    }
    load(false, true);
  },
);
onMounted(() => {
  window.addEventListener("keydown", onConfirmKeydown);
  load();
});
onUnmounted(() => {
  active = false;
  clearTimeout(timer);
  window.removeEventListener("keydown", onConfirmKeydown);
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
});
function formatShortDate(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
function buildModalItemsFromRows(
  targetRowIds?: Set<string>,
  matchById?: Map<string, DuplicateRowMatch>,
) {
  return rows.value
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      if (targetRowIds && !targetRowIds.has(item.row.row_id)) return false;
      return item.row.duplicate_status !== "unique";
    })
    .map(({ item, index }) => {
      const m = matchById?.get(item.row.row_id);
      const dupIssue = item.row.issues.find(
        (iss) =>
          iss.code === "DUPLICATE_EXISTING" ||
          iss.code === "DUPLICATE_SUSPECTED",
      );
      return {
        row_id: item.row.row_id,
        index,
        merchant: item.merchant.trim() || item.row.merchant || "未知商户",
        occurred_at: item.occurred_at ? item.occurred_at.replace("T", " ") : "未填写时间",
        amount: item.amount || "0.00",
        duplicate_status: item.row.duplicate_status as "duplicate" | "suspected",
        reason: m?.reason || dupIssue?.message || "疑似与已入账账单重复",
        matched_summary: m?.matched_summary || "",
      };
    });
}
function openDupModalFromCurrent(
  hint = "以下账单在历史记录中检测到重复或高度疑似重复，请核对后选择处理方式。",
  targetRowIds?: Set<string>,
  matchById?: Map<string, DuplicateRowMatch>,
) {
  dupModalHint.value = hint;
  dupModalItems.value = buildModalItemsFromRows(targetRowIds, matchById);
  dupModalOpen.value = true;
}
function findEditableByRowId(rowId: string): Editable | undefined {
  return rows.value.find((item) => item.row.row_id === rowId);
}
function applyCheckResultToRows(
  matchById: Map<string, DuplicateRowMatch>,
  fileMatch?: DuplicateBatchMatch,
): {
  newlyFlaggedSelected: Set<string>;
  blockingSelected: Set<string>;
} {
  if (batch.value && fileMatch) {
    batch.value = { ...batch.value, duplicate_match: fileMatch };
  }
  const newlyFlaggedSelected = new Set<string>();
  const blockingSelected = new Set<string>();
  for (const item of rows.value) {
    const res = matchById.get(item.row.row_id);
    if (!res) continue;
    const prevStatus = item.row.duplicate_status;
    const keptIssues = item.row.issues.filter(
      (iss) =>
        iss.code !== "DUPLICATE_EXISTING" &&
        (iss.code !== "DUPLICATE_SUSPECTED" || iss.message.includes("同一")),
    );
    if (res.duplicate_status === "duplicate") {
      item.row.issues = [
        ...keptIssues,
        {
          row_id: item.row.row_id,
          field: "source_transaction_id",
          code: "DUPLICATE_EXISTING",
          message:
            res.reason || "该交易此前已入账，确认时会自动跳过",
        },
      ];
      if (item.selected) {
        blockingSelected.add(item.row.row_id);
        if (prevStatus !== "duplicate") {
          newlyFlaggedSelected.add(item.row.row_id);
        }
        item.selected = false;
      }
      item.allow_suspected_duplicate = false;
    } else if (res.duplicate_status === "suspected") {
      const hasSameIntra = keptIssues.some(
        (iss) => iss.code === "DUPLICATE_SUSPECTED",
      );
      item.row.issues = hasSameIntra
        ? keptIssues
        : [
            ...keptIssues,
            {
              row_id: item.row.row_id,
              field: "occurred_at",
              code: "DUPLICATE_SUSPECTED",
              message: res.reason || "疑似与已入账记录重复",
            },
          ];
      if (item.selected && !item.allow_suspected_duplicate) {
        blockingSelected.add(item.row.row_id);
        if (prevStatus === "unique") {
          newlyFlaggedSelected.add(item.row.row_id);
        }
      }
    } else {
      item.row.issues = keptIssues;
      item.allow_suspected_duplicate = false;
    }
    item.row.duplicate_status = res.duplicate_status;
  }
  return { newlyFlaggedSelected, blockingSelected };
}
async function runDuplicatePrecheck(): Promise<{
  matchById: Map<string, DuplicateRowMatch>;
  newlyFlaggedSelected: Set<string>;
  blockingSelected: Set<string>;
  fileMatch?: DuplicateBatchMatch;
} | null> {
  if (!batch.value || !rows.value.length) return null;
  const payload = {
    expected_version: batch.value.version,
    rows: rows.value.map((r) => ({
      row_id: r.row.row_id,
      source_transaction_id: r.row.source_transaction_id,
      occurred_at: r.occurred_at ? fromLocalInput(r.occurred_at) : null,
      amount_fen: parseYuan(r.amount),
      flow_type: r.flow_type,
      merchant: r.merchant.trim(),
      description: r.description,
    })),
  };
  const result = await withCsrfRetry(() =>
    api.checkImportDuplicates(
      { path: { id: batch.value!.id }, body: payload },
      csrf(),
    ),
  );
  const matchById = new Map(result.rows.map((m) => [m.row_id, m]));
  const { newlyFlaggedSelected, blockingSelected } = applyCheckResultToRows(
    matchById,
    result.file_match,
  );
  return {
    matchById,
    newlyFlaggedSelected,
    blockingSelected,
    fileMatch: result.file_match,
  };
}
async function checkDuplicatesManual() {
  if (!batch.value || !ready.value || !rows.value.length) return;
  dupCheckBusy.value = true;
  dupCheckNotice.value = "";
  error.value = "";
  try {
    const res = await runDuplicatePrecheck();
    if (!res) return;
    if (dupCounts.value.total > 0 || res.fileMatch) {
      openDupModalFromCurrent(
        dupCounts.value.total > 0
          ? `实时核对发现 ${dupCounts.value.total} 笔与已入账账单重复/疑似重复的明细，请确认处理方式。`
          : "当前批次文件与历史上传一致，但明细行暂未命中已入账交易（可能尚未确认入账）。",
        undefined,
        res.matchById,
      );
    } else {
      dupCheckNotice.value = "实时判重完成：当前明细未发现已入账重复记录。";
    }
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) load(true);
  } finally {
    dupCheckBusy.value = false;
  }
}
function edited(rowId?: string) {
  retryPayload = null;
  notice.value = "";
  dupCheckNotice.value = "";
  if (rowId) {
    const item = findEditableByRowId(rowId);
    if (item && item.row.duplicate_status !== "suspected") {
      item.allow_suspected_duplicate = false;
    }
  }
  if (rowId && rowErrors.value[rowId]) {
    const next = { ...rowErrors.value };
    delete next[rowId];
    rowErrors.value = next;
  }
}
async function original() {
  if (!batch.value) return;
  try {
    if (batch.value.ingestion_method === "screenshot" && originalUrl.value) {
      window.open(originalUrl.value, "_blank", "noopener");
      return;
    }
    const blob = await api.getImportOriginal({
      path: { id: batch.value.id },
    });
    if (batch.value.ingestion_method === "file") {
      download(blob, batch.value.file_name);
      return;
    }
    if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
    originalUrl.value = URL.createObjectURL(blob);
    originalLoadedFor.value = batch.value.id;
    window.open(originalUrl.value, "_blank", "noopener");
  } catch (e) {
    error.value = errorText(e);
  }
}
async function retry() {
  if (!batch.value) return;
  const targetId = batch.value.id;
  busy.value = true;
  clearTimeout(timer);
  timer = undefined;
  elapsed.value = 0;
  retryPayload = null;
  rowErrors.value = {};
  try {
    fill(
      await withCsrfRetry(() =>
        api.retryImport(
          {
            path: { id: targetId },
            body: { expected_version: batch.value!.version },
          },
          csrf(),
        ),
      ),
    );
    error.value = "";
    load(false, true);
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) load();
  } finally {
    busy.value = false;
  }
}
async function confirm(skipPrecheck = false) {
  if (
    !batch.value ||
    !ready.value ||
    !selected.value.length ||
    invalid.value.length
  )
    return;
  busy.value = true;
  error.value = "";
  dupCheckNotice.value = "";
  rowErrors.value = {};
  try {
    if (!skipPrecheck) {
      const check = await runDuplicatePrecheck();
      if (check && check.blockingSelected.size > 0) {
        retryPayload = null;
        openDupModalFromCurrent(
          check.newlyFlaggedSelected.size > 0
            ? "提交前实时判重发现以下账单此前已经录入或高度疑似重复！明确重复项已自动取消勾选，疑似重复项需勾选「仍要入账」或取消选择后再提交。"
            : "当前选中账单中包含尚未确认的疑似重复记录，请在下方逐项核对。",
          check.blockingSelected,
          check.matchById,
        );
        return;
      }
    }
    if (!selected.value.length || invalid.value.length || hasUnallowedSuspectedSelected.value) {
      return;
    }
    if (!retryPayload)
      retryPayload = {
        request_id: crypto.randomUUID(),
        expected_version: batch.value.version,
        rows: selected.value.map((r) => ({
          row_id: r.row.row_id,
          allow_suspected_duplicate:
            r.row.duplicate_status === "suspected" &&
            r.allow_suspected_duplicate,
          transaction: {
            source_transaction_id: r.row.source_transaction_id,
            occurred_at: fromLocalInput(r.occurred_at),
            amount_fen: parseYuan(r.amount)!,
            currency: "CNY",
            flow_type: r.flow_type!,
            merchant: r.merchant.trim(),
            description: r.description,
            category: r.category,
          },
        })),
      };
    const result = await withCsrfRetry(() =>
      api.confirmImport(
        { path: { id: batch.value!.id }, body: retryPayload! },
        csrf(),
      ),
    );
    dupModalOpen.value = false;
    notice.value = `已入账 ${result.created_count} 笔，跳过重复 ${result.duplicate_count} 笔，忽略 ${result.ignored_count} 笔。`;
    await load(true);
    retryPayload = null;
  } catch (e) {
    error.value = errorText(e);
    const err = e as {
      status?: number;
      payload?: {
        error?: {
          details?: {
            fields?: Array<{
              row_id?: string | null;
              field?: string;
              message?: string;
            }>;
          };
        };
      };
    };
    const fields = err?.payload?.error?.details?.fields ?? [];
    if (fields.length) {
      const grouped: Record<string, string[]> = {};
      for (const item of fields) {
        const key = item.row_id || "_global";
        grouped[key] = [...(grouped[key] ?? []), item.message || "字段无效"];
      }
      rowErrors.value = grouped;
      const firstRowId = fields.find((f) => f.row_id)?.row_id;
      if (firstRowId) {
        requestAnimationFrame(() => {
          document
            .getElementById(`draft-row-${firstRowId}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }
    }
    if (err?.status === 409) {
      retryPayload = null;
      await load(true);
    }
  } finally {
    busy.value = false;
  }
}
function missingHintFor(row: TransactionDraft): string {
  const timeIssue = row.issues.find((i) => i.code === "TIME_MISSING");
  const catIssue = row.issues.find((i) => i.code === "CATEGORY_UNCERTAIN");
  const parts: string[] = [];
  if (!row.occurred_at) {
    const m = timeIssue?.message.match(/缺少具体年份[（(]([^）)]+)[）)]/);
    parts.push(m ? `缺年份 (${m[1]})` : "未识别到交易时间");
  }
  if (catIssue || row.category === "pending") {
    parts.push("类别待确认");
  }
  return parts.join(" · ");
}
function openResolveModal() {
  resolveError.value = "";
  if (resolveYear.value === null) {
    resolveYear.value = new Date().getFullYear();
  }
  resolveOpen.value = true;
}
function applyResolvedBatch(prevBatch: Batch | null, updated: Batch) {
  const prevById = new Map(
    (prevBatch?.rows ?? []).map((row) => [row.row_id, row]),
  );
  const localById = new Map(rows.value.map((item) => [item.row.row_id, item]));
  batch.value = updated;
  retryPayload = null;
  rowErrors.value = {};
  rows.value = updated.rows.map((newRow) => {
    const prevRow = prevById.get(newRow.row_id);
    const local = localById.get(newRow.row_id);
    const serverTimeChanged =
      !prevRow || newRow.occurred_at !== prevRow.occurred_at;
    const serverCatChanged = !prevRow || newRow.category !== prevRow.category;
    const serverFlowChanged =
      !prevRow || newRow.flow_type !== prevRow.flow_type;
    const serverDescChanged =
      !prevRow || newRow.description !== prevRow.description;

    const occurred_at = serverTimeChanged
      ? toLocalInput(newRow.occurred_at)
      : (local?.occurred_at ?? toLocalInput(newRow.occurred_at));
    const category = serverCatChanged
      ? newRow.category
      : (local?.category ?? newRow.category);
    const flow_type = serverFlowChanged
      ? newRow.flow_type
      : (local?.flow_type ?? newRow.flow_type);
    const amount =
      local && prevRow && prevRow.amount_fen !== null
        ? local.amount
        : newRow.amount_fen === null
          ? ""
          : (newRow.amount_fen / 100).toFixed(2);
    const merchant = local ? local.merchant : newRow.merchant;
    const description = serverDescChanged
      ? newRow.description
      : (local?.description ?? newRow.description);
    const validForSelect =
      newRow.duplicate_status === "unique" &&
      isRowComplete({ occurred_at, amount, flow_type, merchant });
    return {
      row: newRow,
      selected: validForSelect,
      occurred_at,
      amount,
      flow_type,
      merchant,
      description,
      category,
      allow_suspected_duplicate: false,
    };
  });
}
async function submitResolveMissing(quickOnly = false) {
  if (!batch.value) return;
  const yearVal =
    resolveYear.value !== null && Number.isFinite(Number(resolveYear.value))
      ? Number(resolveYear.value)
      : null;
  const instr = quickOnly ? "" : resolveInstruction.value.trim();
  if (yearVal === null && !instr) {
    resolveError.value = "请选择或填写默认年份，或输入给智能体的补充说明。";
    return;
  }
  resolveBusy.value = true;
  resolveError.value = "";
  error.value = "";
  const prevBatch = batch.value;
  try {
    const updated = await withCsrfRetry(() =>
      api.resolveImportMissing(
        {
          path: { id: batch.value!.id },
          body: {
            expected_version: batch.value!.version,
            default_year: yearVal,
            instruction: instr || null,
          },
        },
        csrf(),
      ),
    );
    const beforeMissing = prevBatch.rows.filter((r) => !r.occurred_at).length;
    const afterMissing = updated.rows.filter((r) => !r.occurred_at).length;
    const resolvedTime = Math.max(0, beforeMissing - afterMissing);
    const newlyDup = updated.rows.filter((r) => {
      const old = prevBatch.rows.find((p) => p.row_id === r.row_id);
      return (
        r.duplicate_status !== "unique" && old?.duplicate_status === "unique"
      );
    }).length;

    applyResolvedBatch(prevBatch, updated);
    resolveOpen.value = false;
    const msgs: string[] = [];
    if (resolvedTime > 0) msgs.push(`已智能补全 ${resolvedTime} 笔交易时间`);
    else msgs.push("已完成智能体核对更新");
    if (newlyDup > 0)
      msgs.push(`重跑判重检测到 ${newlyDup} 笔已入账/疑似重复`);
    if (afterMissing > 0)
      msgs.push(
        `尚有 ${afterMissing} 笔缺少时间（可在列表中手动补全或再次打开「AI 智能补充」）`,
      );
    notice.value = msgs.join("；") + "。";
  } catch (e) {
    resolveError.value = errorText(e);
    if ((e as { status?: number }).status === 409) {
      await load(true);
    }
  } finally {
    resolveBusy.value = false;
  }
}
</script>
<template>
  <div class="page-head">
    <div>
      <RouterLink to="/import" class="back-link"
        ><ArrowLeft :size="16" /> 返回导入</RouterLink
      >
      <h1>核对并确认</h1>
      <p>逐笔检查识别结果，只有选中的账单会入账。</p>
    </div>
    <button class="secondary-btn" @click="load(true, true)">
      <RefreshCw :size="16" /> 刷新状态
    </button>
  </div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <div v-if="notice" class="alert success" role="status">
    {{ notice }} <button @click="router.push('/transactions')">查看账单</button>
  </div>
  <div v-if="!batch" class="empty-state">正在读取导入批次…</div>
  <template v-else
    ><div class="batch-strip">
      <div>
        <span class="batch-source">{{ sources[batch.source] }}</span
        ><strong>{{ batch.file_name }}</strong
        ><small>{{
          batch.ingestion_method === "file" ? "账单文件" : "交易截图"
        }}</small>
      </div>
      <span class="status-pill" :class="batch.status">{{
        statusLabel[batch.status]
      }}</span>
    </div>
    <div v-if="dupBatchMatch" class="alert dup-batch-banner" role="alert">
      <div class="dup-batch-copy">
        <strong>
          <AlertTriangle :size="16" />
          {{
            dupBatchMatch.match_type === "exact_file"
              ? "重复上传提醒：你此前已上传过完全相同的账单文件"
              : "相似截图提醒：该截图与此前上传的账单高度相似"
          }}
        </strong>
        <p>
          历史批次「{{ dupBatchMatch.file_name }}」（{{
            formatShortDate(dupBatchMatch.created_at)
          }}，{{ statusLabel[dupBatchMatch.status] }}，
          <template v-if="dupBatchMatch.created_count > 0"
            >已正式入账 {{ dupBatchMatch.created_count }} 笔</template
          >
          <template v-else>尚未正式入账</template>）。请仔细核对后再确认提交。
        </p>
      </div>
      <div class="dup-batch-actions">
        <button
          type="button"
          class="secondary-btn"
          @click="router.push(`/import/${dupBatchMatch.batch_id}`)"
        >
          查看原批次
        </button>
        <button
          type="button"
          class="secondary-btn"
          @click="router.push('/transactions')"
        >
          查看已入账单
        </button>
      </div>
    </div>
    <div v-if="dupCheckNotice" class="alert success" role="status">
      {{ dupCheckNotice }}
    </div>
    <div v-if="batch.status === 'failed'" class="alert error">
      {{ batch.issues.map((x) => x.message).join("；") || "本批次处理失败。" }}
      <button :disabled="busy" @click="retry">重试处理</button>
    </div>
    <div v-else-if="!ready && batch.status !== 'completed'" class="processing">
      <div class="processing-icon"><RefreshCw :size="22" /></div>
      <h2>{{ elapsed >= 120 ? "仍在处理中" : "正在识别账单" }}</h2>
      <p>
        {{
          elapsed >= 120
            ? "自动刷新已暂停（已超过 2 分钟），可点击下方按钮继续检查。"
            : "识别完成后，你可以核对每一笔交易。"
        }}
      </p>
      <div v-if="batch.progress.total" class="progress-track">
        <span
          :style="{
            width: `${Math.min(100, (batch.progress.current / batch.progress.total) * 100)}%`,
          }"
        ></span>
      </div>
      <div v-else-if="elapsed < 120" class="progress-track indeterminate">
        <span></span>
      </div>
      <button
        v-if="elapsed >= 120"
        type="button"
        class="secondary-btn continue-wait-btn"
        @click="load(false, true)"
      >
        <RefreshCw :size="15" /> 继续等待刷新
      </button>
    </div>
    <div v-if="ready || batch.status === 'completed'" class="confirm-layout">
      <aside class="original-panel">
        <div class="panel-heading">
          <h2>原始来源</h2>
          <button v-if="!isDemo" class="text-btn" @click="original">
            {{ batch.ingestion_method === "file" ? "下载原文件" : "新窗口查看" }}
            <ExternalLink :size="14" />
          </button>
        </div>
        <div
          v-if="batch.ingestion_method === 'screenshot' && originalUrl"
          class="original-preview"
        >
          <button
            type="button"
            class="original-preview-btn"
            title="点击放大查看原始截图"
            @click="originalZoomed = true"
          >
            <img :src="originalUrl" :alt="batch.file_name" />
          </button>
          <p class="original-caption">{{ batch.file_name }}（点击图片可放大）</p>
        </div>
        <div v-else class="original-placeholder">
          <span>{{
            batch.ingestion_method === "file" ? "CSV / XLSX" : "PNG / JPEG"
          }}</span
          ><strong>{{ batch.file_name }}</strong>
          <p>
            {{
              isDemo
                ? "合成数据演示不包含原始文件"
                : originalLoading
                  ? "正在加载原始截图预览…"
                  : batch.ingestion_method === "file"
                    ? "点击上方按钮下载原始账单文件，对照右侧逐笔核对。"
                    : "点击上方查看原始内容，对照右侧逐笔核对。"
            }}
          </p>
        </div>
        <div class="issue-list" v-if="batch.issues.length">
          <h3>批次提示</h3>
          <p
            v-for="(issue, idx) in batch.issues"
            :key="issue.code + (issue.row_id ?? '') + idx"
          >
            {{ issue.message }}
          </p>
        </div>
      </aside>
      <section class="draft-panel">
        <div class="panel-heading">
          <div>
            <h2>识别明细</h2>
            <p>共 {{ rows.length }} 笔，已选择 {{ selected.length }} 笔</p>
          </div>
          <div class="panel-heading-actions">
            <button
              v-if="ready && rows.length"
              type="button"
              class="secondary-btn"
              :disabled="dupCheckBusy || busy"
              @click="checkDuplicatesManual"
            >
              <RefreshCw :size="15" />
              <span>{{ dupCheckBusy ? "判重中…" : "重检已录入账单" }}</span>
            </button>
            <button
              v-if="ready && rows.length"
              type="button"
              class="secondary-btn ai-trigger-btn"
              :class="{ highlight: missingTimeRows.length > 0 }"
              @click="openResolveModal"
            >
              <Sparkles :size="15" />
              <span>{{
                missingTimeRows.length > 0
                  ? `AI 补全缺失年份/时间 (${missingTimeRows.length})`
                  : "AI 补充/调整明细"
              }}</span>
            </button>
          </div>
        </div>
        <div
          v-if="ready && dupCounts.total > 0"
          class="alert dup-rows-banner"
          role="status"
        >
          <div>
            <strong>已识别出 {{ dupCounts.total }} 笔可能重复的账单</strong>
            <p>
              明确重复 {{ dupCounts.dup }} 笔（已自动取消勾选并会在入账时跳过），疑似重复 {{ dupCounts.sus }} 笔（需核对并手动确认后才会入账）。
            </p>
          </div>
          <button
            type="button"
            class="secondary-btn"
            @click="openDupModalFromCurrent()"
          >
            查看重复详情
          </button>
        </div>
        <div
          v-if="ready && missingTimeRows.length > 0"
          class="alert resolve-banner"
        >
          <div>
            <strong>有 {{ missingTimeRows.length }} 笔交易缺少完整时间</strong>
            <p>
              其中 {{ missingYearCount }} 笔仅缺少具体年份。点击右侧按钮让智能体结合您的确认一键补全并重跑判重，无需逐条手填。
            </p>
          </div>
          <button
            type="button"
            class="primary-btn"
            @click="openResolveModal"
          >
            立即补充
          </button>
        </div>
        <div class="draft-list">
          <article
            v-for="(r, index) in rows"
            :key="r.row.row_id"
            :id="'draft-row-' + r.row.row_id"
            class="draft-row"
            :class="{ 'has-error': !!rowErrors[r.row.row_id]?.length }"
          >
            <div class="draft-top">
              <label
                class="check-label"
                :title="
                  !r.selected && !isRowComplete(r)
                    ? '请先补全交易时间、金额、收支方向和商户名称'
                    : undefined
                "
                ><input
                  v-model="r.selected"
                  type="checkbox"
                  :disabled="
                    batch.status === 'completed' ||
                    r.row.duplicate_status === 'duplicate' ||
                    (!r.selected && !isRowComplete(r))
                  "
                  @change="edited(r.row.row_id)"
                /><strong>第 {{ index + 1 }} 笔</strong></label
              ><span
                v-if="r.row.duplicate_status === 'duplicate'"
                class="small-tag warn"
                >明确重复，将自动跳过</span
              ><span
                v-else-if="r.row.duplicate_status === 'suspected'"
                class="small-tag warn"
                >疑似重复，需主动确认</span
              ><span v-else class="small-tag">{{
                classificationSources[r.row.classification_source] || "识别结果"
              }}</span>
            </div>
            <div class="draft-fields">
              <label
                >交易时间<input
                  type="datetime-local"
                  v-model="r.occurred_at"
                  :disabled="batch.status === 'completed'"
                  @input="edited(r.row.row_id)" /></label
              ><label
                >金额（元）<input
                  v-model="r.amount"
                  inputmode="decimal"
                  placeholder="如 23.00"
                  :disabled="batch.status === 'completed'"
                  @input="edited(r.row.row_id)" /></label
              ><label
                >收支方向<select
                  v-model="r.flow_type"
                  :disabled="batch.status === 'completed'"
                  @change="edited(r.row.row_id)"
                >
                  <option :value="null">请选择</option>
                  <option v-for="(label, key) in flows" :key="key" :value="key">
                    {{ label }}
                  </option>
                </select></label
              ><label
                >商户<input
                  v-model="r.merchant"
                  placeholder="商户名称"
                  :disabled="batch.status === 'completed'"
                  @input="edited(r.row.row_id)" /></label
              ><label
                >摘要/备注<input
                  v-model="r.description"
                  placeholder="可选说明"
                  :disabled="batch.status === 'completed'"
                  @input="edited(r.row.row_id)" /></label
              ><label
                >类别<select
                  v-model="r.category"
                  :disabled="batch.status === 'completed'"
                  @change="edited(r.row.row_id)"
                >
                  <option
                    v-for="(label, key) in categories"
                    :key="key"
                    :value="key"
                  >
                    {{ label }}
                  </option>
                </select></label
              >
            </div>
            <p v-if="r.row.classification_reason" class="row-reason">
              分类依据：{{ r.row.classification_reason }}
            </p>
            <p v-if="r.row.issues.length" class="row-issue">
              {{ r.row.issues.map((x) => x.message).join("；") }}
            </p>
            <p v-if="rowErrors[r.row.row_id]?.length" class="row-field-error">
              {{ rowErrors[r.row.row_id].join("；") }}
            </p>
            <label
              v-if="r.row.duplicate_status === 'suspected' && r.selected"
              class="suspect-check"
              ><input
                v-model="r.allow_suspected_duplicate"
                type="checkbox"
                :disabled="batch.status === 'completed'"
                @change="edited(r.row.row_id)"
              />
              我已核对，仍要将这笔疑似重复交易入账</label
            >
          </article>
        </div>
        <div class="confirm-footer">
          <p v-if="invalid.length">
            已选记录中有 {{ invalid.length }} 笔缺少交易时间、金额、收支方向或商户名称。
          </p>
          <p
            v-else-if="
              selected.some(
                (x) =>
                  x.row.duplicate_status === 'suspected' &&
                  !x.allow_suspected_duplicate,
              )
            "
          >
            请确认疑似重复交易。
          </p>
          <p v-else>未选中的记录不会进入账本。</p>
          <button
            class="primary-btn"
            :disabled="
              !ready ||
              !selected.length ||
              !!invalid.length ||
              hasUnallowedSuspectedSelected ||
              busy
            "
            @click="confirm(false)"
          >
            {{ busy ? "正在确认…" : `确认入账 ${selected.length} 笔` }}
          </button>
        </div>
      </section>
    </div>
    <div
      v-if="resolveOpen && batch"
      class="modal-backdrop"
      @click.self="!resolveBusy && (resolveOpen = false)"
    >
      <section
        class="edit-dialog resolve-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="智能助手补充缺失信息"
      >
        <div class="dialog-head">
          <div>
            <h2 class="resolve-title">
              <Sparkles :size="18" /> 智能助手 · 补充缺失账单信息
            </h2>
            <p>
              当前共 {{ rows.length }} 笔明细，其中
              <strong>{{ missingTimeRows.length }}</strong> 笔缺少完整时间<template
                v-if="missingYearCount > 0"
                >（{{ missingYearCount }} 笔仅缺年份）</template
              ><template v-if="uncertainCatCount > 0"
                >，{{ uncertainCatCount }} 笔类别待确认</template
              >。补全后会自动重跑重复校验。
            </p>
          </div>
          <button
            class="icon-btn"
            aria-label="关闭"
            :disabled="resolveBusy"
            @click="resolveOpen = false"
          >
            <X :size="20" />
          </button>
        </div>

        <div v-if="resolveError" class="alert error">{{ resolveError }}</div>

        <div class="resolve-preview">
          <div
            v-for="(item, idx) in rows"
            :key="item.row.row_id"
            class="resolve-preview-row"
            :class="{ missing: !item.occurred_at || item.category === 'pending' }"
          >
            <span class="row-num">第 {{ idx + 1 }} 笔</span>
            <strong class="row-merchant">{{
              item.merchant || "未知商户"
            }}</strong>
            <span class="row-amt">¥{{ item.amount || "0.00" }}</span>
            <span v-if="missingHintFor(item.row)" class="row-hint">{{
              missingHintFor(item.row)
            }}</span>
            <span v-else class="row-ok">信息完整</span>
          </div>
        </div>

        <div class="resolve-form">
          <div class="year-row">
            <label class="year-label">
              快捷默认年份
              <input
                v-model.number="resolveYear"
                type="number"
                min="2000"
                max="2100"
                placeholder="如 2026"
              />
            </label>
            <div class="year-chips">
              <button
                v-for="y in quickYears"
                :key="y"
                type="button"
                class="chip-btn"
                :class="{ active: resolveYear === y }"
                @click="resolveYear = y"
              >
                {{ y }} 年
              </button>
              <button
                type="button"
                class="chip-btn"
                :class="{ active: resolveYear === null }"
                @click="resolveYear = null"
              >
                不设默认年份
              </button>
            </div>
          </div>

          <label class="instr-label">
            告诉智能体具体情况（可选，支持多行自然语言）
            <textarea
              v-model="resolveInstruction"
              rows="3"
              placeholder="例如：前7笔都是2026年，第8笔是2026年11月1日 12:00；第2笔转账给刘家铭归类为其他"
            />
          </label>
          <div class="quick-prompts">
            <span>快捷示例：</span>
            <button
              type="button"
              class="link-chip"
              @click="
                resolveInstruction =
                  '只缺年份的按默认年份补全；如某笔未写具体日期请保持待填写'
              "
            >
              仅补全缺年份行
            </button>
            <button
              type="button"
              class="link-chip"
              @click="
                resolveInstruction = `前${Math.max(1, rows.length - 1)}笔是${resolveYear ?? new Date().getFullYear()}年，最后一笔是${resolveYear ?? new Date().getFullYear()}年11月1日 12:00`
              "
            >
              前几笔同年 + 指定末笔日期
            </button>
          </div>
        </div>

        <div class="dialog-actions">
          <button
            type="button"
            class="secondary-btn"
            :disabled="resolveBusy"
            @click="resolveOpen = false"
          >
            先手动填写
          </button>
          <button
            v-if="
              missingYearCount > 0 &&
              resolveYear !== null &&
              resolveInstruction.trim()
            "
            type="button"
            class="secondary-btn"
            :disabled="resolveBusy"
            @click="submitResolveMissing(true)"
          >
            仅用 {{ resolveYear }} 年快捷补全
          </button>
          <button
            type="button"
            class="primary-btn"
            :disabled="resolveBusy"
            @click="submitResolveMissing(false)"
          >
            {{ resolveBusy ? "智能体补全中…" : "确认并智能补全" }}
          </button>
        </div>
      </section>
    </div></template
  >
  <div
    v-if="dupModalOpen && batch"
    class="modal-backdrop"
    @click.self="!busy && (dupModalOpen = false)"
  >
    <section
      class="edit-dialog resolve-dialog dup-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="已录入或重复账单提醒"
    >
      <div class="dialog-head">
        <div>
          <h2 class="dup-dialog-title">
            <AlertTriangle :size="18" /> 检测到已录入或重复账单
          </h2>
          <p>{{ dupModalHint }}</p>
        </div>
        <button
          class="icon-btn"
          aria-label="关闭"
          :disabled="busy"
          @click="dupModalOpen = false"
        >
          <X :size="20" />
        </button>
      </div>

      <div v-if="dupBatchMatch" class="dup-modal-filebox">
        <strong>{{
          dupBatchMatch.match_type === "exact_file"
            ? "上传原件与历史批次完全一致"
            : "上传截图与历史批次高度相似"
        }}</strong>
        <p>
          历史上传「{{ dupBatchMatch.file_name }}」（{{
            formatShortDate(dupBatchMatch.created_at)
          }}，{{ statusLabel[dupBatchMatch.status] }}，已入账
          {{ dupBatchMatch.created_count }} 笔）。
        </p>
      </div>

      <div v-if="dupModalItems.length" class="dup-modal-list">
        <div
          v-for="item in dupModalItems"
          :key="item.row_id"
          class="dup-modal-item"
          :class="item.duplicate_status"
        >
          <div class="dup-item-top">
            <span class="row-num">第 {{ item.index + 1 }} 笔</span>
            <strong class="row-merchant">{{ item.merchant }}</strong>
            <span class="row-amt">¥{{ item.amount }}</span>
            <span class="small-tag warn">
              {{
                item.duplicate_status === "duplicate"
                  ? "明确已入账"
                  : "疑似重复"
              }}
            </span>
          </div>
          <p class="dup-item-meta">
            当前编辑时间：{{ item.occurred_at }}
            <template v-if="item.matched_summary">
              · 命中已入账记录：<strong>{{ item.matched_summary }}</strong>
            </template>
          </p>
          <p class="dup-item-reason">{{ item.reason }}</p>
          <div
            v-if="item.duplicate_status === 'suspected'"
            class="dup-item-controls"
          >
            <label v-if="findEditableByRowId(item.row_id)" class="check-label">
              <input
                v-model="findEditableByRowId(item.row_id)!.selected"
                type="checkbox"
                @change="edited(item.row_id)"
              />
              <span>选中此笔（取消勾选可跳过不入账）</span>
            </label>
            <label
              v-if="
                findEditableByRowId(item.row_id)?.selected
              "
              class="suspect-check"
            >
              <input
                v-model="
                  findEditableByRowId(item.row_id)!.allow_suspected_duplicate
                "
                type="checkbox"
              />
              <span>我已核对，确认仍要作为新交易入账</span>
            </label>
          </div>
        </div>
      </div>
      <div v-else class="dup-modal-empty">
        当前选中待入账明细未直接命中已入账交易（可能原批次仍处于草稿状态，或你已取消勾选重复行）。
      </div>

      <div class="dialog-actions">
        <button
          type="button"
          class="secondary-btn"
          :disabled="busy"
          @click="dupModalOpen = false"
        >
          返回列表修改
        </button>
        <button
          type="button"
          class="secondary-btn"
          :disabled="busy"
          @click="router.push('/transactions')"
        >
          查看已入账单
        </button>
        <button
          v-if="
            ready &&
            selected.length > 0 &&
            !invalid.length &&
            !hasUnallowedSuspectedSelected
          "
          type="button"
          class="primary-btn"
          :disabled="busy"
          @click="confirm(true)"
        >
          {{
            busy ? "正在确认…" : `确认提交剩余 ${selected.length} 笔`
          }}
        </button>
      </div>
    </section>
  </div>
  <div
    v-if="originalZoomed && originalUrl && batch"
    class="modal-backdrop"
    @click.self="originalZoomed = false"
  >
    <section
      class="edit-dialog zoom-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="原始截图预览"
    >
      <div class="dialog-head">
        <div>
          <h2>原始截图对照</h2>
          <p>{{ batch.file_name }}</p>
        </div>
        <button
          class="icon-btn"
          aria-label="关闭"
          @click="originalZoomed = false"
        >
          <X :size="20" />
        </button>
      </div>
      <div class="zoom-frame">
        <img :src="originalUrl" :alt="batch.file_name" />
      </div>
    </section>
  </div>
</template>
<style scoped>
.original-preview {
  margin-top: 16px;
  display: grid;
  gap: 8px;
}
.original-preview-btn {
  display: block;
  width: 100%;
  padding: 6px;
  background: #f4f8f7;
  border: 1px solid #d7e5e1;
  border-radius: 12px;
  overflow: hidden;
  cursor: zoom-in;
  transition: border-color 0.18s ease;
}
.original-preview-btn:hover {
  border-color: #087f78;
}
.original-preview-btn img {
  display: block;
  width: 100%;
  max-height: 440px;
  object-fit: contain;
  border-radius: 8px;
}
.original-caption {
  margin: 0;
  font-size: 11px;
  color: #6b8180;
  text-align: center;
  overflow-wrap: anywhere;
}
.zoom-dialog {
  width: min(94vw, 820px);
  max-height: 92vh;
  overflow-y: auto;
}
.zoom-frame {
  background: #f4f8f7;
  border: 1px solid #d7e5e1;
  border-radius: 12px;
  padding: 8px;
  text-align: center;
}
.zoom-frame img {
  max-width: 100%;
  max-height: 75vh;
  object-fit: contain;
  border-radius: 8px;
}
.progress-track.indeterminate {
  overflow: hidden;
}
.progress-track.indeterminate span {
  width: 38%;
  animation: progressIndeterminate 1.4s ease-in-out infinite;
}
@keyframes progressIndeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(280%);
  }
}
.continue-wait-btn {
  margin: 18px auto 0;
}
.draft-row.has-error {
  border-color: #d97c83;
  background: #fff9f9;
}
.row-reason {
  margin: 10px 0 0;
  font-size: 11px;
  color: #5b7572;
}
.row-field-error {
  margin: 6px 0 0;
  font-size: 11px;
  color: #c62828;
  font-weight: 500;
}
.ai-trigger-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.ai-trigger-btn.highlight {
  border-color: #7cc9bb;
  background: #edf8f4;
  color: #087f78;
}
.resolve-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #edf8f4;
  border: 1px solid #b8e3d9;
  border-radius: 14px;
}
.resolve-banner strong {
  display: block;
  margin-bottom: 4px;
  color: #0f5c55;
  font-size: 13px;
}
.resolve-banner p {
  margin: 0;
  color: #3f6360;
  font-size: 12px;
}
.resolve-banner .primary-btn {
  flex: none;
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
}
.resolve-dialog {
  width: min(100%, 680px);
  max-height: 90vh;
  overflow-y: auto;
}
.resolve-title {
  display: flex;
  align-items: center;
  gap: 7px;
}
.resolve-preview {
  display: grid;
  gap: 6px;
  max-height: 184px;
  overflow-y: auto;
  margin: 14px 0;
  padding: 10px 12px;
  background: #f6faf8;
  border: 1px solid #e1ece8;
  border-radius: 12px;
}
.resolve-preview-row {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 78px auto;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  padding: 4px 6px;
  border-radius: 8px;
}
.resolve-preview-row.missing {
  background: #fff9f0;
}
.row-num {
  color: #6b7280;
  font-weight: 600;
}
.row-merchant {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.row-amt {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.row-hint {
  color: #c25e00;
  font-size: 11px;
  background: #ffefd6;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.row-ok {
  color: #18794e;
  font-size: 11px;
  background: #e6f6ee;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.resolve-form {
  display: grid;
  gap: 12px;
}
.year-row {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
}
.year-label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #4b5563;
}
.year-label input {
  width: 118px;
  height: 36px;
  padding: 0 10px;
  border: 1px solid #d5dbe2;
}
.year-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip-btn {
  height: 34px;
  padding: 0 11px;
  border: 1px solid #d9dfe6;
  border-radius: 10px;
  background: #fff;
  color: #374151;
  font-size: 12px;
  font-weight: 500;
}
.chip-btn.active {
  border-color: #087f78;
  background: #e5f5f0;
  color: #0a6b65;
}
.instr-label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #4b5563;
}
.instr-label textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d5dbe2;
  border-radius: 12px;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
}
.instr-label textarea:focus {
  border-color: #087f78;
  box-shadow: 0 0 0 4px rgba(8, 127, 120, 0.14);
  outline: none;
}
.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #6b7280;
}
.link-chip {
  padding: 3px 9px;
  border: 1px dashed #8ad4c7;
  border-radius: 999px;
  background: #f1faf7;
  color: #087f78;
  font-size: 11px;
}
@media (max-width: 640px) {
  .resolve-banner {
    flex-direction: column;
    align-items: flex-start;
  }
  .resolve-preview-row {
    grid-template-columns: 52px minmax(0, 1fr) auto;
  }
  .resolve-preview-row .row-amt {
    text-align: left;
  }
  .resolve-preview-row .row-hint,
  .resolve-preview-row .row-ok {
    grid-column: 1 / -1;
    justify-self: start;
  }
}
.panel-heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.dup-batch-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
  background: #fff6e6;
  border: 1px solid #f0be6b;
  color: #7c4a03;
}
.dup-batch-copy strong {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  margin-bottom: 4px;
}
.dup-batch-copy p {
  margin: 0;
  font-size: 12px;
  color: #8a5a12;
}
.dup-batch-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.dup-batch-actions .secondary-btn {
  text-decoration: none;
  background: #fff;
  border: 1px solid #e3b25a;
  color: #7c4a03;
  height: 34px;
  padding: 0 12px;
}
.dup-rows-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  background: #fff4ec;
  border: 1px solid #f3b589;
  color: #8f3c07;
  margin-bottom: 14px;
}
.dup-rows-banner strong {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
}
.dup-rows-banner p {
  margin: 0;
  font-size: 12px;
}
.dup-rows-banner .secondary-btn {
  flex: none;
  text-decoration: none;
  background: #fff;
  border: 1px solid #e79e69;
  color: #8f3c07;
  height: 34px;
  padding: 0 12px;
}
.dup-dialog-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #b25200;
}
.dup-modal-filebox {
  margin: 12px 0;
  padding: 12px 14px;
  background: #fff7ea;
  border: 1px solid #f3c87d;
  border-radius: 10px;
  font-size: 12px;
  color: #7c4a03;
}
.dup-modal-filebox p {
  margin: 4px 0 0;
}
.dup-modal-list {
  display: grid;
  gap: 10px;
  max-height: 320px;
  overflow-y: auto;
  margin: 14px 0;
}
.dup-modal-item {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid #eed2a4;
  background: #fffcf6;
}
.dup-modal-item.duplicate {
  border-color: #f0b0ab;
  background: #fff7f6;
}
.dup-item-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.dup-item-meta,
.dup-item-reason {
  margin: 6px 0 0;
  font-size: 12px;
  color: #55676b;
}
.dup-item-controls {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e9d4ad;
  font-size: 12px;
}
.dup-modal-empty {
  padding: 14px;
  margin: 12px 0;
  border-radius: 10px;
  background: #f5f9f8;
  font-size: 12px;
  color: #4a6368;
}
</style>
