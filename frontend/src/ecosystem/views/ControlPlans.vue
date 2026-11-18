<script setup lang="ts">
// Every plan the coordinator confirmed in the run: why it was made, how the partners answered (a rejection carries
// a constraint, and the coordinator solves again), what the four objective terms cost, what changed from the previous
// plan, and the plan itself, week by week. Below, how each enterprise's own dialect maps onto the planner's inputs.
import { computed, ref, watch } from 'vue'
import KpiTiles from '@/components/KpiTiles.vue'
import DataGrid from '@/components/DataGrid.vue'
import { fmtInt } from '@/lib/format'
import { entName, idr } from '../labels'
import { useControlStore } from '../store'
import type { PlanRevision } from '../types'

const ctl = useControlStore()
const eco = computed(() => ctl.ecosystem)
const plans = computed(() => eco.value?.plans ?? [])
const picked = ref<number | null>(null)
watch(
  () => ctl.run?.id,
  () => (picked.value = null),
)
const rev = computed<PlanRevision | null>(
  () => plans.value.find((p) => p.revision === picked.value) ?? plans.value[plans.value.length - 1] ?? null,
)

const rejections = computed(() =>
  (eco.value?.decisions ?? []).filter(
    (d) => d.agent === 'coordinator' && d.decision.includes('rejected the plan') && d.week === rev.value?.week,
  ),
)

const tiles = computed(() => {
  const r = rev.value?.result
  if (!r) return []
  return [
    { label: 'Cost', value: idr(r.terms.cost), note: 'production, transport, express, holding, less stock kept' },
    { label: 'Time', value: idr(r.terms.time), note: 'express deliveries, stock waiting at the factory' },
    { label: 'Risk', value: idr(r.terms.risk), note: 'expected defective units from the shared forecast' },
    { label: 'Lost service', value: idr(r.terms.quality), note: 'orders left unserved, at their margin' },
    { label: 'Planned fill rate', value: `${(r.planned_fill_rate * 100).toFixed(1)}%`, note: `${fmtInt(r.totals.lost ?? 0)} orders planned lost` },
  ]
})

