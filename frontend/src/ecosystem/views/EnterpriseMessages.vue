<script setup lang="ts">
// Every message this enterprise's agents received and sent, from its own log (its own database).
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import { computed, ref, watch } from 'vue'
import { errorText } from '@/api'
import { fmtInt } from '@/lib/format'
import { enterpriseApi } from '../api'
import MessageList from '../components/MessageList.vue'
import { DISPLAY_ORDER, entName, entOf, taskLabel } from '../labels'
import { useEnterpriseStore } from '../store'
import type { EcoMessage } from '../types'

const ent = useEnterpriseStore()
const all = ref<EcoMessage[]>([])
const total = ref(0)
const error = ref('')
let timer = 0
async function load() {
  try {
    const r = await enterpriseApi.messages(2000)
    all.value = r.rows
    total.value = r.total
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  }
}
watch(() => ent.revision, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(load, 300)
}, { immediate: true })

const direction = ref<'all' | 'in' | 'out'>('all')
const dirs = [
  { label: 'Both ways', value: 'all' },
  { label: 'Received', value: 'in' },
  { label: 'Sent', value: 'out' },
]
const task = ref<string | null>(null)
const other = ref<string | null>(null)
const text = ref('')
const self = computed(() => ent.node?.key ?? '')
const tasks = computed(() => [...new Set(all.value.map((m) => m.task))].sort().map((t) => ({ value: t, label: taskLabel(t) })))
const others = [...DISPLAY_ORDER, 'control'].filter((k) => k !== self.value).map((k) => ({ value: k, label: entName(k) }))

const rows = computed(() => {
  const needle = text.value.trim().toLowerCase()
  return all.value.filter((m) => {
    if (direction.value !== 'all' && m.direction !== direction.value) return false
    if (task.value && m.task !== task.value) return false
    if (other.value && entOf(m.sender) !== other.value && entOf(m.receiver) !== other.value) return false
    if (needle && !`${m.message_id} ${m.sender} ${m.receiver} ${m.task} ${JSON.stringify(m.payload)}`.toLowerCase().includes(needle))
      return false
    return true
  })
})
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Messages</h1>
      <p class="lede">
        What {{ ent.node?.name }}'s agents received and sent through its A2A endpoint, newest first, as its own log keeps them.
      </p>
    </header>
    <section class="card">
      <div class="filters">
        <SelectButton v-model="direction" :options="dirs" option-label="label" option-value="value" :allow-empty="false" aria-label="Direction" />
        <Select v-model="other" :options="others" option-label="label" option-value="value" placeholder="Any counterpart" show-clear aria-label="Counterpart" />
        <Select v-model="task" :options="tasks" option-label="label" option-value="value" placeholder="Any task" show-clear filter aria-label="Task" />
        <InputText v-model="text" placeholder="Search ids and payloads" aria-label="Search messages" />
        <span class="small muted count">{{ fmtInt(rows.length) }} of {{ fmtInt(total) }}</span>
      </div>
      <p v-if="error" class="caption bad">{{ error }}</p>
      <MessageList :rows="rows" :self="self" empty-text="No message yet: the Control Center has not run a scenario since this server started." />
    </section>
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
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  margin-bottom: 10px;
}
.count {
  margin-left: auto;
}
.bad {
  color: var(--mm-bad);
}
</style>
