<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, ShieldCheck } from "@lucide/vue";
import { errorText, signIn } from "../session";
import { isDemo } from "../api";

const router = useRouter(),
  username = ref(""),
  password = ref(""),
  busy = ref(false),
  error = ref("");
async function submit() {
  if (!username.value || !password.value) {
    error.value = "请输入账号和密码。";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    await signIn(username.value, password.value);
    router.push("/report");
  } catch (e) {
    error.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story">
      <div class="login-brand">
        <span class="brand-mark">归</span> 归账<span class="brand-dot">.</span>
      </div>
      <div class="login-story-copy">
        <h1>钱花在哪里，<br />心里有数。</h1>
        <p>把分散在微信和支付宝的记录，整理成一份可信的个人账本。</p>
      </div>
      <div class="login-preview" aria-hidden="true">
        <div class="preview-head"><span>十一月账目</span><span>归账 / 2026</span></div>
        <div class="preview-line"><span>收入</span><strong>+ ¥10,000.00</strong></div>
        <div class="preview-line"><span>餐饮与日常</span><strong>− ¥2,438.00</strong></div>
        <div class="preview-line"><span>交通出行</span><strong>− ¥856.00</strong></div>
        <div class="preview-total"><span>每一笔，都经过确认。</span><span>↗</span></div>
      </div>
      <div class="login-foot">多平台账单 · 一处核对</div>
    </section>
    <section class="login-form-panel">
      <div class="login-form">
        <div class="login-welcome">
          <span class="welcome-icon"><ShieldCheck :size="23" /></span>
          <h2>欢迎回来</h2>
          <p>登录后继续整理你的账本</p>
        </div>
        <form @submit.prevent="submit">
          <label for="username">账号</label
          ><input
            id="username"
            v-model="username"
            autocomplete="username"
            placeholder="请输入账号"
            required
          /><label for="password">密码</label
          ><input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button
            class="primary-btn login-submit"
            :disabled="busy"
            type="submit"
          >
            {{ busy ? "正在登录…" : "进入账本" }} <ArrowRight :size="18" />
          </button>
        </form>
        <p v-if="isDemo" class="demo-help">
          当前为合成数据演示模式，输入任意账号密码即可预览界面。
        </p>
        <p class="login-security">你的账单仅在本人登录后可见</p>
      </div>
    </section>
  </div>
</template>
