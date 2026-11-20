<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api } from "../api";
import type { ClassificationRule, ResolvedCategory, Source } from "../api";
import { categories, sources } from "../format";
import { errorText, withCsrfRetry } from "../session";
import { ArrowRight, Plus, X } from "@lucide/vue";
import PlatformLogo from "../components/PlatformLogo.vue";
import { notify } from "../motion";

const resolvedCategories = Object.entries(categories).filter(([k]) => k !== "pending") as [
  ResolvedCategory,
  string,
][];
const sourceOptions = Object.entries(sources) as [Source, string][];
const rules = ref<ClassificationRule[]>([]),
  error = ref(""),
  loading = ref(true),
  saving = ref("");

const showCreate = ref(false),
  creating = ref(false),
  createError = ref(""),
  draft = reactive<{
    source: Source;
    merchant: string;
    category: ResolvedCategory;
    enabled: boolean;
  }>({
    source: "wechat",
    merchant: "",
    category: resolvedCategories[0][0],
    enabled: true,
  });

function openCreate() {
  draft.source = "wechat";
  draft.merchant = "";
  draft.category = resolvedCategories[0][0];
  draft.enabled = true;
  createError.value = "";
  showCreate.value = true;
}

function closeCreate() {
  if (creating.value) return;
  showCreate.value = false;
  createError.value = "";
}

async function submitCreate() {
  const merchant = draft.merchant.trim();
  if (!merchant) {
    createError.value = "请输入要匹配的商户名称。";
    return;
  }
  creating.value = true;
  createError.value = "";
  try {
    const saved = await withCsrfRetry((token) =>
      api.createRule(
        {
          body: {
            source: draft.source,
            merchant,
            category: draft.category,
            enabled: draft.enabled,
          },
        },
        token,
      ),
    );
    showCreate.value = false;
    notify(
      saved.version > 1
        ? `已更新规则「${saved.merchant_normalized}」，将在下次导入时生效`
        : `已新增规则「${saved.merchant_normalized}」，将在下次导入时生效`,
    );
    await load();
  } catch (e) {
    createError.value = errorText(e);
  } finally {
    creating.value = false;
  }
}
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
      <div class="rule-head-actions">
        <span v-if="!loading && !error" class="rule-count">{{ rules.length }} 条规则</span>
        <button type="button" class="primary-btn" @click="openCreate">
          <Plus :size="17" /> 新增规则
        </button>
      </div>
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
        ><span>可直接新增规则，或在账单页修正类别时勾选“记住该商户”。</span>
        <div class="empty-actions">
          <button type="button" class="primary-btn" @click="openCreate">
            <Plus :size="16" /> 新增规则
          </button>
          <RouterLink to="/transactions" class="text-btn">前往账单修正分类</RouterLink>
        </div>
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

  <div
    v-if="showCreate"
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="create-rule-title"
    @click.self="closeCreate"
  >
    <section class="edit-dialog rule-dialog">
      <div class="dialog-head rule-dialog-head">
        <div>
          <h2 id="create-rule-title">新增分类规则</h2>
          <p>设置平台、商户与对应类别；保存后下次导入同平台交易将自动优先匹配。</p>
        </div>
        <button
          type="button"
          class="icon-btn"
          aria-label="关闭弹窗"
          :disabled="creating"
          @click="closeCreate"
        >
          <X :size="20" />
        </button>
      </div>
      <form class="rule-form" @submit.prevent="submitCreate">
        <div class="rule-field">
          <span class="rule-field-label">所属平台</span>
          <div class="platform-picker" role="group" aria-label="所属平台">
            <button
              v-for="[key, label] in sourceOptions"
              :key="key"
              type="button"
              class="platform-pill"
              :class="{ active: draft.source === key }"
              :aria-pressed="draft.source === key"
              :disabled="creating"
              @click="draft.source = key"
            >
              <PlatformLogo :source="key" :size="26" />
              <span>{{ label }}</span>
            </button>
          </div>
        </div>

        <label class="rule-field" for="rule-merchant-input">
          <span class="rule-field-label">商户名称</span>
          <input
            id="rule-merchant-input"
            v-model="draft.merchant"
            class="rule-control"
            type="text"
            placeholder="例如：瑞幸咖啡、麦当劳(深圳南山店)"
            maxlength="120"
            :disabled="creating"
            required
          />
          <small class="field-hint"
            >自动做大小写与全半角归一化；若该平台已有同名商户规则，将更新其分类并重新启用。</small
          >
        </label>

        <label class="rule-field" for="rule-category-select">
          <span class="rule-field-label">归属类别</span>
          <select
            id="rule-category-select"
            v-model="draft.category"
            class="rule-control"
            :disabled="creating"
          >
            <option
              v-for="[key, label] in resolvedCategories"
              :key="key"
              :value="key"
            >
              {{ label }}
            </option>
          </select>
        </label>

        <div class="rule-enable-card">
          <div class="rule-enable-copy">
            <strong>保存后立即启用</strong>
            <small>仅影响之后导入的交易，不改写已确认历史账单。</small>
          </div>
          <label class="switch" aria-label="保存后立即启用">
            <input
              v-model="draft.enabled"
              type="checkbox"
              :disabled="creating"
            />
            <span></span>
          </label>
        </div>

        <p v-if="createError" class="form-error" role="alert">{{ createError }}</p>

        <div class="dialog-actions rule-dialog-actions">
          <button
            type="button"
            class="secondary-btn"
            :disabled="creating"
            @click="closeCreate"
          >
            取消
          </button>
          <button type="submit" class="primary-btn" :disabled="creating">
            {{ creating ? "保存中…" : "保存规则" }}
          </button>
        </div>
      </form>
    </section>
  </div>
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
.rule-head-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 14px;
  margin-top: 6px;
}
.rule-dialog {
  width: min(100%, 540px);
  padding: 28px 30px;
}
.rule-dialog-head {
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 22px;
}
.rule-dialog-head p {
  margin-top: 6px;
  line-height: 1.55;
}
.rule-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.rule-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rule-field-label {
  font-size: 13px;
  font-weight: 600;
  color: #2f4b6c;
}
.platform-picker {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.platform-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 8px 14px;
  border: 1px solid #d9e5f4;
  border-radius: 12px;
  background: #fafdff;
  color: #3a5574;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.platform-pill:hover:not(:disabled) {
  border-color: #9ec1ee;
  background: #f3f8ff;
}
.platform-pill.active {
  border-color: #326fca;
  background: #edf5ff;
  color: #1f4f94;
  box-shadow: inset 0 0 0 1px #326fca24;
}
.rule-control {
  height: 44px;
  width: 100%;
  padding: 0 14px;
  border: 1px solid #d6e3f2;
  border-radius: 11px;
  background: #fbfdff;
  color: #18314f;
  font-size: 14px;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.rule-control:focus {
  outline: none;
  border-color: #326fca;
  background: #fff;
  box-shadow: 0 0 0 3px #326fca1c;
}
.field-hint {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.5;
  color: #627894;
}
.rule-enable-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #dce8f7;
  border-radius: 13px;
  background: #f5f9ff;
}
.rule-enable-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.rule-enable-copy strong {
  font-size: 13px;
  font-weight: 600;
  color: #213e61;
}
.rule-enable-copy small {
  font-size: 12px;
  color: #627894;
  line-height: 1.45;
}
.rule-dialog-actions {
  margin-top: 6px;
}
@media (max-width: 560px) {
  .rule-dialog {
    padding: 22px 20px;
  }
  .platform-picker {
    grid-template-columns: 1fr;
  }
}
</style>
