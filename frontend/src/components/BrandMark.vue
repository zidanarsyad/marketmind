<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 32 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" aria-hidden="true" class="brand-mark">
    <circle cx="32" cy="32" r="29" fill="var(--mm-accent)" />
    <circle cx="32" cy="32" r="21" fill="none" stroke="#fcfcfb" stroke-width="3" opacity=".5" />
    <path d="M32 11l7 21-7 21-7-21z" fill="#fcfcfb" />
    <path d="M32 11l7 21H25z" fill="#eb6834" />
    <circle cx="32" cy="32" r="3.5" fill="var(--mm-accent)" />
  </svg>
</template>

<style scoped>
.brand-mark {
  flex: none;
}
</style>
