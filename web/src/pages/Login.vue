<script setup lang="ts">
import { onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, ShieldCheck } from "@lucide/vue";
import { errorText, signIn } from "../session";
import { ApiError, isDemo } from "../api";
import ParticleField from "../components/ParticleField.vue";

const router = useRouter(),
  username = ref(""),
  password = ref(""),
  busy = ref(false),
  error = ref(""),
  lockRemaining = ref(0);
let lockTimer: ReturnType<typeof setInterval> | undefined;
const showLocalDemo = import.meta.env.DEV && !isDemo && ["localhost", "127.0.0.1"].includes(location.hostname);
function startLockCountdown(seconds: number) {
  if (lockTimer) clearInterval(lockTimer);
  lockRemaining.value = Math.max(1, Math.ceil(seconds));
  error.value = `登录失败次数过多，请在 ${lockRemaining.value} 秒后再试。`;
  lockTimer = setInterval(() => {
    lockRemaining.value -= 1;
    if (lockRemaining.value <= 0) {
      lockRemaining.value = 0;
      clearInterval(lockTimer);
      lockTimer = undefined;
      error.value = "";
    } else {
      error.value = `登录失败次数过多，请在 ${lockRemaining.value} 秒后再试。`;
    }
  }, 1000);
}
onUnmounted(() => {
  if (lockTimer) clearInterval(lockTimer);
});
async function enterDemo() {
  if (busy.value || lockRemaining.value > 0) return;
  username.value = "demo_a";
  password.value = "DemoA@2026";
  await submit();
}
async function submit() {
  if (lockRemaining.value > 0) return;
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
    if (e instanceof ApiError && (e.status === 429 || e.payload?.error?.code === "LOGIN_LOCKED")) {
      const wait = e.payload?.error?.details?.retry_after_seconds;
      startLockCountdown(typeof wait === "number" && wait > 0 ? wait : 60);
      return;
    }
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
      <ParticleField />
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
          <button type="button" :disabled="busy || lockRemaining > 0" @click="enterDemo">进入演示账本 <ArrowRight :size="18" /></button>
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
            :disabled="busy || lockRemaining > 0"
            type="submit"
          >
            {{ lockRemaining > 0 ? `请等待 ${lockRemaining} 秒` : busy ? "正在登录…" : "进入账本" }} <ArrowRight :size="18" />
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
