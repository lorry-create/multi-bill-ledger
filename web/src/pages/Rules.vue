<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import type { ClassificationRule, ResolvedCategory } from "../api";
import { categories, sources } from "../format";
import { errorText, withCsrfRetry } from "../session";
import { ArrowRight, SlidersHorizontal, BookOpenCheck, Repeat2 } from "@lucide/vue";
import ParticleField from "../components/ParticleField.vue";
import PlatformLogo from "../components/PlatformLogo.vue";
import { notify } from "../motion";

const resolvedCategories = Object.entries(categories).filter(([k]) => k !== "pending") as [
  ResolvedCategory,
  string,
][];
const rules = ref<ClassificationRule[]>([]),
  error = ref(""),
  loading = ref(true),
  saving = ref("");
async function load() {
  loading.value = true;
  try {
    rules.value = (await api.listRules({})).items;
    error.value = "";
  } catch (e) {
    error.value = errorText(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
async function change(
  rule: ClassificationRule,
  patch: { enabled?: boolean; category?: ResolvedCategory },
) {
  saving.value = rule.id;
  try {
    await withCsrfRetry((token) =>
      api.patchRule(
        {
          path: { id: rule.id },
          body: { expected_version: rule.version, ...patch },
        },
        token,
      ),
    );
    notify(patch.enabled === false ? "规则已停用" : patch.enabled === true ? "规则已启用，将用于之后导入的交易" : "商户分类规则已更新");
    await load();
  } catch (e) {
    error.value = errorText(e);
    if ((e as { status?: number }).status === 409) await load();
  } finally {
    saving.value = "";
  }
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>分类规则</h1>
      <p>记住你对商户的分类选择，让下一笔交易自动归位。</p>
    </div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div>
  <section class="rule-explainer">
    <ParticleField />
    <div><h2>你的选择，会成为下一次的规则。</h2><p>在账单中修正类别，并选择“记住该商户”。同平台的新交易会优先采用你的分类。</p></div>
    <div class="rule-cycle"><span><SlidersHorizontal :size="20" />修正分类</span><ArrowRight :size="16" /><span><BookOpenCheck :size="20" />记住商户</span><ArrowRight :size="16" /><span><Repeat2 :size="20" />下次自动分类</span></div>
  </section>
  <section class="content-panel rules-panel">
    <div class="panel-heading">
      <div>
        <h2>我的规则</h2>
        <p>停用规则只影响之后导入的交易，不会改写已确认账单。</p>
      </div>
      <span class="count-label">{{ rules.length }} 条规则</span>
    </div>
    <div v-if="loading" class="empty-state">正在读取规则…</div>
    <div v-else-if="error" class="empty-state">
      <strong>规则暂时没有加载出来</strong>
      <button type="button" class="text-btn" @click="load">重新加载</button>
    </div>
    <div v-else-if="!rules.length" class="empty-state">
      <strong>还没有分类规则</strong
      ><span>在账单页修正类别时勾选“记住该商户”，规则会显示在这里。</span>
      <RouterLink to="/transactions" class="text-btn">前往账单修正分类</RouterLink>
    </div>
    <div v-else class="rule-list">
      <div v-for="rule in rules" :key="rule.id" class="rule-row">
        <PlatformLogo :source="rule.source" :size="38" />
        <div class="rule-name">
          <strong>{{ rule.merchant_normalized }}</strong
          ><small
            >{{ sources[rule.source] }} ·
            {{ rule.enabled ? "正在生效" : "已停用" }}</small
          >
        </div>
        <select
          :value="rule.category"
          :disabled="saving === rule.id"
          :aria-label="`修改 ${rule.merchant_normalized} 的类别`"
          @change="
            change(rule, {
              category: ($event.target as HTMLSelectElement)
                .value as ResolvedCategory,
            })
          "
        >
          <option
            v-for="[key, label] in resolvedCategories"
            :key="key"
            :value="key"
          >
            {{ label }}
          </option></select
        ><label class="switch" :aria-label="`启用 ${rule.merchant_normalized}`"
          ><input
            type="checkbox"
            :checked="rule.enabled"
            :disabled="saving === rule.id"
            @change="
              change(rule, {
                enabled: ($event.target as HTMLInputElement).checked,
              })
            " /><span></span
        ></label>
      </div>
    </div>
  </section>
</template>
