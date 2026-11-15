<script setup lang="ts">
// Every saved run, newest first, with a filter: a ledger with one row per run. Each row opens the run's Overview.
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import SelectButton from 'primevue/selectbutton'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import RunStatus from '@/components/RunStatus.vue'
import { runDate, seconds } from '@/lib/format'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const query = ref('')
const show = ref<'all' | 'reports' | 'stopped'>('all')
const filters = [
  { label: 'All', value: 'all' },
  { label: 'With a report', value: 'reports' },
  { label: 'Stopped or failed', value: 'stopped' },
]

onMounted(() => void app.loadRuns())

const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return app.runs.filter((r) => {
    const stopped = r.status === 'rejected' || r.status === 'failed'
    if (show.value === 'reports' && stopped) return false
    if (show.value === 'stopped' && !stopped) return false
    return !q || `${r.client ?? ''} ${r.run_id} ${r.llm ?? ''} ${r.status ?? ''}`.toLowerCase().includes(q)
  })
})
</script>

<template>
  <div class="page stack">
    <header class="head">
      <div>
        <h1>Saved runs</h1>
        <p class="caption">{{ app.runs.length }} studies in <code>outputs/runs</code>, newest first.</p>
      </div>
      <RouterLink v-slot="{ navigate }" to="/new" custom>
        <Button label="New study" icon="pi pi-plus" @click="navigate" />
      </RouterLink>
    </header>

    <div class="toolbar">
      <IconField class="search">
        <InputIcon class="pi pi-search" />
        <InputText v-model="query" placeholder="Filter by client, run or LLM" aria-label="Filter the runs" fluid />
      </IconField>
      <SelectButton v-model="show" :options="filters" option-label="label" option-value="value" :allow-empty="false" aria-label="Which runs" />
    </div>

    <p v-if="app.runsError" class="caption">{{ app.runsError }}</p>
    <p v-else-if="app.runsLoaded && !shown.length" class="empty">No runs match.</p>

    <div v-if="shown.length" class="card ledger">
      <div class="row head-row" aria-hidden="true">
        <span>Client and run</span>
        <span>Started</span>
        <span>Took</span>
        <span>Language model</span>
        <span>Approvals</span>
        <span class="outcome">Outcome</span>
      </div>
      <ul>
        <li v-for="r in shown" :key="r.run_id">
          <RouterLink :to="`/runs/${r.run_id}/overview`" class="row">
            <span class="client"><strong>{{ r.client || 'Unknown client' }}</strong><small>Run {{ r.run_id }}</small></span>
            <span class="cell"><span class="cell-label">Started </span>{{ runDate(r.run_id, r.started) }}</span>
            <span class="cell num"><span class="cell-label">Took </span>{{ r.seconds ? seconds(r.seconds) : 'n/a' }}</span>
            <span class="cell"><span class="cell-label">LLM </span>{{ r.use_llm ? r.llm || 'On' : 'Off' }}</span>
            <span class="cell"><span class="cell-label">Approvals </span>{{ r.review ? 'Reviewer' : 'Automatic' }}</span>
            <RunStatus class="outcome" :status="r.status" :qa="r.qa_score" />
          </RouterLink>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.search {
  flex: 1 1 260px;
  max-width: 420px;
}
/* one ruled row per run, the same facts in the same column, instead of a card per run */
.ledger {
  padding: 0;
  overflow: hidden;
}
.ledger ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.row {
  display: grid;
  grid-template-columns: minmax(170px, 1.3fr) minmax(150px, 1fr) minmax(84px, 0.6fr) minmax(110px, 1fr) minmax(104px, 0.8fr) minmax(130px, 0.9fr);
  align-items: center;
  gap: 14px;
  padding: 10px 20px;
  border-top: 1px solid var(--mm-border);
  color: var(--mm-text);
  font-size: var(--mm-fs-sm);
  text-decoration: none;
}
.head-row {
  border-top: 0;
  padding-top: 11px;
  padding-bottom: 10px;
  background: var(--mm-panel-2);
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
  font-weight: 560;
}
a.row:hover {
  background: var(--mm-panel-2);
  text-decoration: none;
}
a.row:hover .client strong {
  color: var(--mm-accent);
}
a.row:focus-visible {
  outline-offset: -2px;
}
.client strong {
  display: block;
  font-size: var(--mm-fs-md);
  font-weight: 620;
}
.client small {
  display: block;
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
  font-variant-numeric: tabular-nums;
}
.cell {
  color: var(--mm-text-2);
  overflow-wrap: anywhere;
}
/* the column headings say what each cell is; a phone, which has no headings, shows these instead */
.cell-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.outcome {
  justify-self: end;
}
@media (max-width: 860px) {
  .row.head-row {
    display: none;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 2px 12px;
    padding: 12px 16px;
  }
  .client {
    flex: 1 1 60%;
    min-width: 0;
    margin-bottom: 2px;
  }
  .outcome {
    order: -1;
    margin-left: auto;
  }
  .client {
    order: -2;
  }
  .cell {
    font-size: var(--mm-fs-xs);
  }
  .cell-label {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip-path: none;
    color: var(--mm-muted);
  }
}
@media (max-width: 720px) {
  .toolbar :deep(.p-selectbutton) {
    width: 100%;
    display: flex;
  }
  .toolbar :deep(.p-togglebutton) {
    flex: 1;
  }
}
</style>
