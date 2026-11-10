<script setup lang="ts">
import { onMounted, reactive, ref, computed } from "vue";
import { useRoute } from "vue-router";
import { Download, Filter, Plus, Pencil, X } from "@lucide/vue";
import { api } from "../api";
import type {
  Category,
  FlowType,
  Source,
  Transaction,
  TransactionPage,
} from "../api";
import {
  categories,
  dateTime,
  download,
  flows,
  parseYuan,
  sources,
  toLocalInput,
  fromLocalInput,
  yuan,
} from "../format";
import { csrf, errorText } from "../session";

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
  error = ref(""),
  editing = ref<Transaction | null>(null),
  saving = ref(false),
  remember = ref(false);
const edit = reactive({
  occurred_at: "",
  amount: "",
  merchant: "",
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
async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.listTransactions({
      query: { ...query.value, page: filters.page, page_size: 20 },
    });
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
function search() {
  filters.page = 1;
  load();
}
function open(t: Transaction) {
  editing.value = t;
  edit.occurred_at = toLocalInput(t.occurred_at);
  edit.amount = (t.amount_fen / 100).toFixed(2);
  edit.merchant = t.merchant;
  edit.category = t.category;
  edit.flow_type = t.flow_type;
  remember.value = false;
}
async function save() {
  if (!editing.value) return;
  const amount = parseYuan(edit.amount);
  if (amount === null || !edit.occurred_at) {
    error.value = "请填写有效的交易时间和金额，金额最多两位小数。";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await api.patchTransaction(
      {
        path: { id: editing.value.id },
        body: {
          expected_version: editing.value.version,
          changes: {
            occurred_at: fromLocalInput(edit.occurred_at),
            amount_fen: amount,
            merchant: edit.merchant,
            category: edit.category,
            flow_type: edit.flow_type,
          },
          remember_rule: remember.value,
        },
      },
      csrf(),
    );
    editing.value = null;
    await load();
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) await load();
  } finally {
    saving.value = false;
  }
}
async function exportCsv() {
  try {
    const blob = await api.exportTransactions({ query: query.value });
    download(blob, "归账-筛选明细.csv");
  } catch (e) {
    error.value = errorText(e);
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
      <button class="secondary-btn" @click="exportCsv">
        <Download :size="16" /> 导出当前筛选
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
              ><small>{{ t.description || flows[t.flow_type] }}</small>
            </td>
            <td>{{ dateTime(t.occurred_at) }}</td>
            <td>{{ sources[t.source] }}</td>
            <td>
              <span class="category-pill">{{ categories[t.category] }}</span>
            </td>
            <td class="money" :class="t.flow_type">
              {{ ["income", "refund"].includes(t.flow_type) ? "+" : "−"
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
        ><span>{{ filters.page }} / {{ Math.ceil(data.total / 20) }}</span
        ><button
          :disabled="filters.page * 20 >= data.total"
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
  <div v-if="editing" class="modal-backdrop" @click.self="editing = null">
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
        <button class="icon-btn" aria-label="关闭" @click="editing = null">
          <X :size="20" />
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
        >
      </div>
      <label class="remember-check"
        ><input
          v-model="remember"
          type="checkbox"
          :disabled="edit.category === 'pending' || !edit.merchant.trim()"
        />
        记住该商户的分类，用于之后的新账单</label
      >
      <div class="dialog-actions">
        <button class="secondary-btn" @click="editing = null">取消</button
        ><button class="primary-btn" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存修改" }}
        </button>
      </div>
    </section>
  </div>
</template>
