<script setup lang="ts">
// The run's findings for one or more analysis areas, in ID order, each with its provenance.
import { computed } from 'vue'
import { useRunStore } from '@/stores/run'
import type { Finding } from '@/types'
import FindingRow from './FindingRow.vue'

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
    <div class="finding-grid">
      <FindingRow v-for="f in items" :key="f.id" :finding="f" show-agent />
    </div>
  </section>
</template>

<style scoped>
.findings {
  container-type: inline-size;
}
.findings h3 {
  margin-bottom: 6px;
}
/* a wide card sets the ledger in two columns, so no line runs past a comfortable measure */
@container (min-width: 880px) {
  .finding-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 40px;
  }
  .finding-grid > :deep(.finding:nth-of-type(2)) {
    border-top: 0;
    padding-top: 4px;
  }
}
</style>
