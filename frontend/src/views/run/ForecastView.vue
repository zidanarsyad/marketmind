<script setup lang="ts">
import Slider from 'primevue/slider'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'
import FindingsList from '@/components/FindingsList.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import SkippedNotice from '@/components/SkippedNotice.vue'
import TableCard from '@/components/TableCard.vue'
import { fmtIdr } from '@/lib/format'
import { simulatePrice } from '@/lib/kpis'
import { toRecords } from '@/lib/tables'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
const horizon = computed(() => run.horizon)

// ------------------------------------------------------------------ price simulator
const elasticity = ref<number | null>(null)
const baseRevenue = ref<number | null>(null)
const priceChange = ref(0)
const marginPct = ref(60)

onMounted(async () => {
  const tables = run.bundle?.summary.tables ?? []
  if (!tables.includes('forecast.tables.elasticities') || !tables.includes('forecast.tables.forecast_summary_brand')) return
  const [el, fsb] = await Promise.all([
    api.table(id.value, 'forecast.tables.elasticities'),
    api.table(id.value, 'forecast.tables.forecast_summary_brand'),
  ])
  const e = toRecords(el).find((r) => r.brand === run.client)
  const b = toRecords(fsb).find((r) => r.brand === run.client)
  if (e && b && typeof e.elasticity === 'number' && typeof b.revenue_next12 === 'number') {
    elasticity.value = e.elasticity
    baseRevenue.value = b.revenue_next12 // the forecast over the plan's horizon, whatever the column is called
  }
})

const outcome = computed(() =>
  elasticity.value !== null && baseRevenue.value !== null
    ? simulatePrice(elasticity.value, baseRevenue.value, priceChange.value, marginPct.value / 100)
    : null,
)
const signed = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`
</script>

<template>
  <div class="stack">
    <SkippedNotice :modules="['forecast']" />
    <FindingsList areas="forecast" />
    <div class="grid-2">
      <PlotlyChart :run-id="id" name="market_forecast" />
      <PlotlyChart :run-id="id" name="client_forecast" />
      <PlotlyChart :run-id="id" name="backtest" />
      <PlotlyChart :run-id="id" name="feature_importance" />
    </div>
    <TableCard :run-id="id" table-key="forecast.tables.backtest_metrics" title="Backtest metrics (mean of 3 rolling folds)" expanded />
    <TableCard :run-id="id" table-key="forecast.tables.forecast_summary_brand" :title="`Forecast by brand (next ${horizon} months)`" />
    <TableCard :run-id="id" table-key="forecast.tables.forecast_summary_category" :title="`Forecast by category (next ${horizon} months)`" />

    <div class="section-title"><h2>Pricing</h2></div>
    <div class="grid-2">
      <PlotlyChart :run-id="id" name="elasticities" />
      <PlotlyChart :run-id="id" name="price_scenarios" />
    </div>

    <section v-if="outcome && elasticity !== null && baseRevenue !== null" class="card simulator">
      <h3>Price simulator for {{ run.client }}</h3>
      <p class="caption">Constant-elasticity demand on the {{ horizon }}-month forecast baseline ({{ fmtIdr(baseRevenue) }}).</p>
      <div class="sliders">
        <label>
          <span>List-price change <strong>{{ priceChange > 0 ? '+' : '' }}{{ priceChange }}%</strong></span>
          <Slider v-model="priceChange" :min="-20" :max="20" :step="1" aria-label="List-price change in percent" />
        </label>
        <label>
          <span>Gross margin at current price <strong>{{ marginPct }}%</strong></span>
          <Slider v-model="marginPct" :min="30" :max="85" :step="1" aria-label="Gross margin in percent" />
        </label>
      </div>
      <div class="tiles">
        <div class="tile"><div class="label">Elasticity</div><div class="value">{{ elasticity.toFixed(2) }}</div></div>
        <div class="tile"><div class="label">Volume change</div><div class="value">{{ signed(outcome.volumeChange) }}</div></div>
        <div class="tile">
          <div class="label">Revenue ({{ horizon }}m)</div>
          <div class="value">{{ fmtIdr(outcome.revenue) }}</div>
          <div class="note" :class="outcome.revenueChange >= 0 ? 'up' : 'down'">{{ signed(outcome.revenueChange) }}</div>
        </div>
        <div class="tile">
          <div class="label">Gross profit change</div>
          <div class="value" :class="outcome.grossProfitChange >= 0 ? 'up' : 'down'">{{ signed(outcome.grossProfitChange) }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.simulator {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.simulator h3 {
  margin: 0;
}
.sliders {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 18px 32px;
  padding: 4px 6px 8px;
}
.sliders label {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 0.9rem;
  color: var(--mm-text-2);
}
.up {
  color: var(--mm-good);
}
.down {
  color: var(--mm-bad);
}
</style>
