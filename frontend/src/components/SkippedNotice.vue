<script setup lang="ts">
// Says so when the study's plan left this view's module(s) out and no agent produced them anyway, instead of
// leaving the reader with empty charts. (Pricing runs inside the segmentation agent; the forecasting agent can still
// run without the forecast module, because pricing needs its elasticities.)
import Message from 'primevue/message'
import { computed } from 'vue'
import { useRunStore } from '@/stores/run'

const props = defineProps<{ modules: string[] }>()
const run = useRunStore()
const TASK: Record<string, string> = { pricing: 'segmentation' }

const skipped = computed(() => {
  const planned = run.meta?.plan?.modules
  if (!planned) return []
  const agents = run.meta?.agents ?? {}
  return props.modules.filter((m) => planned[m] === false && agents[TASK[m] ?? m]?.status !== 'completed')
})
const dropped = computed(() =>
  (run.meta?.approvals ?? []).some((a) => a.gate === 'plan' && a.drop?.some((d) => skipped.value.includes(d))),
)
</script>

<template>
  <Message v-if="skipped.length" severity="secondary" icon="pi pi-info-circle">
    This study left out the {{ skipped.join(' and ') }} {{ skipped.length > 1 ? 'modules' : 'module' }}
    {{ dropped ? '(the reviewer removed it at the plan gate)' : '(not covered by the brief or the data)' }}, so there
    is less to show here.
  </Message>
</template>
