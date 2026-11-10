<script setup lang="ts">
import { computed } from 'vue'
import FindingsList from '@/components/FindingsList.vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import TableCard from '@/components/TableCard.vue'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
</script>

<template>
  <div class="stack">
    <FindingsList areas="market" />
    <div class="grid-2">
      <PlotlyChart :run-id="id" name="market_size" />
      <PlotlyChart :run-id="id" name="category_growth" />
      <PlotlyChart :run-id="id" name="channel_mix" />
      <PlotlyChart :run-id="id" name="region_growth" />
      <PlotlyChart :run-id="id" name="seasonality" />
      <PlotlyChart :run-id="id" name="monthly_market" />
    </div>
    <PlotlyChart :run-id="id" name="topic_trends" />
    <TableCard :run-id="id" table-key="market.tables.topic_trends" title="Topic trend table" />
    <TableCard :run-id="id" table-key="external.macro" title="World Bank indicators (live API)" />
  </div>
</template>
