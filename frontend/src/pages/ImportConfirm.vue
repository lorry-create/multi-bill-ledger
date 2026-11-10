<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, RefreshCw, ExternalLink } from "@lucide/vue";
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
  elapsed = ref(0);
let timer: ReturnType<typeof setTimeout> | undefined;
let retryPayload: ConfirmInput | null = null;
const ready = computed(() => batch.value?.status === "pending_review");
const selected = computed(() => rows.value.filter((r) => r.selected));
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
    </div></template
  >
</template>
