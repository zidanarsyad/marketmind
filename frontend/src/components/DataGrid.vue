<script setup lang="ts">
// A sortable, scrollable table. Wide tables scroll sideways inside their card, so the page itself never does.
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { computed } from 'vue'
import { fmtCell } from '@/lib/format'
import type { Scalar } from '@/types'

export interface GridColumn {
  field: string
  header?: string
  numeric?: boolean
  format?: (v: unknown, row: Record<string, unknown>) => string
  minWidth?: string
}

const props = withDefaults(
  defineProps<{
    columns: (string | GridColumn)[]
    rows: Record<string, unknown>[]
    scrollHeight?: string
    paginate?: number
    emptyText?: string
    sortable?: boolean
  }>(),
  { scrollHeight: '420px', paginate: 0, emptyText: 'Nothing to show.', sortable: true },
)

const cols = computed<GridColumn[]>(() =>
  props.columns.map((c) => {
    const col = typeof c === 'string' ? { field: c } : c
    const sample = props.rows.find((r) => r[col.field] !== null && r[col.field] !== undefined)?.[col.field]
    return { header: col.field, numeric: typeof sample === 'number', ...col }
  }),
)

function cell(col: GridColumn, row: Record<string, unknown>): string {
  const v = row[col.field]
  if (col.format) return col.format(v, row)
  if (typeof v === 'object' && v !== null) return JSON.stringify(v)
  return fmtCell(v as Scalar)
}
</script>

<template>
  <DataTable
    :value="rows"
    scrollable
    :scroll-height="scrollHeight"
    size="small"
    striped-rows
    :paginator="paginate > 0 && rows.length > paginate"
    :rows="paginate || undefined"
    removable-sort
    class="grid"
  >
    <template #empty>
      <span class="muted">{{ emptyText }}</span>
    </template>
    <Column
      v-for="col in cols"
      :key="col.field"
      :field="col.field"
      :header="col.header"
      :sortable="sortable"
      :header-class="col.numeric ? 'num' : ''"
      :body-class="col.numeric ? 'num' : ''"
      :style="col.minWidth ? { minWidth: col.minWidth } : undefined"
    >
      <template #body="{ data }">
        <slot :name="`cell-${col.field}`" :row="data" :value="data[col.field]">{{ cell(col, data) }}</slot>
      </template>
    </Column>
  </DataTable>
</template>

<style scoped>
.grid :deep(td) {
  vertical-align: top;
}
</style>
