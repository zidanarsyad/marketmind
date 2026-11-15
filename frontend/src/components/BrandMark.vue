<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 32 })
</script>

<template>
  <!-- a compass on a seal: research that points the client somewhere, certified -->
  <svg :width="size" :height="size" viewBox="0 0 64 64" aria-hidden="true" class="brand-mark">
    <circle cx="32" cy="32" r="30" fill="var(--mm-accent)" />
    <circle cx="32" cy="32" r="23.5" fill="none" stroke="#ffffff" stroke-width="1.6" opacity=".55" stroke-dasharray="2.2 3" />
    <path d="M32 12l7.2 20L32 52l-7.2-20z" fill="#ffffff" />
    <path d="M32 12l7.2 20H24.8z" fill="#a9ddcf" />
    <circle cx="32" cy="32" r="3.2" fill="var(--mm-accent)" />
  </svg>
</template>

<style scoped>
.brand-mark {
  flex: none;
}
</style>
