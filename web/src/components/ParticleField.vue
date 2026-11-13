<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
type Dot = { x: number; y: number; vx: number; vy: number; size: number; phase: number };
let dots: Dot[] = [];
let width = 0;
let height = 0;
let frame = 0;
let visible = true;
let motionOff = false;
let pointer = { x: -1000, y: -1000 };
let observer: IntersectionObserver | undefined;
let resizeObserver: ResizeObserver | undefined;
let media: MediaQueryList | undefined;

function resize() {
  const element = canvas.value;
  const context = element?.getContext("2d");
  if (!element || !context) return;
  const rect = element.getBoundingClientRect();
  width = rect.width;
  height = rect.height;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  element.width = Math.round(width * ratio);
  element.height = Math.round(height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const count = Math.min(76, Math.max(28, Math.round(width / 15)));
  dots = Array.from({ length: count }, (_, index) => ({
    x: ((index * 83.73) % 100) / 100 * width,
    y: ((index * 57.19) % 100) / 100 * height,
    vx: Math.sin(index * 2.7) * 0.13,
    vy: Math.cos(index * 1.9) * 0.1,
    size: index % 9 === 0 ? 2 : 1,
    phase: index * 0.93,
  }));
  draw(false);
}

function draw(advance: boolean) {
  const context = canvas.value?.getContext("2d");
  if (!context || !width || !height) return;
  context.clearRect(0, 0, width, height);
  for (const dot of dots) {
    if (advance) {
      dot.x = (dot.x + dot.vx + width) % width;
      dot.y = (dot.y + dot.vy + height) % height;
      dot.phase += 0.012;
    }
    const distance = Math.hypot(dot.x - pointer.x, dot.y - pointer.y);
    if (distance < 135) {
      const strength = (1 - distance / 135) * 0.32;
      context.beginPath();
      context.moveTo(dot.x, dot.y);
      context.lineTo(pointer.x, pointer.y);
      context.strokeStyle = `rgba(132, 234, 217, ${strength.toFixed(3)})`;
      context.lineWidth = 0.8;
      context.stroke();
    }
    context.beginPath();
    context.arc(dot.x, dot.y, dot.size + (distance < 90 ? 0.7 : 0), 0, Math.PI * 2);
    context.fillStyle = `rgba(155, 236, 224, ${(0.25 + (Math.sin(dot.phase) + 1) * 0.19).toFixed(3)})`;
    context.fill();
  }
}

function tick() {
  frame = 0;
  if (motionOff || !visible || document.hidden) return;
  draw(true);
  frame = requestAnimationFrame(tick);
}

function sync() {
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
  if (motionOff || !visible || document.hidden) draw(false);
  else frame = requestAnimationFrame(tick);
}

function move(event: PointerEvent) {
  if (event.pointerType === "touch") return;
  const rect = canvas.value?.getBoundingClientRect();
  if (!rect) return;
  pointer = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom
    ? { x: event.clientX - rect.left, y: event.clientY - rect.top }
    : { x: -1000, y: -1000 };
  if (motionOff) draw(false);
}

onMounted(() => {
  if (!canvas.value) return;
  media = window.matchMedia("(prefers-reduced-motion: reduce)");
  motionOff = media.matches;
  const onMotion = () => { motionOff = !!media?.matches; sync(); };
  media.addEventListener("change", onMotion);
  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas.value);
  observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); });
  observer.observe(canvas.value);
  window.addEventListener("pointermove", move, { passive: true });
  document.addEventListener("visibilitychange", sync);
  cleanup = () => {
    media?.removeEventListener("change", onMotion);
    window.removeEventListener("pointermove", move);
    document.removeEventListener("visibilitychange", sync);
  };
  resize();
  sync();
});
let cleanup = () => {};
onBeforeUnmount(() => {
  cleanup();
  resizeObserver?.disconnect();
  observer?.disconnect();
  if (frame) cancelAnimationFrame(frame);
});
</script>

<template><canvas ref="canvas" class="particle-field" aria-hidden="true"></canvas></template>
