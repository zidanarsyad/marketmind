<script setup lang="ts">
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import { computed, onMounted, ref, watch } from 'vue'
import { api, errorText } from '@/api'
import DataAgent from '@/components/DataAgent.vue'
import DataGrid from '@/components/DataGrid.vue'
import { toGrid } from '@/lib/tables'
import { useAppStore } from '@/stores/app'
import { useRunStore } from '@/stores/run'
import type { DatasetPreview, TablePayload } from '@/types'

const run = useRunStore()
const app = useAppStore()
const id = computed(() => run.runId as string)
const tables = computed(() => run.bundle?.summary.tables ?? [])

const catalog = ref<TablePayload | null>(null)
const scorecard = ref<TablePayload | null>(null)
const news = ref<TablePayload | null>(null)
onMounted(async () => {
  const get = (key: string) => (tables.value.includes(key) ? api.table(id.value, key) : Promise.resolve(null))
  const [c, s, n] = await Promise.allSettled([get('data.catalog'), get('dq.scorecard'), get('external.news')])
  if (c.status === 'fulfilled') catalog.value = c.value
  if (s.status === 'fulfilled') scorecard.value = s.value
  if (n.status === 'fulfilled') news.value = n.value
})

const datasets = computed(() => app.config?.datasets ?? [])
const chosen = ref('sales')
const preview = ref<DatasetPreview | null>(null)
const loading = ref(false)
const error = ref('')
async function loadPreview() {
  loading.value = true
  error.value = ''
  try {
    preview.value = await api.dataset(id.value, chosen.value)
  } catch (e) {
    error.value = errorText(e)
    preview.value = null
  } finally {
    loading.value = false
  }
}
watch(chosen, loadPreview, { immediate: true })

const catalogGrid = computed(() => toGrid(catalog.value))
const scoreGrid = computed(() => toGrid(scorecard.value))
const newsGrid = computed(() => toGrid(news.value))
const previewGrid = computed(() => toGrid(preview.value))
const agentLlm = computed(() =>
  app.config?.llm.available ? app.config.llm.description : 'its rule-based policy (offline)',
)
</script>

<template>
  <div class="stack">
    <DataAgent :run-id="id" :llm="agentLlm" />
    <section v-if="catalog" class="card">
      <h3>Data catalogue</h3>
      <DataGrid :columns="catalogGrid.columns" :rows="catalogGrid.rows" scroll-height="none" />
    </section>
    <section v-if="scorecard" class="card">
      <h3>Data quality scorecard</h3>
      <DataGrid :columns="scoreGrid.columns" :rows="scoreGrid.rows" scroll-height="none" />
    </section>

    <section class="card">
      <div class="preview-head">
        <h3>Preview a dataset</h3>
        <Select
          v-model="chosen"
          :options="datasets"
          option-label="name"
          option-value="name"
          class="picker"
          aria-label="Dataset to preview"
        />
      </div>
      <div v-if="loading" class="center"><ProgressSpinner style="width: 28px; height: 28px" /></div>
      <p v-else-if="error" class="caption">{{ error }}</p>
      <template v-else-if="preview">
        <p class="caption">
          {{ preview.description }} · source: {{ preview.source }}
          <template v-if="preview.available"> · showing the first {{ preview.data.length.toLocaleString('en-US') }} rows</template>
        </p>
        <DataGrid v-if="preview.available" :columns="previewGrid.columns" :rows="previewGrid.rows" scroll-height="380px" :paginate="100" />
        <p v-else class="empty">{{ preview.file }} is not in the data folder this run studied.</p>
      </template>
    </section>

    <section v-if="news && news.total" class="card">
      <h3>Latest news headlines (live API)</h3>
      <DataGrid :columns="newsGrid.columns" :rows="newsGrid.rows" scroll-height="380px" />
    </section>
  </div>
</template>

<style scoped>
.card h3 {
  margin-bottom: 8px;
}
.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.preview-head h3 {
  margin: 0;
}
.picker {
  min-width: 200px;
}
.center {
  display: flex;
  justify-content: center;
  padding: 16px;
}
</style>
