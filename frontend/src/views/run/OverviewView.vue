<script setup lang="ts">
import Panel from 'primevue/panel'
import { computed } from 'vue'
import KpiTiles from '@/components/KpiTiles.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import { fmtIdr } from '@/lib/format'
import { overviewTiles } from '@/lib/kpis'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
// one tile per headline the study produced: a skipped module leaves no empty tile
const tiles = computed(() => overviewTiles(run.kpis, run.client, run.horizon))
const keyFindings = computed(() =>
  (run.bundle?.findings ?? [])
    .filter((f) => !f.tags.includes('methodology'))
    .sort((a, b) => b.priority - a.priority)
    .slice(0, 7),
)
const actions = computed(() => (run.bundle?.recommendations ?? []).slice(0, 5))
</script>

<template>
  <div class="stack">
    <Panel header="Research brief" toggleable collapsed class="brief">
      <p>{{ run.meta?.brief }}</p>
    </Panel>

    <KpiTiles :tiles="tiles" />

    <div class="split">
      <section class="card">
        <h2>Key findings</h2>
        <p v-if="!keyFindings.length" class="empty">No findings in this run.</p>
        <div v-for="f in keyFindings" :key="f.id" class="finding" :class="f.swot ? `swot-${f.swot}` : ''">
          <b>{{ f.title }}</b> <span class="meta">[{{ f.id }} · priority {{ f.priority.toFixed(2) }}]</span>
          <p>{{ f.statement }}</p>
        </div>
      </section>
      <section class="card">
        <h2>Priority actions</h2>
        <p v-if="!actions.length" class="empty">No recommendations in this run.</p>
        <article v-for="r in actions" :key="r.id" class="action">
          <div class="action-title"><span class="rid">{{ r.id }}</span>{{ r.title }}</div>
          <div class="action-meta">
            {{ r.horizon }} · {{ r.timeline }} · {{ r.owner }}<template v-if="r.value_idr"> · value {{ fmtIdr(r.value_idr) }}</template>
          </div>
          <div class="kpi"><i class="pi pi-bullseye" /> {{ r.kpi }}</div>
        </article>
      </section>
    </div>

    <div class="grid-2">
      <PlotlyChart :run-id="id" name="brand_share" />
      <PlotlyChart :run-id="id" name="client_forecast" />
    </div>
  </div>
</template>

<style scoped>
.brief p {
  margin: 0;
  color: var(--mm-text-2);
  white-space: pre-wrap;
}
.card h2 {
  margin-bottom: 6px;
}
.action {
  border: 1px solid var(--mm-border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 10px;
  background: var(--mm-panel-2);
}
.action-title {
  font-weight: 620;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.rid {
  flex: none;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--mm-accent);
  background: var(--mm-accent-soft);
  border-radius: 6px;
  padding: 1px 6px;
}
.action-meta {
  font-size: 0.84rem;
  color: var(--mm-text-2);
  margin-top: 2px;
}
.kpi {
  font-size: 0.8rem;
  color: var(--mm-muted);
  margin-top: 4px;
}
.kpi i {
  font-size: 0.75rem;
}
</style>
