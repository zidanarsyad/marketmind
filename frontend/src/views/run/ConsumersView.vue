<script setup lang="ts">
import Panel from 'primevue/panel'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'
import FindingsList from '@/components/FindingsList.vue'
import KpiTiles from '@/components/KpiTiles.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import SentimentTester from '@/components/SentimentTester.vue'
import TableCard from '@/components/TableCard.vue'
import { type ModelCard, modelTiles } from '@/lib/kpis'
import { toRecords } from '@/lib/tables'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
const card = ref<ModelCard | null>(null)
const voices = ref<Record<string, unknown>[]>([])
const tiles = computed(() => {
  try {
    return card.value ? modelTiles(card.value) : []
  } catch {
    return [] // an older model card without these fields
  }
})

onMounted(async () => {
  const tables = run.bundle?.summary.tables ?? []
  const [c, ex] = await Promise.allSettled([
    api.artefact<ModelCard>(id.value, 'consumer.model_card'),
    tables.includes('consumer.tables.example_reviews') ? api.table(id.value, 'consumer.tables.example_reviews', 200) : null,
  ])
  if (c.status === 'fulfilled') card.value = c.value
  if (ex.status === 'fulfilled') voices.value = toRecords(ex.value)
})
</script>

<template>
  <div class="stack">
    <KpiTiles :tiles="tiles" />
    <FindingsList areas="consumer" />
    <div class="grid-3">
      <PlotlyChart :run-id="id" name="model_quality" :height="330" />
      <PlotlyChart :run-id="id" name="confusion" :height="330" />
      <PlotlyChart :run-id="id" name="training_curve" :height="330" />
    </div>
    <div class="grid-2">
      <PlotlyChart :run-id="id" name="sentiment_by_brand" />
      <PlotlyChart :run-id="id" name="aspect_heatmap" :min-width="520" />
      <PlotlyChart :run-id="id" name="social_sentiment" />
      <PlotlyChart :run-id="id" name="client_aspect_trend" />
    </div>
    <TableCard :run-id="id" table-key="consumer.tables.anomalies" title="Detected complaint spikes (Poisson-tested)" expanded />
    <Panel v-if="voices.length" header="Voice of the customer" toggleable collapsed>
      <blockquote v-for="(v, i) in voices" :key="i" class="voice">
        <p>{{ v.text }}</p>
        <footer>{{ v.brand }} · {{ v.aspect }} · {{ v.type }}</footer>
      </blockquote>
    </Panel>
    <SentimentTester v-if="card" :run-id="id" :note="card.real_text_note" />
  </div>
</template>

<style scoped>
.voice {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--mm-border-strong);
}
.voice p {
  margin: 0;
}
.voice footer {
  font-size: 0.8rem;
  color: var(--mm-muted);
  font-style: italic;
  margin-top: 2px;
}
</style>
