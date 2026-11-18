<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ChevronDown, Download } from "@lucide/vue";
import { api, ApiError, isDemo } from "../api";
import type { Batch, Transaction, TransactionDraft } from "../api";
import {
  categories,
  classificationSources,
  dateTime,
  download,
  flows,
  sources,
  yuan,
} from "../format";
import { errorText } from "../session";
import PlatformLogo from "./PlatformLogo.vue";

const { transaction, initiallyOpen = false } = defineProps<{
  transaction: Transaction;
  initiallyOpen?: boolean;
}>();
const batch = ref<Batch | null>(null);
const batchLoading = ref(false);
const batchError = ref("");
const originalLoading = ref(false);
const originalError = ref("");
const fileNameKnown = computed(() =>
  Boolean(batch.value?.file_name && batch.value.file_name !== "未知文件"),
);
let active = true;
onMounted(() => {
  if (initiallyOpen) void loadBatch();
});
onBeforeUnmount(() => {
  active = false;
});

const draft = computed(() => {
  if (!batch.value || !transaction.source_transaction_id) return null;
  const matches = batch.value.rows.filter(
    (row) => row.source_transaction_id === transaction.source_transaction_id,
  );
  return matches.length === 1 ? matches[0] : null;
});

function displayFields(value: Transaction | TransactionDraft) {
  return {
    商户: value.merchant || "未填写",
    交易描述: value.description || "未填写",
    交易时间: value.occurred_at ? dateTime(value.occurred_at) : "未识别",
    金额: value.amount_fen === null ? "未识别" : yuan(value.amount_fen),
    收支: value.flow_type ? flows[value.flow_type] : "未识别",
    类别: categories[value.category],
  };
}
const comparison = computed(() => {
  const saved = displayFields(transaction);
  const imported = draft.value ? displayFields(draft.value) : null;
  return (Object.keys(saved) as (keyof typeof saved)[])
    .map((field) => ({
      field,
      saved: saved[field],
      imported: imported?.[field],
      changed: imported !== null && saved[field] !== imported[field],
    }))
    .sort((a, b) => Number(b.changed) - Number(a.changed));
});
const differenceCount = computed(
  () => comparison.value.filter((row) => row.changed).length,
);

async function loadBatch() {
  if (
    isDemo ||
    !transaction.import_batch_id ||
    batch.value ||
    batchLoading.value
  )
    return;
  batchLoading.value = true;
  batchError.value = "";
  try {
    const result = await api.getImport({
      path: { id: transaction.import_batch_id },
    });
    if (!active) return;
    if (
      result.id === transaction.import_batch_id &&
      result.source === transaction.source
    )
      batch.value = result;
    else batchError.value = "无法确认原导入批次。";
  } catch (error) {
    if (!active) return;
    batchError.value =
      error instanceof ApiError && error.status === 404
        ? "原导入批次不可用。"
        : errorText(error);
  } finally {
    if (active) batchLoading.value = false;
  }
}

async function downloadOriginal() {
  if (!batch.value || originalLoading.value) return;
  const source = batch.value;
  originalLoading.value = true;
  originalError.value = "";
  try {
    const file = await api.getImportOriginal({ path: { id: source.id } });
    if (active) download(file, source.file_name || "原始账单");
  } catch (error) {
    if (!active) return;
    originalError.value =
      error instanceof ApiError && error.status === 404
        ? "此批次没有可下载的原件。"
        : errorText(error);
  } finally {
    if (active) originalLoading.value = false;
  }
}

function onToggle(event: Event) {
  if ((event.currentTarget as HTMLDetailsElement).open && !batchError.value)
    void loadBatch();
}
</script>

