<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowDownRight,
  ArrowUpRight,
  Download,
  Plus,
  Wallet,
} from "@lucide/vue";
import { api, isDemo } from "../api";
import type { Category, MonthlyReport, ResolvedCategory } from "../api";
import { categories, download, parseYuan, yuan } from "../format";
import { csrf, errorText } from "../session";

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
  saving = ref(false);
const activeCategory = ref<Category | null>(null);
const trendMode = ref<"daily" | "weekly">("daily");
const activeTrendIndex = ref<number | null>(null);
const trendData = computed(() => {
  const days = report.value?.daily_trend ?? [];
  if (trendMode.value === "daily") return days.map((day) => ({ ...day, label: `${Number(day.date.slice(-2))}日`, range: day.date }));
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
  const colors = ["#007aff", "#8fc5ff", "#ffad42", "#68a7c8", "#cbd6e1"];
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
function changeTrendMode(mode: "daily" | "weekly") {
  trendMode.value = mode;
  activeTrendIndex.value = null;
}
async function load() {
  loading.value = true;
  error.value = "";
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
    error.value = "请输入有效的预算金额，最多两位小数。";
    return;
  }
  saving.value = true;
  try {
    await api.putBudget(
      {
        body: {
          month: month.value,
          category: budgetCategory.value,
          amount_fen: amount,
        },
      },
      csrf(),
    );
    budgetOpen.value = false;
    await load();
  } catch (e) {
    error.value = errorText(e);
  } finally {
    saving.value = false;
  }
}
async function exportPdf() {
  if (isDemo) {
    error.value = "合成数据演示不提供 PDF，请连接真实后端导出。";
    return;
  }
  try {
    download(
      await api.exportMonthlyPdf({ query: { month: month.value } }),
      `归账-${month.value}-月报.pdf`,
    );
  } catch (e) {
    error.value = errorText(e);
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
      <input
        v-model="month"
        type="month"
        aria-label="选择月份"
        @change="load"
      /><button class="secondary-btn" @click="exportPdf">
        <Download :size="16" /> 导出月报
      </button>
    </div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <div v-if="loading" class="empty-state">正在读取月报…</div>
  <template v-else-if="report"
    ><section class="balance-hero">
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
          <div class="donut" @mouseleave="activeCategory = null">
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
                @mouseenter="activeCategory = item.category"
                @focus="activeCategory = item.category"
                @blur="activeCategory = null"
                @click="goCategory(item.category)"
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
              @mouseenter="activeCategory = item.category"
              @mouseleave="activeCategory = null"
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
            <h2>每日收支</h2>
            <p>每一天的收入与毛支出</p>
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
            @mouseenter="activeTrendIndex = index"
            @focus="activeTrendIndex = index"
            @click="activeTrendIndex = index"
            @keydown.enter="activeTrendIndex = index"
            @keydown.space.prevent="activeTrendIndex = index"
          >
            <span class="trend-bars"
              ><i
                class="income-bar"
                :style="{
                  height: `${Math.max(2, (day.income_fen / maxTrend) * 100)}%`,
                }"
              ></i
              ><i
                class="expense-bar"
                :style="{
                  height: `${Math.max(2, (day.gross_expense_fen / maxTrend) * 100)}%`,
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
        <button class="secondary-btn" @click="budgetOpen = true">
          <Plus :size="16" /> 设置预算
        </button>
      </div>
      <div v-if="!report.budgets.length" class="budget-empty">
        <span class="budget-empty-icon"><Wallet :size="25" /></span>
        <div>
          <strong>还没有设置预算</strong>
          <p>给常用类别设一个月度范围，方便及时发现超支。</p>
        </div>
        <button class="text-btn" @click="budgetOpen = true">设置预算</button>
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
                width: `${budget.budget_fen ? Math.min(100, Math.max(0, (budget.spent_fen / budget.budget_fen) * 100)) : budget.spent_fen > 0 ? 100 : 0}%`,
              }"
              :class="{ over: budget.over_fen > 0 }"
            ></span>
          </div>
          <span class="budget-values"
            >{{ yuan(budget.spent_fen) }} / {{ yuan(budget.budget_fen) }}</span
          ><span class="budget-over">{{
            budget.over_fen > 0 ? `超出 ${yuan(budget.over_fen)}` : "查看明细"
          }}</span>
        </button>
      </div>
    </section></div></template
  >
  <div
    v-if="budgetOpen"
    class="modal-backdrop"
    @click.self="budgetOpen = false"
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
        <button class="icon-btn" aria-label="关闭" @click="budgetOpen = false">
          ×
        </button>
      </div>
      <div class="edit-grid">
        <label
          >类别<select v-model="budgetCategory">
            <option
              v-for="(label, key) in categories"
              :key="key"
              :value="key"
              :disabled="key === 'pending'"
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
        <button class="secondary-btn" @click="budgetOpen = false">取消</button
        ><button class="primary-btn" :disabled="saving" @click="saveBudget">
          {{ saving ? "保存中…" : "保存预算" }}
        </button>
      </div>
    </section>
  </div>
</template>
