<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  Download,
  ChevronLeft,
  ChevronRight,
  Plus,
  Wallet,
  ChevronDown,
} from "@lucide/vue";
import { api, isDemo } from "../api";
import type {
  BudgetStatus,
  Category,
  MonthlyReport,
  ResolvedCategory,
} from "../api";
import { categories, download, parseYuan, yuan } from "../format";
import { csrf, errorText, withCsrfRetry } from "../session";
import "../styles/monthly-statement.css";
import AnimatedAmount from "../components/AnimatedAmount.vue";
import { notify } from "../motion";

const router = useRouter();
const route = useRoute();
const currentMonth = new Date()
  .toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" })
  .slice(0, 7);
function validMonth(value: unknown): value is string {
  return (
    typeof value === "string" && /^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(value)
  );
}
const month = computed(() =>
  validMonth(route.query.month) ? route.query.month : currentMonth,
);
const monthHeading = computed(
  () => `${month.value.slice(0, 4)} 年 ${Number(month.value.slice(5))} 月`,
);
function selectMonth(value: string) {
  if (validMonth(value) && value !== month.value)
    router.replace({ query: { ...route.query, month: value } });
}
function pickMonth(event: Event) {
  const input = event.target as HTMLInputElement;
  if (validMonth(input.value)) selectMonth(input.value);
  else input.value = month.value;
}
const report = ref<MonthlyReport | null>(null),
  incomeParts = ref<{ category: Category; amount_fen: number }[]>([]),
  confirmedActivity = ref(false),
  loading = ref(false),
  error = ref(""),
  budgetCategory = ref<ResolvedCategory>("dining"),
  budgetAmount = ref(""),
  budgetOpen = ref(false),
  budgetError = ref(""),
  saving = ref(false),
  exporting = ref(false),
  exportRetryable = ref(false);
let reportRequest = 0;

const budgetCategoryOptions = Object.entries(categories).filter(
  ([key]) => key !== "pending",
) as [ResolvedCategory, string][];

function fillBudgetAmount(category: ResolvedCategory) {
  const existing = report.value?.budgets.find((b) => b.category === category);
  budgetAmount.value = existing ? (existing.budget_fen / 100).toFixed(2) : "";
}

function openBudget(category: ResolvedCategory = budgetCategory.value) {
  budgetCategory.value = category;
  budgetError.value = "";
  fillBudgetAmount(category);
  budgetOpen.value = true;
}

watch(budgetCategory, (category) => {
  if (budgetOpen.value) {
    budgetError.value = "";
    fillBudgetAmount(category);
  }
});

function onReportKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && budgetOpen.value && !saving.value) {
    budgetOpen.value = false;
  }
}

