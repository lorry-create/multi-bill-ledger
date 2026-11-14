<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { yuan } from "../format";
import { motionPaused } from "../motion";
const props = defineProps<{ value: number }>();
const displayed = ref(props.value);
const accessible = computed(() => yuan(props.value));
let frame = 0;
watch(() => props.value, (next, previous) => {
  cancelAnimationFrame(frame);
  if (motionPaused.value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { displayed.value = next; return; }
  const start = performance.now();
  const from = previous ?? 0;
  const update = (now: number) => {
    const progress = Math.min(1, (now - start) / 520);
    displayed.value = Math.round(from + (next - from) * (1 - Math.pow(1 - progress, 4)));
    if (progress < 1) frame = requestAnimationFrame(update);
  };
  frame = requestAnimationFrame(update);
}, { immediate: true });
onBeforeUnmount(() => cancelAnimationFrame(frame));
watch(motionPaused, (paused) => {
  if (paused) { cancelAnimationFrame(frame); displayed.value = props.value; }
});
</script>
<template><span :aria-label="accessible"><span aria-hidden="true">{{ yuan(displayed) }}</span></span></template>
