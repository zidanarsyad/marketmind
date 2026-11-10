<script setup lang="ts">
// A table artefact of the run in a collapsible card (the dashboard's "Table view" expanders). It loads when opened,
// and stays out of the page when the run has no such table.
import Panel from 'primevue/panel'
import ProgressSpinner from 'primevue/progressspinner'
import { computed, ref, watch } from 'vue'
import { api, errorText } from '@/api'
import { toGrid } from '@/lib/tables'
import { useRunStore } from '@/stores/run'
import type { TablePayload } from '@/types'
import DataGrid from './DataGrid.vue'

const props = withDefaults(
  defineProps<{ runId: string; tableKey: string; title: string; expanded?: boolean; scrollHeight?: string }>(),
  { expanded: false, scrollHeight: '420px' },
)

const run = useRunStore()
const exists = computed(() => run.bundle?.summary.tables.includes(props.tableKey) ?? false)
const open = ref(props.expanded)
const table = ref<TablePayload | null>(null)
const loading = ref(false)
const error = ref('')
const grid = computed(() => toGrid(table.value))

async function load() {
  if (!exists.value || table.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    table.value = await api.table(props.runId, props.tableKey)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.runId, props.tableKey],
  () => {
    table.value = null
    if (open.value) void load()
  },
)
watch(open, (v) => v && void load(), { immediate: true })
</script>

<template>
  <Panel
    v-if="exists && !(table && table.total === 0)"
    :header="title"
    toggleable
    :collapsed="!open"
    class="table-card"
    @update:collapsed="(c: boolean) => (open = !c)"
  >
    <div v-if="loading" class="loading"><ProgressSpinner style="width: 28px; height: 28px" stroke-width="5" /></div>
    <p v-else-if="error" class="caption">{{ error }}</p>
    <template v-else-if="table">
      <DataGrid :columns="grid.columns" :rows="grid.rows" :scroll-height="scrollHeight" />
      <p v-if="table.truncated" class="caption">Showing the first {{ table.data.length.toLocaleString('en-US') }} of {{ table.total.toLocaleString('en-US') }} rows.</p>
    </template>
  </Panel>
</template>

<style scoped>
.table-card {
  background: var(--mm-panel);
  border-color: var(--mm-border);
  border-radius: var(--mm-radius);
}
.loading {
  display: flex;
  justify-content: center;
  padding: 12px;
}
</style>
