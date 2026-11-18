<script setup lang="ts">
// The Control Center's front page: the six enterprises as their servers report them, the scenario runner, and the
// run on screen: local against ecosystem intelligence, the season strip, and where the difference came from.
import { computed } from 'vue'
import { fmtIdr } from '@/lib/format'
import { useTheme } from '@/lib/theme'
import CompareLedger from '../components/CompareLedger.vue'
import EcoChart from '../components/EcoChart.vue'
import EnterpriseCard from '../components/EnterpriseCard.vue'
import ScenarioRunner from '../components/ScenarioRunner.vue'
import SeasonTimeline from '../components/SeasonTimeline.vue'
import { cssVar } from '../identity'
import { byChain, entName } from '../labels'
import { useControlStore } from '../store'

const ctl = useControlStore()
const { mode } = useTheme()
const refs = computed(() => byChain(ctl.enterpriseRefs))
const statusOf = (key: string) => ctl.enterprises.find((e) => e.key === key)
const run = computed(() => ctl.run)
const eco = computed(() => ctl.ecosystem)
const loc = computed(() => ctl.local)
const both = computed(() => !!(eco.value && loc.value))

/** The run in one sentence, the way the case would be told. */
const headline = computed(() => {
  const e = eco.value?.ecosystem
  const l = loc.value?.ecosystem
  if (!run.value) return ''
  if (e && l) {
    const gain = e.total_profit_idr - l.total_profit_idr
    return `${run.value.title}: working as an ecosystem, the six enterprises served ${(e.fill_rate * 100).toFixed(1)}% of Kirana's orders against ${(l.fill_rate * 100).toFixed(1)}% when each decided alone, and earned ${fmtIdr(Math.abs(gain))} ${gain >= 0 ? 'more' : 'less'} between them.`
  }
  const one = eco.value ?? loc.value
  return one ? `${run.value.title}, ${one.mode} intelligence only: ${(one.ecosystem.fill_rate * 100).toFixed(1)}% of orders served.` : ''
})

const series = (m: 'local' | 'ecosystem') => {
  void mode.value
  return m === 'ecosystem'
    ? { color: cssVar('--mm-text', '#102320'), dash: 'solid', name: 'Ecosystem intelligence' }
    : { color: cssVar('--mm-muted', '#5e716c'), dash: 'dot', name: 'Local intelligence' }
}

const fillChart = computed(() => {
  const traces: Record<string, unknown>[] = []
  for (const m of ['local', 'ecosystem'] as const) {
    const r = m === 'local' ? loc.value : eco.value
    if (!r) continue
    const s = series(m)
    traces.push({
      type: 'scatter',
      mode: 'lines+markers',
      name: s.name,
      x: r.weekly.map((w) => `W${w.week}`),
      y: r.weekly.map((w) => w.fill_rate),
      line: { color: s.color, width: 2, dash: s.dash },
      marker: { size: 8, color: s.color, line: { width: 2, color: cssVar('--mm-panel', '#fff') } },
      hovertemplate: `${s.name}<br>%{x}: %{y:.1%} of orders served so far<extra></extra>`,
    })
  }
  return {
    data: traces,
    layout: {
      yaxis: { tickformat: '.0%', range: [0.6, 1.01], title: { text: 'Orders served so far' } },
      xaxis: { title: { text: '' } },
      margin: { l: 10, r: 16, t: 36, b: 10 },
      hovermode: 'x unified',
    },
  }
})

