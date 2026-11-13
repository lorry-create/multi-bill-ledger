<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, computed } from "vue";
import { useRoute } from "vue-router";
import { Download, Filter, Plus, Pencil, X } from "@lucide/vue";
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

const PAGE_SIZE = 50;
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
  source: "",
  flow_type: "",
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
function handleEscape(e: KeyboardEvent) {
  if (e.key === "Escape" && editing.value && !saving.value) {
    closeModal();
  }
}
onMounted(() => {
  window.addEventListener("keydown", handleEscape);
  load();
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleEscape);
});
async function load() {
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    error.value = "开始日期不能晚于结束日期。";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.listTransactions({
      query: { ...query.value, page: filters.page, page_size: PAGE_SIZE },
    });
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
function search() {
  filters.page = 1;
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
  editing.value = t;
  modalError.value = "";
  conflictLatest.value = null;
  fillEditFrom(t);
  remember.value = false;
}
function closeModal() {
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
    closeModal();
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
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    error.value = "开始日期不能晚于结束日期。";
    return;
  }
  exporting.value = true;
  error.value = "";
  try {
    const blob = await api.exportTransactions({ query: query.value });
    download(blob, "账单导出.csv");
  } catch (e) {
    error.value = errorText(e);
  } finally {
    exporting.value = false;
  }
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>全部账单</h1>
      <p>每一笔已确认的交易，都可以在这里核对和修正。</p>
    </div>
    <RouterLink to="/import" class="primary-btn"
      ><Plus :size="18" /> 导入账单</RouterLink
    >
  </div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <section class="content-panel">
    <div class="toolbar">
      <div class="toolbar-title">
        <Filter :size="18" /><strong>筛选账单</strong>
      </div>
      <button class="secondary-btn" :disabled="exporting" @click="exportCsv">
        <Download :size="16" /> {{ exporting ? "导出中…" : "导出当前筛选" }}
      </button>
    </div>
    <div class="filters">
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
          <option v-for="(label, key) in categories" :key="key" :value="key">
            {{ label }}
          </option>
        </select></label
      ><label
        >平台<select v-model="filters.source" @change="search">
          <option value="">全部平台</option>
          <option v-for="(label, key) in sources" :key="key" :value="key">
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
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>交易</th>
            <th>时间</th>
            <th>平台</th>
            <th>类别</th>
            <th>金额</th>
            <th><span class="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in data?.items" :key="t.id">
            <td>
              <strong>{{ t.merchant || "未填写商户" }}</strong
              ><small
                >{{ flows[t.flow_type]
                }}{{ t.description ? ` · ${t.description}` : "" }}</small
              >
            </td>
            <td>{{ dateTime(t.occurred_at) }}</td>
            <td>{{ sources[t.source] }}</td>
            <td>
              <span class="category-pill">{{ categories[t.category] }}</span>
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
                :aria-label="`编辑 ${t.merchant}`"
                @click="open(t)"
              >
                <Pencil :size="16" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="loading" class="empty-state">正在读取账单…</div>
    <div v-else-if="!data?.items.length" class="empty-state">
      <strong>没有找到符合条件的账单</strong
      ><span>试试调整日期或类别，或先导入一份账单。</span>
      <RouterLink to="/import" class="text-btn">去导入账单</RouterLink>
    </div>
    <div v-if="data && data.total > 0" class="pagination">
      <span>共 {{ data.total }} 笔</span>
      <div>
        <button
          :disabled="filters.page <= 1"
          @click="
            filters.page--;
            load();
          "
        >
          上一页</button
        ><span>{{ filters.page }} / {{ Math.ceil(data.total / PAGE_SIZE) }}</span
        ><button
          :disabled="filters.page * PAGE_SIZE >= data.total"
          @click="
            filters.page++;
            load();
          "
        >
          下一页
        </button>
      </div>
    </div>
  </section>
  <div v-if="editing" class="modal-backdrop" @click.self="closeModal">
    <section
      class="edit-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="编辑账单"
    >
      <div class="dialog-head">
        <div>
          <h2>修正账单</h2>
          <p>保存后，相关月报会按新内容重新计算。</p>
        </div>
        <button class="icon-btn" aria-label="关闭" @click="closeModal">
          <X :size="20" />
        </button>
      </div>
      <div v-if="modalError" class="alert error" role="alert">
        {{ modalError }}
        <button v-if="conflictLatest" type="button" @click="applyLatestConflict">
          载入最新版本（v{{ conflictLatest.version }}）
        </button>
      </div>
      <div class="edit-grid">
        <label
          >交易时间<input
            v-model="edit.occurred_at"
            type="datetime-local" /></label
        ><label
          >金额（元）<input v-model="edit.amount" inputmode="decimal" /></label
        ><label>商户<input v-model="edit.merchant" /></label
        ><label
          >收支方向<select v-model="edit.flow_type">
            <option v-for="(label, key) in flows" :key="key" :value="key">
              {{ label }}
            </option>
          </select></label
        ><label
          >类别<select v-model="edit.category">
            <option v-for="(label, key) in categories" :key="key" :value="key">
              {{ label }}
            </option>
          </select></label
        ><label>说明<input v-model="edit.description" placeholder="可选备注" /></label>
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
        <button class="secondary-btn" @click="closeModal">取消</button
        ><button class="primary-btn" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存修改" }}
        </button>
      </div>
    </section>
  </div>
</template>
<style scoped>
.source-note {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  color: #6b7f85;
}
</style>
