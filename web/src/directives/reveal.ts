import type { Directive } from "vue";
import { motionPaused } from "../motion";

type RevealOptions = { type?: "card" | "bar"; delay?: number };
type RevealState = {
  element: HTMLElement;
  options: RevealOptions;
  animation?: Animation;
  settled: boolean;
  finish: () => void;
};

const states = new WeakMap<HTMLElement, RevealState>();
const pending = new Set<RevealState>();
const active = new Set<RevealState>();
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
let observer: IntersectionObserver | undefined;

function canAnimate() {
  return !motionPaused.value && !reduced.matches && !document.hidden;
}

function settle(state: RevealState) {
  state.settled = true;
  observer?.unobserve(state.element);
  pending.delete(state);
  active.delete(state);
  state.animation?.cancel();
  state.animation = undefined;
  state.element.dataset.revealState = "shown";
}

function reveal(state: RevealState) {
  if (state.settled) return;
  observer?.unobserve(state.element);
  pending.delete(state);
  if (!canAnimate()) {
    settle(state);
    return;
  }
  state.settled = true;
  const bar = state.options.type === "bar";
  const phone = window.matchMedia("(max-width: 760px)").matches;
  const frames = bar
    ? [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }]
    : [
        { opacity: 0.45, transform: `translateX(${phone ? -16 : -28}px)` },
        { opacity: 1, transform: "translateX(0)" },
      ];
  const animation = state.element.animate(frames, {
    duration: bar ? 820 : phone ? 420 : 560,
    delay: Math.min(240, Math.max(0, state.options.delay ?? 0)),
    easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    fill: "backwards",
  });
  state.animation = animation;
  state.element.dataset.revealState = "playing";
  active.add(state);
  animation.finished.then(() => settle(state), () => {
    active.delete(state);
  });
}

function settleWhenDisabled() {
  if (canAnimate()) return;
  for (const state of [...pending, ...active]) settle(state);
}

window.addEventListener("ledger-motion-change", settleWhenDisabled);
reduced.addEventListener("change", settleWhenDisabled);
document.addEventListener("visibilitychange", settleWhenDisabled);

// 元素默认保持可见；没有动画能力时直接呈现最终内容。
export const revealDirective: Directive<HTMLElement, RevealOptions | undefined> = {
  mounted(element, binding) {
    if (!canAnimate() || !window.IntersectionObserver || !element.animate) return;
    observer ??= new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const state = states.get(entry.target as HTMLElement);
        if (entry.isIntersecting && state) reveal(state);
      }
    }, { rootMargin: "0px 0px -24px 0px", threshold: 0 });
    const state: RevealState = {
      element,
      options: binding.value ?? {},
      settled: false,
      finish: () => settle(state),
    };
    states.set(element, state);
    element.dataset.reveal = state.options.type ?? "card";
    element.dataset.revealState = "pending";
    pending.add(state);
    element.addEventListener("focusin", state.finish);
    element.addEventListener("pointerdown", state.finish, { passive: true });
    observer.observe(element);
  },
  beforeUnmount(element) {
    const state = states.get(element);
    if (!state) return;
    settle(state);
    element.removeEventListener("focusin", state.finish);
    element.removeEventListener("pointerdown", state.finish);
    states.delete(element);
  },
};