const FIELD: Record<string, string> = { production: 'Production', ship_JKT: 'Ship to Jakarta', ship_SBY: 'Ship to Surabaya', express: 'Express from Surabaya' }
const diffRows = computed(() =>
  (rev.value?.diff ?? []).map((d) => ({ week: `W${d.week}`, figure: FIELD[d.field] ?? d.field, before: d.before, after: d.after, change: d.after - d.before })),
)
const weekRows = computed(() =>
  (rev.value?.result.weeks ?? []).map((w) => ({
    week: `W${w.week}`,
    batches: w.batches ?? 'locked',
    production: w.production,
    'ship JKT': w.ship_JKT,
    'ship SBY': w.ship_SBY,
    surge: w.surge_JKT + w.surge_SBY,
    express: w.express,
    'stock JKT': w.stock_JKT,
    'stock SBY': w.stock_SBY,
    'lost': w.lost_JKT + w.lost_SBY,
  })),
)
const limits = computed(() => Object.entries(rev.value?.result.constraints.max_batches ?? {}))
const signed = (v: unknown) => {
  const n = Number(v)
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${fmtInt(Math.abs(n))}`
}
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Plans</h1>
      <p class="lede">
        The coordinator solves one mixed-integer plan over the weeks left, from what the partners share: weighted cost,
        time, risk and lost service, within each one's capacity. Each partner checks its slice against what only it knows
        and may reject it with a limit; the coordinator then solves again before it confirms.
      </p>
    </header>

    <p v-if="!eco" class="empty">Plans exist only with ecosystem intelligence: run a scenario in “Compare both” or “Ecosystem only”.</p>

    <div v-else class="layout">
      <nav class="card tight revs" aria-label="Plan revisions">
        <h2>Revisions</h2>
        <ul>
          <li v-for="p in plans" :key="p.revision">
            <button type="button" :class="{ current: rev?.revision === p.revision }" @click="picked = p.revision">
              <span class="stamp">{{ p.week === 0 ? 'Setup' : `W${p.week}` }}</span>
              <span class="what">
                <b>Rev. {{ p.revision }}</b>
                <small>{{ p.reason }}</small>
              </span>
              <span v-if="p.rounds > 1" class="chip warn">{{ p.rounds }} rounds</span>
            </button>
          </li>
        </ul>
      </nav>

      <section v-if="rev" class="stack detail">
        <div class="card">
          <h2>Rev. {{ rev.revision }}, {{ rev.week === 0 ? 'before the launch' : `start of W${rev.week}` }}</h2>
          <p class="why">{{ rev.reason.charAt(0).toUpperCase() + rev.reason.slice(1) }}.</p>
          <div v-if="rejections.length" class="rejections">
            <p v-for="(d, i) in rejections" :key="i" class="small">
              <span class="chip bad">round {{ d.round ?? i + 1 }}</span> {{ d.decision }}: {{ d.reasoning }}
            </p>
            <p class="small muted">Round {{ rev.rounds }}: every partner accepted the revised plan, and the coordinator confirmed it.</p>
          </div>
          <p v-else class="small muted">Every partner accepted the first proposal.</p>
          <KpiTiles :tiles="tiles" />
          <p v-if="limits.length" class="small limits">
            Limits added by rejections: <span v-for="[w, n] in limits" :key="w" class="chip">at most {{ n }} batches in W{{ w }}</span>
          </p>
        </div>

        <div class="card">
          <h3>What changed from rev. {{ rev.revision - 1 }}</h3>
          <p v-if="rev.revision === 1" class="small muted">The first plan of the season.</p>
          <p v-else-if="!diffRows.length" class="small muted">No weekly figure moved by 100 units or more.</p>
          <DataGrid
            v-else
            :columns="['week', 'figure', 'before', 'after', { field: 'change', format: signed }]"
            :rows="diffRows"
            scroll-height="300px"
          />
        </div>

        <div class="card">
          <h3>The plan, week by week</h3>
          <p class="caption">Units. A week's production ships the same week and reaches the warehouse the next; “locked” is the week already ordered.</p>
          <DataGrid
            :columns="['week', 'batches', 'production', 'ship JKT', 'ship SBY', 'surge', 'express', 'stock JKT', 'stock SBY', 'lost']"
            :rows="weekRows"
            scroll-height="440px"
            :sortable="false"
          />
        </div>
      </section>
    </div>

    <section v-if="ctl.node" class="card">
      <h2>What the planner reads, and from whom</h2>
      <p class="caption">
        Each enterprise shares facts in its own dialect: its units, its week numbering, its language. The coordinator's
        adapters translate them into one vocabulary before solving.
      </p>
      <DataGrid
        :columns="[
          { field: 'enterprise', format: (v) => entName(String(v)) },
          { field: 'local', header: 'What it shares (its own name)' },
          'unit',
          { field: 'shared', header: 'Planner input' },
          'conversion',
        ]"
        :rows="ctl.node.schema_mapping as unknown as Record<string, unknown>[]"
        scroll-height="360px"
        :sortable="false"
      />
    </section>
  </div>
</template>

<style scoped>
.hero {
  max-width: 78ch;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lede {
  margin: 0;
  color: var(--mm-text-2);
}
.layout {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.revs h2 {
  font-size: var(--mm-fs-md);
  margin: 2px 4px 8px;
}
.revs ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.revs button {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px 8px 10px;
  border: 0;
  border-radius: var(--mm-radius-sm);
  background: transparent;
  color: var(--mm-text);
  text-align: left;
  cursor: pointer;
}
.revs button:hover {
  background: var(--mm-panel-2);
}
.revs button.current {
  background: var(--mm-accent-soft);
}
.revs button.current::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--mm-accent);
}
.revs .stamp {
  min-width: 3.4rem;
  justify-content: center;
}
.what {
  flex: 1;
  min-width: 0;
}
.what b {
  display: block;
  font-size: var(--mm-fs-sm);
  font-weight: 620;
}
.what small {
  display: block;
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.why {
  margin: 4px 0 10px;
  color: var(--mm-text-2);
}
.rejections {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--mm-panel-2);
  border-radius: var(--mm-radius-sm);
}
.rejections p {
  margin: 0;
}
.limits {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
}
.card > h3 {
  margin-bottom: 8px;
}
.card > h2 + .caption,
.card > h3 + .caption {
  margin-bottom: 10px;
}
@media (max-width: 1100px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
