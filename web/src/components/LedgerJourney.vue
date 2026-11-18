<script setup lang="ts">
import { ref } from "vue";
import PlatformLogo from "./PlatformLogo.vue";

const issueDate = new Date();
const issueMonth = new Intl.DateTimeFormat("zh-CN-u-nu-hanidec", {
  month: "long",
  timeZone: "Asia/Shanghai",
}).format(issueDate);
const issueYear = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  timeZone: "Asia/Shanghai",
}).format(issueDate);
const steps = [
  { title: "归集", detail: "上传微信、支付宝导出的账单文件或交易截图。" },
  { title: "核对", detail: "对照原件，确认每一笔的时间、金额与分类。" },
  { title: "月报", detail: "按月查看收支构成、每日走势和预算执行情况。" },
];
const currentStep = ref(0);
</script>
<template>
  <div class="account-cover">
    <div class="cover-paper">
      <div class="cover-issue">
        <span>月度账本</span><span>{{ issueYear }}</span>
      </div>
      <p class="cover-month">{{ issueMonth }}</p>
      <p class="cover-intro">把两份流水，归成一本账。</p>
      <div class="cover-sources">
        <span><PlatformLogo source="wechat" :size="25" />微信支付</span>
        <span><PlatformLogo source="alipay" :size="25" />支付宝</span>
      </div>
      <div class="cover-guide" :style="{ '--cover-step': currentStep }">
        <div class="cover-steps" role="group" aria-label="了解账单处理流程">
          <button
            v-for="(step, index) in steps"
            :key="step.title"
            type="button"
            :aria-pressed="currentStep === index"
            @click="currentStep = index"
          >
            {{ step.title }}
          </button>
        </div>
        <p class="cover-detail" aria-live="polite">
          <span :key="currentStep">{{ steps[currentStep].detail }}</span>
        </p>
      </div>
    </div>
  </div>
</template>
<style scoped>
.account-cover {
  width: min(100%, 550px);
  justify-self: center;
  position: relative;
  isolation: isolate;
  padding: 9px 7px 0 0;
}
.account-cover::before {
  content: "";
  position: absolute;
  z-index: -1;
  inset: 0 0 9px 8px;
  background: linear-gradient(125deg, #b2cceb, #d2e4f8 58%, #b9d2ef);
  border: 1px solid #aac4e1;
  border-radius: 5px 17px 14px 4px;
  transform: rotate(1.4deg);
}
.cover-paper {
  position: relative;
  color: #213e61;
  padding: clamp(24px, 3vw, 48px) clamp(24px, 3.1vw, 53px);
  border: 1px solid #d1dfed;
  border-radius: 4px 13px 13px 4px;
  background: linear-gradient(
    90deg,
    #dce8f5 0,
    #f3f8ff 2.2%,
    #fff 6%,
    #f8fbff 100%
  );
  box-shadow: 0 15px 26px -20px #38597a70;
  transition:
    transform 0.34s var(--ease-arrive),
    box-shadow 0.34s var(--ease-arrive);
}
.cover-issue,
.cover-steps,
.cover-sources,
.cover-sources > span {
  display: flex;
  align-items: center;
}
.cover-issue {
  position: relative;
  overflow: hidden;
  justify-content: space-between;
  border-bottom: 1px solid #c2d4e6;
  padding-bottom: 12px;
  color: #45617e;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cover-issue::after {
  content: "";
  position: absolute;
  inset: auto 0 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    #5f9cdb 78%,
    #abcff6 94%,
    transparent
  );
  opacity: 0;
  pointer-events: none;
}
.cover-month {
  margin: clamp(25px, 4vh, 53px) 0 8px;
  font-family: "Songti SC", "Noto Serif CJK SC", "SimSun", serif;
  font-size: clamp(51px, 5.8vw, 84px);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.03em;
}
.cover-intro {
  color: #425f7c;
  margin: 0;
  font-size: clamp(15px, 1.35vw, 20px);
}
.cover-sources {
  gap: 22px;
  margin: 28px 0;
}
.cover-sources > span {
  gap: 7px;
  color: #41617f;
  font-size: 12px;
}
.cover-guide {
  --cover-step-width: 58px;
  position: relative;
  border-top: 1px solid #c2d4e6;
}
.cover-guide::before {
  content: "";
  position: absolute;
  z-index: 1;
  top: -1px;
  left: 0;
  width: 36px;
  height: 2px;
  border-radius: 2px;
  background: #3777c4;
  transform: translateX(calc(var(--cover-step) * var(--cover-step-width)));
  transition: transform 0.32s var(--ease-arrive);
  pointer-events: none;
}
.cover-steps button {
  background: transparent;
  color: #536b81;
  border: 0;
  text-align: left;
  flex: 0 0 var(--cover-step-width);
  min-height: 44px;
  margin-top: -1px;
  font-size: 13px;
  padding: 0 2px;
}
.cover-steps button:hover {
  color: #214e84;
}
.cover-steps button[aria-pressed="true"] {
  color: #215da6;
  font-weight: 700;
}
.cover-detail {
  color: #526b83;
  font-size: 13px;
  min-height: 2.8em;
  margin: 3px 0 0;
  line-height: 1.6;
}
@media (prefers-reduced-motion: no-preference) {
  .account-cover {
    animation: folio-arrive 0.72s var(--ease-arrive) both;
  }
  .account-cover::before {
    animation: folio-backing 0.85s var(--ease-arrive) both;
  }
  .cover-issue::after {
    animation: folio-rule-glint 0.9s 0.12s var(--ease-arrive) both;
  }
  .cover-detail span {
    display: block;
    animation: folio-detail 0.24s var(--ease-arrive) both;
  }
}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  .account-cover:is(:hover, :focus-within) .cover-paper {
    transform: translateY(-3px);
    box-shadow: 0 21px 32px -20px #38597a82;
  }
}
@keyframes folio-arrive {
  from {
    transform: translateX(-15px);
    opacity: 0.65;
  }
}
@keyframes folio-backing {
  from {
    transform: translate(9px, -7px) rotate(3deg);
  }
  to {
    transform: rotate(1.4deg);
  }
}
@keyframes folio-rule-glint {
  0% {
    transform: translateX(-100%);
    opacity: 0;
  }
  22% {
    opacity: 1;
  }
  100% {
    transform: translateX(95%);
    opacity: 0;
  }
}
@keyframes folio-detail {
  from {
    opacity: 0.4;
    transform: translateY(4px);
  }
}
@media (max-width: 760px) {
  .cover-paper {
    padding: 21px 22px;
  }
  .cover-month {
    margin-top: 17px;
    font-size: 40px;
  }
  .cover-sources {
    margin: 17px 0;
    gap: 14px;
    flex-wrap: wrap;
  }
}
@media (prefers-reduced-motion: reduce) {
  .cover-paper,
  .cover-guide::before {
    transition: none;
  }
}
</style>
