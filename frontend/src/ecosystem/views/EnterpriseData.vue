<script setup lang="ts">
// The enterprise's own database, as the signed-in role may see it: the datasets the role can open, those it cannot,
// those that never leave the enterprise, and each table with the fields the role may not read masked.
import Button from 'primevue/button'
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'
import { ApiError, errorText } from '@/api'
import DataGrid from '@/components/DataGrid.vue'
import { fmtCell, fmtInt } from '@/lib/format'
import type { Scalar } from '@/types'
import { enterpriseApi } from '../api'
import { useEnterpriseStore } from '../store'
import type { DatasetInfo, DatasetPage } from '../types'

const ent = useEnterpriseStore()
const LIMIT = 100
const datasets = ref<DatasetInfo[]>([])
const store = ref('')
const listError = ref('')
const table = ref('')
const page = ref<DatasetPage | null>(null)
const offset = ref(0)
const tableError = ref('')
const loading = ref(false)

const role = computed({ get: () => ent.role, set: (v: string) => ent.setRole(v) })

async function loadList() {
  try {
    const r = await enterpriseApi.datasets(ent.role)
    datasets.value = r.datasets
    store.value = r.store
    listError.value = ''
    if (!table.value || !r.datasets.some((d) => d.name === table.value)) {
      table.value = r.datasets.find((d) => d.open_to_role)?.name ?? r.datasets[0]?.name ?? ''
    }
  } catch (e) {
    listError.value = errorText(e)
  }
}

async function loadTable() {
  if (!table.value) return
  loading.value = true
  try {
    page.value = await enterpriseApi.dataset(table.value, ent.role, LIMIT, offset.value)
    tableError.value = ''
  } catch (e) {
    page.value = null
    tableError.value = e instanceof ApiError && e.status === 403 ? `The ${ent.role} role cannot open ${table.value}. Sign in with another role to read it.` : errorText(e)
  } finally {
    loading.value = false
  }
}

watch(() => ent.role, async () => {
  await loadList()
  offset.value = 0
  await loadTable()
}, { immediate: true })
watch(table, () => {
  offset.value = 0
  void loadTable()
})
watch(offset, () => void loadTable())
watch(() => ent.revision, () => {
  void loadList()
  if (offset.value === 0) void loadTable()
})

const columns = computed(() => Object.keys(page.value?.rows[0] ?? {}))
const MASK = 'hidden for this role'
function show(v: unknown): string {
  if (v !== null && typeof v === 'object') return JSON.stringify(v)
  return fmtCell(v as Scalar)
}
const sorted = computed(() =>
  [...datasets.value].sort((a, b) => Number(b.open_to_role) - Number(a.open_to_role) || a.name.localeCompare(b.name)),
)
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Data explorer</h1>
      <p class="lede">
        {{ ent.node?.name }}'s own database, {{ store || ent.node?.platform.database }}, as the signed-in role sees it.
        Nothing here leaves the enterprise except through its governed API; fields the role may not read are masked.
      </p>
    </header>

    <div class="who">
      <label for="data-role" class="small">Signed in as</label>
      <Select v-model="role" input-id="data-role" :options="ent.node?.roles ?? []" option-label="name" option-value="name" />
      <span v-if="ent.roleInfo" class="small muted">{{ ent.roleInfo.description }}</span>
    </div>

    <div class="layout">
      <nav class="card tight list" aria-label="Datasets">
        <h2>Datasets</h2>
        <p v-if="listError" class="caption bad">{{ listError }}</p>
        <ul>
          <li v-for="d in sorted" :key="d.name">
            <button type="button" :class="{ current: d.name === table, closed: !d.open_to_role }" @click="table = d.name">
              <i :class="d.open_to_role ? 'pi pi-table' : 'pi pi-lock'" :aria-label="d.open_to_role ? 'open' : 'closed to this role'" />
              <span class="name">{{ d.name }}</span>
              <span v-if="d.private" class="chip warn">private</span>
              <span class="rows small muted">{{ fmtInt(d.rows) }}</span>
            </button>
          </li>
        </ul>
      </nav>

      <section class="card table-card">
        <div class="head">
          <h2>{{ table || 'No dataset' }}</h2>
          <span v-if="page" class="small muted">{{ fmtInt(page.total) }} rows</span>
        </div>
        <p v-if="tableError" class="denied"><i class="pi pi-lock" /> {{ tableError }}</p>
        <template v-else-if="page">
          <DataGrid :columns="columns" :rows="page.rows" scroll-height="520px" :empty-text="loading ? 'Loading…' : 'This dataset is empty for now.'">
            <template v-for="c in columns" :key="c" #[`cell-${c}`]="{ value }">
              <span v-if="value === MASK" class="masked">{{ MASK }}</span>
              <span v-else>{{ show(value) }}</span>
            </template>
          </DataGrid>
          <div v-if="page.total > LIMIT" class="pager">
            <Button icon="pi pi-angle-left" text rounded severity="secondary" aria-label="Previous rows" :disabled="offset === 0" @click="offset = Math.max(0, offset - LIMIT)" />
            <span class="small muted">{{ offset + 1 }}–{{ Math.min(page.total, offset + LIMIT) }} of {{ fmtInt(page.total) }}</span>
            <Button icon="pi pi-angle-right" text rounded severity="secondary" aria-label="Next rows" :disabled="offset + LIMIT >= page.total" @click="offset += LIMIT" />
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.hero {
  max-width: 78ch;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lede {
  margin: 0;
  color: var(--mm-text-2);
}
.who {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}
.who label {
  font-weight: 600;
  color: var(--mm-text-2);
}
.layout {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.list h2 {
  font-size: var(--mm-fs-md);
  margin: 2px 4px 8px;
}
.list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.list button {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px 7px 10px;
  border: 0;
  border-radius: var(--mm-radius-sm);
  background: transparent;
  color: var(--mm-text);
  text-align: left;
  cursor: pointer;
  font-size: var(--mm-fs-sm);
}
.list button:hover {
  background: var(--mm-panel-2);
}
.list button.current {
  background: var(--mm-accent-soft);
}
.list button.current::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 2px;
  background: var(--mm-accent);
}
.list button.closed {
  color: var(--mm-muted);
}
.list i {
  font-size: 0.8rem;
  color: var(--mm-muted);
}
.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 540;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.denied {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border: 1px dashed var(--mm-border-strong);
  border-radius: var(--mm-radius-sm);
  color: var(--mm-text-2);
  margin: 0;
}
.masked {
  color: var(--mm-muted);
  font-style: italic;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 8px;
}
.bad {
  color: var(--mm-bad);
}
@media (max-width: 1240px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .list ul {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 4px;
  }
  .list li {
    flex: 1 1 200px;
  }
}
</style>
