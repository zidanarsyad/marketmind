<script setup lang="ts">
import { computed } from 'vue'
import type { Tile } from '@/lib/kpis'

const props = defineProps<{ tiles: Tile[] }>()
// rows of even length: six headlines sit three by two, never five and a stray
const cols = computed(() => {
  const n = props.tiles.length
  return n <= 5 ? n : n === 6 || n === 9 ? 3 : 4
})
</script>

<template>
  <div v-if="tiles.length" class="tiles-wrap">
    <div class="tiles" :data-cols="cols">
      <div v-for="t in tiles" :key="t.label" class="tile">
        <div class="label">{{ t.label }}</div>
        <div class="value">{{ t.value }}</div>
        <div v-if="t.note" class="note">{{ t.note }}</div>
      </div>
    </div>
  </div>
</template>
