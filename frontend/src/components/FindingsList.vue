<script setup lang="ts">
// The run's findings for one or more analysis areas, in ID order, each with its provenance.
import { computed } from 'vue'
import { useRunStore } from '@/stores/run'
import type { Finding } from '@/types'

const props = defineProps<{ areas: string | string[]; limit?: number; title?: string }>()
const run = useRunStore()

const items = computed<Finding[]>(() => {
  const areas = Array.isArray(props.areas) ? props.areas : [props.areas]
  const list = (run.bundle?.findings ?? []).filter((f) => areas.includes(f.area)).sort((a, b) => a.id.localeCompare(b.id))
  return props.limit ? list.slice(0, props.limit) : list
})
</script>

<template>
  <section v-if="items.length" class="card findings">
    <h3 v-if="title">{{ title }}</h3>
    <div v-for="f in items" :key="f.id" class="finding" :class="f.swot ? `swot-${f.swot}` : ''">
      <b>{{ f.title }}</b>
      <span class="meta">[{{ f.id }} · {{ f.agent }} · impact {{ f.impact }}/5 · confidence {{ Math.round(f.confidence * 100) }}%]</span>
      <p>{{ f.statement }}</p>
    </div>
  </section>
</template>

<style scoped>
.findings .finding:first-of-type {
  margin-top: 4px;
}
.findings .finding:last-child {
  margin-bottom: 2px;
}
</style>
