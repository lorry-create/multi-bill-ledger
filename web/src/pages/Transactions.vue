<script setup lang="ts">
import {
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  computed,
  watch,
} from "vue";
import {
  useRoute,
  useRouter,
  type LocationQuery,
  type LocationQueryRaw,
} from "vue-router";
import {
  ChevronDown,
  Download,
  ListFilter,
  Pencil,
  ReceiptText,
  X,
} from "@lucide/vue";
import { api, ApiError } from "../api";
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
import TransactionEvidence from "../components/TransactionEvidence.vue";
import { notify } from "../motion";

const PAGE_SIZE = 50;
const wideLedger = window.matchMedia("(min-width: 960px)");
const inlineMode = ref(wideLedger.matches);
const platforms = ["", "wechat", "alipay"] as const;
const route = useRoute();
const router = useRouter();
type Filters = {
  date_from: string;
  date_to: string;
  category: "" | Category;
  source: "" | Source;
  flow_type: "" | FlowType;
  page: number;
};
const defaultFilters: Filters = {
  date_from: "",
  date_to: "",
  category: "",
  source: "",
  flow_type: "",
  page: 1,
};

function validDate(value: unknown) {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    value.startsWith("0000")
  )
    return "";
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) &&
    date.toISOString().slice(0, 10) === value
    ? value
    : "";
}

function validOption<T extends string>(
  value: unknown,
  options: readonly T[],
): T | "" {
  return typeof value === "string" && options.includes(value as T)
    ? (value as T)
    : "";
}

function readFilters(query: LocationQuery): Filters {
  const page =
    typeof query.page === "string" && /^\d+$/.test(query.page)
      ? Number(query.page)
      : 1;
  return {
    date_from: validDate(query.date_from),
    date_to: validDate(query.date_to),
    category: validOption(
      query.category,
      Object.keys(categories) as Category[],
    ),
    source: validOption(query.source, platforms),
    flow_type: validOption(query.flow_type, Object.keys(flows) as FlowType[]),
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  };
}

const filters = computed(() => readFilters(route.query));
const data = ref<TransactionPage | null>(null),
  loading = ref(false),
  exporting = ref(false),
  error = ref(""),
  editing = ref<Transaction | null>(null),
  editMode = ref(false),
  pendingSelection = ref<Transaction | null>(null),
  modalError = ref(""),
  conflictLatest = ref<Transaction | null>(null),
  conflictState = ref<"loading" | "ready" | "missing" | "error" | null>(null),
  saving = ref(false),
  remember = ref(false);
