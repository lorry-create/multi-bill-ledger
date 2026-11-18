<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { yuan } from "../format";
import { motionPaused } from "../motion";

const props = defineProps<{ value: number }>();
const accessible = computed(() => yuan(props.value));
const digits = Array.from({ length: 11 }, (_, index) => index % 10);
const normalize = (position: number) => ((position % 10) + 10) % 10;
const valueDigits = () =>
  [...accessible.value]
    .filter((char) => /\d/.test(char))
    .reverse()
    .map(Number);
const positions = ref(valueDigits());
let frame = 0;

const tokens = computed(() => {
  let place = valueDigits().length;
  return [...accessible.value].map((char, index) => {
    const digit = /\d/.test(char);
    return {
      char,
      digit,
      place: digit ? --place : -1,
      key: digit ? `digit-${place}` : `mark-${index}`,
    };
  });
});

function settle() {
  cancelAnimationFrame(frame);
  positions.value = valueDigits();
}

watch(
  () => props.value,
  (next, previous) => {
    cancelAnimationFrame(frame);
    const target = valueDigits();
    if (motionPaused.value || document.hidden) {
      settle();
      return;
    }
    const direction = next >= previous ? 1 : -1;
    const from = target.map((digit, place) => positions.value[place] ?? digit);
    const distance = target.map((digit, place) => {
      const difference = digit - normalize(from[place]);
      return direction > 0 && difference < 0
        ? difference + 10
        : direction < 0 && difference > 0
          ? difference - 10
          : difference;
    });
    const start = performance.now();
    const update = (now: number) => {
      if (document.hidden || motionPaused.value) {
        settle();
        return;
      }
      const progress = Math.min(1, (now - start) / 520);
      const eased = 1 - (1 - progress) ** 4;
      positions.value = from.map(
        (position, place) => position + distance[place] * eased,
      );
      if (progress < 1) frame = requestAnimationFrame(update);
      else positions.value = target;
    };
    frame = requestAnimationFrame(update);
  },
);

watch(motionPaused, (paused) => {
  if (paused) settle();
});
onBeforeUnmount(() => cancelAnimationFrame(frame));
</script>

<template>
  <span
    class="rolling-amount"
    :aria-label="accessible"
    :data-value="accessible"
  >
    <span class="rolling-amount-visual" aria-hidden="true">
      <template v-for="token in tokens" :key="token.key">
        <span v-if="token.digit" class="rolling-digit">
          <span
            class="rolling-digit-track"
            :style="{
              '--digit-position': normalize(
                positions[token.place] ?? Number(token.char),
              ),
            }"
          >
            <span v-for="(digit, index) in digits" :key="index">{{
              digit
            }}</span>
          </span>
        </span>
        <span v-else>{{ token.char }}</span>
      </template>
    </span>
  </span>
</template>

<style scoped>
.rolling-amount,
.rolling-amount span {
  font: inherit;
  color: inherit;
  letter-spacing: inherit;
}
.rolling-amount {
  display: inline-block;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.rolling-amount-visual {
  display: inline-flex;
  align-items: center;
  line-height: 1.15;
}
.rolling-digit {
  display: block;
  width: 1ch;
  height: 1.15em;
  overflow: hidden;
}
.rolling-digit-track {
  display: block;
  transform: translateY(calc(var(--digit-position) * -1.15em));
}
.rolling-digit-track > span {
  display: block;
  height: 1.15em;
  line-height: 1.15;
}
</style>
