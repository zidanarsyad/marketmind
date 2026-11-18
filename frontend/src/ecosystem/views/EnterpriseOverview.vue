<script setup lang="ts">
// An enterprise's own dashboard: its KPIs, its agents at work, the enterprise model the course asks for
// (users and roles, modules, data, agents, protocol, governance), and exactly what it shares right now.
import { computed, ref, watch } from 'vue'
import KpiTiles from '@/components/KpiTiles.vue'
import { errorText } from '@/api'
import { enterpriseApi } from '../api'
import { HEADLINE_KPIS, kpiLabel, kpiValue } from '../labels'
import { useEnterpriseStore } from '../store'

const ent = useEnterpriseStore()
const node = computed(() => ent.node!)
const status = computed(() => ent.status)

const tiles = computed(() => {
  const k = status.value?.kpis ?? {}
  return (HEADLINE_KPIS[node.value.key] ?? Object.keys(k).slice(0, 6)).map((key) => ({ label: kpiLabel(key), value: kpiValue(key, k[key]), note: '' }))
})
const allKpis = computed(() => Object.entries(status.value?.kpis ?? {}))

const KIND_LABEL: Record<string, string> = {
  predictive: 'predictive model',
  planning: 'planning',
  negotiation: 'negotiation',
  operations: 'operations',
  monitoring: 'monitoring',
  service: 'service',
}
const agents = computed(() => status.value?.agents ?? [])

const shared = ref<{ partner: Record<string, unknown>; control: Record<string, unknown> } | null>(null)
const sharedError = ref('')
async function loadShared() {
  try {
    const [p, c] = await Promise.all([enterpriseApi.shared('partner'), enterpriseApi.shared('control')])
    shared.value = { partner: p.view, control: c.view }
    sharedError.value = ''
  } catch (e) {
    sharedError.value = errorText(e)
  }
}
watch(() => `${status.value?.mode}|${status.value?.scenario}|${Math.floor((status.value?.week ?? 0) / 4)}`, loadShared, { immediate: true })

const store = ref('')
void enterpriseApi.datasets(ent.role || '').then((d) => (store.value = d.store)).catch(() => {})