let listRequest = 0;
let conflictRequest = 0;
const edit = reactive({
  occurred_at: "",
  amount: "",
  merchant: "",
  description: "",
  category: "pending" as Category,
  flow_type: "expense" as FlowType,
});
const dirty = computed(() => {
  const current = editing.value;
  return (
    editMode.value &&
    current !== null &&
    (remember.value ||
      edit.occurred_at !== toLocalInput(current.occurred_at) ||
      edit.amount !== (current.amount_fen / 100).toFixed(2) ||
      edit.merchant !== current.merchant ||
      edit.description !== current.description ||
      edit.category !== current.category ||
      edit.flow_type !== current.flow_type)
  );
});
const query = computed(() => ({
  date_from: filters.value.date_from || undefined,
  date_to: filters.value.date_to || undefined,
  category: filters.value.category || undefined,
  source: filters.value.source || undefined,
  flow_type: filters.value.flow_type || undefined,
}));
const advancedCount = computed(
  () =>
    [
      filters.value.date_from,
      filters.value.date_to,
      filters.value.category,
      filters.value.flow_type,
    ].filter(Boolean).length,
);
const advancedOpen = ref(advancedCount.value > 0);
const hasFilters = computed(
  () => advancedCount.value > 0 || Boolean(filters.value.source),
);
const editor = ref<HTMLDialogElement | null>(null);
const scrollRegion = ref<HTMLElement | null>(null);
const editorTitle = ref<HTMLElement | null>(null);
const editAction = ref<HTMLButtonElement | null>(null);
const firstEditField = ref<HTMLInputElement | null>(null);
const listFailed = ref(false);
const playEntrance = ref(false);
let firstResults = true;
const pageCount = computed(() =>
  Math.ceil((data.value?.total ?? 0) / PAGE_SIZE),
);
const numberFormat = new Intl.NumberFormat("zh-CN");
const dayFormat = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
});
const weekdayFormat = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  weekday: "short",
});
const days = computed(() => {
  const grouped = new Map<
    string,
    {
      day: string;
      label: string;
      weekday: string;
      start: number;
      rows: Transaction[];
    }
  >();
  for (const [index, item] of (data.value?.items ?? []).entries()) {
    const day = toLocalInput(item.occurred_at).slice(0, 10);
    const group = grouped.get(day);
    if (group) group.rows.push(item);
    else
      grouped.set(day, {
        day,
        label: dayFormat.format(new Date(item.occurred_at)),
        weekday: weekdayFormat.format(new Date(item.occurred_at)),
        start: index,
        rows: [item],
      });
  }
  return Array.from(grouped.values());
});
const selectedGroup = computed(() =>
  days.value.find((group) =>
    group.rows.some((item) => item.id === editing.value?.id),
  ),
);
const panelTarget = computed(() => {
  if (!inlineMode.value) return "#ledger-sheet";
  return selectedGroup.value ? "#ledger-active-voucher" : "#ledger-detached";
});
function arrivalDelay(index: number) {
  const count = data.value?.items.length ?? 1;
  return Math.round(index * Math.min(80, 1000 / count)) + "ms";
}
function signedAmount(item: Transaction) {
  const sign =
    item.flow_type === "income" || item.flow_type === "refund"
      ? "+"
      : item.flow_type === "expense"
        ? "−"
        : "";
  return sign + yuan(item.amount_fen);
}
const viewport = window.visualViewport;
function resizeEditor() {
  const dialog = editor.value;
  if (!dialog?.open || !viewport) return;
  const keyboardInset = Math.max(
    0,
    document.documentElement.clientHeight -
      viewport.height -
      viewport.offsetTop,
  );
  dialog.style.setProperty(
    "--ledger-editor-viewport-height",
    `${viewport.height}px`,
  );
  dialog.style.setProperty(
    "--ledger-editor-keyboard-inset",
    `${keyboardInset}px`,
  );
}
onMounted(() => {
  wideLedger.addEventListener("change", onLayoutChange);
  viewport?.addEventListener("resize", resizeEditor);
  viewport?.addEventListener("scroll", resizeEditor);
  load();
});
onUnmounted(() => {
  listRequest++;
  conflictRequest++;
  wideLedger.removeEventListener("change", onLayoutChange);
  viewport?.removeEventListener("resize", resizeEditor);
  viewport?.removeEventListener("scroll", resizeEditor);
});
watch(
  () => route.query,
  () => {
    if (route.path === "/transactions") load(true);
  },
);
async function load(selectFromResults = false) {
  const request = ++listRequest;
  playEntrance.value = false;
  const { date_from, date_to, page } = filters.value;
  listFailed.value = false;
  if (date_from && date_to && date_from > date_to) {
    error.value = "开始日期不能晚于结束日期。";
    data.value = null;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  const requestedQuery = {
    ...query.value,
    page,
    page_size: PAGE_SIZE,
  };
  try {
    const result = await api.listTransactions({ query: requestedQuery });
    if (request !== listRequest || route.path !== "/transactions") return;
    const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
    if (page > lastPage) {
      await navigateFilters({ ...filters.value, page: lastPage }, true);
      return;
    }
    playEntrance.value = firstResults && result.items.length > 0;
    firstResults = false;
    data.value = result;
    if (!editMode.value && inlineMode.value) {
      const current = result.items.find(
        (item) => item.id === editing.value?.id,
      );
      if (current) editing.value = current;
      else if (selectFromResults) setSelected(null);
    }
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
function navigateFilters(next: Filters, replace = false) {
  const nextQuery: LocationQueryRaw = { ...route.query };
  for (const key of Object.keys(defaultFilters) as (keyof Filters)[]) {
    if (next[key] === defaultFilters[key]) delete nextQuery[key];
    else nextQuery[key] = String(next[key]);
  }
  const location = {
    path: "/transactions",
    query: nextQuery,
    hash: route.hash,
  };
  return replace ? router.replace(location) : router.push(location);
}
function selectPlatform(platform: "" | Source) {
  if (filters.value.source === platform) {
    if (listFailed.value) load();
    return;
  }
  navigateFilters({ ...filters.value, source: platform, page: 1 });
}
function changePage(offset: number) {
  navigateFilters({ ...filters.value, page: filters.value.page + offset });
}
function changeFilter(
  field: "date_from" | "date_to" | "category" | "flow_type",
  event: Event,
) {
  const value = (event.target as HTMLInputElement | HTMLSelectElement).value;
  navigateFilters({ ...filters.value, [field]: value, page: 1 });
}
function clearFilters() {
  navigateFilters(defaultFilters);
}
function fillEditFrom(t: Transaction) {
  edit.occurred_at = toLocalInput(t.occurred_at);
  edit.amount = (t.amount_fen / 100).toFixed(2);
  edit.merchant = t.merchant;
  edit.description = t.description;
  edit.category = t.category;
  edit.flow_type = t.flow_type;
}
function resetEditState() {
  editMode.value = false;
  pendingSelection.value = null;
  conflictRequest++;
  modalError.value = "";
  conflictLatest.value = null;
  conflictState.value = null;
  remember.value = false;
}
function setSelected(t: Transaction | null) {
  editing.value = t;
  resetEditState();
  if (scrollRegion.value) scrollRegion.value.scrollTop = 0;
}
async function showSheet() {
  await nextTick();
  if (!editing.value || inlineMode.value || !editor.value || editor.value.open)
    return;
  editor.value.showModal();
  resizeEditor();
}
function onLayoutChange(event: MediaQueryListEvent) {
  inlineMode.value = event.matches;
  if (event.matches) {
    editor.value?.close();
  } else if (editMode.value) {
    void showSheet();
  } else {
    setSelected(null);
  }
}
async function open(t: Transaction) {
  if (loading.value || saving.value || editor.value?.open) return;
  if (editing.value?.id === t.id) {
    closeModal();
    return;
  }
  if (dirty.value) {
    pendingSelection.value = t;
    await nextTick();
    scrollRegion.value?.querySelector<HTMLElement>(".alert button")?.focus();
    return;
  }
  setSelected(t);
  if (!inlineMode.value) await showSheet();
  else {
    await nextTick();
    document
      .getElementById("ledger-open-" + t.id)
      ?.scrollIntoView({ block: "nearest" });
  }
}
function closeModal() {
  if (saving.value) return;
  if (dirty.value) {
    modalError.value = "有未保存的修改。要离开，请先保存或取消修改。";
    void nextTick(() =>
      scrollRegion.value
        ?.querySelector(".alert.error")
        ?.scrollIntoView({ block: "nearest" }),
    );
    return;
  }
  const trigger = document.getElementById("ledger-open-" + editing.value?.id);
  editor.value?.close();
  setSelected(null);
  void nextTick(() => trigger?.focus({ preventScroll: true }));
}
async function startEdit() {
  if (!editing.value) return;
  fillEditFrom(editing.value);
  editMode.value = true;
  await nextTick();
  if (inlineMode.value) firstEditField.value?.focus({ preventScroll: true });
  else editorTitle.value?.focus({ preventScroll: true });
  if (scrollRegion.value) scrollRegion.value.scrollTop = 0;
}
async function cancelEdit() {
  resetEditState();
  if (scrollRegion.value) scrollRegion.value.scrollTop = 0;
  await nextTick();
  editAction.value?.focus({ preventScroll: true });
}
async function confirmSwitch() {
  if (!pendingSelection.value) return;
  setSelected(pendingSelection.value);
  await nextTick();
  editorTitle.value?.focus();
}
async function continueEdit() {
  pendingSelection.value = null;
  await nextTick();
  firstEditField.value?.focus({ preventScroll: true });
}
function applyLatestConflict() {
  if (!conflictLatest.value) return;
  editing.value = conflictLatest.value;
  fillEditFrom(conflictLatest.value);
  conflictLatest.value = null;
  conflictState.value = null;
  modalError.value = "";
}
async function findLatestConflict() {
  const previous = editing.value;
  if (!previous) return;
  const request = ++conflictRequest;
  conflictState.value = "loading";
  conflictLatest.value = null;
  try {
    // 现有查询契约按列表分页；平台不可编辑，能缩小查找范围。
    const pageSize = 100;
    let lastPage = 1;
    for (let page = 1; page <= lastPage; page++) {
      const result = await api.listTransactions({
        query: { source: previous.source, page, page_size: pageSize },
      });
      if (request !== conflictRequest) return;
      const latest = result.items.find((item) => item.id === previous.id);
      if (latest) {
        conflictLatest.value = latest;
        conflictState.value = "ready";
        return;
      }
      if (page === 1) lastPage = Math.ceil(result.total / pageSize);
    }
    conflictState.value = "missing";
  } catch {
    if (request === conflictRequest) conflictState.value = "error";
  }
}
async function save() {
  if (!editing.value || saving.value || conflictState.value) return;
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
    const updated = await withCsrfRetry((token) =>
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
    if (inlineMode.value) {
      setSelected(updated);
      await nextTick();
      editAction.value?.focus({ preventScroll: true });
    } else {
      editor.value?.close();
      setSelected(null);
    }
    await load();
  } catch (e) {
    modalError.value = errorText(e);
    if (
      e instanceof ApiError &&
      e.status === 409 &&
      e.payload.error.code === "VERSION_CONFLICT"
    ) {
      void findLatestConflict();
      void load();
    }
  } finally {
    saving.value = false;
  }
}
async function exportCsv() {
  if (exporting.value) return;
  if (
    filters.value.date_from &&
    filters.value.date_to &&
    filters.value.date_from > filters.value.date_to
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
  <header class="ledger-heading">
    <div class="ledger-heading-copy">
      <h1>全部账单</h1>
      <p role="status">
        <template v-if="loading">正在更新账单…</template>
        <template v-else-if="data"
          >{{ hasFilters ? "符合筛选" : "已确认" }}
          {{ numberFormat.format(data.total) }} 笔</template
        >
      </p>
    </div>
  </header>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>

  <div class="ledger-workspace">
    <section class="ledger-filter" aria-label="筛选账单">
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
            <PlatformLogo v-if="platform" :source="platform" :size="19" />
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
            <ListFilter :size="16" />筛选
            <span v-if="advancedCount" class="ledger-filter-count">{{
              advancedCount
            }}</span>
            <ChevronDown class="ledger-chevron" :size="14" />
          </button>
          <button
            v-if="hasFilters"
            class="ledger-clear"
            type="button"
            @click="clearFilters"
          >
            <X :size="15" />清除筛选
          </button>
          <button
            class="secondary-btn ledger-export"
            type="button"
            :disabled="exporting || loading"
            aria-label="导出当前筛选"
            @click="exportCsv"
          >
            <Download :size="16" />{{ exporting ? "导出中…" : "导出 CSV" }}
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
                :value="filters.date_from"
                type="date"
                @change="changeFilter('date_from', $event)"
            /></label>
            <label
              >结束日期<input
                :value="filters.date_to"
                type="date"
                @change="changeFilter('date_to', $event)"
            /></label>
            <label
              >类别
              <select
                :value="filters.category"
                @change="changeFilter('category', $event)"
              >
                <option value="">全部类别</option>
                <option
                  v-for="(label, key) in categories"
                  :key="key"
                  :value="key"
                >
                  {{ label }}
                </option>
              </select>
            </label>
            <label
              >收支
              <select
                :value="filters.flow_type"
                @change="changeFilter('flow_type', $event)"
              >
                <option value="">全部收支</option>
                <option v-for="(label, key) in flows" :key="key" :value="key">
                  {{ label }}
                </option>
              </select>
            </label>
          </div>
        </div>
      </div>
    </section>

    <div class="ledger-columns">
      <div id="ledger-detached" class="ledger-voucher ledger-detached"></div>
      <section class="ledger-results" aria-labelledby="ledger-results-title">
        <h2 id="ledger-results-title" class="sr-only">交易明细</h2>
        <div class="ledger-results-content" :aria-busy="loading">
          <div
            v-if="days.length"
            class="ledger-table"
            :class="{ 'ledger-arriving': playEntrance }"
          >
            <table role="table" aria-label="按交易日期分组的账单">
              <thead>
                <tr>
                  <th scope="col" class="ledger-date-heading">日期</th>
                  <th scope="col">交易</th>
                  <th scope="col">来源与类别</th>
                  <th scope="col" class="ledger-amount-heading">金额</th>
                </tr>
              </thead>
              <tbody
                v-for="group in days"
                :key="group.day"
                class="ledger-day-group"
                role="rowgroup"
              >
                <tr class="ledger-day" role="row">
                  <th colspan="3" scope="rowgroup" role="rowheader">
                    <time :datetime="group.day">{{ group.label }}</time>
                  </th>
                </tr>
                <template v-for="(t, index) in group.rows" :key="t.id">
                  <tr
                    class="ledger-row"
                    :style="{
                      '--ledger-arrival-delay': arrivalDelay(
                        group.start + index,
                      ),
                    }"
                    :class="{ 'is-selected': editing?.id === t.id }"
                    role="row"
                    @click="open(t)"
                  >
                    <th
                      v-if="index === 0"
                      scope="rowgroup"
                      class="ledger-date-rail"
                      :rowspan="
                        group.rows.length +
                        (inlineMode && selectedGroup?.day === group.day ? 1 : 0)
                      "
                      @click.stop
                    >
                      <time :datetime="group.day" :aria-label="group.label">
                        <strong
                          >{{ group.day.slice(5, 7) }}.{{
                            group.day.slice(8)
                          }}</strong
                        >
                        <small
                          >{{ group.day.slice(0, 4) }} ·
                          {{ group.weekday }}</small
                        >
                      </time>
                    </th>
                    <td role="cell" class="ledger-trade">
                      <button
                        :id="'ledger-open-' + t.id"
                        class="ledger-row-open"
                        type="button"
                        :aria-label="'核对 ' + (t.merchant || '账单')"
                        :aria-expanded="
                          inlineMode ? editing?.id === t.id : undefined
                        "
                        :aria-controls="
                          inlineMode && editing?.id === t.id
                            ? 'ledger-active-voucher'
                            : undefined
                        "
                        :aria-haspopup="inlineMode ? undefined : 'dialog'"
                        :aria-disabled="loading || saving"
                        @click.stop="open(t)"
                      >
                        {{ t.merchant || "未填写商户" }}
                      </button>
                      <small class="ledger-row-description"
                        >{{ flows[t.flow_type]
                        }}<template v-if="t.description">
                          · {{ t.description }}</template
                        ></small
                      >
                    </td>
                    <td class="ledger-row-meta" role="cell">
                      <span class="transaction-source"
                        ><PlatformLogo :source="t.source" :size="19" />{{
                          sources[t.source]
                        }}</span
                      >
                      <span class="ledger-row-category">{{
                        categories[t.category]
                      }}</span>
                    </td>
                    <td class="ledger-row-amount" role="cell">
                      <strong class="money" :class="t.flow_type">{{
                        signedAmount(t)
                      }}</strong>
                      <time :datetime="t.occurred_at">{{
                        toLocalInput(t.occurred_at).slice(11)
                      }}</time>
                    </td>
                  </tr>
                  <tr
                    v-if="inlineMode && editing?.id === t.id"
                    class="ledger-voucher-row"
                  >
                    <td colspan="3">
                      <div id="ledger-active-voucher" class="ledger-voucher" />
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <div v-else-if="loading" class="ledger-loading" aria-hidden="true">
            <span v-for="line in 4" :key="line"></span>
          </div>
          <div v-else-if="listFailed" class="empty-state ledger-empty">
            <strong>账单暂时无法加载</strong>
            <button class="secondary-btn" type="button" @click="load()">
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
              class="text-btn"
              type="button"
              @click="clearFilters"
            >
              清除筛选
            </button>
            <RouterLink v-else to="/import" class="text-btn"
              >去导入账单</RouterLink
            >
          </div>
          <div
            v-if="data && pageCount > 1"
            class="pagination ledger-pagination"
          >
            <span>每页 {{ PAGE_SIZE }} 笔</span>
            <div>
              <button
                type="button"
                :disabled="loading || filters.page <= 1"
                @click="changePage(-1)"
              >
                上一页
              </button>
              <span>{{ data.page }} / {{ pageCount }}</span>
              <button
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
          id="ledger-sheet"
          class="edit-dialog ledger-editor"
          aria-labelledby="ledger-editor-title"
          @cancel.prevent="closeModal"
          @click.self="closeModal"
        ></dialog>
      </Teleport>
      <Teleport
        v-if="editing"
        :key="
          inlineMode ? editing.id + '/' + (selectedGroup?.day ?? '') : 'sheet'
        "
        :to="panelTarget"
        defer
      >
        <section class="ledger-editor-body" aria-label="账单核对">
          <div class="ledger-inspector-head">
            <div>
              <h2 id="ledger-editor-title" ref="editorTitle" tabindex="-1">
                {{ editing.merchant || "未填写商户" }}
              </h2>
              <p>{{ editMode ? "修正账单" : "账单核对" }}</p>
            </div>
            <button
              class="icon-btn"
              type="button"
              aria-label="关闭核对"
              :disabled="saving"
              :autofocus="!inlineMode"
              @click="closeModal"
            >
              <X :size="20" />
            </button>
          </div>
          <div ref="scrollRegion" class="ledger-editor-scroll">
            <div v-if="pendingSelection" class="alert" role="status">
              <p>这笔账单有未保存的修改。</p>
              <button class="text-btn" type="button" @click="confirmSwitch">
                放弃修改并切换
              </button>
              <button class="text-btn" type="button" @click="continueEdit">
                继续编辑
              </button>
            </div>
            <div
              v-if="!selectedGroup && inlineMode && !loading"
              class="ledger-inspector-notice"
            >
              这笔账单不在当前列表中。
            </div>
            <div v-if="!editMode" class="ledger-inspector-summary">
              <strong
                class="ledger-inspector-amount money"
                :class="editing.flow_type"
                >{{ signedAmount(editing) }}</strong
              >
              <dl class="ledger-inspector-meta">
                <div>
                  <dt>交易时间</dt>
                  <dd>{{ dateTime(editing.occurred_at) }}</dd>
                </div>
                <div>
                  <dt>支付平台</dt>
                  <dd class="transaction-source">
                    <PlatformLogo :source="editing.source" :size="19" />{{
                      sources[editing.source]
                    }}
                  </dd>
                </div>
                <div>
                  <dt>收支 · 类别</dt>
                  <dd>
                    {{ flows[editing.flow_type] }} ·
                    {{ categories[editing.category] }}
                  </dd>
                </div>
              </dl>
              <div
                v-if="editing.description"
                class="ledger-inspector-description"
              >
                <span>已保存描述</span>
                <p>{{ editing.description }}</p>
              </div>
            </div>

            <form
              v-if="editMode"
              id="ledger-edit-form"
              class="ledger-editor-form"
              @submit.prevent="save"
            >
              <div v-if="modalError" class="alert error" role="alert">
                {{ modalError }}
                <p v-if="conflictState === 'loading'">
                  正在查找这笔账单的最新版本…
                </p>
                <template v-else-if="conflictLatest">
                  <p>载入后会替换本次未保存的输入。</p>
                  <button type="button" @click="applyLatestConflict">
                    载入最新版本（v{{ conflictLatest.version }}）
                  </button>
                </template>
                <template
                  v-else-if="
                    conflictState === 'missing' || conflictState === 'error'
                  "
                >
                  <p>
                    {{
                      conflictState === "missing"
                        ? "未找到这笔账单，可能已不可访问。"
                        : "未能读取最新版本。"
                    }}当前输入仍保留。
                  </p>
                  <button type="button" @click="findLatestConflict">
                    重试查找
                  </button>
                </template>
              </div>
              <fieldset :disabled="saving">
                <div class="edit-grid">
                  <label class="ledger-editor-time"
                    >交易时间<input
                      ref="firstEditField"
                      v-model="edit.occurred_at"
                      type="datetime-local"
                  /></label>
                  <label
                    >金额（元）<input v-model="edit.amount" inputmode="decimal"
                  /></label>
                  <label>商户<input v-model="edit.merchant" /></label>
                  <label
                    >收支方向<select v-model="edit.flow_type">
                      <option
                        v-for="(label, key) in flows"
                        :key="key"
                        :value="key"
                      >
                        {{ label }}
                      </option>
                    </select></label
                  >
                  <label
                    >类别<select v-model="edit.category">
                      <option
                        v-for="(label, key) in categories"
                        :key="key"
                        :value="key"
                      >
                        {{ label }}
                      </option>
                    </select></label
                  >
                  <label class="ledger-editor-description"
                    >说明<input
                      v-model="edit.description"
                      placeholder="可选备注"
                  /></label>
                </div>
                <label class="remember-check">
                  <input
                    v-model="remember"
                    type="checkbox"
                    :disabled="
                      edit.category === 'pending' || !edit.merchant.trim()
                    "
                  />
                  记住该商户的分类，用于之后导入的账单
                </label>
              </fieldset>
            </form>
            <TransactionEvidence
              :key="editing.id"
              :transaction="editing"
              :initially-open="inlineMode"
            />
          </div>
          <div class="dialog-actions">
            <template v-if="editMode">
              <button
                class="secondary-btn"
                type="button"
                :disabled="saving"
                @click="cancelEdit"
              >
                取消修改
              </button>
              <button
                class="primary-btn"
                type="submit"
                form="ledger-edit-form"
                :disabled="saving || Boolean(conflictState)"
              >
                {{ saving ? "保存中…" : "保存修改" }}
              </button>
            </template>
            <button
              v-else
              ref="editAction"
              class="primary-btn"
              type="button"
              @click="startEdit"
            >
              <Pencil :size="15" />修正账单
            </button>
          </div>
        </section>
      </Teleport>
    </div>
  </div>
</template>
<style scoped src="../styles/transactions.css"></style>
