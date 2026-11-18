<script setup lang="ts">
// The season on one strip: the campaigns, the disruptions (in the colour of the enterprise they hit), every plan the
// coordinator confirmed (a ring when an enterprise rejected the first proposal), and the orders lost each week under
// local and under ecosystem intelligence. When the environment changes, the plan markers show the ecosystem reacting.
import { computed } from 'vue'
import { fmtInt } from '@/lib/format'
import { entName } from '../labels'
import type { PlanRevision, RunEvent, WeekRecord } from '../types'

const props = withDefaults(
  defineProps<{
    campaigns: { name: string; weeks: number[] }[]
    events: RunEvent[]
    plans?: PlanRevision[]
    weekly?: { local?: WeekRecord[]; ecosystem?: WeekRecord[] }
    weekStarts?: Record<string, string>
    weeks?: number
  }>(),
  { plans: () => [], weekly: () => ({}), weekStarts: () => ({}), weeks: 16 },
)

const cols = computed(() => Array.from({ length: props.weeks }, (_, i) => i + 1))
const date = (w: number) => {
  const iso = props.weekStarts[String(w)]
  return iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : ''
}
const span = (start: number, end: number) => ({ gridColumn: `${start + 1} / ${end + 2}` })

/** A label needs about three weeks of the strip: a one-week band lends its label the weeks after it. */
const labelEnd = (start: number, end: number) => Math.min(props.weeks, Math.max(end, start + 2))

const campaignSpans = computed(() =>
  props.campaigns.map((c) => {
    const start = Math.min(...c.weeks)
    const end = Math.max(...c.weeks)
    return { name: c.name, start, end, labelEnd: labelEnd(start, end) }
  }),
)

/** Disruptions in lanes, so that overlapping ones (the stress scenario) sit one above the other. */
const lanes = computed(() => {
  type Band = { key: string; title: string; target: string; start: number; end: number; labelEnd: number; detail: string }
  const out: Band[][] = []
  const ds = props.events
    .filter((e) => e.kind === 'disruption')
    .map((e) => {
      const start = e.start ?? e.week
      const end = e.end ?? e.week
      return { key: e.key, title: e.title, target: e.target, start, end, labelEnd: labelEnd(start, end), detail: e.detail }
    })
    .sort((a, b) => a.start - b.start)
  for (const d of ds) {
    const lane = out.find((l) => l[l.length - 1].labelEnd < d.start)
    if (lane) lane.push(d)
    else out.push([d])
  }
  return out
})

const planAt = computed(() => {
  const m = new Map<number, PlanRevision>()
  for (const p of props.plans) if (p.week >= 1) m.set(p.week, p)
  return m
})
const firstPlan = computed(() => props.plans.find((p) => p.week === 0) ?? null)
const triggered = (p: PlanRevision) => !p.reason.includes('fortnightly')
const planTitle = (p: PlanRevision) =>
  `Plan rev. ${p.revision}, W${p.week}: ${p.reason}. ${p.rounds > 1 ? `${p.rounds} rounds (a partner rejected the first proposal). ` : ''}` +
  `Planned fill rate ${(p.result.planned_fill_rate * 100).toFixed(1)}%, ${p.diff.length} weekly figures changed.`

function weeklyLost(rows?: WeekRecord[]): number[] {
  if (!rows?.length) return []
  return rows.map((r, i) => r.lost - (i ? rows[i - 1].lost : 0))
}
const lost = computed(() => ({ local: weeklyLost(props.weekly.local), ecosystem: weeklyLost(props.weekly.ecosystem) }))
const maxLost = computed(() => Math.max(1, ...lost.value.local, ...lost.value.ecosystem))
const cellStyle = (n: number) => (n > 0 ? { background: `rgba(var(--lost-rgb), ${0.12 + 0.6 * (n / maxLost.value)})` } : {})
const compact = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : fmtInt(n))
</script>

