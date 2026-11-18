<script setup lang="ts">
// Local against ecosystem intelligence on the same scenario and the same customers, KPI by KPI, with the change and
// whether it is better (said in words and an arrow, not by colour alone).
import { fmtInt } from '@/lib/format'
import { idr } from '../labels'
import type { Comparison, ComparisonRow } from '../types'

defineProps<{ comparison: Comparison }>()

function value(r: ComparisonRow, v: number): string {
  if (r.kpi === 'fill_rate') return `${(v * 100).toFixed(1)}%`
  if (r.kpi.endsWith('_idr')) return idr(v)
  return fmtInt(v)
}

function change(r: ComparisonRow): string {
  if (r.delta === null) return ''
  const sign = r.delta > 0 ? '+' : r.delta < 0 ? '−' : ''
  const a = Math.abs(r.delta)
  if (r.kpi === 'fill_rate') return `${sign}${(a * 100).toFixed(1)} pts`
  if (r.kpi.endsWith('_idr')) return `${sign}${idr(a)}`
  return `${sign}${fmtInt(a)}`
}

function verdict(r: ComparisonRow): 'better' | 'worse' | 'same' | 'info' {
  if (r.better === 'info' || r.delta === null) return 'info'
  if (r.delta === 0) return 'same'
  return (r.better === 'higher') === r.delta > 0 ? 'better' : 'worse'
}
</script>

<template>
  <div class="card tight scroll-x">
    <table class="ledger">
      <thead>
        <tr>
          <th scope="col">KPI</th>
          <th scope="col" class="num">Local intelligence</th>
          <th scope="col" class="num">Ecosystem intelligence</th>
          <th scope="col" class="num">Change</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in comparison.rows" :key="r.kpi" :class="{ info: r.better === 'info' }">
          <th scope="row">{{ r.label }}</th>
          <td class="num">{{ value(r, r.local) }}</td>
          <td class="num strong">{{ value(r, r.ecosystem) }}</td>
          <td class="num">
            <span class="delta" :class="verdict(r)">
              <i v-if="verdict(r) === 'better' || verdict(r) === 'worse'" :class="r.delta! > 0 ? 'pi pi-arrow-up' : 'pi pi-arrow-down'" aria-hidden="true" />
              {{ change(r) }}
              <small v-if="verdict(r) === 'better' || verdict(r) === 'worse'">{{ verdict(r) }}</small>
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.ledger {
  width: 100%;
  min-width: 520px;
  border-collapse: collapse;
  font-size: var(--mm-fs-sm);
}
th,
td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--mm-border);
  text-align: left;
  font-weight: 450;
}
thead th {
  font-size: var(--mm-fs-xs);
  font-weight: 600;
  color: var(--mm-muted);
  white-space: nowrap;
}
tbody th {
  font-weight: 560;
}
tbody tr:last-child th,
tbody tr:last-child td {
  border-bottom: 0;
}
tr.info th,
tr.info td {
  color: var(--mm-text-2);
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.strong {
  font-weight: 650;
}
.delta {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  color: var(--mm-text-2);
}
.delta i {
  font-size: 0.7rem;
}
.delta small {
  font-size: 0.72rem;
}
.delta.better {
  color: var(--mm-good);
}
.delta.worse {
  color: var(--mm-bad);
}
</style>
