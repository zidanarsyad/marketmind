<script setup lang="ts">
// The decisions this enterprise's agents made, newest first, each with its reasoning, the inputs it used, what it
// decided, and the messages it answered.
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'
import { errorText } from '@/api'
import { fmtInt } from '@/lib/format'
import { enterpriseApi } from '../api'
import { weekLabel } from '../labels'
import { useEnterpriseStore } from '../store'
import type { EnterpriseDecision } from '../types'

const ent = useEnterpriseStore()
const rows = ref<EnterpriseDecision[]>([])
const total = ref(0)
const error = ref('')
let timer = 0
async function load() {
  try {
    const r = await enterpriseApi.decisions(2000)
    rows.value = r.rows
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

const agentTitle = computed(() => Object.fromEntries((ent.status?.agents ?? []).map((a) => [a.name, a.title])))
const agent = ref<string | null>(null)
const agents = computed(() => [...new Set(rows.value.map((d) => d.agent))].map((a) => ({ value: a, label: agentTitle.value[a] ?? a })))
const shown = computed(() => rows.value.filter((d) => !agent.value || d.agent === agent.value))
const has = (o: Record<string, unknown> | undefined) => !!o && Object.keys(o).length > 0
const json = (v: unknown) => JSON.stringify(v, null, 2)
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Decisions</h1>
      <p class="lede">Every decision {{ ent.node?.name }}'s agents made in the current run, and why.</p>
    </header>
    <section class="card">
      <div class="filters">
        <Select v-model="agent" :options="agents" option-label="label" option-value="value" placeholder="Every agent" show-clear aria-label="Agent" />
        <span class="small muted count">{{ fmtInt(shown.length) }} of {{ fmtInt(total) }}</span>
      </div>
      <p v-if="error" class="caption bad">{{ error }}</p>
      <p v-else-if="!shown.length" class="empty">No decision yet: the Control Center has not run a scenario since this server started.</p>
      <ul class="log">
        <li v-for="(d, i) in shown" :key="i">
          <span class="stamp">{{ weekLabel(d.week) }}</span>
          <div class="body">
            <p><span class="chip">{{ agentTitle[d.agent] ?? d.agent }}</span> <b>{{ d.decision }}</b></p>
            <p class="small reason">{{ d.reasoning }}</p>
            <details v-if="has(d.inputs) || has(d.outputs) || d.messages?.length" class="more">
              <summary class="small">Inputs, outputs and messages</summary>
              <div class="grid-2">
                <div v-if="has(d.inputs)"><h4>Inputs</h4><pre>{{ json(d.inputs) }}</pre></div>
                <div v-if="has(d.outputs)"><h4>Decided</h4><pre>{{ json(d.outputs) }}</pre></div>
              </div>
              <p v-if="d.messages?.length" class="small muted refs">In answer to <span v-for="r in d.messages" :key="r" class="stamp">{{ r }}</span></p>
            </details>
          </div>
        </li>
      </ul>
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
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.count {
  margin-left: auto;
}
.log {
  list-style: none;
  margin: 0;
  padding: 0;
}
.log li {
  display: grid;
  grid-template-columns: 3.4rem minmax(0, 1fr);
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid var(--mm-border);
}
.log li:first-child {
  border-top: 0;
}
.log .stamp {
  justify-content: center;
  align-self: start;
  margin-top: 2px;
}
.body p {
  margin: 0;
}
.body b {
  font-weight: 620;
}
.reason {
  color: var(--mm-text-2);
  max-width: 90ch;
  margin-top: 2px !important;
}
.more summary {
  cursor: pointer;
  color: var(--mm-accent);
  margin-top: 4px;
}
.more h4 {
  font-size: var(--mm-fs-xs);
  margin: 8px 0 4px;
  color: var(--mm-text-2);
}
.more pre {
  margin: 0;
  padding: 8px 10px;
  max-height: 240px;
  overflow: auto;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius-sm);
  font-size: 0.76rem;
}
.refs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-top: 6px !important;
}
.bad {
  color: var(--mm-bad);
}
</style>
