<script setup lang="ts">
// A study as it runs: each agent's status, the live trace (thoughts, tool calls, findings) streamed over SSE, and the
// approval form whenever the study waits at a gate. The study lives on the server: reloading this page, or opening it
// in another tab, picks it up again, gate included.
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ApiError, api, errorText } from '@/api'
import ApprovalForm from '@/components/ApprovalForm.vue'
import { seconds } from '@/lib/format'
import { useAppStore } from '@/stores/app'
import type { Decision, StudySnapshot, TraceEvent } from '@/types'

const props = defineProps<{ id: string }>()
const app = useAppStore()
const router = useRouter()
const toast = useToast()

const snapshot = ref<StudySnapshot | null>(null)
const events = ref<TraceEvent[]>([])
const connection = ref<'connecting' | 'open' | 'lost' | 'closed'>('connecting')
const missing = ref(false)
const deciding = ref(false)
const decideError = ref('')
const now = ref(Date.now() / 1000)
const feed = ref<HTMLElement>()
let es: EventSource | null = null
let clock: ReturnType<typeof setInterval> | null = null
let sawRunning = false

const FINAL = ['completed', 'unverified', 'failed', 'rejected', 'error']
const FEED_KINDS = ['thought', 'action', 'finding', 'message', 'warning', 'error', 'llm', 'approval']
const STATUS: Record<string, { text: string; icon: string; cls: string }> = {
  started: { text: 'running', icon: 'pi pi-spin pi-spinner', cls: 'accent' },
  completed: { text: 'done', icon: 'pi pi-check', cls: 'good' },
  failed: { text: 'failed', icon: 'pi pi-times', cls: 'bad' },
  skipped: { text: 'skipped', icon: 'pi pi-minus', cls: '' },
}

function connect() {
  es?.close()
  events.value = [] // a new stream replays every event from the start
  connection.value = 'connecting'
  es = new EventSource(api.eventsUrl(props.id))
  es.onopen = () => (connection.value = 'open')
  es.addEventListener('trace', (e) => {
    events.value.push(JSON.parse((e as MessageEvent).data))
    void follow()
  })
  es.addEventListener('state', (e) => update(JSON.parse((e as MessageEvent).data)))
  es.addEventListener('end', (e) => {
    es?.close()
    connection.value = 'closed'
    update(JSON.parse((e as MessageEvent).data))
    void finished()
  })
  es.onerror = async () => {
    if (!es || es.readyState !== EventSource.CLOSED) {
      connection.value = 'lost' // the browser retries on its own, resuming after the last event it had
      return
    }
    connection.value = 'closed'
    try {
      update(await api.study(props.id))
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) missing.value = true
    }
  }
}

function update(s: StudySnapshot) {
  snapshot.value = s
  app.upsertStudy(s)
  if (!FINAL.includes(s.state)) sawRunning = true
}

async function finished() {
  const s = snapshot.value
  if (!s) return
  await app.loadRuns()
  if (!sawRunning) return // opened after the study had ended: stay and show how it ended
  if (s.saved && s.state !== 'failed' && s.state !== 'error') {
    const qa = s.result?.qa_score !== null && s.result?.qa_score !== undefined ? ` · QA ${s.result.qa_score}/100` : ''
    toast.add({ severity: s.state === 'rejected' ? 'warn' : 'success', summary: `Study ${s.state}`, detail: `Run ${s.id}${qa}`, life: 5000 })
    await router.push(`/runs/${s.id}/overview`)
  }
}

async function decide(d: Decision) {
  deciding.value = true
  decideError.value = ''
  try {
    await api.decide(props.id, d)
    if (snapshot.value) snapshot.value = { ...snapshot.value, pending: null, state: 'running' }
    toast.add({
      severity: d.approved ? 'success' : 'warn',
      summary: d.approved ? `${d.gate === 'plan' ? 'Plan' : 'Recommendations'} approved` : 'Study rejected',
      detail: d.approved ? (d.drop.length ? `Left out: ${d.drop.join(', ')}` : 'The agents carry on.') : 'The study stops here.',
      life: 4000,
    })
  } catch (e) {
    decideError.value = errorText(e)
  } finally {
    deciding.value = false
  }
}

const agents = computed(() => {
  const status = new Map<string, string>()
  const secs = new Map<string, number>()
  for (const e of events.value) {
    if (e.kind !== 'status' || e.agent === 'System') continue
    status.set(e.agent, e.message)
    if (typeof e.data?.seconds === 'number') secs.set(e.agent, e.data.seconds)
  }
  return [...status].map(([agent, s]) => ({ agent, ...(STATUS[s] ?? { text: s, icon: 'pi pi-circle', cls: '' }), seconds: secs.get(agent) }))
})
const feedEvents = computed(() => events.value.filter((e) => FEED_KINDS.includes(e.kind)).slice(-200))
const state = computed(() => snapshot.value?.state ?? 'starting')
const elapsed = computed(() => {
  const s = snapshot.value
  if (!s) return ''
  return seconds((s.finished ?? now.value) - s.created)
})
const headline = computed(() => {
  const s = snapshot.value
  switch (state.value) {
    case 'waiting':
      return 'Waiting for your approval'
    case 'running':
    case 'starting':
      return 'The agent team is working…'
    case 'error':
      return `The study failed: ${s?.error ?? 'unknown error'}`
    default:
      return `Run ${state.value}` + (s?.result ? ` in ${seconds(s.result.seconds)}` : '')
  }
})

