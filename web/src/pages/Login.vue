<script setup lang="ts">
import { onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  UserRound,
} from "@lucide/vue";
import { errorText, signIn } from "../session";
import { ApiError, isDemo } from "../api";
import LedgerJourney from "../components/LedgerJourney.vue";
const passwordVisible = ref(false);

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
  <main class="entry-shell">
    <header class="entry-brand">
      <img src="/brand.svg?v=4" alt="" width="38" height="38" />
      <span>归账</span>
    </header>

    <div class="entry-layout">
      <section class="entry-auth" aria-labelledby="entry-title">
        <div class="entry-form-header">
          <h1 id="entry-title">登录归账</h1>
        </div>
        <form class="entry-form" :aria-busy="busy" @submit.prevent="submit">
          <div class="entry-fieldset">
            <div class="entry-field">
              <UserRound
                :size="19"
                :stroke-width="1.7"
                class="entry-field-icon"
                aria-hidden="true"
              />
              <div class="entry-field-body">
                <label for="username">账号</label>
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
            <div class="entry-field">
              <LockKeyhole
                :size="18"
                :stroke-width="1.7"
                class="entry-field-icon"
                aria-hidden="true"
              />
              <div class="entry-field-body">
                <label for="password">密码</label>
                <input
                  id="password"
                  v-model="password"
                  :type="passwordVisible ? 'text' : 'password'"
                  autocomplete="current-password"
                  placeholder="请输入密码"
                  required
                />
              </div>
              <button
                class="entry-password-toggle"
                type="button"
                :aria-label="passwordVisible ? '隐藏密码' : '显示密码'"
                :aria-pressed="passwordVisible"
                @click="passwordVisible = !passwordVisible"
              >
                <EyeOff v-if="passwordVisible" :size="19" aria-hidden="true" />
                <Eye v-else :size="19" aria-hidden="true" />
              </button>
            </div>
          </div>

          <p v-if="error" class="entry-error" role="alert">{{ error }}</p>

          <button
            class="entry-submit"
            :disabled="busy || lockRemaining > 0"
            type="submit"
          >
            <span>{{
              lockRemaining > 0
                ? `请等待 ${lockRemaining} 秒`
                : busy
                  ? "正在登录…"
                  : "进入账本"
            }}</span>
            <LoaderCircle
              v-if="busy"
              :size="19"
              class="entry-loading-icon"
              aria-hidden="true"
            />
            <ArrowRight v-else :size="20" aria-hidden="true" />
          </button>
        </form>
        <div v-if="showLocalDemo" class="entry-demo">
          <button
            type="button"
            :disabled="busy || lockRemaining > 0"
            @click="enterDemo"
          >
            进入演示账本 <ArrowRight :size="16" aria-hidden="true" />
          </button>
          <small>本地演示使用合成数据</small>
        </div>
        <p v-if="isDemo" class="entry-demo-copy">
          当前为合成数据演示模式，输入任意账号密码即可预览界面。
        </p>
        <p class="entry-security">
          <ShieldCheck :size="16" :stroke-width="1.7" aria-hidden="true" />
          账单仅对你本人可见
        </p>
      </section>

      <section class="entry-story" aria-labelledby="entry-story-title">
        <h2 id="entry-story-title">微信和支付宝，<br />归进同一本账。</h2>
        <LedgerJourney />
      </section>
    </div>
  </main>
</template>

<style scoped>
.entry-shell {
  --entry-ink: #153454;
  --entry-muted: #4b6582;
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  padding: 28px max(28px, calc((100vw - 1210px) / 2)) 48px;
  color: var(--entry-ink);
  background:
    radial-gradient(ellipse at 12% 54%, #c6dff9b0, transparent 62%),
    radial-gradient(ellipse at 88% 89%, #c9d9f38c, transparent 45%),
    linear-gradient(112deg, #f4f9ff, #eaf2fc 57%, #f3f7fd);
}
.entry-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  align-self: flex-start;
  font-size: 24px;
  font-weight: 720;
  letter-spacing: -0.03em;
}
.entry-brand img {
  flex: none;
  border-radius: 11px;
  box-shadow: 0 6px 16px #2c69b32b;
}
.entry-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.13fr) minmax(0, 1fr);
  grid-template-areas: "story auth";
  align-items: center;
  gap: clamp(40px, 8vw, 122px);
  flex: 1;
  padding-top: 28px;
}
.entry-story {
  grid-area: story;
  min-width: 0;
}
.entry-story h2 {
  margin: 0 0 clamp(31px, 4.8vh, 56px);
  color: #153454;
  font-size: clamp(36px, 4.25vw, 66px);
  line-height: 1.13;
  letter-spacing: -0.035em;
  font-weight: 720;
}