<template>
  <div class="timeline-wrap scroll-x">
    <div class="timeline" :style="{ '--weeks': weeks }">
      <div class="row head">
        <span class="lab" />
        <span v-for="w in cols" :key="w" class="wk">
          <b>W{{ w }}</b><small>{{ date(w) }}</small>
        </span>
      </div>

      <div class="row">
        <span class="lab" style="grid-row: 1">Campaigns</span>
        <template v-for="c in campaignSpans" :key="c.name">
          <span class="band campaign" :style="{ ...span(c.start, c.end), gridRow: 1 }" />
          <span class="label" :style="{ ...span(c.start, c.labelEnd), gridRow: 1 }"><b>{{ c.name }}</b></span>
        </template>
      </div>

      <div v-for="(lane, i) in lanes" :key="`lane${i}`" class="row">
        <span class="lab" style="grid-row: 1">{{ i === 0 ? 'Disruptions' : '' }}</span>
        <template v-for="d in lane" :key="d.key">
          <span class="band disruption" :style="{ ...span(d.start, d.end), gridRow: 1, '--c': `var(--ent-${d.target}, var(--mm-bad))` }" />
          <span class="label" :style="{ ...span(d.start, d.labelEnd), gridRow: 1 }" :title="d.detail">
            <b>{{ d.title }}</b><small>{{ entName(d.target) }}</small>
          </span>
        </template>
      </div>
      <div v-if="!lanes.length" class="row">
        <span class="lab">Disruptions</span>
        <span class="none" :style="span(1, weeks)">None in this scenario</span>
      </div>

      <div v-if="plans.length" class="row plans">
        <span class="lab">Plans<small v-if="firstPlan">rev. 1 before the launch</small></span>
        <span v-for="w in cols" :key="w" class="cell">
          <span
            v-if="planAt.get(w)"
            class="mark"
            :class="{ hot: triggered(planAt.get(w)!), rounds: planAt.get(w)!.rounds > 1 }"
            :title="planTitle(planAt.get(w)!)"
            :aria-label="planTitle(planAt.get(w)!)"
            role="img"
          >{{ planAt.get(w)!.revision }}</span>
        </span>
      </div>

      <template v-for="m in (['local', 'ecosystem'] as const)" :key="m">
        <div v-if="lost[m].length" class="row lost">
          <span class="lab">Orders lost<small>{{ m === 'local' ? 'local intelligence' : 'ecosystem intelligence' }}</small></span>
          <span v-for="(n, i) in lost[m]" :key="i" class="cell num" :style="cellStyle(n)" :title="`W${i + 1}: ${fmtInt(n)} orders lost`">
            {{ n > 0 ? compact(n) : '' }}
          </span>
        </div>
      </template>
    </div>
    <p v-if="plans.length" class="legend caption">
      <span class="item"><span class="mark" /> fortnightly plan</span>
      <span class="item"><span class="mark hot" /> plan triggered by a reported risk</span>
      <span class="item"><span class="mark hot rounds" /> a partner rejected the first proposal; the coordinator solved again</span>
    </p>
  </div>
</template>

<style scoped>
.timeline-wrap {
  --lab: 8.6rem;
  --lost-rgb: 180, 35, 53;
}
:global(.app-dark) .timeline-wrap {
  --lost-rgb: 240, 122, 134;
}
.timeline {
  min-width: 880px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: grid;
  grid-template-columns: var(--lab) repeat(var(--weeks), minmax(0, 1fr));
  align-items: stretch;
  column-gap: 3px;
  min-height: 30px;
}
.lab {
  grid-column: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  font-size: var(--mm-fs-xs);
  font-weight: 600;
  color: var(--mm-text-2);
  line-height: 1.25;
  padding-right: 8px;
}
.lab small {
  font-weight: 450;
  color: var(--mm-muted);
}
.head .wk {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: var(--mm-fs-xs);
  line-height: 1.2;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--mm-border);
}
.head .wk b {
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.head .wk small {
  color: var(--mm-muted);
  font-size: 0.68rem;
}
.band {
  min-width: 0;
  min-height: 34px;
  border-radius: var(--mm-radius-sm);
}
.label {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  padding: 3px 8px 3px 10px;
  font-size: var(--mm-fs-xs);
  line-height: 1.25;
  pointer-events: auto;
}
.label b,
.label small {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.label b {
  font-weight: 640;
  color: var(--mm-text);
}
.label small {
  color: var(--mm-text-2);
}
.campaign {
  background: var(--mm-panel-2);
  border: 1px dashed var(--mm-border-strong);
}
.disruption {
  background: color-mix(in srgb, var(--c) 16%, transparent);
  border-left: 3px solid var(--c);
}
.none {
  font-size: var(--mm-fs-xs);
  color: var(--mm-muted);
  align-self: center;
  padding-left: 8px;
}
.cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  border-radius: 4px;
  font-size: var(--mm-fs-xs);
}
.lost .cell {
  background: var(--mm-panel-2);
  font-weight: 600;
  color: var(--mm-text);
}
.mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1.5px solid var(--mm-border-strong);
  color: var(--mm-muted);
  background: var(--mm-panel);
  font-size: 0.68rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.mark.hot {
  background: var(--mm-text);
  border-color: var(--mm-text);
  color: var(--mm-panel);
}
.mark.rounds {
  box-shadow: 0 0 0 2px var(--mm-panel), 0 0 0 4px var(--mm-text);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 18px;
  margin-top: 10px;
}
.legend .item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.legend .mark {
  width: 14px;
  height: 14px;
}
.legend .mark.rounds {
  box-shadow: 0 0 0 1.5px var(--mm-panel), 0 0 0 3px var(--mm-text);
}
</style>
