import { readonly, ref } from "vue";

const motionPaused = ref(localStorage.getItem("ledger-motion-paused") === "true");
export { motionPaused };
export function toggleMotion() {
  motionPaused.value = !motionPaused.value;
  localStorage.setItem("ledger-motion-paused", String(motionPaused.value));
  syncMotion();
}
function syncMotion() {
  document.documentElement.classList.toggle("motion-paused", motionPaused.value);
  window.dispatchEvent(new Event("ledger-motion-change"));
}
const message = ref<{ id: number; text: string } | null>(null);
export const notice = readonly(message);
let noticeTimer: ReturnType<typeof setTimeout>;
export function notify(text: string) {
  // The host announces only confirmed API outcomes.
  message.value = { id: Date.now(), text };
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { message.value = null; }, 3600);
}
export function installMotion() {
  syncMotion();
  document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("document-hidden", document.hidden));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let pointerFrame = 0;
  let active: HTMLElement | null = null;
  document.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch" || motionPaused.value || reduced.matches) return;
    if (pointerFrame) cancelAnimationFrame(pointerFrame);
    pointerFrame = requestAnimationFrame(() => {
      const surface = (event.target as Element).closest<HTMLElement>(".content-panel, .upload-main, .upload-aside, .rule-explainer");
      if (active && active !== surface) active.classList.remove("pointer-within");
      active = surface;
      if (!surface) return;
      const rect = surface.getBoundingClientRect();
      surface.style.setProperty("--pointer-x", `${event.clientX - rect.left}px`);
      surface.style.setProperty("--pointer-y", `${event.clientY - rect.top}px`);
      surface.classList.add("pointer-within");
    });
  }, { passive: true });
  document.addEventListener("pointerdown", (event) => {
    if (motionPaused.value || reduced.matches) return;
    const target = (event.target as Element).closest<HTMLElement>(".primary-btn, .secondary-btn, .source-option, .journey-controls button");
    if (!target || target.matches(":disabled")) return;
    const rect = target.getBoundingClientRect();
    const ripple = document.createElement("span");
    ripple.className = "action-ripple";
    const size = Math.max(rect.width, rect.height) * 2;
    Object.assign(ripple.style, { width: `${size}px`, height: `${size}px`, left: `${event.clientX - rect.left - size / 2}px`, top: `${event.clientY - rect.top - size / 2}px` });
    target.append(ripple);
    ripple.animate([{ transform: "scale(0)", opacity: .24 }, { transform: "scale(1)", opacity: 0 }], { duration: 600, easing: "cubic-bezier(.16,1,.3,1)" }).finished.finally(() => ripple.remove());
  }, { passive: true });
}
