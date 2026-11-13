<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, ShieldCheck } from "@lucide/vue";
import { errorText, signIn } from "../session";
import { ApiError, isDemo } from "../api";

const router = useRouter(),
  username = ref(""),
  password = ref(""),
  busy = ref(false),
  error = ref("");
const showLocalDemo = import.meta.env.DEV && !isDemo && ["localhost", "127.0.0.1"].includes(location.hostname);
async function enterDemo() {
  username.value = "demo_a";
  password.value = "DemoA@2026";
  await submit();
}
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
    const message = errorText(e);
    error.value = showLocalDemo && e instanceof ApiError && e.payload?.error?.code === "AUTH_INVALID"
      ? `${message} 本地预览请点击上方「进入演示账本」。`
      : message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story">
      <div class="login-brand">
        <span class="brand-mark"><img src="/brand.svg" alt="" /></span> 归账
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
          <h2>{{ showLocalDemo ? "开始使用归账" : "欢迎回来" }}</h2>
          <p>{{ showLocalDemo ? "本地预览直接进入演示账本" : "登录后继续整理你的账本" }}</p>
        </div>
        <div v-if="showLocalDemo" class="local-demo-entry">
          <span>本地预览 · 合成数据</span>
          <button type="button" :disabled="busy" @click="enterDemo">进入演示账本 <ArrowRight :size="18" /></button>
          <small>一键使用项目提供的演示账号，无需手动输入</small>
        </div>
        <div v-if="showLocalDemo" class="login-method-divider">已有账号登录</div>
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
