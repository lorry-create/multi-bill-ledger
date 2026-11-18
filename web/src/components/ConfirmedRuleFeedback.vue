<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api, ApiError } from "../api";
import type { Source, Transaction } from "../api";
import { categories } from "../format";
import { errorText, withCsrfRetry } from "../session";

const props = defineProps<{
  batchId: string;
  transactionIds: string[];
  source: Source;
  dateFrom: string;
  dateTo: string;
}>();

const candidates = ref<Transaction[]>([]);
const saved = ref(new Set<string>());
const loading = ref(false);
const savingId = ref("");
const error = ref("");
let active = true;

async function load() {
  loading.value = true;
  error.value = "";
  const remaining = new Set(props.transactionIds);
  const matched: Transaction[] = [];
  const pageSize = 100;
  try {
    for (let page = 1; remaining.size; page++) {
      const result = await api.listTransactions({
        query: {
          source: props.source,
          date_from: props.dateFrom,
          date_to: props.dateTo,
          page,
          page_size: pageSize,
        },
      });
      if (!active) return;
      for (const item of result.items) {
        if (
          item.import_batch_id !== props.batchId ||
          !remaining.delete(item.id)
        )
          continue;
        if (
          item.classification_source === "manual" &&
          item.category !== "pending" &&
          item.merchant.trim()
        ) {
          matched.push(item);
        }
      }
      if (!result.items.length || page * pageSize >= result.total) break;
    }
    candidates.value = matched;
  } catch (cause) {
    error.value = errorText(cause);
  } finally {
    loading.value = false;
  }
}

async function remember(item: Transaction) {
  if (savingId.value || saved.value.has(item.id)) return;
  savingId.value = item.id;
  error.value = "";
  try {
    await withCsrfRetry((token) =>
      api.patchTransaction(
        {
          path: { id: item.id },
          body: {
            changes: { category: item.category },
            expected_version: item.version,
            remember_rule: true,
          },
        },
        token,
      ),
    );
    saved.value.add(item.id);
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 409) {
      await load();
      if (!error.value)
        error.value = "账单刚刚更新。请核对最新分类后再保存规则。";
    } else {
      error.value = errorText(cause);
    }
  } finally {
    savingId.value = "";
  }
}
onMounted(load);
onUnmounted(() => {
  active = false;
});
</script>

<template>
  <section
    class="confirmed-feedback"
    aria-labelledby="confirmed-feedback-title"
  >
    <div class="confirmed-feedback-heading">
      <h2 id="confirmed-feedback-title">记住本次修正</h2>
      <RouterLink to="/rules" class="text-btn">查看分类规则</RouterLink>
    </div>
    <p>同一平台下次识别到这个商户时，会优先用你保存的类别。</p>
    <p v-if="loading" role="status">正在读取已入账的分类…</p>
    <p v-else-if="!candidates.length && !error">
      本次新增账单中没有可记住的手动分类。
    </p>
    <div v-if="error" class="alert error" role="alert">
      {{ error }}
      <button type="button" :disabled="loading || !!savingId" @click="load">
        重新读取
      </button>
    </div>
    <ul v-if="candidates.length">
      <li v-for="item in candidates" :key="item.id">
        <span
          ><strong>{{ item.merchant }}</strong
          ><small>{{ categories[item.category] }}</small></span
        >
        <span v-if="saved.has(item.id)" role="status">已保存</span>
        <button
          v-else
          class="secondary-btn"
          type="button"
          :disabled="!!savingId || loading"
          @click="remember(item)"
        >
          {{ savingId === item.id ? "保存中…" : "记住分类" }}
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.confirmed-feedback {
  margin: 14px 0 22px;
  padding: 17px 20px;
  border: 1px solid #d7e5f6;
  border-radius: 12px;
  background: #f8fbff;
}
.confirmed-feedback-heading,
.confirmed-feedback li {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}
.confirmed-feedback h2 {
  margin: 0;
  font-size: 17px;
}
.confirmed-feedback p {
  margin: 6px 0 10px;
  color: #506b86;
  font-size: 13px;
}
.confirmed-feedback ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.confirmed-feedback li {
  border-top: 1px solid #dce7f4;
  padding-block: 9px;
}
.confirmed-feedback li strong {
  overflow-wrap: anywhere;
}
.confirmed-feedback li small {
  display: block;
  margin-top: 3px;
  color: #506b86;
}
.confirmed-feedback li button {
  flex: none;
}
</style>
