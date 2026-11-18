<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, computed } from "vue";
import { useRoute } from "vue-router";
import {
  ChevronDown,
  Download,
  ListFilter,
  Plus,
  Pencil,
  ReceiptText,
  WalletCards,
  X,
} from "@lucide/vue";
import { api } from "../api";
import type {
  Category,
  FlowType,
  Source,
  Transaction,
  TransactionPatch,
  TransactionPage,
} from "../api";
import {
  categories,
  classificationSources,
  dateTime,
  download,
  flows,
  parseYuan,
  sources,
  toLocalInput,
  fromLocalInput,
  yuan,
} from "../format";
import { errorText, withCsrfRetry } from "../session";
import PlatformLogo from "../components/PlatformLogo.vue";
import ParticleField from "../components/ParticleField.vue";
import { notify } from "../motion";

const PAGE_SIZE = 50;
const platforms = ["", "wechat", "alipay"] as const;
const route = useRoute();
const filters = reactive<{
  date_from: string;
  date_to: string;
  category: "" | Category;
  source: "" | Source;
  flow_type: "" | FlowType;
  page: number;
}>({
  date_from: String(route.query.date_from ?? ""),
  date_to: String(route.query.date_to ?? ""),
  category: String(route.query.category ?? "") as "" | Category,
  source: String(route.query.source ?? "") as "" | Source,
  flow_type: String(route.query.flow_type ?? "") as "" | FlowType,
  page: 1,
});
const data = ref<TransactionPage | null>(null),
  loading = ref(false),
  exporting = ref(false),
  error = ref(""),
  editing = ref<Transaction | null>(null),
  modalError = ref(""),
  conflictLatest = ref<Transaction | null>(null),
  saving = ref(false),
  remember = ref(false);
