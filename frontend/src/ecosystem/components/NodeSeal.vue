<script setup lang="ts">
// An enterprise's seal: its initials on its colour. The Control Center's: six points (the enterprises) around a hub.
import { computed } from 'vue'
import { initials } from '../identity'

const props = withDefaults(defineProps<{ name?: string; control?: boolean; size?: number; color?: string }>(), {
  name: '',
  control: false,
  size: 34,
  color: 'var(--mm-accent)',
})
const letters = computed(() => initials(props.name))
const points = Array.from({ length: 6 }, (_, i) => {
  const a = (Math.PI / 3) * i - Math.PI / 2
  return { x: 32 + 19 * Math.cos(a), y: 32 + 19 * Math.sin(a) }
})
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" aria-hidden="true" class="seal">
    <template v-if="control">
      <circle cx="32" cy="32" r="30" :fill="color" />
      <line v-for="(p, i) in points" :key="`l${i}`" x1="32" y1="32" :x2="p.x" :y2="p.y" stroke="var(--seal-ink)" stroke-width="1.6" opacity=".55" />
      <circle v-for="(p, i) in points" :key="`p${i}`" :cx="p.x" :cy="p.y" r="4.6" fill="var(--seal-ink)" />
      <circle cx="32" cy="32" r="6.5" fill="var(--seal-ink)" />
    </template>
    <template v-else>
      <circle cx="32" cy="32" r="30" :fill="color" />
      <circle cx="32" cy="32" r="24" fill="none" stroke="var(--seal-ink)" stroke-width="1.4" opacity=".5" stroke-dasharray="2.2 3" />
      <text x="32" y="33" text-anchor="middle" dominant-baseline="central" class="letters">{{ letters }}</text>
    </template>
  </svg>
</template>

<style scoped>
.seal {
  flex: none;
  --seal-ink: #ffffff;
}
:global(.app-dark) .seal {
  --seal-ink: #0b1513;
}
.letters {
  fill: var(--seal-ink);
  font-family: var(--mm-font);
  font-size: 21px;
  font-weight: 760;
  font-stretch: 112%;
  letter-spacing: 0.02em;
}
</style>
