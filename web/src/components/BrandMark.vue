<script setup lang="ts">
defineProps<{ animated?: boolean; opening?: boolean }>();
</script>

<template>
  <span
    class="brand-symbol"
    :class="{
      'brand-symbol-animated': animated || opening,
      'brand-symbol-opening': opening,
    }"
    aria-hidden="true"
  >
    <svg viewBox="0 0 48 48" fill="none" focusable="false">
      <rect
        class="brand-symbol-ground"
        width="48"
        height="48"
        rx="13"
        fill="#2865B8"
      />
      <rect
        class="brand-symbol-wash"
        width="48"
        height="48"
        rx="13"
        fill="#8BB9EF"
      />
      <path
        class="brand-symbol-back"
        d="M10.5 11.5h7.25A6.25 6.25 0 0 1 24 17.75V36l-3.3-2.35a9 9 0 0 0-5.22-1.65H10.5V11.5Z"
        fill="#BEDBFF"
      />
      <path
        class="brand-symbol-front"
        d="M26.5 17.75a6.25 6.25 0 0 1 6.25-6.25h4.75V32h-2.73a9 9 0 0 0-5.22 1.65L26.5 36V17.75Z"
        fill="white"
      />
    </svg>
  </span>
</template>

<style scoped>
.brand-symbol {
  display: inline-flex;
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  vertical-align: middle;
}
.brand-symbol svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 27%;
}
.brand-symbol-wash {
  opacity: 0;
}
@media (prefers-reduced-motion: no-preference) {
  .brand-symbol-animated .brand-symbol-wash {
    animation: brand-ink-settle 0.7s ease-out both;
  }
  .brand-symbol-animated .brand-symbol-back {
    animation: brand-page-join 0.7s 0.06s cubic-bezier(0.16, 1, 0.3, 1) both;
  }
  .brand-symbol-animated .brand-symbol-front {
    animation: brand-page-settle 0.65s 0.16s cubic-bezier(0.16, 1, 0.3, 1) both;
  }
}
@keyframes brand-ink-settle {
  from {
    opacity: 0.7;
  }
  to {
    opacity: 0;
  }
}
@keyframes brand-page-join {
  from {
    opacity: 0;
    transform: translateX(-12px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
@keyframes brand-page-settle {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