let listRequest = 0;
const edit = reactive({
  occurred_at: "",
  amount: "",
  merchant: "",
  description: "",
  category: "pending" as Category,
  flow_type: "expense" as FlowType,
});
const query = computed(() => ({
  date_from: filters.date_from || undefined,
  date_to: filters.date_to || undefined,
  category: filters.category || undefined,
  source: filters.source || undefined,
  flow_type: filters.flow_type || undefined,
}));
const advancedCount = computed(
  () =>
    [
      filters.date_from,
      filters.date_to,
      filters.category,
      filters.flow_type,
    ].filter(Boolean).length,
);
const advancedOpen = ref(
  advancedCount.value > 0 || window.matchMedia("(min-width: 761px)").matches,
);
const hasFilters = computed(
  () => advancedCount.value > 0 || Boolean(filters.source),
);
const editor = ref<HTMLDialogElement | null>(null);
const listFailed = ref(false);
const pageCount = computed(() =>
  Math.ceil((data.value?.total ?? 0) / PAGE_SIZE),
);
const numberFormat = new Intl.NumberFormat("zh-CN");
onMounted(load);
onUnmounted(() => {
  listRequest++;
});
async function load() {
  const request = ++listRequest;
  listFailed.value = false;
  if (
    filters.date_from &&
    filters.date_to &&
    filters.date_from > filters.date_to
  ) {
    error.value = "开始日期不能晚于结束日期。";
    data.value = null;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  const requestedQuery = {
    ...query.value,
    page: filters.page,
    page_size: PAGE_SIZE,
  };
  try {
    const result = await api.listTransactions({ query: requestedQuery });
    if (request === listRequest) data.value = result;
  } catch (e) {
    if (request === listRequest) {
      data.value = null;
      listFailed.value = true;
      error.value = errorText(e);
    }
  } finally {
    if (request === listRequest) loading.value = false;
  }
}
function selectPlatform(platform: "" | Source) {
  if (filters.source === platform && !listFailed.value) return;
  filters.source = platform;
  search();
}
function changePage(offset: number) {
  filters.page += offset;
  load();
}
function search() {
  filters.page = 1;
  load();
}
function clearFilters() {
  Object.assign(filters, {
    date_from: "",
    date_to: "",
    category: "",
    source: "",
    flow_type: "",
    page: 1,
  });
  load();
}
function fillEditFrom(t: Transaction) {
  edit.occurred_at = toLocalInput(t.occurred_at);
  edit.amount = (t.amount_fen / 100).toFixed(2);
  edit.merchant = t.merchant;
  edit.description = t.description;
  edit.category = t.category;
  edit.flow_type = t.flow_type;
}
function open(t: Transaction) {
  if (loading.value || editor.value?.open) return;
  editing.value = t;
  modalError.value = "";
  conflictLatest.value = null;
  fillEditFrom(t);
  remember.value = false;
  editor.value?.showModal();
}
function closeModal(saved = false) {
  if (saving.value && !saved) return;
  editor.value?.close();
  editing.value = null;
  modalError.value = "";
  conflictLatest.value = null;
}
function applyLatestConflict() {
  if (!conflictLatest.value) return;
  editing.value = conflictLatest.value;
  fillEditFrom(conflictLatest.value);
  conflictLatest.value = null;
  modalError.value = "";
}
async function save() {
  if (!editing.value) return;
  const amount = parseYuan(edit.amount);
  if (amount === null || !edit.occurred_at) {
    modalError.value = "请填写有效的交易时间和金额，金额最多两位小数。";
    return;
  }
  const orig = editing.value;
  const nextOccurred = fromLocalInput(edit.occurred_at);
  const nextMerchant = edit.merchant.trim();
  const nextDesc = edit.description.trim();
  if (remember.value && (!nextMerchant || edit.category === "pending")) {
    modalError.value = "记住商户规则需要先填写商户名称并选择具体分类。";
    return;
  }
  const changes: TransactionPatch["changes"] = {};
  if (nextOccurred !== fromLocalInput(toLocalInput(orig.occurred_at))) {
    changes.occurred_at = nextOccurred;
  }
  if (amount !== orig.amount_fen) changes.amount_fen = amount;
  if (nextMerchant !== orig.merchant) changes.merchant = nextMerchant;
  if (nextDesc !== orig.description) changes.description = nextDesc;
  if (edit.category !== orig.category) changes.category = edit.category;
  if (edit.flow_type !== orig.flow_type) changes.flow_type = edit.flow_type;

  if (!Object.keys(changes).length && !remember.value) {
    modalError.value = "未检测到字段改动。";
    return;
  }
  if (!Object.keys(changes).length && remember.value) {
    changes.category = edit.category;
  }

  saving.value = true;
  modalError.value = "";
  try {
    await withCsrfRetry((token) =>
      api.patchTransaction(
        {
          path: { id: orig.id },
          body: {
            expected_version: orig.version,
            changes,
            remember_rule: remember.value,
          },
        },
        token,
      ),
    );
    notify(
      remember.value
        ? "账单已更新，已记住该商户的分类"
        : "账单已更新，相关月报已同步",
    );
    closeModal(true);
    await load();
  } catch (e) {
    modalError.value = errorText(e);
    if ((e as { status?: number }).status === 409) {
      await load();
      const latest = data.value?.items.find((x) => x.id === orig.id) ?? null;
      conflictLatest.value = latest;
    }
  } finally {
    saving.value = false;
  }
}
async function exportCsv() {
  if (exporting.value) return;
  if (
    filters.date_from &&
    filters.date_to &&
    filters.date_from > filters.date_to
  ) {
    error.value = "开始日期不能晚于结束日期。";
    return;
  }
  exporting.value = true;
  error.value = "";
  try {
    const blob = await api.exportTransactions({ query: query.value });
    download(blob, "账单导出.csv");
    notify("当前筛选的全部账单已导出");
  } catch (e) {
    error.value = errorText(e);
  } finally {
    exporting.value = false;
  }
}
</script>
<template>
  <header class="ledger-heading" v-reveal>
    <div class="ledger-heading-copy">
      <h1>全部账单</h1>
      <p>核对、修正和导出已确认的交易。</p>
      <RouterLink to="/import" class="primary-btn"
        ><Plus :size="17" />导入账单</RouterLink
      >
    </div>
    <div class="ledger-illustration" aria-hidden="true">
      <ParticleField />
      <div class="ledger-plates">
        <span class="ledger-plate back"></span>
        <span class="ledger-plate middle"></span>
        <span class="ledger-plate front"
          ><WalletCards :size="23" :stroke-width="1.6"
        /></span>
      </div>
    </div>
  </header>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <section
    v-reveal="{ delay: 45 }"
    class="content-panel ledger-filter"
    aria-label="筛选账单"
  >
    <div class="ledger-filter-bar">
      <div
        class="ledger-platforms"
        role="group"
        aria-label="筛选平台"
        :style="{ '--platform-index': platforms.indexOf(filters.source) }"
      >
        <span class="ledger-platform-thumb" aria-hidden="true"></span>
        <button
          v-for="platform in platforms"
          :key="platform"
          type="button"
          :aria-pressed="filters.source === platform"
          @click="selectPlatform(platform)"
        >
          <PlatformLogo v-if="platform" :source="platform" :size="22" />
          {{ platform ? sources[platform] : "全部平台" }}
        </button>
      </div>
      <div class="ledger-filter-actions">
        <button
          class="ledger-filter-toggle"
          type="button"
          :aria-expanded="advancedOpen"
          aria-controls="ledger-advanced-filters"
          @click="advancedOpen = !advancedOpen"
        >
          <ListFilter :size="16" />更多筛选
          <span v-if="advancedCount" class="ledger-filter-count">{{
            advancedCount
          }}</span>
          <ChevronDown class="ledger-chevron" :size="15" />
        </button>
        <button
          v-if="hasFilters"
          class="ledger-clear"
          type="button"
          @click="clearFilters"
        >
          <X :size="15" />清除筛选
        </button>
      </div>
    </div>
    <div
      id="ledger-advanced-filters"
      class="ledger-filter-fold"
      :class="{ expanded: advancedOpen }"
      :inert="!advancedOpen"
    >
      <div class="ledger-filter-clip">
        <div class="filters ledger-fields">
          <label
            >开始日期<input
              v-model="filters.date_from"
              type="date"
              @change="search" /></label
          ><label
            >结束日期<input
              v-model="filters.date_to"
              type="date"
              @change="search" /></label
          ><label
            >类别<select v-model="filters.category" @change="search">
              <option value="">全部类别</option>
              <option
                v-for="(label, key) in categories"
                :key="key"
                :value="key"
              >
                {{ label }}
              </option>
            </select></label
          ><label
            >收支<select v-model="filters.flow_type" @change="search">
              <option value="">全部收支</option>
              <option v-for="(label, key) in flows" :key="key" :value="key">
                {{ label }}
              </option>
            </select></label
          >
        </div>
      </div>
    </div>
  </section>
  <section
    v-reveal="{ delay: 85 }"
    class="content-panel ledger-results"
    aria-labelledby="ledger-results-title"
  >
    <div class="ledger-results-head">
      <div>
        <h2 id="ledger-results-title">交易明细</h2>
        <p role="status">
          <template v-if="loading">正在更新账单…</template>
          <template v-else-if="data"
            >{{ hasFilters ? "符合筛选" : "共" }}
            {{ numberFormat.format(data.total) }} 笔</template
          >
          <template v-else>查看已确认的账单</template>
        </p>
      </div>
      <button
        class="secondary-btn ledger-export"
        type="button"
        :disabled="exporting || loading"
        aria-label="导出当前筛选"
        @click="exportCsv"
      >
        <Download :size="16" /> {{ exporting ? "导出中…" : "导出 CSV" }}
      </button>
    </div>
    <div class="ledger-results-content" :aria-busy="loading">
      <div v-if="data?.items.length" class="table-scroll ledger-table">
        <table>
          <thead>
            <tr>
              <th>交易</th>
              <th>时间</th>
              <th>平台</th>
              <th>类别</th>
              <th class="ledger-amount-heading">金额</th>
              <th><span class="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(t, index) in data.items"
              :key="t.id"
              v-reveal="index < 6 ? { type: 'row', delay: index * 27 } : false"
            >
              <td>
                <strong>{{ t.merchant || "未填写商户" }}</strong
                ><small
                  >{{ flows[t.flow_type]
                  }}{{ t.description ? ` · ${t.description}` : "" }}</small
                >
              </td>
              <td>{{ dateTime(t.occurred_at) }}</td>
              <td>
                <span class="transaction-source"
                  ><PlatformLogo :source="t.source" :size="23" />{{
                    sources[t.source]
                  }}</span
                >
              </td>
              <td>
                <span class="category-pill" :class="`category-${t.category}`">{{
                  categories[t.category]
                }}</span>
                <small class="source-note">{{
                  classificationSources[t.classification_source]
                }}</small>
              </td>
              <td class="money" :class="t.flow_type">
                {{
                  ["income", "refund"].includes(t.flow_type)
                    ? "+"
                    : t.flow_type === "expense"
                      ? "−"
                      : ""
                }}{{ yuan(t.amount_fen) }}
              </td>
              <td>
                <button
                  class="table-action"
                  type="button"
                  :aria-label="`编辑 ${t.merchant || '账单'}`"
                :aria-disabled="loading"
                  @click="open(t)"
                >
                  <Pencil :size="16" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="loading" class="ledger-loading" aria-hidden="true">
        <span v-for="line in 3" :key="line"></span>
      </div>
      <div v-else-if="listFailed" class="empty-state ledger-empty">
        <strong>账单暂时无法加载</strong>
        <button class="secondary-btn" type="button" @click="load">
          重新加载
        </button>
      </div>
      <div v-else-if="data" class="empty-state ledger-empty">
        <ReceiptText :size="24" />
        <strong>{{
          hasFilters ? "没有找到符合条件的账单" : "还没有已确认的账单"
        }}</strong>
        <button
          v-if="hasFilters"
          class="secondary-btn"
          type="button"
          @click="clearFilters"
        >
          清除筛选
        </button>
        <RouterLink v-else to="/import" class="text-btn">去导入账单</RouterLink>
      </div>
      <div v-if="data && pageCount > 1" class="pagination ledger-pagination">
        <span>每页 {{ PAGE_SIZE }} 笔</span>
        <div>
          <button
            type="button"
            :disabled="loading || filters.page <= 1"
            @click="changePage(-1)"
          >
            上一页</button
          ><span>{{ data.page }} / {{ pageCount }}</span
          ><button
            type="button"
            :disabled="loading || filters.page >= pageCount"
            @click="changePage(1)"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  </section>
  <Teleport to="body">
    <dialog
      ref="editor"
      class="edit-dialog ledger-editor"
      aria-labelledby="ledger-editor-title"
      @cancel.prevent="closeModal()"
      @click.self="closeModal()"
    >
      <div class="ledger-editor-body">
        <div class="dialog-head">
          <div>
            <h2 id="ledger-editor-title">修正账单</h2>
            <p>保存后，相关月报会按新内容重新计算。</p>
          </div>
          <button
            class="icon-btn"
            type="button"
            aria-label="关闭"
            :disabled="saving"
            autofocus
            @click="closeModal()"
          >
            <X :size="20" />
          </button>
        </div>
        <div v-if="modalError" class="alert error" role="alert">
          {{ modalError }}
          <button
            v-if="conflictLatest"
            type="button"
            @click="applyLatestConflict"
          >
            载入最新版本（v{{ conflictLatest.version }}）
          </button>
        </div>
        <div class="edit-grid">
          <label
            >交易时间<input
              v-model="edit.occurred_at"
              type="datetime-local" /></label
          ><label
            >金额（元）<input
              v-model="edit.amount"
              inputmode="decimal" /></label
          ><label>商户<input v-model="edit.merchant" /></label
          ><label
            >收支方向<select v-model="edit.flow_type">
              <option v-for="(label, key) in flows" :key="key" :value="key">
                {{ label }}
              </option>
            </select></label
          ><label
            >类别<select v-model="edit.category">
              <option
                v-for="(label, key) in categories"
                :key="key"
                :value="key"
              >
                {{ label }}
              </option>
            </select></label
          ><label
            >说明<input v-model="edit.description" placeholder="可选备注"
          /></label>
        </div>
        <label class="remember-check"
          ><input
            v-model="remember"
            type="checkbox"
            :disabled="edit.category === 'pending' || !edit.merchant.trim()"
          />
          记住该商户的分类，仅用于之后新导入账单（不影响历史记录）</label
        >
        <div class="dialog-actions">
          <button
            class="secondary-btn"
            type="button"
            :disabled="saving"
            @click="closeModal()"
          >
            取消</button
          ><button class="primary-btn" :disabled="saving" @click="save">
            {{ saving ? "保存中…" : "保存修改" }}
          </button>
        </div>
      </div>
    </dialog>
  </Teleport>
</template>
<style scoped src="../styles/transactions.css"></style>
