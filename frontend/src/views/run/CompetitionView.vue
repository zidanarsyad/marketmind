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
    <FindingsList areas="competition" />
    <div class="grid-2">
      <PlotlyChart :run-id="id" name="brand_share" />
      <PlotlyChart :run-id="id" name="share_trend" />
      <PlotlyChart :run-id="id" name="channel_index" />
      <PlotlyChart :run-id="id" name="region_index" />
      <PlotlyChart :run-id="id" name="threats" />
      <PlotlyChart :run-id="id" name="white_space" />
    </div>
    <PlotlyChart :run-id="id" name="positioning" />
    <TableCard :run-id="id" table-key="competition.tables.brand_share" title="Brand share table" />
    <TableCard :run-id="id" table-key="competition.tables.threats" title="Threat scoring components" />
    <TableCard :run-id="id" table-key="competition.tables.white_space" title="White-space scan" />
  </div>
</template>
