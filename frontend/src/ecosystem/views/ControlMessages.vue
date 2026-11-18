<script setup lang="ts">
// Every message the agents exchanged in the run, as the bus delivered them: who talks to whom (click a cell to read
// that pair's messages), filters by enterprise, task and text, and each message in full.
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import { computed, ref, watch } from 'vue'
import { errorText } from '@/api'
import { fmtInt } from '@/lib/format'
import { controlApi } from '../api'
import MessageList from '../components/MessageList.vue'
import { DISPLAY_ORDER, entName, entOf, taskLabel, typeLabel } from '../labels'
import { useControlStore } from '../store'
import type { EcoMessage, Mode } from '../types'

const ctl = useControlStore()
const modes = computed(() => (['ecosystem', 'local'] as Mode[]).filter((m) => ctl.run?.results?.[m]))
const mode = ref<Mode>('ecosystem')
watch(modes, (ms) => {
  if (ms.length && !ms.includes(mode.value)) mode.value = ms[0]
}, { immediate: true })

const all = ref<EcoMessage[]>([])
const loading = ref(false)
const error = ref('')
async function load() {
  const id = ctl.run?.id
  if (!id || !ctl.run?.results?.[mode.value]) {
    all.value = []
    return
  }
  loading.value = true
  try {
    all.value = (await controlApi.messages(id, mode.value, { limit: 5000 })).rows
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
watch([() => ctl.run?.id, mode], load, { immediate: true })

const NODES = [...DISPLAY_ORDER, 'control']
const enterprise = ref<string | null>(null)
const task = ref<string | null>(null)
const text = ref('')
const pair = ref<{ from: string; to: string } | null>(null)

const tasks = computed(() => [...new Set(all.value.map((m) => m.task))].sort().map((t) => ({ value: t, label: taskLabel(t) })))
const enterprises = NODES.map((k) => ({ value: k, label: entName(k) }))

const matrix = computed(() => {
  const counts: Record<string, Record<string, number>> = {}
  for (const m of all.value) {
    const a = entOf(m.sender)
    const b = entOf(m.receiver)
    counts[a] ??= {}
    counts[a][b] = (counts[a][b] ?? 0) + 1
  }
  return counts
})
const maxCell = computed(() => Math.max(1, ...Object.values(matrix.value).flatMap((r) => Object.values(r))))
const cell = (a: string, b: string) => matrix.value[a]?.[b] ?? 0
const tint = (n: number) => (n ? { background: `rgba(var(--mm-attn), ${0.08 + 0.5 * (n / maxCell.value)})` } : {})

const rows = computed(() => {
  const needle = text.value.trim().toLowerCase()
  return all.value.filter((m) => {
    const a = entOf(m.sender)
    const b = entOf(m.receiver)
    if (pair.value && (a !== pair.value.from || b !== pair.value.to)) return false
    if (enterprise.value && a !== enterprise.value && b !== enterprise.value) return false
    if (task.value && m.task !== task.value) return false
    if (needle && !`${m.message_id} ${m.sender} ${m.receiver} ${m.task} ${JSON.stringify(m.payload)}`.toLowerCase().includes(needle))
      return false
    return true
  })
})

const byType = computed(() => {
  const c: Record<string, number> = {}
  for (const m of all.value) c[m.message_type] = (c[m.message_type] ?? 0) + 1
  return Object.entries(c).sort((x, y) => y[1] - x[1])
})
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Agent messages</h1>
      <p class="lede">
        The agents of different enterprises talk only through messages in one contract (sender, receiver, performative,
        task, payload), each delivered to the receiving enterprise's own server.
      </p>
    </header>

    <p v-if="!ctl.run?.results" class="empty">Run a scenario first: its messages appear here.</p>
    <template v-else>
      <div class="toolbar">
        <SelectButton v-if="modes.length > 1" v-model="mode" :options="modes" :allow-empty="false" aria-label="Which run to read" />
        <span class="small muted">{{ loading ? 'Loading…' : `${fmtInt(all.length)} messages in the ${mode} run` }}</span>
        <span class="chips">
          <span v-for="[t, n] in byType" :key="t" class="chip">{{ typeLabel(t) }} {{ fmtInt(n) }}</span>
        </span>
      </div>
      <p v-if="error" class="caption bad">{{ error }}</p>

      <section class="card">
        <h2>Who talks to whom</h2>
        <p class="caption">Messages from each sender (rows) to each receiver (columns). Click a cell to read them.</p>
        <div class="scroll-x">
          <table class="matrix">
            <thead>
              <tr>
                <th scope="col"><span class="muted small">from \ to</span></th>
                <th v-for="b in NODES" :key="b" scope="col"><i class="dot" :style="{ background: `var(--ent-${b}, var(--mm-text-2))` }" />{{ entName(b) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in NODES" :key="a">
                <th scope="row"><i class="dot" :style="{ background: `var(--ent-${a}, var(--mm-text-2))` }" />{{ entName(a) }}</th>
                <td v-for="b in NODES" :key="b" class="num" :style="tint(cell(a, b))">
                  <button
                    v-if="cell(a, b)"
                    type="button"
                    :class="{ on: pair?.from === a && pair?.to === b }"
                    :aria-label="`${cell(a, b)} messages from ${entName(a)} to ${entName(b)}`"
                    @click="pair = pair?.from === a && pair?.to === b ? null : { from: a, to: b }"
                  >{{ fmtInt(cell(a, b)) }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <div class="filters">
          <Select v-model="enterprise" :options="enterprises" option-label="label" option-value="value" placeholder="Any enterprise" show-clear aria-label="Enterprise" />
          <Select v-model="task" :options="tasks" option-label="label" option-value="value" placeholder="Any task" show-clear filter aria-label="Task" />
          <InputText v-model="text" placeholder="Search ids and payloads" aria-label="Search messages" />
          <span v-if="pair" class="chip accent">{{ entName(pair.from) }} to {{ entName(pair.to) }}
            <button type="button" class="clear" aria-label="Clear the pair filter" @click="pair = null"><i class="pi pi-times" /></button>
          </span>
          <span class="small muted count">{{ fmtInt(rows.length) }} shown</span>
        </div>
        <MessageList :rows="rows" empty-text="No message matches these filters." />
      </section>
    </template>
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
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
}
.card > h2 {
  margin-bottom: 4px;
}
.card > .caption {
  margin-bottom: 10px;
}
.matrix {
  border-collapse: separate;
  border-spacing: 3px;
  font-size: var(--mm-fs-xs);
  min-width: 720px;
}
.matrix th {
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
  padding: 4px 6px;
  color: var(--mm-text-2);
}
.matrix thead th {
  vertical-align: bottom;
}
.matrix td {
  min-width: 64px;
  height: 32px;
  border-radius: 4px;
  background: var(--mm-panel-2);
  padding: 0;
}
.matrix td button {
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--mm-text);
  font: inherit;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  border-radius: 4px;
}
.matrix td button:hover,
.matrix td button.on {
  outline: 2px solid var(--mm-accent);
  outline-offset: -2px;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  margin-bottom: 10px;
}
.clear {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0 0 0 4px;
}
.clear i {
  font-size: 0.65rem;
}
.count {
  margin-left: auto;
}
.bad {
  color: var(--mm-bad);
}
</style>
