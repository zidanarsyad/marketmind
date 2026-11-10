<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { computed, onMounted, ref } from 'vue'
import { api, errorText } from '@/api'
import DataGrid from '@/components/DataGrid.vue'
import { useRunStore } from '@/stores/run'
import type { EvaluationState } from '@/types'

const run = useRunStore()
const id = computed(() => run.runId as string)
const state = ref<EvaluationState | null>(null)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    state.value = await api.evaluation(id.value)
  } catch (e) {
    error.value = errorText(e)
  }
})

async function evaluate() {
  busy.value = true
  error.value = ''
  try {
    state.value = await api.evaluate(id.value)
    run.markEvaluated(id.value)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

const result = computed(() => state.value?.result ?? null)
const rows = computed(() =>
  (result.value?.checks ?? []).map((c) => ({ result: c.passed ? 'pass' : 'fail', ...c })),
)
const qa = computed(() => run.meta?.qa)
</script>

<template>
  <div class="stack">
    <div v-if="!state && !error" class="center"><ProgressSpinner style="width: 32px; height: 32px" /></div>
    <template v-else-if="state">
      <Message v-if="!state.available" severity="info">
        This run studied real data, which has no planted answers to score against. Judge its findings by the evidence
        each one cites (Data and Strategy views) and by the QA certificate in the report.
      </Message>
      <template v-else>
        <p class="caption">
          The data is simulated, so the true market facts are known. This checks how many of them the agents recovered.
        </p>
        <div v-if="!state.evaluated">
          <Button label="Evaluate this run against the ground truth" icon="pi pi-check-square" :loading="busy" @click="evaluate" />
        </div>
      </template>
      <template v-if="result && result.total">
        <div class="tiles">
          <div class="tile"><div class="label">Ground-truth checks passed</div><div class="value">{{ result.passed }}/{{ result.total }}</div></div>
          <div class="tile">
            <div class="label">Insight recall</div>
            <div class="value">{{ result.score !== null ? `${Math.round(result.score * 100)}%` : 'n/a' }}</div>
          </div>
          <div class="tile">
            <div class="label">QA score</div>
            <div class="value">{{ qa?.score ?? 'n/a' }}<span v-if="qa?.score !== null && qa?.score !== undefined">/100</span></div>
          </div>
        </div>
        <section class="card">
          <DataGrid
            :columns="[
              { field: 'result', minWidth: '5.5rem' },
              'area',
              { field: 'check', minWidth: '14rem' },
              { field: 'expected', minWidth: '9rem' },
              { field: 'found', minWidth: '9rem' },
              { field: 'detail', minWidth: '14rem' },
            ]"
            :rows="rows"
            scroll-height="none"
          >
            <template #cell-result="{ value }">
              <span class="chip" :class="value === 'pass' ? 'good' : 'bad'">
                <i :class="value === 'pass' ? 'pi pi-check' : 'pi pi-times'" style="font-size: 0.7rem" />{{ value }}
              </span>
            </template>
          </DataGrid>
        </section>
      </template>
    </template>
    <p v-if="error" class="caption err">{{ error }}</p>
  </div>
</template>

<style scoped>
.center {
  display: flex;
  justify-content: center;
  padding: 40px;
}
.err {
  color: var(--mm-bad);
}
</style>
