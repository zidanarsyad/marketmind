<script setup lang="ts">
// One negotiation: who, about what, how it ended, and the offers (each side's line closes on the other's until one
// accepts). A Contract Net round shows the routes proposed and the one chosen.
import { computed } from 'vue'
import DataGrid from '@/components/DataGrid.vue'
import { fmtInt } from '@/lib/format'
import { useTheme } from '@/lib/theme'
import { entColor } from '../identity'
import { entName, taskLabel } from '../labels'
import type { NegotiationThread } from '../types'
import EcoChart from './EcoChart.vue'

const props = defineProps<{ thread: NegotiationThread }>()
const { mode } = useTheme()

const ABOUT: Record<string, string> = {
  production_contract:
    'Kirana asks MaklonNusa to fill 200,000 units over the season. MaklonNusa opens near its list price and concedes late (Boulware); Kirana counters from its target and concedes faster. A side accepts an offer inside its private limit that is worth at least what it would offer next.',
  campaign_terms:
    'PasarNusa wants the brand to fund more of the campaign voucher, Kirana less of it. Joining the 12.12 and Ramadan campaigns brings their traffic lift; the share each pays is what they negotiate.',
  quality_compensation:
    "After KemasPrima's defect forecast, MaklonNusa asks for compensation. KemasPrima offers a discount together with 100% inspection of the sets it ships, and the two settle the discount.",
  reroute_options:
    'Contract Net: before the flood, KirimCepat proposes routes around the Jakarta lane; Kirana scores them on its own weights (cost, delay, risk, kept private) and accepts one.',
}

const issue = computed(() => props.thread.offers[0]?.issue ?? '')

function fmt(v: unknown): string {
  if (typeof v !== 'number') return String(v ?? '')
  if (issue.value === 'unit_price') return `Rp ${fmtInt(v)}`
  return `${(v * 100).toFixed(1)}%`
}

const chart = computed(() => {
  void mode.value
  const t = props.thread
  const parties = [...new Set(t.offers.map((o) => o.by))]
  const money = issue.value === 'unit_price'
  return {
    data: parties.map((p) => {
      const pts = t.offers.map((o, i) => ({ ...o, n: i + 1 })).filter((o) => o.by === p)
      const color = entColor(p)
      return {
        type: 'scatter',
        mode: 'lines+markers+text',
        name: entName(p),
        x: pts.map((o) => o.n),
        y: pts.map((o) => o.value),
        text: pts.map((_, i) => (i === pts.length - 1 ? entName(p) : '')),
        textposition: 'top center',
        textfont: { color, size: 11 },
        line: { color, width: 2 },
        marker: { color, size: 9 },
        hovertemplate: `${entName(p)}<br>offer %{x}: ${money ? 'Rp %{y:,.0f}' : '%{y:.1%}'}<extra></extra>`,
      }
    }),
    layout: {
      xaxis: { title: { text: 'Offer, in the order made' }, dtick: 1 },
      yaxis: { tickformat: money ? ',.0f' : '.0%', tickprefix: money ? 'Rp ' : '' },
      margin: { l: 10, r: 24, t: 36, b: 10 },
    },
  }
})

const offerRows = computed(() =>
  props.thread.offers.map((o, i) => ({ offer: i + 1, by: entName(o.by), type: o.type.replace('_', ' ').toLowerCase(), value: fmt(o.value) })),
)

const optionRows = computed(() =>
  (props.thread.options ?? []).map((o) => ({
    route: String(o.title ?? o.id),
    'Rp per unit': o.cost_idr_per_unit as number,
    'delay (days)': o.delay_days as number,
    risk: `${((o.risk as number) * 100).toFixed(0)}%`,
    capacity: o.capacity_units as number,
    chosen: o.id === props.thread.agreed ? 'chosen' : '',
  })),
)

const outcome = computed(() => {
  const t = props.thread
  if (t.outcome !== 'agreed') return t.outcome === 'open' ? 'Still open' : 'No agreement: standard terms apply'
  if (t.task === 'reroute_options') {
    const o = (t.options ?? []).find((x) => x.id === t.agreed)
    return `Agreed: ${String(o?.title ?? t.agreed)}`
  }
  return `Agreed at ${fmt(t.agreed)} after ${t.offers.length} offers`
})
</script>

<template>
  <article class="card thread">
    <header>
      <div>
        <h2>{{ taskLabel(thread.task) }}</h2>
        <p class="parties small">
          <span v-for="p in thread.parties" :key="p" class="party"><i class="dot" :style="{ background: `var(--ent-${p})` }" />{{ entName(p) }}</span>
          <span class="muted">{{ thread.week > 0 ? `week ${thread.week}` : 'before the launch' }}, conversation <span class="stamp">{{ thread.conversation_id }}</span></span>
        </p>
      </div>
      <span class="chip" :class="thread.outcome === 'agreed' ? 'good' : thread.outcome === 'open' ? 'warn' : 'bad'">{{ outcome }}</span>
    </header>
    <p class="about">{{ ABOUT[thread.task] ?? '' }}</p>
    <div v-if="thread.offers.length" class="split">
      <EcoChart :data="chart.data" :layout="chart.layout" :height="260" />
      <DataGrid :columns="['offer', 'by', 'type', 'value']" :rows="offerRows" scroll-height="260px" :sortable="false" />
    </div>
    <DataGrid
      v-else-if="thread.options?.length"
      :columns="['route', 'Rp per unit', 'delay (days)', 'risk', 'capacity', 'chosen']"
      :rows="optionRows"
      scroll-height="220px"
      :sortable="false"
    />
  </article>
</template>

<style scoped>
.thread header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.parties {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
  margin: 4px 0 0;
}
.party {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.about {
  margin: 10px 0 14px;
  color: var(--mm-text-2);
  font-size: var(--mm-fs-sm);
  max-width: 90ch;
}
</style>