.entry-auth {
  grid-area: auth;
  width: 100%;
  max-width: 460px;
  justify-self: end;
  padding: 39px 37px 25px;
  border-radius: 25px;
  border: 1px solid #ffffff;
  background: linear-gradient(156deg, #fff 45%, #f5f9ff);
  box-shadow:
    0 21px 57px #2951871a,
    0 0 0 1px #cddcee;
  transition: box-shadow 0.26s ease;
}
.entry-auth:focus-within {
  box-shadow:
    0 24px 58px #29518724,
    0 0 0 1px #afc9ea;
}
.entry-form-header {
  margin-bottom: 27px;
}
.entry-form-header h1 {
  margin: 0;
  color: #173656;
  font-size: clamp(28px, 2.65vw, 40px);
  line-height: 1.15;
  letter-spacing: -0.035em;
  font-weight: 720;
}
.entry-form {
  display: grid;
  gap: 18px;
}
.entry-fieldset {
  border: 1px solid #d2deec;
  border-radius: 16px;
  background: #f5f8fd;
}
.entry-field {
  display: grid;
  position: relative;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 11px;
  min-height: 74px;
  padding: 10px 10px 10px 15px;
  border-radius: 15px 15px 0 0;
  transition:
    background 0.2s ease,
    box-shadow 0.2s ease;
}
.entry-field + .entry-field {
  border-radius: 0 0 15px 15px;
}
.entry-field + .entry-field::before {
  content: "";
  position: absolute;
  inset: 0 13px auto 47px;
  border-top: 1px solid #d4e1ef;
  pointer-events: none;
}
.entry-field:focus-within {
  z-index: 1;
  background: #fff;
  box-shadow: inset 0 0 0 1.5px #588bcd;
}
.entry-field + .entry-field:focus-within::before {
  opacity: 0;
}
.entry-field-icon {
  color: #5b7a9f;
  transition:
    color 0.2s ease,
    transform 0.2s ease;
}
.entry-field:focus-within .entry-field-icon {
  color: #235fae;
  transform: translateY(-1px);
}
.entry-field-body {
  min-width: 0;
  display: grid;
  gap: 3px;
}
.entry-field label {
  font-size: 12px;
  color: #395574;
  font-weight: 680;
}
.entry-field .entry-field-body input {
  appearance: none;
  width: 100%;
  min-width: 0;
  height: 31px;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: transparent;
  font: inherit;
  font-size: 16px;
  color: #1d3a5c;
}
.entry-field input:focus {
  outline: none;
  box-shadow: none;
  border: 0;
}
.entry-field input::placeholder {
  color: #566d87;
}
.entry-password-toggle {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 9px;
  color: #46678e;
  background: transparent;
}
.entry-password-toggle:hover {
  color: #205da8;
  background: #e7f0fc;
}
.entry-error {
  margin: 0;
  padding: 11px 12px;
  border: 1px solid #f1d6d0;
  border-radius: 9px;
  background: #fff4f1;
  color: #a23e2c;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.entry-submit {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  min-height: 53px;
  padding: 0 17px;
  border: 1px solid #2c5c9b;
  border-radius: 12px;
  background: linear-gradient(108deg, #285fa8, #214d8a);
  color: #fff;
  font-size: 14px;
  font-weight: 680;
  box-shadow:
    0 9px 17px #254d8530,
    inset 0 1px #bedcff29;
  transition:
    transform 0.22s var(--ease-arrive),
    box-shadow 0.22s ease;
}
.entry-submit svg {
  flex: none;
  transition: transform 0.22s var(--ease-arrive);
}
.entry-submit:hover:not(:disabled) {
  box-shadow:
    0 12px 21px #254d8541,
    inset 0 1px #bedcff50;
}
.entry-submit:hover:not(:disabled) svg {
  transform: translateX(3px);
}
.entry-submit:active:not(:disabled) {
  transform: scale(0.985);
}
.entry-submit:disabled {
  opacity: 0.8;
  cursor: not-allowed;
}
.entry-demo {
  display: grid;
  gap: 0;
  margin-top: 14px;
}
.entry-demo button {
  display: flex;
  gap: 7px;
  align-items: center;
  justify-self: start;
  min-height: 44px;
  padding: 0 3px;
  border: 0;
  background: transparent;
  color: #255a9a;
  font-size: 13px;
  font-weight: 620;
}
.entry-demo button:hover:enabled {
  color: #123b72;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.entry-demo button:disabled {
  opacity: 0.65;
}
.entry-demo small {
  color: var(--entry-muted);
  padding-inline: 3px;
  font-size: 11px;
}
.entry-demo-copy {
  color: var(--entry-muted);
  font-size: 12px;
  line-height: 1.7;
}
.entry-security {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 19px 0 0;
  padding-top: 15px;
  border-top: 1px solid #dae5f1;
  color: var(--entry-muted);
  font-size: 12px;
}
.entry-security svg {
  flex: none;
}

@media (prefers-reduced-motion: no-preference) {
  .entry-auth {
    animation: entry-panel-in 0.5s var(--ease-arrive) both;
  }
  .entry-loading-icon {
    animation: entry-loading 0.8s linear infinite;
  }
}
@keyframes entry-panel-in {
  from {
    opacity: 0.72;
    transform: translateY(9px);
  }
}
@keyframes entry-loading {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .entry-layout {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 38px;
  }
  .entry-auth {
    padding: 28px 24px 20px;
  }
}
@media (max-width: 760px) {
  .entry-shell {
    padding: 21px 17px 30px;
  }
  .entry-brand {
    align-self: center;
    font-size: 21px;
  }
  .entry-brand img {
    width: 32px;
    height: 32px;
    border-radius: 9px;
  }
  .entry-layout {
    width: min(100%, 436px);
    align-self: center;
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: "auth" "story";
    gap: 38px;
    padding-top: 25px;
  }
  .entry-auth {
    padding: 25px 20px 19px;
    justify-self: center;
    border-radius: 20px;
  }
  .entry-form-header {
    margin-bottom: 19px;
  }
  .entry-story {
    padding: 0 4px;
  }
  .entry-story h2 {
    margin-bottom: 25px;
    font-size: clamp(30px, 8vw, 38px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .entry-auth,
  .entry-field,
  .entry-field-icon,
  .entry-submit,
  .entry-submit svg {
    transition: none;
  }
}
</style>