onMounted(() => window.addEventListener("keydown", onReportKeydown));
onUnmounted(() => window.removeEventListener("keydown", onReportKeydown));
const activeCategory = ref<Category | null>(null);
const trendMode = ref<"daily" | "weekly">("weekly");
const activeTrendIndex = ref<number | null>(null);
type Tooltip = {
  x: number;
  y: number;
  title: string;
  color: string;
  rows: { label: string; value: string }[];
};
const tooltip = ref<Tooltip | null>(null);
function placeTooltip(
  event: PointerEvent,
  title: string,
  color: string,
  rows: Tooltip["rows"],
) {
  if (event.pointerType === "touch") return;
  tooltip.value = {
    x: Math.max(12, Math.min(event.clientX + 18, window.innerWidth - 228)),
    y: Math.max(12, Math.min(event.clientY + 18, window.innerHeight - 154)),
    title,
    color,
    rows,
  };
}
function showCategoryTooltip(
  event: PointerEvent,
  item: (typeof chartSegments.value)[number],
) {
  activeCategory.value = item.category;
  placeTooltip(event, categories[item.category], item.color, [
    { label: "支出", value: yuan(item.amount_fen) },
    { label: "占比", value: `${item.percent.toFixed(1)}%` },
  ]);
}
function selectSegment(event: MouseEvent, category: Category) {
  if (
    (event as PointerEvent).pointerType === "touch" ||
    (event.detail > 0 && window.matchMedia("(hover: none)").matches)
  ) {
    activeCategory.value = category;
    return;
  }
  goCategory(category, "expense");
}
function showTrendTooltip(event: PointerEvent, index: number) {
  activeTrendIndex.value = index;
  const item = trendData.value[index];
  if (!item) return;
  placeTooltip(event, item.range, "#397ed8", [
    { label: "收入", value: yuan(item.income_fen) },
    { label: "支出", value: yuan(item.gross_expense_fen) },
    { label: "退款", value: yuan(item.refund_fen) },
  ]);
}
function hideTooltip() {
  tooltip.value = null;
}
function leaveCategory(event: PointerEvent) {
  hideTooltip();
  if (event.pointerType !== "touch") activeCategory.value = null;
}
function shiftMonth(delta: number) {
  const [year, part] = month.value.split("-").map(Number);
  const next = new Date(year, part - 1 + delta, 1);
  selectMonth(
    `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`,
  );
}
const trendData = computed(() => {
  const days = report.value?.daily_trend ?? [];
  if (trendMode.value === "daily")
    return days.map((day) => ({
      ...day,
      label: String(Number(day.date.slice(-2))),
      range: day.date,
    }));
  const weeks = [];
  for (let i = 0; i < days.length; i += 7) {
    const group = days.slice(i, i + 7);
    weeks.push({
      date: group[0].date,
      label: `${i + 1}–${i + group.length}日`,
      range: `${group[0].date} — ${group[group.length - 1].date}`,
      income_fen: group.reduce((sum, day) => sum + day.income_fen, 0),
      gross_expense_fen: group.reduce(
        (sum, day) => sum + day.gross_expense_fen,
        0,
      ),
      refund_fen: group.reduce((sum, day) => sum + day.refund_fen, 0),
    });
  }
  return weeks;
});
const inspectedTrend = computed(() => {
  const items = trendData.value;
  const fallback = items.findIndex(
    (item) =>
      item.income_fen > 0 || item.gross_expense_fen > 0 || item.refund_fen > 0,
  );
  return items[activeTrendIndex.value ?? (fallback < 0 ? 0 : fallback)];
});
const trendPeak = computed(() =>
  Math.max(
    0,
    ...trendData.value.map((x) =>
      Math.max(x.income_fen, x.gross_expense_fen, x.refund_fen),
    ),
  ),
);
const maxTrend = computed(() => trendPeak.value || 1);
function axisAmount(fen: number) {
  const value = fen / 100;
  if (value >= 10000)
    return new Intl.NumberFormat("zh-CN", {
      notation: "compact",
      maximumSignificantDigits: 4,
    }).format(value);
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
const categoryTotal = computed(
  () =>
    report.value?.expense_by_category.reduce((n, x) => n + x.amount_fen, 0) ??
    0,
);
const chartSegments = computed(() => {
  let offset = 0;
  const colors: Record<Category, string> = {
    dining: "#2f69bd",
    shopping: "#5997be",
    transport: "#6379b1",
    housing: "#467891",
    entertainment: "#8c79ab",
    health: "#438c89",
    education: "#8196b6",
    salary: "#456192",
    other: "#6e8296",
    pending: "#a6aeb7",
  };
  return (report.value?.expense_by_category ?? [])
    .filter((x) => x.amount_fen > 0)
    .sort((left, right) => right.amount_fen - left.amount_fen)
    .map((x) => {
      const percent = categoryTotal.value
        ? (x.amount_fen / categoryTotal.value) * 100
        : 0;
      const segment = {
        ...x,
        percent,
        offset,
        color: colors[x.category],
      };
      offset += percent;
      return segment;
    });
});
const inspectedCategory = computed(() =>
  chartSegments.value.find((x) => x.category === activeCategory.value),
);
const budgetByCategory = computed(
  () => new Map(report.value?.budgets.map((item) => [item.category, item])),
);
function budgetWidth(budget: BudgetStatus) {
  if (budget.budget_fen === 0) return budget.over_fen > 0 ? 100 : 0;
  return Math.min(
    100,
    Math.max(0, (budget.spent_fen / budget.budget_fen) * 100),
  );
}
function budgetLevel(budget: BudgetStatus) {
  if (budget.over_fen > 0) return "over";
  if (budget.budget_fen > 0 && budget.spent_fen >= budget.budget_fen * 0.9)
    return "near";
  return "normal";
}
function budgetLabel(budget?: BudgetStatus) {
  if (!budget) return "未设预算";
  if (budget.over_fen > 0) return `超出 ${yuan(budget.over_fen)}`;
  if (budget.remaining_fen === 0)
    return budget.budget_fen === 0 ? "零额度" : "已用完";
  if (budgetLevel(budget) === "near")
    return `接近额度 · 余 ${yuan(budget.remaining_fen)}`;
  return `剩余 ${yuan(budget.remaining_fen)}`;
}
function changeTrendMode(mode: "daily" | "weekly") {
  trendMode.value = mode;
  activeTrendIndex.value = null;
  hideTooltip();
}
async function load() {
  const request = ++reportRequest;
  const requestedMonth = month.value;
  loading.value = true;
  error.value = "";
  exportRetryable.value = false;
  try {
    const nextReport = await api.getMonthlyReport({
      query: { month: requestedMonth },
    });
    if (request !== reportRequest) return;
    const [year, part] = requestedMonth.split("-").map(Number);
    const date_to = `${requestedMonth}-${new Date(year, part, 0).getDate()}`;
    const dates = { date_from: `${requestedMonth}-01`, date_to };
    // 收入、支出均为零时，也可能已经确认了还款或转账。
    const hasReportActivity =
      nextReport.totals.income_fen > 0 ||
      nextReport.totals.gross_expense_fen > 0 ||
      nextReport.totals.refund_fen > 0;
    const hasConfirmed =
      hasReportActivity ||
      (
        await api.listTransactions({
          query: { ...dates, page: 1, page_size: 1 },
        })
      ).total > 0;
    if (request !== reportRequest) return;
    let page = 1;
    const totals = new Map<Category, number>();
    while (nextReport.totals.income_fen > 0) {
      const result = await api.listTransactions({
        query: { ...dates, flow_type: "income", page, page_size: 100 },
      });
      if (request !== reportRequest) return;
      for (const item of result.items)
        totals.set(
          item.category,
          (totals.get(item.category) ?? 0) + item.amount_fen,
        );
      if (page * 100 >= result.total) break;
      page++;
    }
    if (request !== reportRequest) return;
    confirmedActivity.value = hasConfirmed;
    report.value = nextReport;
    incomeParts.value = [...totals]
      .map(([category, amount_fen]) => ({ category, amount_fen }))
      .sort((a, b) => b.amount_fen - a.amount_fen);
  } catch (e) {
    if (request === reportRequest) {
      report.value = null;
      error.value = errorText(e);
    }
  } finally {
    if (request === reportRequest) loading.value = false;
  }
}
watch(
  month,
  () => {
    activeCategory.value = null;
    activeTrendIndex.value = null;
    hideTooltip();
    if (route.path === "/report") load();
  },
  { immediate: true },
);
async function saveBudget() {
  const amount = parseYuan(budgetAmount.value, true);
  if (amount === null) {
    budgetError.value = "请输入有效的预算金额，最多两位小数。";
    return;
  }
  saving.value = true;
  budgetError.value = "";
  try {
    await withCsrfRetry(() =>
      api.putBudget(
        {
          body: {
            month: month.value,
            category: budgetCategory.value,
            amount_fen: amount,
          },
        },
        csrf(),
      ),
    );
    budgetOpen.value = false;
    await load();
    notify("本月类别预算已保存");
  } catch (e) {
    budgetError.value = errorText(e);
  } finally {
    saving.value = false;
  }
}
async function exportPdf() {
  if (isDemo) {
    exportRetryable.value = false;
    error.value = "合成数据演示不提供 PDF，请连接真实后端导出。";
    return;
  }
  if (exporting.value || !/^\d{4}-\d{2}$/.test(month.value)) {
    return;
  }
  const exportedMonth = month.value;
  exporting.value = true;
  error.value = "";
  exportRetryable.value = false;
  try {
    download(
      await api.exportMonthlyPdf({ query: { month: exportedMonth } }),
      `收支月报_${exportedMonth}.pdf`,
    );
    notify("收支月报已导出");
  } catch (e) {
    const err = e as {
      status?: number;
      payload?: { error?: { code?: string } };
    };
    exportRetryable.value =
      err?.payload?.error?.code === "EXPORT_UNAVAILABLE" || err?.status === 503;
    error.value = errorText(e);
  } finally {
    exporting.value = false;
  }
}
function goCategory(category: Category, flow_type?: "income" | "expense") {
  const [year, part] = month.value.split("-").map(Number);
  const last = new Date(year, part, 0).getDate();
  router.push({
    path: "/transactions",
    query: {
      category,
      flow_type,
      date_from: `${month.value}-01`,
      date_to: `${month.value}-${last}`,
    },
  });
}
</script>
<template>
  <article class="monthly-statement" :aria-busy="loading">
    <header class="statement-mast">
      <div class="statement-title">
        <h1>
          <label
            >{{ monthHeading }}<ChevronDown :size="18" aria-hidden="true" />
            <input
              type="month"
              aria-label="选择月份"
              :value="month"
              @change="pickMonth"
            />
          </label>
        </h1>
        <span>收支月报</span>
      </div>
      <div class="statement-actions">
        <div class="month-arrows">
          <button type="button" aria-label="上个月" @click="shiftMonth(-1)">
            <ChevronLeft :size="17" />
          </button>
          <button type="button" aria-label="下个月" @click="shiftMonth(1)">
            <ChevronRight :size="17" />
          </button>
        </div>
        <button
          class="secondary-btn"
          :disabled="exporting || loading || !report"
          @click="exportPdf"
        >
          <Download :size="16" /> {{ exporting ? "导出中…" : "导出月报" }}
        </button>
      </div>
    </header>
    <div v-if="error" class="alert error" role="alert">
      <span>{{ error }}</span>
      <button
        v-if="exportRetryable || !report"
        type="button"
        class="text-btn"
        :disabled="exporting"
        @click="exportRetryable ? exportPdf() : load()"
      >
        重试
      </button>
    </div>
    <div v-if="loading" class="empty-state" role="status">正在读取月报…</div>
    <template v-else-if="report">
      <div v-if="!confirmedActivity" class="statement-empty">
        <div>
          <h2>本月还没有已确认的账单</h2>
          <p>导入账单文件或截图，核对后即可查看当月收支。</p>
        </div>
        <RouterLink class="primary-btn" to="/import"
          ><Plus :size="16" /> 导入账单</RouterLink
        >
      </div>
      <template v-if="confirmedActivity">
        <div class="statement-spread">
          <section class="statement-balance" aria-label="月度收支汇总">
            <h2>本月收支差额</h2>
            <strong
              class="statement-amount"
              :class="{
                'compact-amount':
                  Math.abs(report.totals.balance_fen) >= 100000000,
              }"
              ><AnimatedAmount :value="report.totals.balance_fen"
            /></strong>
            <dl>
              <div>
                <dt><ArrowUpRight :size="16" />收入</dt>
                <dd>{{ yuan(report.totals.income_fen) }}</dd>
              </div>
              <div>
                <dt><ArrowDownRight :size="16" />净支出</dt>
                <dd>{{ yuan(report.totals.net_expense_fen) }}</dd>
              </div>
            </dl>
            <p>按已确认账单统计，净支出已扣除退款。</p>
          </section>
          <section class="trend-panel statement-trend">
            <div class="panel-heading">
              <div>
                <h2>收支走势</h2>
              </div>
              <div class="chart-switch" role="group" aria-label="趋势时间范围">
                <button
                  :class="{ active: trendMode === 'daily' }"
                  :aria-pressed="trendMode === 'daily'"
                  @click="changeTrendMode('daily')"
                >
                  按日
                </button>
                <button
                  :class="{ active: trendMode === 'weekly' }"
                  :aria-pressed="trendMode === 'weekly'"
                  @click="changeTrendMode('weekly')"
                >
                  按周
                </button>
              </div>
            </div>
            <div class="statement-plot">
              <div class="statement-scale" aria-label="纵轴金额（元）">
                <small v-if="trendPeak">{{ axisAmount(trendPeak) }}</small>
                <small
                  v-if="trendPeak >= 2"
                  class="half-tick"
                  :style="{
                    top:
                      (1 - Math.round(trendPeak / 2) / trendPeak) * 100 + '%',
                  }"
                  >{{ axisAmount(Math.round(trendPeak / 2)) }}</small
                >
                <small class="zero-tick">0 元</small>
              </div>
              <div class="statement-chart-scroll">
                <div
                  :key="trendMode"
                  class="trend-chart"
                  :class="{ weekly: trendMode === 'weekly' }"
                  aria-label="收入、毛支出与退款柱状图"
                >
                  <div
                    v-for="(day, index) in trendData"
                    :key="day.date"
                    class="trend-day"
                    :style="{ '--bar-index': index % 7 }"
                    :class="{ selected: activeTrendIndex === index }"
                    role="button"
                    tabindex="0"
                    :aria-label="`${day.range} 收入 ${yuan(day.income_fen)}，支出 ${yuan(day.gross_expense_fen)}，退款 ${yuan(day.refund_fen)}`"
                    @pointerenter="showTrendTooltip($event, index)"
                    @pointermove="showTrendTooltip($event, index)"
                    @pointerleave="hideTooltip()"
                    @focus="activeTrendIndex = index"
                    @click="activeTrendIndex = index"
                    @keydown.enter="activeTrendIndex = index"
                    @keydown.space.prevent="activeTrendIndex = index"
                  >
                    <span class="trend-bars"
                      ><i
                        class="income-bar"
                        :data-lit="day.income_fen > 0"
                        :style="{
                          height: `${(day.income_fen / maxTrend) * 100}%`,
                        }"
                      ></i
                      ><i
                        class="expense-bar"
                        :data-lit="day.gross_expense_fen > 0"
                        :style="{
                          height: `${(day.gross_expense_fen / maxTrend) * 100}%`,
                        }"
                      ></i
                      ><i
                        class="refund-bar"
                        :data-lit="day.refund_fen > 0"
                        :style="{
                          height: `${(day.refund_fen / maxTrend) * 100}%`,
                        }"
                      ></i></span
                    ><small
                      v-if="
                        trendMode === 'weekly' ||
                        Number(day.date.slice(-2)) % 5 === 0 ||
                        day.date.endsWith('01')
                      "
                      >{{ day.label }}</small
                    >
                  </div>
                </div>
              </div>
            </div>
            <div
              v-if="inspectedTrend"
              class="trend-inspector statement-inspector"
              aria-live="polite"
            >
              <strong>{{ inspectedTrend.range }}</strong>
              <div class="chart-key">
                <span
                  ><i class="income-key"></i>收入
                  {{ yuan(inspectedTrend.income_fen) }}</span
                ><span
                  ><i class="expense-key"></i>支出
                  {{ yuan(inspectedTrend.gross_expense_fen) }}</span
                ><span
                  ><i class="refund-key"></i>退款
                  {{ yuan(inspectedTrend.refund_fen) }}</span
                >
              </div>
            </div>
          </section>
        </div>
        <section class="statement-block category-panel">
          <div class="panel-heading">
            <div>
              <h2>支出去向</h2>
              <p>按毛支出统计，不含转账与还款。</p>
            </div>
            <button
              v-if="chartSegments.length"
              class="text-btn statement-largest"
              @click="goCategory(chartSegments[0].category, 'expense')"
            >
              最大支出 · {{ categories[chartSegments[0].category] }}
              {{ chartSegments[0].percent.toFixed(1) }}%
              <ChevronRight :size="14" />
            </button>
          </div>
          <div v-if="categoryTotal" class="category-content">
            <div class="donut" @pointerleave="leaveCategory">
              <svg
                viewBox="0 0 180 180"
                role="group"
                aria-label="支出类别环形图"
              >
                <defs>
                  <linearGradient
                    v-for="item in chartSegments"
                    :key="item.category"
                    :id="`ink-${item.category}`"
                    x1="0"
                    y1="1"
                    x2="1"
                    y2="0"
                    gradientUnits="objectBoundingBox"
                  >
                    <stop offset="0" :stop-color="item.color" />
                    <stop offset=".62" :stop-color="item.color" />
                    <stop
                      offset="1"
                      :stop-color="item.color"
                      stop-opacity=".65"
                    />
                  </linearGradient>
                </defs>
                <circle
                  class="donut-track"
                  cx="90"
                  cy="90"
                  r="70"
                  fill="none"
                  stroke-width="25"
                />
                <circle
                  v-for="item in chartSegments"
                  :key="item.category"
                  class="donut-segment"
                  :class="{
                    muted: activeCategory && activeCategory !== item.category,
                    active: activeCategory === item.category,
                  }"
                  cx="90"
                  cy="90"
                  r="70"
                  fill="none"
                  stroke-width="25"
                  pathLength="100"
                  :stroke="`url(#ink-${item.category})`"
                  :stroke-dasharray="`${item.percent} ${100 - item.percent}`"
                  :stroke-dashoffset="-item.offset"
                  transform="rotate(-90 90 90)"
                  role="button"
                  tabindex="0"
                  :aria-label="`${categories[item.category]} ${yuan(item.amount_fen)}，占 ${item.percent.toFixed(1)}%`"
                  @pointerenter="showCategoryTooltip($event, item)"
                  @pointermove="showCategoryTooltip($event, item)"
                  @focus="activeCategory = item.category"
                  @blur="activeCategory = null"
                  @click="selectSegment($event, item.category)"
                  @keydown.enter="goCategory(item.category, 'expense')"
                  @keydown.space.prevent="goCategory(item.category, 'expense')"
                />
                <g
                  class="statement-ring-dust"
                  aria-hidden="true"
                  pointer-events="none"
                >
                  <circle cx="90" cy="20" r="1.8" />
                  <circle cx="85" cy="20.2" r="1" />
                  <circle cx="159" cy="102" r="1.25" />
                </g>
              </svg>
              <div class="donut-hole" aria-live="polite">
                <span>{{
                  inspectedCategory
                    ? categories[inspectedCategory.category]
                    : "毛支出"
                }}</span>
                <strong>{{
                  yuan(
                    inspectedCategory?.amount_fen ??
                      report.totals.gross_expense_fen,
                  )
                }}</strong>
                <small v-if="inspectedCategory"
                  >{{ inspectedCategory.percent.toFixed(1) }}%</small
                >
              </div>
            </div>
            <div
              class="category-legend statement-legend"
              aria-label="类别支出明细"
            >
              <button
                v-for="item in chartSegments"
                :key="item.category"
                :class="{ active: activeCategory === item.category }"
                @pointerenter="showCategoryTooltip($event, item)"
                @pointermove="showCategoryTooltip($event, item)"
                @pointerleave="leaveCategory"
                @focus="activeCategory = item.category"
                @blur="activeCategory = null"
                @click="goCategory(item.category, 'expense')"
              >
                <i :style="{ background: item.color }"></i
                ><span
                  >{{ categories[item.category]
                  }}<em
                    v-if="item.category !== 'pending'"
                    >{{ budgetLabel(budgetByCategory.get(item.category)) }}</em
                  ></span
                ><strong>{{ yuan(item.amount_fen) }}</strong
                ><small>{{ item.percent.toFixed(1) }}%</small
                ><ChevronRight :size="14" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div v-else class="empty-state">
            <strong>本月还没有支出</strong
            ><span>确认入账后，这里会显示类别分布。</span>
          </div>
        </section>
      </template>
      <div
        class="statement-bottom"
        :class="{ 'budget-only': !confirmedActivity }"
      >
        <section class="statement-block budget-panel">
          <div class="panel-heading">
            <div>
              <h2>类别预算</h2>
              <p>按净支出使用额度，退款计入到账月份。</p>
            </div>
            <button class="secondary-btn" @click="openBudget()">
              <Plus :size="16" /> 设置预算
            </button>
          </div>
          <div v-if="!report.budgets.length" class="budget-empty">
            <Wallet :size="22" aria-hidden="true" /><strong
              >本月还没有设置预算</strong
            >
          </div>
          <div v-else class="statement-budgets">
            <div
              v-for="budget in report.budgets"
              :key="budget.category"
              class="statement-budget"
              :data-level="budgetLevel(budget)"
            >
              <button
                class="budget-detail"
                @click="goCategory(budget.category)"
              >
                <strong>{{ categories[budget.category] }}</strong>
                <span class="budget-status"
                  >{{ budgetLabel(budget) }}<ChevronRight :size="13"
                /></span>
                <span class="budget-track" aria-hidden="true"
                  ><i :style="{ width: budgetWidth(budget) + '%' }"></i
                ></span>
                <small
                  >净支出 {{ yuan(budget.spent_fen) }} · 额度
                  {{ yuan(budget.budget_fen) }}</small
                >
              </button>
            </div>
          </div>
        </section>
        <section v-if="confirmedActivity" class="statement-block income-panel">
          <div class="panel-heading">
            <div>
              <h2>收入构成</h2>
              <p>按已确认收入的类别汇总</p>
            </div>
          </div>
          <div v-if="incomeParts.length" class="income-list">
            <button
              v-for="(part, index) in incomeParts"
              :key="part.category"
              class="income-row"
              type="button"
              @click="goCategory(part.category, 'income')"
              :aria-label="`${categories[part.category]}收入 ${yuan(part.amount_fen)}，查看明细`"
            >
              <span>{{ categories[part.category] }}</span>
              <div class="income-track">
                <i
                  v-reveal="{ type: 'bar', delay: 120 + index * 70 }"
                  :style="{
                    width: `${report.totals.income_fen ? (part.amount_fen / report.totals.income_fen) * 100 : 0}%`,
                  }"
                ></i>
              </div>
              <strong>{{ yuan(part.amount_fen) }}</strong>
            </button>
          </div>
          <div v-else class="empty-state">
            <strong>本月没有收入明细</strong
            ><span>收入账单确认后会在这里展示来源。</span>
          </div>
        </section>
      </div>
    </template>
  </article>
  <div
    v-if="budgetOpen"
    class="modal-backdrop"
    @click.self="!saving && (budgetOpen = false)"
  >
    <section
      class="edit-dialog budget-dialog"
      role="dialog"
      aria-modal="true"
      aria-label="设置预算"
    >
      <div class="dialog-head">
        <div>
          <h2>设置月度预算</h2>
          <p>{{ month }} · 按类别管理计划金额</p>
        </div>
        <button
          class="icon-btn"
          aria-label="关闭"
          :disabled="saving"
          @click="budgetOpen = false"
        >
          ×
        </button>
      </div>
      <div v-if="budgetError" class="alert error" role="alert">
        {{ budgetError }}
      </div>
      <div class="edit-grid">
        <label
          >类别<select v-model="budgetCategory">
            <option
              v-for="[key, label] in budgetCategoryOptions"
              :key="key"
              :value="key"
            >
              {{ label }}
            </option>
          </select></label
        ><label
          >预算金额（元）<input
            v-model="budgetAmount"
            inputmode="decimal"
            placeholder="如 800.00"
        /></label>
      </div>
      <div class="dialog-actions">
        <button
          class="secondary-btn"
          :disabled="saving"
          @click="budgetOpen = false"
        >
          取消</button
        ><button class="primary-btn" :disabled="saving" @click="saveBudget">
          {{ saving ? "保存中…" : "保存预算" }}
        </button>
      </div>
    </section>
  </div>
  <Teleport to="body">
    <div
      v-if="tooltip"
      class="chart-cursor-tooltip"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
      role="status"
    >
      <div class="cursor-tooltip-title">
        <i :style="{ background: tooltip.color }"></i
        ><strong>{{ tooltip.title }}</strong>
      </div>
      <div
        v-for="row in tooltip.rows"
        :key="row.label"
        class="cursor-tooltip-row"
      >
        <span>{{ row.label }}</span
        ><strong>{{ row.value }}</strong>
      </div>
    </div>
  </Teleport>
</template>
