<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { motionPaused } from "../motion";

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
  const count = Math.min(90, Math.max(34, Math.round(width / 13)));
  dots = Array.from({ length: count }, (_, index) => ({
    x: ((index * 83.73) % 100) / 100 * width,
    y: ((index * 57.19) % 100) / 100 * height,
    vx: Math.sin(index * 2.7) * 0.16,
    vy: Math.cos(index * 1.9) * 0.12,
    size: index % 9 === 0 ? 2.2 : 1.15,
    phase: index * 0.93,
  }));
  draw(false);
}

function draw(advance: boolean) {
  const context = canvas.value?.getContext("2d");
  if (!context || !width || !height) return;
  context.clearRect(0, 0, width, height);
  if (pointer.x >= 0 && pointer.x <= width && pointer.y >= 0 && pointer.y <= height) {
    const halo = context.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 180);
    halo.addColorStop(0, "rgba(98,164,245,.18)");
    halo.addColorStop(1, "rgba(98,164,245,0)");
    context.fillStyle = halo;
    context.fillRect(pointer.x - 180, pointer.y - 180, 360, 360);
  }
  for (let i = 0; i < dots.length; i++) {
    for (let j = i + 1; j < Math.min(i + 7, dots.length); j++) {
      const first = dots[i], second = dots[j];
      const distance = Math.hypot(first.x - second.x, first.y - second.y);
      if (distance > 92) continue;
      context.beginPath();
      context.moveTo(first.x, first.y);
      context.lineTo(second.x, second.y);
      context.strokeStyle = `rgba(63,127,215,${((1 - distance / 92) * .14).toFixed(3)})`;
      context.lineWidth = .7;
      context.stroke();
    }
  }
  for (const dot of dots) {
    if (advance) {
      dot.x = (dot.x + dot.vx + width) % width;
      dot.y = (dot.y + dot.vy + height) % height;
      dot.phase += 0.012;
    }
    const distance = Math.hypot(dot.x - pointer.x, dot.y - pointer.y);
    if (distance < 135) {
      const strength = (1 - distance / 135) * 0.28;
      context.beginPath();
      context.moveTo(dot.x, dot.y);
      context.lineTo(pointer.x, pointer.y);
      context.strokeStyle = `rgba(57, 118, 209, ${strength.toFixed(3)})`;
      context.lineWidth = 0.8;
      context.stroke();
    }
    context.beginPath();
    context.arc(dot.x, dot.y, dot.size + (distance < 90 ? 0.7 : 0), 0, Math.PI * 2);
    context.fillStyle = `rgba(52, 116, 207, ${(0.3 + (Math.sin(dot.phase) + 1) * 0.17).toFixed(3)})`;
    context.fill();
  }
}

function tick() {
  frame = 0;
  if (motionOff || motionPaused.value || !visible || document.hidden) return;
  draw(true);
  frame = requestAnimationFrame(tick);
}

function sync() {
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
  if (motionOff || motionPaused.value || !visible || document.hidden) draw(false);
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
  window.addEventListener("ledger-motion-change", sync);
  cleanup = () => {
    media?.removeEventListener("change", onMotion);
    window.removeEventListener("pointermove", move);
    document.removeEventListener("visibilitychange", sync);
    window.removeEventListener("ledger-motion-change", sync);
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
