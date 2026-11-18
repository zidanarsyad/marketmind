<script setup lang="ts">
// One enterprise as the Control Center sees it through its API: online or not, its mode and week, its agents, and
// the KPIs it reports. The link opens the enterprise's own dashboard (its own server) in a new window.
import { computed } from 'vue'
import { HEADLINE_KPIS, kpiLabel, kpiValue, SCENARIO_TITLES } from '../labels'
import type { EnterpriseRef, EnterpriseStatus } from '../types'
import NodeSeal from './NodeSeal.vue'

const props = defineProps<{ ent: EnterpriseRef; status?: EnterpriseStatus }>()
const online = computed(() => props.status?.online !== false && !!props.status)
const active = computed(() => props.status?.agents?.filter((a) => a.status === 'active').length ?? 0)
const lastAgent = computed(() =>
  [...(props.status?.agents ?? [])].filter((a) => a.last_action).sort((a, b) => (b.last_week ?? -1) - (a.last_week ?? -1))[0],
)
const kpis = computed(() =>
  (HEADLINE_KPIS[props.ent.key] ?? []).filter((k) => k !== 'profit_idr').slice(0, 2).map((k) => ({ key: k, value: props.status?.kpis?.[k] })),
)
</script>

<template>
  <article class="ent" :style="{ '--c': `var(--ent-${ent.key})` }">
    <header>
      <NodeSeal :name="ent.name" :size="30" color="var(--c)" />
      <div class="who">
        <strong>{{ ent.name }}</strong>
        <small>{{ ent.industry }}, {{ ent.city }}</small>
      </div>
      <span class="state" :class="{ off: !online }">{{ status ? (online ? 'online' : 'offline') : '…' }}</span>
    </header>
    <template v-if="online && status">
      <p class="mode small">
        <span class="chip" :class="status.mode === 'ecosystem' ? 'accent' : ''">{{ status.mode }}</span>
        {{ SCENARIO_TITLES[status.scenario] ?? status.scenario }}, {{ status.week > 0 ? `week ${status.week}` : 'setup' }}
      </p>
      <dl>
        <div>
          <dt>Profit</dt>
          <dd class="num">{{ kpiValue('profit_idr', status.kpis.profit_idr) }}</dd>
        </div>
        <div v-for="k in kpis" :key="k.key">
          <dt>{{ kpiLabel(k.key) }}</dt>
          <dd class="num">{{ kpiValue(k.key, k.value) }}</dd>
        </div>
      </dl>
      <p class="agents small muted">
        {{ active }} of {{ status.agents.length }} agents active<template v-if="lastAgent">; last: {{ lastAgent.title }}, “{{ lastAgent.last_action.replace(/_/g, ' ') }}”</template>
      </p>
    </template>
    <p v-else-if="status" class="small bad">The server at {{ ent.url }} does not answer ({{ status.error ?? 'no reply' }}).</p>
    <a class="open small" :href="ent.url" target="_blank" rel="noopener">Open its dashboard <i class="pi pi-external-link" /></a>
  </article>
</template>

<style scoped>
.ent {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px 12px;
  background: var(--mm-panel);
  border: 1px solid var(--mm-border);
  border-top: 3px solid var(--c);
  border-radius: var(--mm-radius);
  min-width: 0;
}
header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.who {
  flex: 1;
  min-width: 0;
}
.who strong {
  display: block;
  font-weight: 680;
  font-stretch: 108%;
  line-height: 1.2;
}
.who small {
  display: block;
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--mm-good);
}
.state.off {
  color: var(--mm-bad);
}
.mode {
  margin: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--mm-text-2);
}
dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin: 0;
}
dt {
  font-size: 0.72rem;
  color: var(--mm-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
dd {
  margin: 0;
  font-weight: 650;
  font-size: var(--mm-fs-sm);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.agents {
  margin: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.open {
  margin-top: auto;
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.open i {
  font-size: 0.7rem;
}
.bad {
  color: var(--mm-bad);
  margin: 0;
}
</style>
