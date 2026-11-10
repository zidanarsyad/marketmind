<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'
import FindingsList from '@/components/FindingsList.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import SkippedNotice from '@/components/SkippedNotice.vue'
import TableCard from '@/components/TableCard.vue'
import { toRecords } from '@/lib/tables'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)

interface Profile {
  segment: number
  name: string
  share: number
  description: string
  drivers: string
  concept_t2b: number
  nps_main_brand: number
}
const profiles = ref<Profile[]>([])
const roles = ref<Record<string, string>>({})

onMounted(async () => {
  const tables = run.bundle?.summary.tables ?? []
  if (!tables.includes('segmentation.tables.profiles')) return
  const [p, c] = await Promise.allSettled([
    api.table(id.value, 'segmentation.tables.profiles'),
    tables.includes('segmentation.tables.concept') ? api.table(id.value, 'segmentation.tables.concept') : null,
  ])
  if (p.status === 'fulfilled') profiles.value = toRecords(p.value) as unknown as Profile[]
  if (c.status === 'fulfilled' && c.value) {
    roles.value = Object.fromEntries(
      toRecords(c.value)
        .filter((r) => 'role' in r)
        .map((r) => [String(r.segment), String(r.role ?? '')]),
    )
  }
})

const tag = (segment: number) => ({ primary: 'Primary target', secondary: 'Secondary target' })[roles.value[String(segment)]] ?? ''
const sign = (x: number) => (x >= 0 ? `+${x.toFixed(0)}` : x.toFixed(0))
</script>

<template>
  <div class="stack">
    <SkippedNotice :modules="['segmentation', 'pricing']" />
    <FindingsList areas="segmentation" />
    <PlotlyChart :run-id="id" name="segment_map" :height="340" :min-width="680" />
    <div class="split">
      <PlotlyChart :run-id="id" name="segment_importance" :min-width="520" />
      <PlotlyChart :run-id="id" name="concept" />
    </div>
    <div v-if="profiles.length" class="profiles">
      <article v-for="p in profiles" :key="p.segment" class="card profile" :class="roles[String(p.segment)]">
        <span v-if="tag(p.segment)" class="chip" :class="roles[String(p.segment)] === 'primary' ? 'accent' : ''">
          <i v-if="roles[String(p.segment)] === 'primary'" class="pi pi-bullseye" style="font-size: 0.7rem" />{{ tag(p.segment) }}
        </span>
        <h3>{{ p.name }}</h3>
        <div class="share">{{ Math.round(p.share * 100) }}% of consumers</div>
        <p class="desc">{{ p.description }}</p>
        <p class="small">Drivers: <em>{{ p.drivers }}</em></p>
        <p class="small">Concept intent: <strong>{{ Math.round(p.concept_t2b * 100) }}%</strong> · NPS {{ sign(p.nps_main_brand) }}</p>
      </article>
    </div>
    <FindingsList areas="pricing" />
    <PlotlyChart :run-id="id" name="van_westendorp" />
    <TableCard :run-id="id" table-key="segmentation.tables.vw_points" title="Van Westendorp price points" expanded />
    <TableCard :run-id="id" table-key="segmentation.tables.k_selection" title="Choosing k (silhouette, Calinski-Harabasz, Davies-Bouldin)" />
  </div>
</template>

<style scoped>
.profiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 12px;
}
.profile {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}
.profile.primary {
  border-color: var(--mm-accent);
  box-shadow: 0 0 0 1px var(--mm-accent);
}
.profile h3 {
  margin: 2px 0 0;
}
.share {
  color: var(--mm-text-2);
  font-size: 0.86rem;
}
.desc {
  color: var(--mm-muted);
  font-size: 0.84rem;
  margin: 4px 0;
}
.profile p.small {
  margin: 0;
}
</style>
