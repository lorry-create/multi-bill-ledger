import type { Directive } from "vue";
import { motionPaused } from "../motion";

// Animate content in reading order. Data rows with their own choreography keep it.
const regions = [
  ".page-head",
  ".ledger-heading",
  ".statement-mast",
  ".statement-balance",
  ".statement-trend",
  ".statement-block > .panel-heading",
  ".category-panel .statement-legend",
  ".statement-largest",
  ".statement-income-legend",
  ".statement-income-total",
  ".statement-budget",
  ".budget-empty",
  ".statement-empty",
  ".ledger-filter",
  ".ledger-table thead",
  ".ledger-pagination",
  ".ledger-empty",
  ".batch-strip",
  ".review-views",
  ".original-panel",
  ".draft-panel > .panel-heading",
  ".draft-row",
  ".confirm-footer",
  ".processing",
  ".index-head",
  ".rule-row",
  ".rule-note",
  ".index-body > .empty-state",
].join(",");
const independentMotion =
  "[data-reveal], .ledger-row, .edit-dialog, .modal-backdrop";
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
type RegionState = {
  phase: "pending" | "playing" | "shown";
  animation?: Animation;
};
type Controller = { destroy: () => void };
const controllers = new WeakMap<HTMLElement, Controller>();

function canAnimate() {
  return !motionPaused.value && !reduced.matches && !document.hidden;
}

function createEntrance(root: HTMLElement): Controller {
  const states = new Map<HTMLElement, RegionState>();
  const added = new Set<Element>();
  let scanFrame = 0;
  let disposed = false;

  function settle(element: HTMLElement, state: RegionState) {
    state.phase = "shown";
    state.animation?.cancel();
    state.animation = undefined;
    element.dataset.pageEntrance = "shown";
    intersection.unobserve(element);
  }

  function play(element: HTMLElement, state: RegionState, index: number) {
    if (!canAnimate()) {
      settle(element, state);
      return;
    }
    const row = element.matches(".statement-budget, .draft-row, .rule-row");
    const small = element.matches(
      ".statement-largest, .statement-income-total, .ledger-pagination, thead",
    );
    const distance = row ? 10 : small ? 6 : 12;
    const animation = element.animate(
      [
        {
          opacity: 0,
          transform: row
            ? `translateX(-${distance}px)`
            : `translateY(${distance}px)`,
        },
        { opacity: 1, transform: "translate(0, 0)" },
      ],
      {
        duration: row ? 460 : small ? 380 : 520,
        delay: Math.min(index * 42, 210),
        easing: "cubic-bezier(0.16, 1, 0.3, 1)",
        fill: "backwards",
      },
    );
    state.phase = "playing";
    state.animation = animation;
    element.dataset.pageEntrance = "playing";
    animation.finished.then(
      () => {
        if (!disposed) settle(element, state);
      },
      () => {
        /* Cancellation reveals the final, usable content immediately. */
      },
    );
  }

  const intersection = new IntersectionObserver(
    (entries) => {
      const arriving: HTMLElement[] = [];
      for (const entry of entries) {
        const element = entry.target as HTMLElement;
        const state = states.get(element);
        if (!state) continue;
        if (entry.isIntersecting && state.phase === "pending")
          arriving.push(element);
        else if (!entry.isIntersecting && state.phase === "playing")
          settle(element, state);
      }
      arriving.sort((a, b) =>
        a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING
          ? -1
          : 1,
      );
      arriving.forEach((element, index) =>
        play(element, states.get(element)!, index),
      );
    },
    { rootMargin: "0px 0px -12px 0px", threshold: 0 },
  );

  function register(element: HTMLElement) {
    if (states.has(element) || !root.contains(element)) return;
    if (
      element.closest(independentMotion) ||
      element.querySelector(independentMotion)
    )
      return;
    // Only one region owns an entrance; nested controls move with that region.
    if (element.parentElement?.closest(regions)) return;
    const state: RegionState = { phase: "pending" };
    states.set(element, state);
    if (!canAnimate()) settle(element, state);
    else {
      element.dataset.pageEntrance = "pending";
      intersection.observe(element);
    }
  }

  function scan(branch: Element) {
    if (branch instanceof HTMLElement && branch.matches(regions))
      register(branch);
    branch.querySelectorAll<HTMLElement>(regions).forEach(register);
  }

  function flushAdded() {
    scanFrame = 0;
    if (disposed) return;
    for (const branch of added) if (root.contains(branch)) scan(branch);
    added.clear();
    for (const [element, state] of states) {
      if (!root.contains(element)) {
        settle(element, state);
        states.delete(element);
      }
    }
  }

  const mutations = new MutationObserver((records) => {
    let changed = false;
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node instanceof Element) {
          added.add(node);
          changed = true;
        }
      }
      if ([...record.removedNodes].some((node) => node instanceof Element))
        changed = true;
    }
    if (changed && !scanFrame) scanFrame = requestAnimationFrame(flushAdded);
  });

  function settleWhenDisabled() {
    if (canAnimate()) return;
    for (const [element, state] of states)
      if (state.phase !== "shown") settle(element, state);
  }

  function settleInteraction(event: Event) {
    const element = (event.target as Element).closest<HTMLElement>(
      "[data-page-entrance]",
    );
    const state = element && states.get(element);
    if (element && state && state.phase !== "shown") settle(element, state);
  }

  scan(root);
  mutations.observe(root, { childList: true, subtree: true });
  root.addEventListener("focusin", settleInteraction);
  root.addEventListener("pointerdown", settleInteraction, { passive: true });
  window.addEventListener("ledger-motion-change", settleWhenDisabled);
  document.addEventListener("visibilitychange", settleWhenDisabled);
  reduced.addEventListener("change", settleWhenDisabled);

  return {
    destroy() {
      disposed = true;
      cancelAnimationFrame(scanFrame);
      mutations.disconnect();
      intersection.disconnect();
      for (const state of states.values()) state.animation?.cancel();
      states.clear();
      added.clear();
      root.removeEventListener("focusin", settleInteraction);
      root.removeEventListener("pointerdown", settleInteraction);
      window.removeEventListener("ledger-motion-change", settleWhenDisabled);
      document.removeEventListener("visibilitychange", settleWhenDisabled);
      reduced.removeEventListener("change", settleWhenDisabled);
    },
  };
}

export const pageEntranceDirective: Directive<HTMLElement> = {
  mounted(element) {
    if (!window.IntersectionObserver || !element.animate) return;
    controllers.set(element, createEntrance(element));
  },
  beforeUnmount(element) {
    controllers.get(element)?.destroy();
    controllers.delete(element);
  },
};
