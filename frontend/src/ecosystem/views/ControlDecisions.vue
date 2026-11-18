<script setup lang="ts">
// What changed in the environment and what the Control Center's own agents decided about it: the Environment
// announcing disruptions, the Coordinator planning, replanning and solving again after a rejection.
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import { computed, ref, watch } from 'vue'
import SeasonTimeline from '../components/SeasonTimeline.vue'
import { entName, weekLabel } from '../labels'
import { useControlStore } from '../store'
import type { Mode } from '../types'

const ctl = useControlStore()
const modes = computed(() => (['ecosystem', 'local'] as Mode[]).filter((m) => ctl.run?.results?.[m]))
const mode = ref<Mode>('ecosystem')
watch(modes, (ms) => {
  if (ms.length && !ms.includes(mode.value)) mode.value = ms[0]
}, { immediate: true })
const result = computed(() => ctl.run?.results?.[mode.value] ?? null)

const agent = ref<string | null>(null)
const agents = computed(() => [...new Set((result.value?.decisions ?? []).map((d) => d.agent))].map((a) => ({ value: a, label: a })))
const decisions = computed(() =>
  [...(result.value?.decisions ?? [])].filter((d) => !agent.value || d.agent === agent.value).reverse(),
)
const events = computed(() => result.value?.events ?? [])
const KIND: Record<string, string> = { disruption: 'bad', recovery: 'good', campaign: 'accent' }
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Decisions and events</h1>
      <p class="lede">
        The Control Center has three agents: the Environment announces what changes in the world, the Coordinator plans
        for the ecosystem, and the Monitor keeps this record. Each enterprise keeps its own decision log on its own server.
      </p>
    </header>

    <p v-if="!result" class="empty">Run a scenario first.</p>
    <template v-else>
      <SelectButton v-if="modes.length > 1" v-model="mode" :options="modes" :allow-empty="false" aria-label="Which run to read" />
      <section class="card">
        <h2>The season</h2>
        <SeasonTimeline
          :campaigns="ctl.node?.campaigns ?? []"
          :events="events"
          :plans="result.plans"
          :weekly="mode === 'local' ? { local: result.weekly } : { ecosystem: result.weekly }"
          :week-starts="ctl.node?.week_starts"
        />
      </section>

      <div class="grid-2">
        <section class="card">
          <h2>Events</h2>
          <p v-if="!events.length" class="empty">Nothing happened beyond the campaigns.</p>
          <ul class="log">
            <li v-for="(e, i) in events" :key="i">
              <span class="stamp">{{ weekLabel(e.week) }}</span>
              <div>
                <p><span class="chip" :class="KIND[e.kind]">{{ e.kind }}</span> <b>{{ e.title }}</b></p>
                <p v-if="e.kind === 'recovery'" class="small muted">{{ entName(e.target) }} is back to normal.</p>
                <p v-else class="small muted">{{ e.detail }}<template v-if="e.kind === 'disruption'"> Hits {{ entName(e.target) }}.</template></p>
              </div>
            </li>
          </ul>
        </section>

        <section class="card">
          <div class="head">
            <h2>Control Center decisions</h2>
            <Select v-model="agent" :options="agents" option-label="label" option-value="value" placeholder="Every agent" show-clear aria-label="Agent" />
          </div>
          <p v-if="!decisions.length" class="empty">No decision recorded.</p>
          <ul class="log">
            <li v-for="(d, i) in decisions" :key="i">
              <span class="stamp">{{ weekLabel(d.week) }}</span>
              <div>
                <p><span class="chip">{{ d.agent }}</span> <b>{{ d.decision }}</b></p>
                <p class="small muted">{{ d.reasoning }}</p>
              </div>
            </li>
          </ul>
        </section>
      </div>
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
.card > h2 {
  margin-bottom: 10px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.log {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 560px;
  overflow-y: auto;
}
.log li {
  display: grid;
  grid-template-columns: 3.4rem minmax(0, 1fr);
  gap: 10px;
  padding: 9px 0;
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
.log p {
  margin: 0;
}
.log b {
  font-weight: 620;
}
</style>
