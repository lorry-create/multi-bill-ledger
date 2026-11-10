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
import type { MonthlyReport, ResolvedCategory } from "../api";
import { categories, download, parseYuan, yuan } from "../format";
import { csrf, errorText } from "../session";

const router = useRouter(),
  month = ref(
    new Date()
      .toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" })
      .slice(0, 7),
  ),
  report = ref<MonthlyReport | null>(null),
  loading = ref(false),
  error = ref(""),
  budgetCategory = ref<ResolvedCategory>("dining"),
  budgetAmount = ref(""),
  budgetOpen = ref(false),
  saving = ref(false);
const maxTrend = computed(() =>
  Math.max(
    1,
    ...(report.value?.daily_trend ?? []).map((x) =>
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
  const colors = ["#297f78", "#85b8aa", "#e9ad72", "#8da6bc", "#c3cdd0"];
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
const donut = computed(() =>
  chartSegments.value.length
    ? `conic-gradient(${chartSegments.value.map((x) => `${x.color} ${x.offset}% ${x.offset + x.percent}%`).join(",")})`
    : "#e7eceb",
);
async function load() {
  loading.value = true;
  error.value = "";
  try {
    report.value = await api.getMonthlyReport({
      query: { month: month.value },
    });
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
          <div class="donut" :style="{ background: donut }">
            <div class="donut-hole">
              <span>毛支出</span
              ><strong>{{ yuan(report.totals.gross_expense_fen) }}</strong>
            </div>
          </div>
          <div class="category-legend">
            <button
              v-for="item in chartSegments"
              :key="item.category"
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
          <div class="chart-key">
            <span><i class="income-key"></i>收入</span
            ><span><i class="expense-key"></i>支出</span>
          </div>
        </div>
        <div class="trend-chart" role="img" aria-label="每日收入与支出柱状图">
          <div
            v-for="day in report.daily_trend"
            :key="day.date"
            class="trend-day"
            :title="`${day.date} 收入 ${yuan(day.income_fen)}，支出 ${yuan(day.gross_expense_fen)}，退款 ${yuan(day.refund_fen)}`"
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
              v-if="
                Number(day.date.slice(-2)) % 5 === 0 || day.date.endsWith('01')
              "
              >{{ Number(day.date.slice(-2)) }}</small
            >
          </div>
        </div>
        <div class="trend-foot">
          <span>本月退款 {{ yuan(report.totals.refund_fen) }}</span
          ><span>净支出 {{ yuan(report.totals.net_expense_fen) }}</span>
        </div>
      </section>
    </div>
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
    </section></template
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
