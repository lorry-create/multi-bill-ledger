<script setup lang="ts">
import { computed, ref } from "vue";
import { BarChart3, FileCheck2, Files } from "@lucide/vue";
import PlatformLogo from "./PlatformLogo.vue";

const steps = [
  {
    title: "归集",
    target: "导入账单",
    detail: "上传微信、支付宝导出的账单文件或交易截图。",
    icon: Files,
  },
  {
    title: "核对",
    target: "逐笔确认",
    detail: "对照原件，确认每一笔的时间、金额与分类。",
    icon: FileCheck2,
  },
  {
    title: "月报",
    target: "收支与预算",
    detail: "按月查看收支构成、每日走势和预算执行。",
    icon: BarChart3,
  },
];
const paths = [
  "M125 31 V51 C125 108 250 72 250 138",
  "M375 31 V51 C375 108 250 72 250 138",
];
const current = ref(0);
const step = computed(() => steps[current.value]);
</script>

<template>
  <div class="entry-journey">
    <div class="journey-diagram">
      <div class="journey-platforms">
        <span><PlatformLogo source="wechat" :size="29" />微信支付</span>
        <span><PlatformLogo source="alipay" :size="29" />支付宝</span>
      </div>
      <svg
        class="journey-paths"
        viewBox="0 0 500 204"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          v-for="path in paths"
          :key="path"
          :d="path"
          class="journey-track"
        />
        <g :key="current" class="journey-pulses">
          <path v-for="path in paths" :key="path" :d="path" pathLength="1" />
        </g>
      </svg>
      <div class="journey-result-card">
        <Transition name="result-change">
          <div :key="current" class="journey-result-content">
            <component
              :is="step.icon"
              :size="20"
              :stroke-width="1.7"
              aria-hidden="true"
            />
            <span>{{ step.target }}</span>
          </div>
        </Transition>
      </div>
    </div>

    <div class="journey-guide">
      <div
        class="journey-step-list"
        role="group"
        aria-label="了解账单处理流程"
        :style="{ '--active-step': current }"
      >
        <button
          v-for="(item, index) in steps"
          :key="item.title"
          type="button"
          :aria-pressed="index === current"
          @click="current = index"
        >
          {{ item.title }}
        </button>
      </div>
      <p class="journey-step-detail" aria-live="polite">
        <span :key="current">{{ step.detail }}</span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.entry-journey {
  --diagram-height: 204px;
  width: 100%;
  max-width: 520px;
}
.journey-diagram {
  position: relative;
  isolation: isolate;
  height: var(--diagram-height);
}
.journey-platforms {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  justify-items: center;
}
.journey-platforms > span {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 47px;
  padding: 6px 14px 6px 8px;
  border: 1px solid #ccdaec;
  border-radius: 13px;
  background: #f8fcff;
  box-shadow: 0 6px 14px #224a7810;
  color: #2b486a;
  font-size: 13px;
  font-weight: 620;
  white-space: nowrap;
}
.journey-paths {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.journey-paths path {
  fill: none;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
.journey-track {
  stroke: #a0b9d9;
  stroke-width: 1.3;
}
.journey-pulses path {
  stroke: #3976c6;
  stroke-width: 3.25;
  stroke-dasharray: 0.03 0.97;
  opacity: 0;
}
.journey-result-card {
  position: absolute;
  z-index: 1;
  top: 65%;
  left: 50%;
  display: grid;
  width: 148px;
  min-height: 53px;
  transform: translateX(-50%);
  border: 1px solid #a6c8f3;
  border-radius: 13px;
  background: linear-gradient(145deg, #f0f8ff, #deebfd);
  box-shadow:
    0 8px 0 -4px #d0e1f6,
    0 12px 22px #285f9f26;
  color: #224f82;
}
.journey-result-content {
  grid-area: 1 / 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 650;
  padding: 8px;
}
.journey-guide {
  margin-top: 10px;
}
.journey-step-list {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  width: min(100%, 248px);
  padding: 3px;
  border: 1px solid #bfd1e7;
  border-radius: 12px;
  background: #dce8f7;
}
.journey-step-list::before {
  content: "";
  position: absolute;
  z-index: -1;
  inset: 3px auto 3px 3px;
  width: calc((100% - 6px) / 3);
  transform: translateX(calc(var(--active-step) * 100%));
  border-radius: 8px;
  background: #f8fbff;
  box-shadow: 0 2px 7px #223e6015;
  transition: transform 0.32s var(--ease-arrive);
}
.journey-step-list button {
  min-height: 44px;
  padding: 4px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #435d7c;
  font-size: 13px;
  font-weight: 600;
}
.journey-step-list button[aria-pressed="true"] {
  color: #204f91;
}
.journey-step-list button:hover {
  color: #173f76;
}
.journey-step-detail {
  min-height: 3em;
  margin: 12px 0 0;
  color: #395674;
  font-size: 13px;
  line-height: 1.6;
}

@media (prefers-reduced-motion: no-preference) {
  .journey-track {
    stroke-dasharray: 300;
    animation: journey-draw 0.78s var(--ease-arrive) both;
  }
  .journey-pulses path {
    animation: journey-pass 1.35s 0.15s linear 2 both;
  }
  .journey-pulses path:nth-child(2) {
    animation-delay: 0.32s;
  }
  .journey-step-detail span {
    display: block;
    animation: journey-detail-in 0.23s var(--ease-arrive) both;
  }
  .result-change-enter-active,
  .result-change-leave-active {
    transition:
      opacity 0.18s ease,
      transform 0.27s var(--ease-arrive);
  }
  .result-change-enter-from {
    opacity: 0;
    transform: translateY(7px);
  }
  .result-change-leave-to {
    opacity: 0;
    transform: translateY(-6px);
  }
}
@keyframes journey-draw {
  from {
    stroke-dashoffset: 300;
    opacity: 0.15;
  }
  to {
    stroke-dashoffset: 0;
    opacity: 1;
  }
}
@keyframes journey-pass {
  from {
    stroke-dashoffset: 1;
    opacity: 0;
  }
  12%,
  82% {
    opacity: 1;
  }
  to {
    stroke-dashoffset: 0;
    opacity: 0;
  }
}
@keyframes journey-detail-in {
  from {
    opacity: 0.5;
    transform: translateY(4px);
  }
}
@media (max-width: 760px) {
  .entry-journey {
    --diagram-height: 173px;
  }
  .journey-guide {
    margin-top: 7px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .journey-step-list::before {
    transition: none;
  }
}
</style>