const json = (v: unknown) => JSON.stringify(v, null, 2)
const policy = (v: unknown) => (typeof v === 'number' ? (v < 1 && v > 0 ? `${(v * 100).toFixed(1)}%` : v.toLocaleString('en-US')) : String(v))
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>{{ node.name }}</h1>
      <p class="lede">{{ node.description }}</p>
      <p class="small muted">
        The case: the launch of the {{ node.product.name }} (Rp {{ node.product.price_idr.toLocaleString('en-US') }})
        through 12.12 and Ramadan 2027, from 23 November 2026, with five partners.
      </p>
    </header>

    <section aria-labelledby="kpi-title" class="stack-sm">
      <div class="section-title">
        <h2 id="kpi-title">Key figures</h2>
        <span class="hint">{{ status ? `${status.mode} intelligence, ${status.week > 0 ? `after week ${status.week}` : 'before the launch'}` : 'Loading…' }}</span>
      </div>
      <KpiTiles :tiles="tiles" />
      <details class="all-kpis">
        <summary class="small">Every figure this enterprise reports</summary>
        <table>
          <tbody>
            <tr v-for="[k, v] in allKpis" :key="k">
              <th scope="row">{{ kpiLabel(k) }}</th>
              <td class="num">{{ kpiValue(k, v) }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>

    <section aria-labelledby="agents-title">
      <div class="section-title">
        <h2 id="agents-title">Agents</h2>
        <span class="hint">{{ agents.filter((a) => a.status === 'active').length }} of {{ agents.length }} active in this run</span>
      </div>
      <div class="agents">
        <article v-for="a in agents" :key="a.name" class="agent" :class="{ active: a.status === 'active' }">
          <header>
            <strong>{{ a.title }}</strong>
            <span class="chip" :class="a.kind === 'predictive' || a.kind === 'planning' ? 'accent' : ''">{{ KIND_LABEL[a.kind] ?? a.kind }}</span>
          </header>
          <p class="small">{{ a.description }}</p>
          <p v-if="a.model" class="small muted model">Model: {{ a.model }}</p>
          <p class="small last">
            <span class="state" :class="a.status">{{ a.status }}</span>
            <template v-if="a.last_action">
              {{ a.last_week !== null && a.last_week > 0 ? `W${a.last_week}` : 'setup' }}: {{ a.last_action.replace(/_/g, ' ') }}
            </template>
            <template v-else>nothing yet</template>
          </p>
        </article>
      </div>
    </section>

    <section class="card" aria-labelledby="model-title">
      <h2 id="model-title">The enterprise, as a model</h2>
      <p class="caption">E = (U, M, D, A, P, G): who works here, its modules, its data, its agents, how it talks, and its rules.</p>
      <dl class="spec">
        <div>
          <dt><span class="stamp">U</span> Users and roles</dt>
          <dd>
            <ul>
              <li v-for="r in node.roles" :key="r.name"><b>{{ r.name }}</b>: {{ r.description }}<template v-if="r.can_approve">; approves contracts</template></li>
            </ul>
          </dd>
        </div>
        <div>
          <dt><span class="stamp">M</span> Modules</dt>
          <dd>
            <ul>
              <li v-for="m in node.modules" :key="m.module"><b>{{ m.module }}</b>: {{ m.description }}</li>
            </ul>
          </dd>
        </div>
        <div>
          <dt><span class="stamp">D</span> Data</dt>
          <dd>
            <p>{{ store || node.platform.database }}, on this server only.</p>
            <p v-if="node.governance.private_datasets.length" class="small muted">Never shared: {{ node.governance.private_datasets.join(', ') }}.</p>
            <RouterLink to="/data" class="small">Open the data explorer</RouterLink>
          </dd>
        </div>
        <div>
          <dt><span class="stamp">A</span> Agents</dt>
          <dd>
            <p>{{ agents.length }} agents: {{ [...new Set(agents.map((a) => KIND_LABEL[a.kind] ?? a.kind))].join(', ') }}.</p>
          </dd>
        </div>
        <div>
          <dt><span class="stamp">P</span> Protocol and platform</dt>
          <dd>
            <ul>
              <li v-for="(v, k) in node.platform" :key="k"><b>{{ String(k).replace(/_/g, ' ') }}</b>: {{ v }}</li>
              <li><b>A2A endpoint</b>: <code>POST /api/a2a/messages</code>, <a href="/.well-known/agent-card.json" target="_blank" rel="noopener">agent card</a></li>
            </ul>
          </dd>
        </div>
        <div>
          <dt><span class="stamp">G</span> Governance</dt>
          <dd>
            <ul>
              <li><b>Public</b>: {{ node.governance.public.join(', ') || 'nothing' }}</li>
              <li><b>With partners</b> (ecosystem only): {{ node.governance.shared_with_partners.join(', ') || 'nothing' }}</li>
              <li><b>With the Control Center</b> (ecosystem only): {{ node.governance.shared_with_control_center.join(', ') || 'nothing' }}</li>
              <li v-for="(v, k) in node.governance.policies" :key="k"><b>{{ String(k).replace(/_/g, ' ') }}</b>: {{ policy(v) }}</li>
              <li v-if="node.governance.approval_threshold_idr"><b>Approval above</b>: Rp {{ node.governance.approval_threshold_idr.toLocaleString('en-US') }}</li>
            </ul>
          </dd>
        </div>
      </dl>
    </section>

    <section class="card" aria-labelledby="shared-title">
      <h2 id="shared-title">What it shares right now</h2>
      <p class="caption">
        Read from its own API, as a partner and as the Control Center would.
        {{ status?.mode === 'local' ? 'With local intelligence only the public keys leave the enterprise.' : 'With ecosystem intelligence the partner and Control Center keys are added.' }}
      </p>
      <p v-if="sharedError" class="caption bad">{{ sharedError }}</p>
      <div v-if="shared" class="grid-2">
        <div>
          <h3>A partner sees</h3>
          <pre>{{ json(shared.partner) }}</pre>
        </div>
        <div>
          <h3>The Control Center sees</h3>
          <pre>{{ json(shared.control) }}</pre>
        </div>
      </div>
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
  font-size: var(--mm-fs-md);
}
.hero p {
  margin: 0;
}
.stack-sm {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.all-kpis summary {
  cursor: pointer;
  color: var(--mm-accent);
}
.all-kpis table {
  margin-top: 8px;
  border-collapse: collapse;
  font-size: var(--mm-fs-sm);
  min-width: min(100%, 420px);
}
.all-kpis th,
.all-kpis td {
  padding: 4px 12px 4px 0;
  border-bottom: 1px solid var(--mm-border);
  text-align: left;
  font-weight: 450;
}
.all-kpis .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.agents {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: 12px;
  margin-top: 10px;
}
.agent {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--mm-panel);
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius);
}
.agent.active {
  border-left: 3px solid var(--mm-accent);
}
.agent header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.agent strong {
  font-weight: 650;
  font-stretch: 104%;
}
.agent p {
  margin: 0;
}
.model {
  overflow-wrap: anywhere;
}
.last {
  color: var(--mm-text-2);
  margin-top: auto !important;
  padding-top: 4px;
}
.state {
  font-weight: 650;
  margin-right: 4px;
}
.state.active {
  color: var(--mm-accent);
}
.state.idle {
  color: var(--mm-muted);
}
dl.spec {
  margin: 12px 0 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
  gap: 14px 24px;
}
dl.spec dt {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 650;
  margin-bottom: 4px;
}
dl.spec dd {
  margin: 0;
  color: var(--mm-text-2);
  font-size: var(--mm-fs-sm);
}
dl.spec dd p {
  margin: 0 0 4px;
}
dl.spec ul {
  margin: 0;
  padding-left: 1.1rem;
}
dl.spec b {
  font-weight: 600;
  color: var(--mm-text);
}
h3 {
  font-size: var(--mm-fs-sm);
  margin: 8px 0 6px;
}
pre {
  margin: 0;
  padding: 10px 12px;
  max-height: 360px;
  overflow: auto;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius-sm);
  font-size: 0.78rem;
  line-height: 1.45;
}
.bad {
  color: var(--mm-bad);
}
</style>
