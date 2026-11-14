<script setup lang="ts">
defineProps<{ source: "wechat" | "alipay"; size?: number }>();
</script>
<template>
  <span class="platform-logo" :class="source" :style="{ width: `${size ?? 36}px`, height: `${size ?? 36}px` }" aria-hidden="true">
    <img :src="`/brands/${source}.svg`" alt="" />
  </span>
</template>
