<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  Download,
  ChevronLeft,
  ChevronRight,
  Plus,
  Wallet,
} from "@lucide/vue";
import { api, isDemo } from "../api";
import type { Category, MonthlyReport, ResolvedCategory } from "../api";
import { categories, download, parseYuan, yuan } from "../format";
import { csrf, errorText, withCsrfRetry } from "../session";
import ParticleField from "../components/ParticleField.vue";

const router = useRouter(),
  month = ref(
    new Date()
      .toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" })
      .slice(0, 7),
  ),
  report = ref<MonthlyReport | null>(null),
  incomeParts = ref<{ category: Category; amount_fen: number }[]>([]),
  loading = ref(false),
  error = ref(""),
  budgetCategory = ref<ResolvedCategory>("dining"),
  budgetAmount = ref(""),
  budgetOpen = ref(false),
  budgetError = ref(""),
  saving = ref(false),
  exporting = ref(false),
  exportRetryable = ref(false);

const budgetCategoryOptions = Object.entries(categories).filter(
  ([key]) => key !== "pending",
) as [ResolvedCategory, string][];

function fillBudgetAmount(category: ResolvedCategory) {
  const existing = report.value?.budgets.find((b) => b.category === category);
  budgetAmount.value =
    existing && existing.budget_fen > 0
      ? (existing.budget_fen / 100).toFixed(2)
      : "";
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
type Tooltip = { x: number; y: number; title: string; color: string; rows: { label: string; value: string }[] };
const tooltip = ref<Tooltip | null>(null);
function placeTooltip(event: PointerEvent, title: string, color: string, rows: Tooltip["rows"]) {
  if (event.pointerType === "touch") return;
  tooltip.value = {
    x: Math.max(12, Math.min(event.clientX + 18, window.innerWidth - 228)),
    y: Math.max(12, Math.min(event.clientY + 18, window.innerHeight - 154)),
    title, color, rows,
  };
}
function showCategoryTooltip(event: PointerEvent, item: (typeof chartSegments.value)[number]) {
  activeCategory.value = item.category;
  placeTooltip(event, categories[item.category], item.color, [
    { label: "支出", value: yuan(item.amount_fen) },
    { label: "占比", value: `${item.percent.toFixed(1)}%` },
  ]);
}
function chooseCategory(category: Category) {
  if (
    window.matchMedia("(hover: none)").matches &&
    activeCategory.value !== category
  ) {
    activeCategory.value = category;
    return;
  }
  goCategory(category);
}
function showTrendTooltip(event: PointerEvent, index: number) {
  activeTrendIndex.value = index;
  const item = trendData.value[index];
  if (!item) return;
  placeTooltip(event, item.range, "#19b59c", [
    { label: "收入", value: yuan(item.income_fen) },
    { label: "支出", value: yuan(item.gross_expense_fen) },
    { label: "退款", value: yuan(item.refund_fen) },
  ]);
}
function hideTooltip() { tooltip.value = null; }
function leaveCategory(event: PointerEvent) {
  hideTooltip();
  if (event.pointerType !== "touch") activeCategory.value = null;
}
function shiftMonth(delta: number) {
  if (!/^\d{4}-\d{2}$/.test(month.value)) {
    month.value = new Date()
      .toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" })
      .slice(0, 7);
  }
  const [year, part] = month.value.split("-").map(Number);
  const next = new Date(year, part - 1 + delta, 1);
  month.value = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
  activeCategory.value = null;
  activeTrendIndex.value = null;
  tooltip.value = null;
  load();
}
const trendData = computed(() => {
  const days = report.value?.daily_trend ?? [];
  if (trendMode.value === "daily") return days.map((day) => ({ ...day, label: String(Number(day.date.slice(-2))), range: day.date }));
  const weeks = [];
  for (let i = 0; i < days.length; i += 7) {
    const group = days.slice(i, i + 7);
    weeks.push({
      date: group[0].date,
      label: `${i + 1}–${i + group.length}日`,
      range: `${group[0].date} — ${group[group.length - 1].date}`,
      income_fen: group.reduce((sum, day) => sum + day.income_fen, 0),
      gross_expense_fen: group.reduce((sum, day) => sum + day.gross_expense_fen, 0),
      refund_fen: group.reduce((sum, day) => sum + day.refund_fen, 0),
    });
  }
  return weeks;
});
const inspectedTrend = computed(() => {
  const items = trendData.value;
  const fallback = items.findIndex((item) => item.income_fen > 0 || item.gross_expense_fen > 0);
  return items[activeTrendIndex.value ?? (fallback < 0 ? 0 : fallback)];
});
const maxTrend = computed(() =>
  Math.max(
    1,
    ...trendData.value.map((x) =>
      Math.max(x.income_fen, x.gross_expense_fen),
    ),
  ),
);
const categoryTotal = computed(
  () =>
    report.value?.expense_by_category.reduce((n, x) => n + x.amount_fen, 0) ??
    0,
);
const chartSegments = computed(() => {
  let offset = 0;
  const colors = [
    "#19b59c",
    "#74d4bb",
    "#f4ad69",
    "#6e9bac",
    "#e88d67",
    "#2e9d8f",
    "#9cc97f",
    "#d97c83",
    "#5d7b93",
    "#a8c6c6",
  ];
  return (report.value?.expense_by_category ?? [])
    .filter((x) => x.amount_fen > 0)
    .map((x, i) => {
      const percent = categoryTotal.value
        ? (x.amount_fen / categoryTotal.value) * 100
        : 0;
      const segment = {
        ...x,
        percent,
        offset,
        color: colors[i % colors.length],
      };
      offset += percent;
      return segment;
    });
});
const inspectedCategory = computed(() => chartSegments.value.find((x) => x.category === activeCategory.value));
const topExpense = computed(() => [...chartSegments.value].sort((a, b) => b.amount_fen - a.amount_fen)[0]);
const exceededBudgets = computed(() => (report.value?.budgets ?? []).filter((x) => x.over_fen > 0));
function changeTrendMode(mode: "daily" | "weekly") {
  trendMode.value = mode;
  activeTrendIndex.value = null;
  hideTooltip();
}
async function load() {
  if (!/^\d{4}-\d{2}$/.test(month.value)) {
    return;
  }
  loading.value = true;
  error.value = "";
  exportRetryable.value = false;
  try {
    report.value = await api.getMonthlyReport({
      query: { month: month.value },
    });
    incomeParts.value = [];
    const [year, part] = month.value.split("-").map(Number);
    const date_to = `${month.value}-${new Date(year, part, 0).getDate()}`;
    let page = 1;
    const totals = new Map<Category, number>();
    while (true) {
      const result = await api.listTransactions({query:{date_from:`${month.value}-01`,date_to,flow_type:"income",page,page_size:100}});
      for (const item of result.items) totals.set(item.category,(totals.get(item.category)??0)+item.amount_fen);
      if (page * 100 >= result.total) break;
      page++;
    }
    incomeParts.value = [...totals].map(([category,amount_fen])=>({category,amount_fen})).sort((a,b)=>b.amount_fen-a.amount_fen);
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
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
  exporting.value = true;
  error.value = "";
  exportRetryable.value = false;
  try {
    download(
      await api.exportMonthlyPdf({ query: { month: month.value } }),
      `收支月报_${month.value}.pdf`,
    );
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
function goCategory(category: string) {
  const [year, part] = month.value.split("-").map(Number);
  const last = new Date(year, part, 0).getDate();
  router.push({
    path: "/transactions",
    query: {
      category,
      date_from: `${month.value}-01`,
      date_to: `${month.value}-${last}`,
    },
  });
}
</script>
<template>
  <div class="page-head report-head">
    <div>
      <h1>月度概览</h1>
      <p>把这个月的收支，放在一张清楚的账上。</p>
    </div>
    <div class="head-actions">
      <button class="month-step" type="button" aria-label="上个月" @click="shiftMonth(-1)"><ChevronLeft :size="17" /></button>
      <input
        v-model="month"
        type="month"
        aria-label="选择月份"
        @change="load"
      />
      <button class="month-step" type="button" aria-label="下个月" @click="shiftMonth(1)"><ChevronRight :size="17" /></button>
      <button class="secondary-btn" :disabled="exporting" @click="exportPdf">
        <Download :size="16" /> {{ exporting ? "导出中…" : "导出月报" }}
      </button>
    </div>
  </div>
  <div v-if="error" class="alert error" role="alert">
    <span>{{ error }}</span>
    <button
      v-if="exportRetryable"
      type="button"
      class="text-btn"
      :disabled="exporting"
      @click="exportPdf"
    >
      重试导出
    </button>
  </div>
  <div v-if="loading" class="empty-state">正在读取月报…</div>
  <template v-else-if="report"
    ><section class="balance-hero">
      <ParticleField />
      <div class="balance-main">
        <span>本月收支差额</span
        ><strong>{{ yuan(report.totals.balance_fen) }}</strong>
        <p>收入减去支出，加上退款；不代表账户余额。</p>
      </div>
      <div class="balance-side">
        <div>
          <span><ArrowUpRight :size="17" /> 本月收入</span
          ><strong>{{ yuan(report.totals.income_fen) }}</strong>
        </div>
        <div>
          <span><ArrowDownRight :size="17" /> 净支出</span
          ><strong>{{ yuan(report.totals.net_expense_fen) }}</strong>
        </div>
      </div>
      <div class="hero-decoration" aria-hidden="true"></div>
    </section>
    <div class="report-grid">
      <section class="content-panel category-panel">
        <div class="panel-heading">
          <div>
            <h2>钱花在了哪里</h2>
            <p>按毛支出统计，不含转账和还款</p>
          </div>
        </div>
        <div v-if="categoryTotal" class="category-content">
          <div class="donut" @pointerleave="leaveCategory">
            <svg viewBox="0 0 180 180" role="group" aria-label="支出类别环形图">
              <circle class="donut-track" cx="90" cy="90" r="70" fill="none" stroke-width="25" />
              <circle
                v-for="item in chartSegments"
                :key="item.category"
                class="donut-segment"
                :class="{ muted: activeCategory && activeCategory !== item.category, active: activeCategory === item.category }"
                cx="90" cy="90" r="70" fill="none" stroke-width="25" pathLength="100"
                :stroke="item.color"
                :stroke-dasharray="`${item.percent} ${100 - item.percent}`"
                :stroke-dashoffset="-item.offset"
                transform="rotate(-90 90 90)"
                role="button" tabindex="0"
                :aria-label="`${categories[item.category]} ${yuan(item.amount_fen)}，占 ${item.percent.toFixed(1)}%`"
                @pointerenter="showCategoryTooltip($event, item)"
                @pointermove="showCategoryTooltip($event, item)"
                @focus="activeCategory = item.category"
                @blur="activeCategory = null"
                @click="chooseCategory(item.category)"
                @keydown.enter="goCategory(item.category)"
                @keydown.space.prevent="goCategory(item.category)"
              />
            </svg>
            <div class="donut-hole" aria-live="polite">
              <span>{{ inspectedCategory ? categories[inspectedCategory.category] : "毛支出" }}</span>
              <strong>{{ yuan(inspectedCategory?.amount_fen ?? report.totals.gross_expense_fen) }}</strong>
              <small v-if="inspectedCategory">{{ inspectedCategory.percent.toFixed(1) }}%</small>
            </div>
          </div>
          <div class="category-legend">
            <button
              v-for="item in chartSegments"
              :key="item.category"
              :class="{ active: activeCategory === item.category }"
              @pointerenter="showCategoryTooltip($event, item)"
              @pointermove="showCategoryTooltip($event, item)"
              @pointerleave="leaveCategory"
              @focus="activeCategory = item.category"
              @blur="activeCategory = null"
              @click="goCategory(item.category)"
            >
              <i :style="{ background: item.color }"></i
              ><span>{{ categories[item.category] }}</span
              ><strong>{{ yuan(item.amount_fen) }}</strong
              ><small>{{ item.percent.toFixed(0) }}%</small>
            </button>
          </div>
        </div>
        <div v-else class="empty-state">
          <strong>本月还没有支出</strong
          ><span>确认入账后，这里会显示类别分布。</span>
        </div>
      </section>
      <section class="content-panel trend-panel">
        <div class="panel-heading">
          <div>
            <h2>收支走势</h2>
            <p>{{ trendMode === 'weekly' ? '先看全月节奏，再按日查看细节' : '逐日查看收入与毛支出' }}</p>
          </div>
          <div class="chart-switch" role="group" aria-label="趋势时间范围">
            <button :class="{ active: trendMode === 'daily' }" :aria-pressed="trendMode === 'daily'" @click="changeTrendMode('daily')">按日</button>
            <button :class="{ active: trendMode === 'weekly' }" :aria-pressed="trendMode === 'weekly'" @click="changeTrendMode('weekly')">按周</button>
          </div>
        </div>
        <div v-if="inspectedTrend" class="trend-inspector" aria-live="polite">
          <strong>{{ inspectedTrend.range }}</strong>
          <div class="chart-key"><span><i class="income-key"></i>收入 {{ yuan(inspectedTrend.income_fen) }}</span><span><i class="expense-key"></i>支出 {{ yuan(inspectedTrend.gross_expense_fen) }}</span><span>退款 {{ yuan(inspectedTrend.refund_fen) }}</span></div>
        </div>
        <div class="trend-chart" :class="{ weekly: trendMode === 'weekly' }" aria-label="收入与支出柱状图">
          <div
            v-for="(day, index) in trendData"
            :key="day.date"
            class="trend-day"
            :class="{ selected: activeTrendIndex === index }"
            role="button" tabindex="0"
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
                :style="{
                  height: `${(day.income_fen / maxTrend) * 100}%`,
                }"
              ></i
              ><i
                class="expense-bar"
                :style="{
                  height: `${(day.gross_expense_fen / maxTrend) * 100}%`,
                }"
              ></i></span
            ><small
              v-if="trendMode === 'weekly' || Number(day.date.slice(-2)) % 5 === 0 || day.date.endsWith('01')"
              >{{ day.label }}</small
            >
          </div>
        </div>
        <div class="trend-foot">
          <span>本月退款 {{ yuan(report.totals.refund_fen) }}</span
          ><span>净支出 {{ yuan(report.totals.net_expense_fen) }}</span>
        </div>
      </section>
    </div>
    <section v-if="topExpense || exceededBudgets.length" class="report-insights" aria-label="消费观察">
      <div class="insight-intro"><span>消费观察</span><strong>从数字里找到下一步</strong></div>
      <button v-if="topExpense" class="insight-item" @click="goCategory(topExpense.category)">
        <span>本月最大支出类别</span><strong>{{ categories[topExpense.category] }} · {{ yuan(topExpense.amount_fen) }}</strong><span>查看明细 <ChevronRight :size="14" /></span>
      </button>
      <button v-if="exceededBudgets.length" class="insight-item" @click="goCategory(exceededBudgets[0].category)">
        <span>需要留意</span><strong>{{ categories[exceededBudgets[0].category] }}超出预算 {{ yuan(exceededBudgets[0].over_fen) }}{{ exceededBudgets.length > 1 ? `（另有 ${exceededBudgets.length - 1} 项超支）` : "" }}</strong><span>查看相关账单 <ChevronRight :size="14" /></span>
      </button>
    </section>
    <div class="report-lower-grid"><section class="content-panel income-panel">
      <div class="panel-heading"><div><h2>收入构成</h2><p>按已确认收入的类别汇总</p></div></div>
      <div v-if="incomeParts.length" class="income-list">
        <div v-for="part in incomeParts" :key="part.category" class="income-row">
          <span>{{ categories[part.category] }}</span><div class="income-track"><i :style="{width:`${report.totals.income_fen?part.amount_fen/report.totals.income_fen*100:0}%`}"></i></div><strong>{{ yuan(part.amount_fen) }}</strong>
        </div>
      </div>
      <div v-else class="empty-state"><strong>本月没有收入明细</strong><span>收入账单确认后会在这里展示来源。</span></div>
    </section>
    <section class="content-panel budget-panel">
      <div class="panel-heading">
        <div>
          <h2>类别预算</h2>
          <p>按净支出计算，跨月退款可能让已用金额为负。</p>
        </div>
        <button class="secondary-btn" @click="openBudget()">
          <Plus :size="16" /> 设置预算
        </button>
      </div>
      <div v-if="!report.budgets.length" class="budget-empty">
        <span class="budget-empty-icon"><Wallet :size="25" /></span>
        <div>
          <strong>还没有设置预算</strong>
          <p>给常用类别设一个月度范围，方便及时发现超支。</p>
        </div>
        <button class="text-btn" @click="openBudget()">设置预算</button>
      </div>
      <div v-else class="budget-list">
        <button
          v-for="budget in report.budgets"
          :key="budget.category"
          class="budget-row"
          @click="goCategory(budget.category)"
        >
          <span class="budget-name">{{ categories[budget.category] }}</span>
          <div class="budget-track">
            <span
              :style="{
                width: `${budget.budget_fen ? Math.min(100, Math.max(0, (budget.spent_fen / budget.budget_fen) * 100)) : 0}%`,
              }"
              :class="{ over: budget.over_fen > 0 }"
            ></span>
          </div>
          <span class="budget-values">{{
            budget.budget_fen > 0
              ? `${yuan(budget.spent_fen)} / ${yuan(budget.budget_fen)}`
              : `已花 ${yuan(budget.spent_fen)} · 未设预算`
          }}</span
          ><span class="budget-over">{{
            budget.over_fen > 0
              ? `超出 ${yuan(budget.over_fen)}`
              : budget.budget_fen > 0
                ? `剩余 ${yuan(budget.remaining_fen)}`
                : "查看明细"
          }}</span>
        </button>
      </div>
    </section></div></template
  >
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
    <div v-if="tooltip" class="chart-cursor-tooltip" :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }" role="status">
      <div class="cursor-tooltip-title"><i :style="{ background: tooltip.color }"></i><strong>{{ tooltip.title }}</strong></div>
      <div v-for="row in tooltip.rows" :key="row.label" class="cursor-tooltip-row"><span>{{ row.label }}</span><strong>{{ row.value }}</strong></div>
    </div>
  </Teleport>
</template>
