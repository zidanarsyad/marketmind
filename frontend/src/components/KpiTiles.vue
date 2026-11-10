<script setup lang="ts">
import type { Tile } from '@/lib/kpis'

defineProps<{ tiles: Tile[] }>()
</script>

<template>
  <div v-if="tiles.length" class="tiles">
    <div v-for="t in tiles" :key="t.label" class="tile">
      <div class="label">{{ t.label }}</div>
      <div class="value">{{ t.value }}</div>
      <div v-if="t.note" class="note">{{ t.note }}</div>
    </div>
  </div>
</template>
