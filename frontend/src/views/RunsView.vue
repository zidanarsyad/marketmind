<script setup lang="ts">
// Every saved run, newest first, with a filter. Each card opens the run's Overview.
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

    <ul class="run-grid">
      <li v-for="r in shown" :key="r.run_id">
        <RouterLink :to="`/runs/${r.run_id}/overview`" class="card run-card">
          <div class="top">
            <strong>{{ r.client || 'Unknown client' }}</strong>
            <RunStatus :status="r.status" :qa="r.qa_score" />
          </div>
          <div class="when">{{ runDate(r.run_id, r.started) }}<span v-if="r.seconds"> · {{ seconds(r.seconds) }}</span></div>
          <div class="chips">
            <span class="chip"><i class="pi pi-hashtag" style="font-size: 0.7rem" />{{ r.run_id }}</span>
            <span class="chip" :class="r.use_llm ? 'accent' : ''">
              <i class="pi pi-sparkles" style="font-size: 0.7rem" />{{ r.use_llm ? `LLM: ${r.llm}` : 'LLM off' }}
            </span>
            <span v-if="r.review" class="chip"><i class="pi pi-user-edit" style="font-size: 0.7rem" />reviewed</span>
          </div>
        </RouterLink>
      </li>
    </ul>
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
.run-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr));
  gap: 12px;
}
.run-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  color: var(--mm-text);
  text-decoration: none;
  transition:
    border-color 0.15s,
    transform 0.15s;
}
.run-card:hover {
  border-color: var(--mm-accent);
  text-decoration: none;
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.top strong {
  font-size: 1.02rem;
}
.when {
  color: var(--mm-muted);
  font-size: 0.85rem;
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
