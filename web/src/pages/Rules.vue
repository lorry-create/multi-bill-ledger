<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import type { ClassificationRule, ResolvedCategory } from "../api";
import { categories, sources } from "../format";
import { csrf, errorText } from "../session";

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
    await api.patchRule(
      {
        path: { id: rule.id },
        body: { expected_version: rule.version, ...patch },
      },
      csrf(),
    );
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
  <section class="content-panel rules-panel">
    <div class="panel-heading">
      <div>
        <h2>我的规则</h2>
        <p>停用规则只影响之后导入的交易，不会改写已确认账单。</p>
      </div>
      <span class="count-label">{{ rules.length }} 条规则</span>
    </div>
    <div v-if="loading" class="empty-state">正在读取规则…</div>
    <div v-else-if="!rules.length" class="empty-state">
      <strong>还没有分类规则</strong
      ><span>在账单页修正类别时勾选“记住该商户”，规则会显示在这里。</span>
    </div>
    <div v-else class="rule-list">
      <div v-for="rule in rules" :key="rule.id" class="rule-row">
        <span class="rule-avatar">{{
          rule.merchant_normalized.slice(0, 1)
        }}</span>
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
            v-for="(label, key) in categories"
            :key="key"
            :value="key"
            :disabled="key === 'pending'"
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