async function follow() {
  const el = feed.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  await nextTick()
  if (atBottom) el.scrollTop = el.scrollHeight
}

onMounted(() => {
  connect()
  clock = setInterval(() => (now.value = Date.now() / 1000), 1000)
})
watch(
  () => props.id,
  () => {
    sawRunning = false
    missing.value = false
    connect()
  },
)
onBeforeUnmount(() => {
  es?.close()
  if (clock) clearInterval(clock)
})
</script>

<template>
  <div class="page stack">
    <Message v-if="missing" severity="warn">
      This study is not running on the server (it may have restarted). If it had finished, its run is under
      <RouterLink to="/runs">Saved runs</RouterLink>.
    </Message>

    <template v-else>
      <header class="head">
        <div class="title">
          <ProgressSpinner v-if="state === 'running' || state === 'starting'" style="width: 26px; height: 26px" stroke-width="6" />
          <i v-else-if="state === 'waiting'" class="pi pi-pause-circle big warn" />
          <i v-else-if="state === 'completed' || state === 'unverified'" class="pi pi-check-circle big good" />
          <i v-else class="pi pi-times-circle big bad" />
          <div>
            <h1>{{ headline }}</h1>
            <p class="caption">
              Run {{ id }}<template v-if="snapshot?.client"> · {{ snapshot.client }}</template>
              <template v-if="elapsed"> · {{ elapsed }}</template>
              <template v-if="snapshot?.review"> · you review the plan and recommendations</template>
              <template v-if="connection === 'lost'"> · reconnecting…</template>
            </p>
          </div>
        </div>
        <div v-if="snapshot && FINAL.includes(state)" class="done-actions">
          <RouterLink v-if="snapshot.saved" v-slot="{ navigate }" :to="`/runs/${id}/overview`" custom>
            <Button label="Open the results" icon="pi pi-arrow-right" icon-pos="right" @click="navigate" />
          </RouterLink>
          <RouterLink v-slot="{ navigate }" to="/new" custom>
            <Button label="New study" icon="pi pi-plus" severity="secondary" outlined @click="navigate" />
          </RouterLink>
        </div>
      </header>

      <ApprovalForm v-if="snapshot?.pending" :pending="snapshot.pending" :busy="deciding" :error="decideError" @decide="decide" />

      <div class="live">
        <section class="card">
          <h3>Agent status</h3>
          <p v-if="!agents.length" class="empty">Starting…</p>
          <ul class="agents">
            <li v-for="a in agents" :key="a.agent">
              <span class="name">{{ a.agent }}</span>
              <span class="chip" :class="a.cls"><i :class="a.icon" style="font-size: 0.7rem" />{{ a.text }}</span>
              <span class="secs">{{ a.seconds !== undefined ? `${a.seconds}s` : '' }}</span>
            </li>
          </ul>
        </section>
        <section class="card">
          <h3>Live trace <span class="caption">thoughts, tool calls, findings</span></h3>
          <ol ref="feed" class="feed" aria-live="polite">
            <li v-for="(e, i) in feedEvents" :key="i" :class="e.kind">
              <time>{{ e.time }}</time>
              <strong>{{ e.agent }}</strong>
              <span class="kind">{{ e.kind }}</span>
              <span class="msg">{{ e.message.length > 320 ? `${e.message.slice(0, 320)}…` : e.message }}</span>
            </li>
            <li v-if="!feedEvents.length" class="empty">Waiting for the first events…</li>
          </ol>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
.title {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.title h1 {
  font-size: 1.35rem;
}
.big {
  font-size: 1.6rem;
}
.good {
  color: var(--mm-good);
}
.bad {
  color: var(--mm-bad);
}
.warn {
  color: var(--mm-warn);
}
.done-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.live {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr);
  gap: 16px;
  align-items: start;
}
.card h3 {
  margin-bottom: 8px;
}
.agents {
  list-style: none;
  margin: 0;
  padding: 0;
}
.agents li {
  display: grid;
  grid-template-columns: 1fr auto 3.5rem;
  gap: 10px;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid var(--mm-border);
  font-size: 0.9rem;
}
.agents li:last-child {
  border-bottom: 0;
}
.secs {
  text-align: right;
  color: var(--mm-muted);
  font-variant-numeric: tabular-nums;
  font-size: 0.82rem;
}
.feed {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 560px;
  overflow-y: auto;
  font-size: 0.86rem;
}
.feed li {
  padding: 6px 2px;
  border-bottom: 1px solid var(--mm-border);
  overflow-wrap: anywhere;
}
.feed time {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.78rem;
  color: var(--mm-muted);
  margin-right: 8px;
}
.feed .kind {
  font-size: 0.72rem;
  color: var(--mm-muted);
  border: 1px solid var(--mm-border-strong);
  border-radius: 999px;
  padding: 0 6px;
  margin: 0 6px;
}
.feed .msg {
  color: var(--mm-text-2);
}
.feed .finding .kind {
  color: var(--mm-accent);
  border-color: var(--mm-accent);
}
.feed .warning .kind,
.feed .approval .kind {
  color: var(--mm-warn);
  border-color: var(--mm-warn);
}
.feed .error .kind {
  color: var(--mm-bad);
  border-color: var(--mm-bad);
}
@media (max-width: 900px) {
  .live {
    grid-template-columns: minmax(0, 1fr);
  }
  .feed {
    max-height: 420px;
  }
}
</style>
