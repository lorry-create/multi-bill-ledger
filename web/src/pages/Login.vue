<script setup lang="ts">
import { onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, ShieldCheck, Eye, EyeOff, Pause, Play } from "@lucide/vue";
import { errorText, signIn } from "../session";
import { ApiError, isDemo } from "../api";
import ParticleField from "../components/ParticleField.vue";
import LedgerJourney from "../components/LedgerJourney.vue";
import { motionPaused, toggleMotion } from "../motion";
const passwordVisible = ref(false);

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
        <span class="brand-mark"><img src="/brand.svg?v=4" alt="" /></span> 归账
      </div>
      <button type="button" class="cover-motion" :aria-pressed="motionPaused" @click="toggleMotion"><Play v-if="motionPaused" :size="14" /><Pause v-else :size="14" />{{ motionPaused ? '开启动效' : '暂停动效' }}</button>
      <div class="login-story-copy">
        <h1>把每一笔，<br />归于清楚。</h1>
        <p>微信、支付宝，一处整理。<br />从账单核对到月度分析，看清收支，也看见下一步。</p>
      </div>
      <LedgerJourney />
      <div class="login-foot"><ShieldCheck :size="15" /> 账单加密保存，由你确认入账</div>
    </section>
    <section class="login-form-panel">
      <div class="login-form">
        <div class="login-welcome">
          <span class="welcome-icon"><ShieldCheck :size="23" /></span>
          <h2>登录归账</h2>
          <p>欢迎回来，继续整理你的个人账本。</p>
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
          ><div class="password-control"><input
            id="password"
            v-model="password"
            :type="passwordVisible ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          /><button type="button" class="password-toggle" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :aria-pressed="passwordVisible" @click="passwordVisible = !passwordVisible"><EyeOff v-if="passwordVisible" :size="19" /><Eye v-else :size="19" /></button></div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button
            class="primary-btn login-submit"
            :disabled="busy || lockRemaining > 0"
            type="submit"
          >
            {{ lockRemaining > 0 ? `请等待 ${lockRemaining} 秒` : busy ? "正在登录…" : "进入账本" }} <ArrowRight :size="18" />
          </button>
        </form>
        <div v-if="showLocalDemo" class="local-demo-entry">
          <button type="button" :disabled="busy || lockRemaining > 0" @click="enterDemo">进入演示账本 <ArrowRight :size="17" /></button>
          <small>本地预览使用合成数据，不代表真实交易</small>
        </div>
        <p v-if="isDemo" class="demo-help">
          当前为合成数据演示模式，输入任意账号密码即可预览界面。
        </p>
        <p class="login-security">你的账单仅在本人登录后可见</p>
      </div>
    </section>
  </div>
</template>
