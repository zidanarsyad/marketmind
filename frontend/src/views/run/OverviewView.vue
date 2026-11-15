<script setup lang="ts">
import { computed } from 'vue'
import FindingRow from '@/components/FindingRow.vue'
import KpiTiles from '@/components/KpiTiles.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import { fmtIdr, range } from '@/lib/format'
import { overviewTiles } from '@/lib/kpis'
import { useRunStore } from '@/stores/run'
import type { Recommendation } from '@/types'

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

// "Core move over 0–6 months, led by Marketing, worth Rp 74.5 bn"
function plan(r: Recommendation): string {
  const span = r.timeline ? ` over ${range(r.timeline)}` : ''
  const owner = r.owner ? `, led by ${r.owner}` : ''
  const value = r.value_idr ? `, worth ${fmtIdr(r.value_idr)}` : ''
  return `${span}${owner}${value}`
}
</script>

<template>
  <div class="stack">
    <KpiTiles :tiles="tiles" />

    <div class="split">
      <section class="card ledger">
        <h2>Key findings</h2>
        <p v-if="!keyFindings.length" class="empty">No findings in this run.</p>
        <FindingRow v-for="f in keyFindings" :key="f.id" :finding="f" />
      </section>
      <section class="card ledger actions">
        <h2>Priority actions</h2>
        <p v-if="!actions.length" class="empty">No recommendations in this run.</p>
        <article v-for="r in actions" :key="r.id" class="finding action">
          <span class="stamp">{{ r.id }}</span>
          <b>{{ r.title }}</b>
          <p><strong class="horizon">{{ r.horizon }}</strong>{{ plan(r) }}</p>
          <div class="meta"><span>Target: {{ r.kpi }}</span></div>
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
.ledger h2 {
  margin-bottom: 8px;
}
/* the actions stay beside the reader while the longer findings column scrolls past */
.ledger.actions {
  position: sticky;
  top: 62px;
}
.action > .stamp {
  min-width: 2.4rem;
}
.action p {
  font-size: var(--mm-fs-sm);
}
@media (max-width: 1100px) {
  .ledger.actions {
    position: static;
  }
}
.horizon {
  font-weight: 620;
  color: var(--mm-text);
}
</style>
