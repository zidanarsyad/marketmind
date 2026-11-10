<script setup lang="ts">
import MultiSelect from 'primevue/multiselect'
import { computed, onMounted, ref } from 'vue'
import { api, errorText } from '@/api'
import DataGrid from '@/components/DataGrid.vue'
import WorkflowGraph from '@/components/WorkflowGraph.vue'
import { useRunStore } from '@/stores/run'
import type { TraceEvent } from '@/types'

const run = useRunStore()
const meta = computed(() => run.meta!)

const roster = computed(() => {
  // the latest result per agent (an agent sent back for more work appears again)
  const results = new Map(Object.values(meta.value.agents ?? {}).map((r) => [r.agent, r]))
  return (meta.value.agent_roster ?? []).map((a) => {
    const r = results.get(a.name)
    return {
      name: a.name,
      role: a.role,
      ml: a.ml,
      status: r?.status ?? '',
      seconds: r?.seconds ?? null,
      tool_calls: r?.tool_calls ?? null,
      findings: r?.findings ?? null,
      llm_calls: r?.llm_calls ?? null,
      summary: r?.summary || r?.error || '',
    }
  })
})

const messages = computed(() => meta.value.messages ?? [])
const qaHistory = computed(() => meta.value.qa?.history ?? [])
const reviewSteps = computed(() => [
  ...(meta.value.approvals ?? []).map((a) => ({
    step: `approval: ${a.gate}`,
    decision: a.approved ? 'approved' : 'rejected',
    by: a.reviewer,
    detail: [a.drop?.length ? `removed ${a.drop.join(', ')}` : '', a.comment].filter(Boolean).join(', ') || '-',
  })),
  ...(meta.value.adaptations ?? []).map((a) => ({
    step: `follow-up: ${a.agent}`,
    decision: a.action,
    by: 'Research Director',
    detail: `${a.reason} -> ${a.outcome}`,
  })),
])
const llmRows = computed(() => {
  const l = meta.value.llm
  if (!l) return []
  return [
    { item: 'Provider', value: l.provider },
    { item: 'Model', value: l.model ?? '-' },
    { item: 'Used in this run', value: meta.value.options?.use_llm ? 'yes' : 'no (deterministic run)' },
    ...Object.entries(l.stats ?? {}).map(([k, v]) => ({ item: k.replace(/_/g, ' '), value: v })),
    ...(l.last_error ? [{ item: 'Last error', value: l.last_error }] : []),
  ]
})

// ---------------------------------------------------------------- trace explorer
const trace = ref<TraceEvent[]>([])
const traceError = ref('')
const who = ref<string[]>([])
const kinds = ref<string[]>([])
onMounted(async () => {
  try {
    trace.value = await api.trace(run.runId as string)
    const present = new Set(trace.value.map((e) => e.kind))
    kinds.value = ['thought', 'finding', 'action', 'warning', 'message'].filter((k) => present.has(k))
  } catch (e) {
    traceError.value = errorText(e)
  }
})
const agentOptions = computed(() => [...new Set(trace.value.map((e) => e.agent))].sort())
const kindOptions = computed(() => [...new Set(trace.value.map((e) => e.kind))].sort())
const traceRows = computed(() =>
  trace.value
    .filter((e) => (!who.value.length || who.value.includes(e.agent)) && (!kinds.value.length || kinds.value.includes(e.kind)))
    .map((e) => ({ time: e.time, agent: e.agent, kind: e.kind, message: e.message })),
)
</script>

<template>
  <div class="stack">
    <section class="card">
      <h2>How the agent team worked</h2>
      <WorkflowGraph
        v-if="meta.workflow?.layers?.length"
        :layers="meta.workflow.layers"
        :edges="meta.workflow.edges"
        :tasks="meta.workflow.tasks"
        :agents="meta.agents"
      />
      <p v-else class="empty">The study stopped before the workflow ran.</p>
    </section>

    <section class="card">
      <h3>The agents</h3>
      <DataGrid
        :columns="[
          { field: 'name', header: 'Agent', minWidth: '11rem' },
          { field: 'role', header: 'Role', minWidth: '18rem' },
          { field: 'ml', header: 'ML / DL capability', minWidth: '14rem' },
          'status',
          'seconds',
          { field: 'tool_calls', header: 'tool calls' },
          'findings',
          { field: 'llm_calls', header: 'LLM calls' },
          { field: 'summary', minWidth: '16rem' },
        ]"
        :rows="roster"
        scroll-height="480px"
      />
    </section>

    <div class="grid-2">
      <section class="card">
        <h3>Agent-to-agent messages</h3>
        <DataGrid v-if="messages.length" :columns="['sender', 'recipient', 'content']" :rows="messages" scroll-height="260px" />
        <p v-else class="empty">No messages (QA passed first time).</p>
        <h3 class="mt">QA history</h3>
        <DataGrid
          v-if="qaHistory.length"
          :columns="Object.keys(qaHistory[0])"
          :rows="qaHistory"
          scroll-height="200px"
        />
        <p v-else class="empty">The Critic did not run.</p>
        <h3 class="mt">Human review and follow-ups</h3>
        <DataGrid v-if="reviewSteps.length" :columns="['step', 'decision', 'by', 'detail']" :rows="reviewSteps" scroll-height="260px" />
        <p v-else class="empty">Not recorded for this run.</p>
      </section>
      <section class="card">
        <h3>LLM usage</h3>
        <DataGrid :columns="['item', 'value']" :rows="llmRows" scroll-height="none" :sortable="false" />
      </section>
    </div>

    <section class="card">
      <h3>Trace explorer</h3>
      <p v-if="traceError" class="caption">{{ traceError }}</p>
      <div class="filters">
        <MultiSelect v-model="who" :options="agentOptions" placeholder="All agents" display="chip" :max-selected-labels="2" filter class="filter" aria-label="Agents" />
        <MultiSelect v-model="kinds" :options="kindOptions" placeholder="All event kinds" display="chip" :max-selected-labels="3" class="filter" aria-label="Event kinds" />
        <span class="caption">{{ traceRows.length }} of {{ trace.length }} events</span>
      </div>
      <DataGrid
        :columns="[{ field: 'time', minWidth: '5rem' }, { field: 'agent', minWidth: '10rem' }, 'kind', { field: 'message', minWidth: '24rem' }]"
        :rows="traceRows"
        :paginate="50"
        scroll-height="520px"
      />
    </section>
  </div>
</template>

<style scoped>
.mt {
  margin-top: 18px;
  margin-bottom: 6px;
}
.card h3 {
  margin-bottom: 8px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.filter {
  flex: 1 1 240px;
  max-width: 420px;
}
</style>
