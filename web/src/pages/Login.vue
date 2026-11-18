<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowRight,
  ShieldCheck,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  UserRound,
} from "@lucide/vue";
import { errorText, signIn } from "../session";
import { ApiError, isDemo } from "../api";
import ParticleField from "../components/ParticleField.vue";
import LedgerJourney from "../components/LedgerJourney.vue";
const passwordVisible = ref(false);
const narrowLayout = window.matchMedia("(max-width: 760px)");
const mobileCover = ref(narrowLayout.matches);
function updateCoverPosition(event: MediaQueryListEvent) {
  mobileCover.value = event.matches;
}
onMounted(() => narrowLayout.addEventListener("change", updateCoverPosition));

const router = useRouter(),
  route = useRoute(),
  username = ref(""),
  password = ref(""),
  busy = ref(false),
  error = ref(""),
  lockRemaining = ref(0);
let lockTimer: ReturnType<typeof setInterval> | undefined;
const showLocalDemo =
  import.meta.env.DEV &&
  !isDemo &&
  ["localhost", "127.0.0.1"].includes(location.hostname);
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
  narrowLayout.removeEventListener("change", updateCoverPosition);
  if (lockTimer) clearInterval(lockTimer);
});
async function enterDemo() {
  if (busy.value || lockRemaining.value > 0) return;
  username.value = "demo_a";
  password.value = "DemoA@2026";
  await submit();
}
async function submit() {
  if (busy.value || lockRemaining.value > 0) return;
  if (!username.value || !password.value) {
    error.value = "请输入账号和密码。";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    await signIn(username.value, password.value);
    const next = route.query.next;
    const target = typeof next === "string" ? router.resolve(next) : null;
    if (target?.path === "/transactions") router.replace(target.fullPath);
    else router.push("/report");
  } catch (e) {
    if (
      e instanceof ApiError &&
      (e.status === 429 || e.payload?.error?.code === "LOGIN_LOCKED")
    ) {
      const wait = e.payload?.error?.details?.retry_after_seconds;
      startLockCountdown(typeof wait === "number" && wait > 0 ? wait : 60);
      return;
    }
    const message = errorText(e);
    error.value =
      showLocalDemo &&
      e instanceof ApiError &&
      e.payload?.error?.code === "AUTH_INVALID"
        ? `${message} 本地预览可选择「进入演示账本」。`
        : message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <main class="login-page folio-login">
    <section class="login-story">
      <ParticleField />
      <div class="login-brand">
        <span class="brand-mark"><img src="/brand.svg?v=4" alt="" /></span> 归账
      </div>
      <Teleport defer to="#login-cover-slot" :disabled="!mobileCover">
        <LedgerJourney />
      </Teleport>
      <div class="login-foot">
        <ShieldCheck :size="15" /> 账单加密保存，由你确认入账
      </div>
    </section>
    <section class="login-form-panel" aria-labelledby="folio-login-title">
      <div class="login-form">
        <div class="login-welcome">
          <h1 id="folio-login-title">登录归账</h1>
          <p>打开你的个人账本。</p>
        </div>
        <form :aria-busy="busy" @submit.prevent="submit">
          <div class="folio-field">
            <label for="username">账号</label>
            <div class="folio-input">
              <UserRound
                class="folio-input-icon"
                :size="18"
                :stroke-width="1.7"
                aria-hidden="true"
              />
              <input
                id="username"
                v-model="username"
                autocomplete="username"
                autocapitalize="none"
                spellcheck="false"
                placeholder="请输入账号"
                required
              />
            </div>
          </div>
          <div class="folio-field">
            <label for="password">密码</label>
            <div class="folio-input password-control">
              <LockKeyhole
                class="folio-input-icon"
                :size="18"
                :stroke-width="1.7"
                aria-hidden="true"
              />
              <input
                id="password"
                v-model="password"
                :type="passwordVisible ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="请输入密码"
                required
              />
              <button
                type="button"
                class="password-toggle"
                :aria-label="passwordVisible ? '隐藏密码' : '显示密码'"
                :aria-pressed="passwordVisible"
                @click="passwordVisible = !passwordVisible"
              >
                <EyeOff v-if="passwordVisible" :size="19" aria-hidden="true" />
                <Eye v-else :size="19" aria-hidden="true" />
              </button>
            </div>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button
            class="primary-btn login-submit"
            :disabled="busy || lockRemaining > 0"
            type="submit"
          >
            {{
              lockRemaining > 0
                ? `请等待 ${lockRemaining} 秒`
                : busy
                  ? "正在登录…"
                  : "进入账本"
            }}
            <LoaderCircle
              v-if="busy"
              :size="18"
              class="folio-spinner"
              aria-hidden="true"
            />
            <ArrowRight v-else :size="18" aria-hidden="true" />
          </button>
        </form>
        <div v-if="showLocalDemo" class="local-demo-entry">
          <button
            type="button"
            :disabled="busy || lockRemaining > 0"
            @click="enterDemo"
          >
            进入演示账本 <ArrowRight :size="17" />
          </button>
          <small>本地预览使用合成数据，不代表真实交易</small>
        </div>
        <p v-if="isDemo" class="demo-help">
          当前为合成数据演示模式，输入任意账号密码即可预览界面。
        </p>
        <p class="login-security">你的账单仅在本人登录后可见</p>
      </div>
    </section>
    <div id="login-cover-slot"></div>
  </main>
</template>
<style scoped>
.folio-login .login-story {
  display: grid;
  align-content: space-between;
  align-items: start;
  gap: clamp(26px, 5vh, 56px);
  background:
    radial-gradient(ellipse at 18% 10%, #f5f9ff 8%, transparent 68%), #e6effb;
}
.folio-login .login-foot {
  margin: 0;
  padding-top: 0;
}
#login-cover-slot:empty {
  display: none;
}
#login-cover-slot {
  display: contents;
}
.folio-login .login-form-panel {
  background: #fff;
}
.folio-login .login-form {
  max-width: 390px;
}
.folio-login .login-welcome {
  margin-bottom: 29px;
}
.folio-login .login-welcome h1 {
  margin: 0 0 9px;
  color: #203d60;
  font-size: clamp(30px, 3vw, 43px);
  font-weight: 730;
  line-height: 1.15;
  letter-spacing: -0.035em;
}
.folio-login .login-welcome::after {
  content: "";
  display: block;
  width: 42px;
  height: 2px;
  margin-top: 19px;
  transform-origin: left;
  border-radius: 2px;
  background: #6d9dd7;
}
.folio-field + .folio-field {
  margin-top: 19px;
}
.folio-field label {
  display: block;
}
.folio-input {
  position: relative;
}
.folio-login .login-form .folio-input input {
  width: 100%;
  height: 52px;
  margin: 0;
  padding-left: 43px;
  border-color: #d3dfed;
  background: #f8fbff;
  font-size: 16px;
}
.folio-login .login-form .folio-input input:focus {
  background: #fff;
  border-color: #5286c8;
}
.folio-input-icon {
  position: absolute;
  left: 14px;
  top: 17px;
  color: #59799e;
  pointer-events: none;
  transition:
    color 0.18s ease,
    transform 0.18s var(--ease-arrive);
}
.folio-input:focus-within .folio-input-icon {
  color: #295fac;
  transform: translateX(2px);
}
.folio-login .password-control {
  margin-bottom: 0;
}
.folio-login .password-toggle {
  top: 4px;
}
.folio-login .login-form .login-submit {
  margin-top: 23px;
}
.folio-login .login-form .form-error {
  margin: 13px 0 0;
}
.folio-login .login-form .local-demo-entry {
  margin-top: 18px;
}
.folio-login .login-security {
  margin-top: 21px;
}
@media (prefers-reduced-motion: no-preference) {
  .folio-login .login-welcome::after {
    animation: folio-header-rule 0.55s 0.12s var(--ease-arrive) both;
  }
  .folio-spinner {
    animation: folio-wait 0.8s linear infinite;
  }
}
@keyframes folio-header-rule {
  from {
    transform: scaleX(0);
  }
}
@keyframes folio-wait {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 760px) {
  .folio-login {
    display: flex;
    flex-direction: column;
    background: white;
  }
  .folio-login .login-story {
    display: contents;
  }
  .folio-login .login-brand {
    padding: 22px 25px 0;
    order: 0;
  }
  .folio-login .login-form-panel {
    order: 1;
    padding: 29px 25px 31px;
  }
  #login-cover-slot :deep(.account-cover) {
    order: 2;
    align-self: center;
    width: min(calc(100% - 50px), 430px);
    margin: 0 0 32px;
  }
  .folio-login .login-story :deep(.particle-field),
  .folio-login .login-foot {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .folio-input-icon {
    transition: none;
    transform: none;
  }
}
</style>
