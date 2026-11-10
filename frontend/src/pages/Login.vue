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
      <div class="login-art" aria-hidden="true">
        <div class="art-line art-one"></div>
        <div class="art-line art-two"></div>
        <div class="art-line art-three"></div>
        <div class="art-circle"></div>
      </div>
      <div class="login-story-copy">
        <h1>从散落的账单，<br />看见清楚的生活。</h1>
        <p>微信、支付宝的每笔收支，汇成一份你看得懂、核得准的账。</p>
      </div>
      <div class="login-foot">个人财务管理 · 数据由你确认</div>
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