const profitChart = computed(() => {
  const c = run.value?.comparison
  if (!c) return null
  const rows = byChain(c.enterprises.map((e) => ({ ...e, key: e.enterprise }))).reverse()
  const y = rows.map((r) => entName(r.key))
  const trace = (m: 'local' | 'ecosystem') => {
    const s = series(m)
    const xs = rows.map((r) => (m === 'local' ? r.local_profit_idr : r.ecosystem_profit_idr) / 1e9)
    return {
      type: 'bar',
      orientation: 'h',
      name: s.name,
      y,
      x: xs,
      marker: { color: s.color, line: { width: 0 } },
      hovertemplate: `${s.name}<br>%{y}: Rp %{x:.2f} bn<extra></extra>`,
    }
  }
  return {
    data: [trace('local'), trace('ecosystem')],
    layout: {
      barmode: 'group',
      bargap: 0.35,
      bargroupgap: 0.12,
      xaxis: { title: { text: 'Profit over the season, Rp bn' }, ticksuffix: '' },
      margin: { l: 10, r: 16, t: 36, b: 10 },
    },
  }
})
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Global Agentic Control Center</h1>
      <p class="lede">
        Six enterprises, each on its own server with its own database, agents and rules, launch Kirana's moisturizer
        through 12.12 and Ramadan. Their agents trade messages, negotiate and plan together; this center sees only
        what each one's governance lets it see, and plays the season with local or with ecosystem intelligence.
      </p>
      <p v-if="headline" class="headline">{{ headline }}</p>
    </header>

    <section aria-labelledby="ents-title">
      <div class="section-title">
        <h2 id="ents-title">Enterprises</h2>
        <span class="hint">{{ ctl.enterprisesError ? `Not reachable: ${ctl.enterprisesError}` : 'As each server reports itself, every few seconds' }}</span>
      </div>
      <div class="ent-grid">
        <EnterpriseCard v-for="e in refs" :key="e.key" :ent="e" :status="statusOf(e.key)" />
      </div>
    </section>

    <section class="split">
      <ScenarioRunner />
      <div class="card about">
        <h2>How a season runs</h2>
        <ol class="steps">
          <li>The Control Center resets every enterprise through its API, in the chosen mode.</li>
          <li>Week by week, the environment announces disruptions and sends customer orders; each enterprise's agents act on their own data and sensors.</li>
          <li>With ecosystem intelligence, enterprises share what their governance allows, negotiate terms, and the coordinator solves a joint plan; each partner may reject its slice, and a reported risk triggers a new plan.</li>
          <li>With local intelligence, nobody shares or negotiates: list prices, standard terms, each forecasting alone.</li>
        </ol>
      </div>
    </section>

    <section v-if="run && run.results" class="stack" aria-labelledby="run-title">
      <div class="section-title">
        <h2 id="run-title">{{ run.title }}{{ both ? ': local against ecosystem intelligence' : '' }}</h2>
        <span class="hint">{{ run.id }}, seed {{ run.seed }}</span>
      </div>
      <CompareLedger v-if="run.comparison" :comparison="run.comparison" />
      <div class="card">
        <h3>The season</h3>
        <SeasonTimeline
          :campaigns="ctl.node?.campaigns ?? []"
          :events="(eco ?? loc)?.events ?? []"
          :plans="eco?.plans ?? []"
          :weekly="{ local: loc?.weekly, ecosystem: eco?.weekly }"
          :week-starts="ctl.node?.week_starts"
        />
      </div>
      <div class="grid-2">
        <div class="card">
          <EcoChart title="Share of Kirana's orders served, week by week" :data="fillChart.data" :layout="fillChart.layout" :height="300" />
        </div>
        <div v-if="profitChart" class="card">
          <EcoChart title="Profit by enterprise" :data="profitChart.data" :layout="profitChart.layout" :height="300" />
        </div>
      </div>
    </section>
    <p v-else-if="!ctl.busy" class="empty">No finished run yet. Pick a scenario and run it: the comparison appears here.</p>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 78ch;
}
.lede {
  margin: 0;
  color: var(--mm-text-2);
}
.headline {
  margin: 4px 0 0;
  font-size: var(--mm-fs-lg);
  font-weight: 560;
  font-stretch: 104%;
  line-height: 1.4;
  padding-left: 14px;
  border-left: 3px solid var(--mm-text);
}
.ent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: 14px;
  margin-top: 10px;
}
.about h2 {
  margin-bottom: 8px;
}
.steps {
  margin: 0;
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--mm-text-2);
  font-size: var(--mm-fs-sm);
}
.card > h3 {
  margin-bottom: 12px;
}
</style>
