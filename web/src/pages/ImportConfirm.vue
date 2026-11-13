<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
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
import {
  categories,
  flows,
  fromLocalInput,
  parseYuan,
  sources,
  toLocalInput,
} from "../format";
import { csrf, errorText } from "../session";

type Editable = {
  row: TransactionDraft;
  selected: boolean;
  occurred_at: string;
  amount: string;
  flow_type: FlowType | null;
  merchant: string;
  category: Category;
  allow_suspected_duplicate: boolean;
};
const route = useRoute(),
  router = useRouter(),
  batch = ref<Batch | null>(null),
  rows = ref<Editable[]>([]),
  busy = ref(false),
  error = ref(""),
  notice = ref(""),
  originalUrl = ref(""),
  elapsed = ref(0),
  resolveOpen = ref(false),
  resolveBusy = ref(false),
  resolveYear = ref<number | null>(new Date().getFullYear()),
  resolveInstruction = ref(""),
  resolveError = ref(""),
  promptAutoShownFor = ref<string>("");
let timer: ReturnType<typeof setTimeout> | undefined;
let retryPayload: ConfirmInput | null = null;
const ready = computed(() => batch.value?.status === "pending_review");
const selected = computed(() => rows.value.filter((r) => r.selected));
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
  selected.value.filter(
    (r) => !r.occurred_at || parseYuan(r.amount) === null || !r.flow_type,
  ),
);
function fill(b: Batch, preserve = false) {
  batch.value = b;
  if (!preserve)
    rows.value = b.rows.map((row) => ({
      row,
      selected:
        row.duplicate_status === "unique" &&
        !!row.occurred_at &&
        row.amount_fen !== null &&
        !!row.flow_type,
      occurred_at: toLocalInput(row.occurred_at),
      amount: row.amount_fen === null ? "" : (row.amount_fen / 100).toFixed(2),
      flow_type: row.flow_type,
      merchant: row.merchant,
      category: row.category,
      allow_suspected_duplicate: false,
    }));
}
async function load(preserve = false) {
  try {
    const b = await api.getImport({ path: { id: String(route.params.id) } });
    fill(b, preserve);
    if (
      b.status === "pending_review" &&
      promptAutoShownFor.value !== b.id &&
      b.rows.some((row) => !row.occurred_at)
    ) {
      promptAutoShownFor.value = b.id;
      openResolveModal();
    }
    if (["uploaded", "processing"].includes(b.status) && elapsed.value < 120) {
      timer = setTimeout(
        () => {
          elapsed.value += 2;
          load();
        },
        elapsed.value ? 2000 : 1000,
      );
    }
  } catch (e) {
    error.value = errorText(e);
  }
}
onMounted(() => load());
onUnmounted(() => {
  clearTimeout(timer);
  if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
});
function edited() {
  retryPayload = null;
  notice.value = "";
}
async function original() {
  try {
    const blob = await api.getImportOriginal({
      path: { id: String(route.params.id) },
    });
    if (originalUrl.value) URL.revokeObjectURL(originalUrl.value);
    originalUrl.value = URL.createObjectURL(blob);
    window.open(originalUrl.value, "_blank", "noopener");
  } catch (e) {
    error.value = errorText(e);
  }
}
async function retry() {
  if (!batch.value) return;
  busy.value = true;
  try {
    fill(
      await api.retryImport(
        {
          path: { id: batch.value.id },
          body: { expected_version: batch.value.version },
        },
        csrf(),
      ),
    );
    error.value = "";
    load(true);
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) load();
  } finally {
    busy.value = false;
  }
}
async function confirm() {
  if (
    !batch.value ||
    !ready.value ||
    !selected.value.length ||
    invalid.value.length
  )
    return;
  busy.value = true;
  error.value = "";
  try {
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
            merchant: r.merchant,
            description: r.row.description,
            category: r.category,
          },
        })),
      };
    const result = await api.confirmImport(
      { path: { id: batch.value.id }, body: retryPayload },
      csrf(),
    );
    notice.value = `已入账 ${result.created_count} 笔，跳过重复 ${result.duplicate_count} 笔，忽略 ${result.ignored_count} 笔。`;
    await load(true);
    retryPayload = null;
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) {
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
  rows.value = updated.rows.map((newRow) => {
    const prevRow = prevById.get(newRow.row_id);
    const local = localById.get(newRow.row_id);
    const serverTimeChanged =
      !prevRow || newRow.occurred_at !== prevRow.occurred_at;
    const serverCatChanged = !prevRow || newRow.category !== prevRow.category;
    const serverFlowChanged =
      !prevRow || newRow.flow_type !== prevRow.flow_type;

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
    const validForSelect =
      newRow.duplicate_status === "unique" &&
      !!occurred_at &&
      Number(amount) > 0 &&
      !!flow_type;
    return {
      row: newRow,
      selected: validForSelect,
      occurred_at,
      amount,
      flow_type,
      merchant,
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
    const updated = await api.resolveImportMissing(
      {
        path: { id: batch.value.id },
        body: {
          expected_version: batch.value.version,
          default_year: yearVal,
          instruction: instr || null,
        },
      },
      csrf(),
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
    <button class="secondary-btn" @click="load(true)">
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
            ? "自动刷新已暂停，请稍后手动刷新。"
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
    </div>
    <div v-if="ready || batch.status === 'completed'" class="confirm-layout">
      <aside class="original-panel">
        <div class="panel-heading">
          <h2>原始来源</h2>
          <button class="text-btn" @click="original">
            查看原文件 <ExternalLink :size="14" />
          </button>
        </div>
        <div class="original-placeholder">
          <span>{{
            batch.ingestion_method === "file" ? "CSV / XLSX" : "PNG / JPEG"
          }}</span
          ><strong>{{ batch.file_name }}</strong>
          <p>
            {{
              isDemo
                ? "合成数据演示不包含原始文件"
                : "点击上方查看原始内容，对照右侧逐笔核对。"
            }}
          </p>
        </div>
        <div class="issue-list" v-if="batch.issues.length">
          <h3>批次提示</h3>
          <p v-for="issue in batch.issues" :key="issue.code + issue.row_id">
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
            class="draft-row"
          >
            <div class="draft-top">
              <label class="check-label"
                ><input
                  v-model="r.selected"
                  type="checkbox"
                  :disabled="
                    batch.status === 'completed' ||
                    r.row.duplicate_status === 'duplicate'
                  "
                  @change="edited"
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
                r.row.classification_source === "user_rule"
                  ? "个人规则"
                  : r.row.classification_source === "deepseek"
                    ? "智能分类"
                    : "识别结果"
              }}</span>
            </div>
            <div class="draft-fields">
              <label
                >交易时间<input
                  type="datetime-local"
                  v-model="r.occurred_at"
                  :disabled="batch.status === 'completed'"
                  @input="edited" /></label
              ><label
                >金额（元）<input
                  v-model="r.amount"
                  inputmode="decimal"
                  placeholder="如 23.00"
                  :disabled="batch.status === 'completed'"
                  @input="edited" /></label
              ><label
                >收支方向<select
                  v-model="r.flow_type"
                  :disabled="batch.status === 'completed'"
                  @change="edited"
                >
                  <option :value="null">请选择</option>
                  <option v-for="(label, key) in flows" :key="key" :value="key">
                    {{ label }}
                  </option>
                </select></label
              ><label
                >商户<input
                  v-model="r.merchant"
                  :disabled="batch.status === 'completed'"
                  @input="edited" /></label
              ><label
                >类别<select
                  v-model="r.category"
                  :disabled="batch.status === 'completed'"
                  @change="edited"
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
            <p v-if="r.row.issues.length" class="row-issue">
              {{ r.row.issues.map((x) => x.message).join("；") }}
            </p>
            <label
              v-if="r.row.duplicate_status === 'suspected' && r.selected"
              class="suspect-check"
              ><input
                v-model="r.allow_suspected_duplicate"
                type="checkbox"
                @change="edited"
              />
              我已核对，仍要将这笔疑似重复交易入账</label
            >
          </article>
        </div>
        <div class="confirm-footer">
          <p v-if="invalid.length">
            已选记录中有 {{ invalid.length }} 笔缺少时间、金额或收支方向。
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
              selected.some(
                (x) =>
                  x.row.duplicate_status === 'suspected' &&
                  !x.allow_suspected_duplicate,
              ) ||
              busy
            "
            @click="confirm"
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
</template>
<style scoped>
.ai-trigger-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.ai-trigger-btn.highlight {
  border-color: #7bbcff;
  background: #f0f7ff;
  color: #006ee6;
}
.resolve-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f3f9ff;
  border: 1px solid #cce3ff;
  border-radius: 14px;
}
.resolve-banner strong {
  display: block;
  margin-bottom: 4px;
  color: #005bb8;
  font-size: 13px;
}
.resolve-banner p {
  margin: 0;
  color: #46617b;
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
  background: #f8fafc;
  border: 1px solid #e7ebf0;
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
  border-color: #007aff;
  background: #eaf4ff;
  color: #006ee6;
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
  border-color: #007aff;
  box-shadow: 0 0 0 4px rgba(0, 122, 255, 0.11);
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
  border: 1px dashed #b9d6fa;
  border-radius: 999px;
  background: #f5f9ff;
  color: #006ee6;
  font-size: 11px;
}
</style>
