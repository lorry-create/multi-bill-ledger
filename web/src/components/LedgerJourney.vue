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
      <div class="cover-issue"><span>月度账本</span><span>{{ issueYear }}</span></div>
      <h1>{{ issueMonth }}</h1>
      <p class="cover-intro">把两份流水，归成一本账。</p>
      <div class="cover-sources">
        <span><PlatformLogo source="wechat" :size="25" />微信支付</span>
        <span><PlatformLogo source="alipay" :size="25" />支付宝</span>
      </div>
      <div class="cover-guide">
        <div class="cover-steps" role="group" aria-label="了解账单处理流程">
          <button v-for="(step, index) in steps" :key="step.title" type="button"
            :aria-pressed="currentStep === index" @click="currentStep = index">
            {{ step.title }}
          </button>
        </div>
        <p class="cover-detail" aria-live="polite">{{ steps[currentStep].detail }}</p>
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
  background: #b9d2ef;
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
  background: linear-gradient(90deg, #dce8f5 0, #f3f8ff 2.2%, #fff 6%, #f8fbff 100%);
  box-shadow: 0 15px 26px -20px #38597a70;
}
.cover-issue, .cover-steps, .cover-sources, .cover-sources > span {
  display: flex;
  align-items: center;
}
.cover-issue {
  justify-content: space-between;
  border-bottom: 1px solid #c2d4e6;
  padding-bottom: 12px;
  color: #45617e;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cover-paper h1 {
  margin: clamp(25px, 4vh, 53px) 0 8px;
  font-family: "Songti SC", "Noto Serif CJK SC", "SimSun", serif;
  font-size: clamp(51px, 5.8vw, 84px);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -.03em;
}
.cover-intro { color: #425f7c; margin: 0; font-size: clamp(15px, 1.35vw, 20px); }
.cover-sources { gap: 22px; margin: 28px 0; }
.cover-sources > span { gap: 7px; color: #41617f; font-size: 12px; }
.cover-guide { border-top: 1px solid #c2d4e6; }
.cover-steps { gap: 20px; }
.cover-steps button {
  background: transparent;
  color: #536b81;
  border: 0;
  border-top: 2px solid transparent;
  min-height: 44px;
  margin-top: -1px;
  font-size: 13px;
  padding: 0 2px;
}
.cover-steps button[aria-pressed="true"] { color: #215da6; border-color: #3777c4; font-weight: 700; }
.cover-detail { color: #526b83; font-size: 13px; min-height: 2.8em; margin: 3px 0 0; line-height: 1.6; }
@media (max-width: 760px) {
  .cover-paper { padding: 19px 24px; }
  .cover-paper h1 { margin-top: 16px; font-size: 39px; }
  .cover-guide { display: none; }
  .cover-sources { margin: 16px 0 0; }
}
</style>
