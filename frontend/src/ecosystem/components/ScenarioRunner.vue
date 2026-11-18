<script setup lang="ts">
// Start a season: a scenario, local or ecosystem intelligence (or both, on the same customers), and a seed. The
// Control Center resets every enterprise through its API and plays the 16 weeks; the progress shows here.
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import { computed, ref } from 'vue'
import { entName } from '../labels'
import { useControlStore } from '../store'
import type { Mode } from '../types'

const ctl = useControlStore()
const scenario = ref('stress')
const mode = ref<Mode | 'compare'>('compare')
const seed = ref(7)
const modes = [
  { label: 'Compare both', value: 'compare' },
  { label: 'Local only', value: 'local' },
  { label: 'Ecosystem only', value: 'ecosystem' },
]
const chosen = computed(() => ctl.node?.scenarios.find((s) => s.key === scenario.value))
const offline = computed(() => ctl.enterprises.filter((e) => e.online === false).map((e) => e.name))
const running = computed(() => ctl.busy && ctl.live?.status === 'running' ? ctl.live : null)
const progress = computed(() => {
  const r = running.value
  if (!r?.progress) return 0
  const phases = r.mode === 'compare' ? 2 : 1
  const done = r.mode === 'compare' && r.progress.phase === 'ecosystem' ? 1 : 0
  return Math.round(((done * 16 + r.progress.week) / (phases * 16)) * 100)
})
const progressText = computed(() => {
  const r = running.value
  if (!r) return ''
  const phase = r.progress?.phase ?? r.phase
  const who = phase === 'ecosystem' ? 'ecosystem intelligence' : phase === 'local' ? 'local intelligence' : 'the enterprises'
  return r.progress?.week ? `Week ${r.progress.week} of 16 with ${who}` : `Resetting the enterprises for ${who}`
})

function run() {
  void ctl.start(scenario.value, mode.value, seed.value ?? 7)
}
</script>

<template>
  <section class="card runner" aria-labelledby="runner-title">
    <h2 id="runner-title">Run a scenario</h2>
    <div class="field">
      <label for="eco-scenario">Scenario</label>
      <Select v-model="scenario" input-id="eco-scenario" :options="ctl.node?.scenarios ?? []" option-label="title" option-value="key" class="w-full" />
      <p v-if="chosen" class="caption">{{ chosen.description }}</p>
      <ul v-if="chosen?.events.length" class="events">
        <li v-for="e in chosen.events" :key="e.key">
          <span class="stamp">W{{ e.start }}{{ e.end > e.start ? `–${e.end}` : '' }}</span>
          <span>{{ e.title }}</span>
          <span class="who"><i class="dot" :style="{ background: `var(--ent-${e.target})` }" />{{ entName(e.target) }}</span>
        </li>
      </ul>
    </div>
    <div class="field">
      <span id="eco-mode-label" class="label">Intelligence</span>
      <SelectButton v-model="mode" :options="modes" option-label="label" option-value="value" :allow-empty="false" aria-labelledby="eco-mode-label" />
    </div>
    <div class="row">
      <div class="field seed">
        <label for="eco-seed">Seed</label>
        <InputNumber v-model="seed" input-id="eco-seed" :min="0" :max="9999" :use-grouping="false" />
      </div>
      <Button
        label="Run scenario"
        icon="pi pi-play"
        :loading="!!ctl.busy"
        :disabled="!!ctl.busy || offline.length > 0"
        @click="run"
      />
    </div>
    <p v-if="offline.length" class="caption bad">Start every server first: {{ offline.join(', ') }} {{ offline.length > 1 ? 'are' : 'is' }} offline.</p>
    <p v-if="ctl.startError" class="caption bad">{{ ctl.startError }}</p>
    <div v-if="running" class="progress" aria-live="polite">
      <ProgressBar :value="progress" :show-value="false" style="height: 6px" />
      <span class="small">{{ running.id }}: {{ progressText }}</span>
    </div>
  </section>
</template>

<style scoped>
.runner {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.field label,
.field .label {
  font-size: var(--mm-fs-xs);
  font-weight: 600;
  color: var(--mm-text-2);
}
.w-full {
  width: 100%;
}
.events {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.events li {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: var(--mm-fs-sm);
}
.who {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.seed :deep(input) {
  width: 6.5rem;
}
.progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bad {
  color: var(--mm-bad);
}
</style>