<template>
  <details
    class="transaction-evidence"
    :open="initiallyOpen"
    @toggle="onToggle"
  >
    <summary>
      <PlatformLogo :source="transaction.source" :size="23" />
      <span class="evidence-summary">
        <strong>来源与原件</strong>
        <small
          >{{ sources[transaction.source] }} · 已保存 v{{
            transaction.version
          }}</small
        >
      </span>
      <ChevronDown class="evidence-chevron" :size="16" />
    </summary>
    <div class="evidence-content">
      <p v-if="isDemo">合成演示账单没有原件或可核对的导入草稿。</p>
      <p v-else-if="!transaction.import_batch_id">
        这笔账单没有关联的导入批次。
      </p>
      <p v-else-if="batchLoading" role="status">正在读取导入批次…</p>
      <div v-else-if="batchError" class="evidence-file">
        <p role="status">{{ batchError }}</p>
        <button class="text-btn" type="button" @click="loadBatch">重试</button>
      </div>
      <template v-else-if="batch">
        <div v-if="fileNameKnown" class="evidence-file">
          <strong>{{ batch.file_name }}</strong>
          <button
            class="secondary-btn"
            type="button"
            :disabled="originalLoading"
            @click="downloadOriginal"
          >
            <Download :size="15" />
            {{
              originalLoading
                ? "正在读取…"
                : batch.ingestion_method === "screenshot"
                  ? "下载原始截图"
                  : "下载原始文件"
            }}
          </button>
        </div>
        <div v-else class="evidence-file">
          <p>此批次未提供原件名称。</p>
          <button
            v-if="!originalError"
            class="text-btn"
            type="button"
            :disabled="originalLoading"
            @click="downloadOriginal"
          >
            {{ originalLoading ? "正在检查…" : "检查原件" }}
          </button>
        </div>
        <p v-if="originalError" role="status">{{ originalError }}</p>
        <p v-if="draft">
          {{
            differenceCount
              ? differenceCount + " 项与导入草稿不同"
              : "核对字段与导入草稿一致"
          }}
          · 按平台交易号匹配
        </p>
        <p v-else>此笔账单没有可对照的导入草稿。</p>
      </template>

      <table v-if="draft" class="evidence-comparison" aria-label="账单核对值">
        <thead>
          <tr>
            <th scope="col">字段</th>
            <th scope="col">导入草稿</th>
            <th scope="col">已保存 v{{ transaction.version }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in comparison" :key="row.field">
            <th scope="row">{{ row.field }}</th>
            <td>{{ row.imported }}</td>
            <td :class="{ 'evidence-changed': row.changed }">
              {{ row.saved }}
              <span v-if="row.changed" class="sr-only">与导入草稿不同</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p>
        分类来源：{{ classificationSources[transaction.classification_source] }}
      </p>
    </div>
  </details>
</template>

<style scoped>
.transaction-evidence {
  margin-top: 18px;
  border: 1px solid #dbe6f4;
  border-radius: 13px;
  background: #f5f9ff;
  color: #405a78;
  font-size: 12px;
}

.transaction-evidence summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 9px 12px;
  border-radius: inherit;
  cursor: pointer;
  list-style: none;
}

.transaction-evidence summary::-webkit-details-marker {
  display: none;
}
.transaction-evidence[open] .evidence-chevron {
  transform: rotate(180deg);
}
.evidence-chevron {
  transition: transform 0.22s var(--ease-arrive);
}
.evidence-summary {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 5px 10px;
  flex-wrap: wrap;
}
.evidence-summary strong,
.evidence-file strong {
  color: var(--ink);
}
.evidence-summary small {
  font-size: 11px;
}
.evidence-content {
  padding: 4px 12px 12px;
}
.evidence-content p {
  margin: 6px 0;
  line-height: 1.65;
}
.evidence-file {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 6px 10px;
}
.evidence-file strong {
  overflow-wrap: anywhere;
}
.evidence-comparison {
  table-layout: fixed;
  margin-block: 8px;
}
.evidence-comparison th,
.evidence-comparison td {
  padding: 7px 4px;
  white-space: normal;
  overflow-wrap: anywhere;
  color: #405a78;
}
.evidence-comparison th {
  background: transparent;
}
.evidence-comparison th:first-child {
  width: 65px;
}
.evidence-comparison tbody th {
  border-top: 1px solid #e4edf8;
}
.evidence-comparison .evidence-changed {
  color: #215aa6;
  font-weight: 650;
}
</style>
