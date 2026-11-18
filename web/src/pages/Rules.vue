<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api";
import type { ClassificationRule, ResolvedCategory } from "../api";
import { categories, sources } from "../format";
import { errorText, withCsrfRetry } from "../session";
import { ArrowRight } from "@lucide/vue";
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
  <section class="rule-index">
    <header class="page-head">
      <div>
        <h1>分类规则</h1>
        <p>同一平台再次出现这个商户时，自动使用你选的类别。</p>
      </div>
      <span v-if="!loading && !error" class="rule-count">{{ rules.length }} 条规则</span>
    </header>
    <div v-if="error" class="alert error" role="alert">{{ error }}</div>
    <div v-reveal class="index-body">
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
      <template v-else>
        <div class="index-head" aria-hidden="true">
          <span>商户与平台</span><span>归入类别</span><span>启用</span>
        </div>
        <ul class="rule-list">
          <li v-for="rule in rules" :key="rule.id" class="rule-row">
            <PlatformLogo :source="rule.source" :size="32" />
            <div class="rule-name">
              <strong>{{ rule.merchant_normalized }}</strong
              ><small
                >{{ sources[rule.source] }} ·
                {{ rule.enabled ? "正在生效" : "已停用" }}</small
              >
            </div>
            <ArrowRight :size="15" class="mapping-arrow" aria-hidden="true" />
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
            ><label class="switch"
              ><input
                type="checkbox"
                :aria-label="`启用 ${rule.merchant_normalized} 的分类规则`"
                :checked="rule.enabled"
                :disabled="saving === rule.id"
                @change="
                  change(rule, {
                    enabled: ($event.target as HTMLInputElement).checked,
                  })
                " /><span></span
            ></label>
          </li>
        </ul>
        <footer class="rule-note">在账单中修正类别时，选择「记住该商户」即可添加规则。启用或停用仅影响后续导入。</footer>
      </template>
    </div>
  </section>
</template>
<style scoped>
.rule-index { width: min(100%, 960px); margin: 0 auto; }
.rule-index .page-head { align-items: baseline; gap: 12px; }
.rule-count { flex: none; font-size: 12px; color: #54708b; }
.index-body { border-block: 1px solid #cddceb; }
.index-head, .rule-index .rule-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) 18px minmax(90px, 160px) 46px;
  align-items: center;
  gap: 12px;
  padding-inline: 12px;
}
.index-head {
  padding-block: 11px;
  color: #59708a;
  font-size: 12px;
  background: #eef4fa;
}
.index-head span:first-child { grid-column: 1 / 4; }
.index-head span:last-child { text-align: center; }
.rule-index .rule-list { padding: 0; margin: 0; list-style: none; }
.rule-index .rule-row { padding-block: 10px; border-top: 0; border-bottom: 1px solid #dfebf6; }
.rule-index .rule-name { min-width: 0; }
.rule-name strong { overflow-wrap: anywhere; }
.rule-index .rule-name small { color: #526d86; }
.rule-index .mapping-arrow { color: #7392b5; }
.rule-index select { width: 100%; height: 44px; margin: 0; }
.rule-index .switch { display: grid; position: relative; place-items: center; width: 44px; height: 44px; }
.rule-index .switch input:focus-visible + span { outline: 2px solid #326fca; outline-offset: 4px; }
.rule-note { margin: 16px 12px; font-size: 12px; line-height: 1.7; color: #566f89; }
@media (max-width: 550px) {
  .index-head, .rule-index .rule-row { grid-template-columns: 28px minmax(0, 1fr) 82px 44px; gap: 7px; padding-inline: 2px; }
  .index-head span:first-child { grid-column: 1 / 3; }
  .rule-index .mapping-arrow { display: none; }
  .rule-index select { padding-inline: 6px; }
  .rule-index .page-head { align-items: start; flex-direction: column; }
}
</style>
