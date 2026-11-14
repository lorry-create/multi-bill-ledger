<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import { Check, ScanLine, FolderInput, ChartNoAxesCombined, Pause, Play, ChevronDown } from "@lucide/vue";
import PlatformLogo from "./PlatformLogo.vue";
const stage = ref(0);
const paused = ref(false);
const expanded = ref(false);
const root = ref<HTMLElement | null>(null);
const inactive = ref(false);
let observer: IntersectionObserver | undefined;
onMounted(() => {
  observer = new IntersectionObserver(([entry]) => { inactive.value = !entry.isIntersecting; });
  if (root.value) observer.observe(root.value);
});
onBeforeUnmount(() => observer?.disconnect());
const steps = [
  { title: "归集账单", detail: "上传微信、支付宝账单文件或交易截图。", icon: FolderInput },
  { title: "识别与分类", detail: "提取交易信息，标记缺失字段与疑似重复。", icon: ScanLine },
  { title: "确认后入账", detail: "由你核对每一笔，修正后同步到月度报表。", icon: ChartNoAxesCombined },
];
</script>
<template>
  <div ref="root" class="ledger-journey" :class="[`journey-stage-${stage}`, { 'journey-paused': paused, 'motion-inactive': inactive, 'journey-expanded': expanded }]">
    <button class="journey-mobile-toggle" type="button" :aria-expanded="expanded" aria-controls="journey-details" @click="expanded = !expanded">了解账单如何归集<ChevronDown :size="17" /></button>
    <div id="journey-details" class="journey-details"><div class="journey-details-inner">
    <div class="journey-scene" aria-label="账单从两个平台归集到个人账本的功能示意">
      <svg class="journey-routes" viewBox="0 0 560 270" fill="none" aria-hidden="true">
        <path d="M95 65 C210 65 178 135 280 135 S360 205 470 205" />
        <path d="M95 205 C210 205 178 135 280 135 S360 65 470 65" />
        <path class="route-energy" d="M95 65 C210 65 178 135 280 135 S360 205 470 205" />
        <path class="route-energy second" d="M95 205 C210 205 178 135 280 135 S360 65 470 65" />
      </svg>
      <div class="journey-source source-wechat"><PlatformLogo source="wechat" :size="43" /><span>微信支付</span><small>账单与截图</small></div>
      <div class="journey-source source-alipay"><PlatformLogo source="alipay" :size="43" /><span>支付宝</span><small>账单与截图</small></div>
      <div class="journey-core"><div class="core-orbit"></div><img src="/brand.svg?v=4" alt="归账" /><span>你的个人账本</span></div>
      <div class="journey-result result-top"><ScanLine :size="18" /><span>智能解析</span><Check :size="15" /></div>
      <div class="journey-result result-bottom"><ChartNoAxesCombined :size="18" /><span>月度分析</span><Check :size="15" /></div>
    </div>
    <div class="journey-controls" role="group" aria-label="了解账单处理流程">
      <button v-for="(step, index) in steps" :key="step.title" type="button" :class="{ active: stage === index }" :aria-pressed="stage === index" @click="stage = index"><component :is="step.icon" :size="17" />{{ step.title }}</button>
      <button class="journey-pause" type="button" :aria-label="paused ? '播放流程动画' : '暂停流程动画'" :aria-pressed="paused" @click="paused = !paused"><Play v-if="paused" :size="15" /><Pause v-else :size="15" /></button>
    </div>
    <div class="journey-caption" aria-live="polite"><Transition name="caption" mode="out-in"><p :key="stage">{{ steps[stage].detail }}</p></Transition></div>
    </div></div>
  </div>
</template>
