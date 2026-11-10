<script setup lang="ts">
import Button from 'primevue/button'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, errorText } from '@/api'
import { runDate } from '@/lib/format'
import { useAppStore } from '@/stores/app'
import BrandMark from './BrandMark.vue'
import RunStatus from './RunStatus.vue'
import ThemeToggle from './ThemeToggle.vue'

const app = useAppStore()
const route = useRoute()
const SHOWN = 12

const recent = computed(() => app.runs.slice(0, SHOWN))
// switching runs keeps the view you are on (Market stays Market)
const view = computed(() => (route.path.startsWith('/runs/') && typeof route.name === 'string' ? route.name : 'overview'))
const currentRun = computed(() => (route.path.startsWith('/runs/') ? String(route.params.id ?? '') : ''))

const pinging = ref(false)
const ping = ref<{ ok: boolean; message: string } | null>(null)
async function testLlm() {
  pinging.value = true
  ping.value = null
  try {
    ping.value = await api.pingLlm()
  } catch (e) {
    ping.value = { ok: false, message: errorText(e) }
  } finally {
    pinging.value = false
  }
}
</script>

<template>
  <nav class="sidebar">
    <RouterLink to="/" class="brand">
      <BrandMark :size="34" />
      <span>
        <strong>MarketMind</strong>
        <small>Multi-agent market research · Indonesian local skincare</small>
      </span>
    </RouterLink>

    <RouterLink v-slot="{ navigate }" to="/new" custom>
      <Button label="New study" icon="pi pi-plus" class="w-full" @click="navigate" />
    </RouterLink>

    <RouterLink
      v-if="app.activeStudy"
      :to="`/studies/${app.activeStudy.id}`"
      class="active-study"
      :class="{ waiting: app.activeStudy.state === 'waiting' }"
    >
      <span class="pulse" />
      <span>
        <strong>{{ app.activeStudy.state === 'waiting' ? 'Waiting for your approval' : 'Study running' }}</strong>
        <small>{{ app.activeStudy.client || 'Client from the brief' }} · run {{ app.activeStudy.id }}</small>
      </span>
      <i class="pi pi-angle-right" />
    </RouterLink>

    <div class="runs-head">
      <h3>Saved runs</h3>
      <RouterLink to="/runs" class="small">All {{ app.runs.length || '' }}</RouterLink>
    </div>
    <p v-if="app.runsError" class="caption">{{ app.runsError }}</p>
    <p v-else-if="app.runsLoaded && !app.runs.length" class="caption">No runs yet. Start a study to see results here.</p>
    <ul class="runs">
      <li v-for="r in recent" :key="r.run_id">
        <RouterLink :to="`/runs/${r.run_id}/${view}`" :class="{ current: r.run_id === currentRun }">
          <span class="run-main">
            <strong>{{ r.client || 'Unknown client' }}</strong>
            <small>{{ runDate(r.run_id, r.started) }}</small>
          </span>
          <RunStatus :status="r.status" :qa="r.qa_score" compact />
        </RouterLink>
      </li>
    </ul>

    <div class="footer">
      <p v-if="app.config?.data.kind === 'real'" class="caption">Data: real, from {{ app.config.data.source }}</p>
      <p v-else-if="app.config && !app.config.data.ready" class="caption warn">Datasets not found: generate them from New study.</p>
      <div class="llm">
        <span class="caption"><strong>LLM:</strong> {{ app.config?.llm.description ?? '…' }}</span>
        <Button
          v-if="app.config?.llm.available"
          label="Test LLM connection"
          size="small"
          severity="secondary"
          outlined
          :loading="pinging"
          @click="testLlm"
        />
        <p v-if="ping" class="caption" :class="ping.ok ? 'ok' : 'warn'">
          {{ ping.ok ? 'Connected' : 'Failed' }}: {{ ping.message.slice(0, 200) }}
        </p>
      </div>
      <ThemeToggle />
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 16px 20px;
  min-height: 100%;
}
.brand {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--mm-text);
  text-decoration: none;
  padding-right: 36px;
}
.brand strong {
  display: block;
  font-size: 1.12rem;
  letter-spacing: -0.01em;
}
.brand small {
  display: block;
  color: var(--mm-muted);
  font-size: 0.74rem;
  line-height: 1.3;
}
.w-full {
  width: 100%;
}
.active-study {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--mm-accent-soft);
  color: var(--mm-accent);
  text-decoration: none;
}
.active-study.waiting {
  background: var(--mm-warn-soft);
  color: var(--mm-warn);
}
.active-study span:nth-child(2) {
  flex: 1;
  min-width: 0;
}
.active-study strong {
  display: block;
  font-size: 0.86rem;
}
.active-study small {
  display: block;
  color: var(--mm-text-2);
  font-size: 0.74rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pulse {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}
.runs-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 4px;
}
.runs-head h3 {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--mm-muted);
  font-weight: 650;
}
.runs {
  list-style: none;
  margin: -6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.runs a {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 8px;
  color: var(--mm-text);
  text-decoration: none;
}
.runs a:hover {
  background: var(--mm-panel-2);
}
.runs a.current {
  background: var(--mm-accent-soft);
}
.run-main {
  flex: 1;
  min-width: 0;
}
.run-main strong {
  display: block;
  font-size: 0.88rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-main small {
  display: block;
  font-size: 0.74rem;
  color: var(--mm-muted);
}
.footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--mm-border);
}
.llm {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.llm .caption {
  overflow-wrap: anywhere;
}
.ok {
  color: var(--mm-good);
}
.warn {
  color: var(--mm-warn);
}
</style>
