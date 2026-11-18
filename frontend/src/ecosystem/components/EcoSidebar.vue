<script setup lang="ts">
import Select from 'primevue/select'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { byChain, SCENARIO_TITLES } from '../labels'
import { CONTROL_NAV, ENTERPRISE_NAV } from '../router'
import { useControlStore, useEnterpriseStore } from '../store'
import type { EcoNode } from '../types'
import NodeSeal from './NodeSeal.vue'

const props = defineProps<{ node: EcoNode }>()
const isEnterprise = computed(() => props.node.kind === 'enterprise')
const nav = computed(() => (isEnterprise.value ? ENTERPRISE_NAV : CONTROL_NAV))

const ent = useEnterpriseStore()
const ctl = useControlStore()

const role = computed({
  get: () => ent.role,
  set: (v: string) => ent.setRole(v),
})
const peers = computed(() => {
  const n = props.node
  return n.kind === 'enterprise' ? byChain(n.directory.filter((d) => d.key !== n.key)) : []
})
const online = computed(() => Object.fromEntries(ctl.enterprises.map((e) => [e.key, e.online !== false])))
const controlEnterprises = computed(() => (props.node.kind === 'control' ? byChain(props.node.enterprises) : []))
const recentRuns = computed(() => ctl.runs.slice(0, 8))
</script>

<template>
  <nav class="sidebar">
    <RouterLink to="/" class="brand">
      <NodeSeal v-if="node.kind === 'enterprise'" :name="node.name" />
      <NodeSeal v-else control />
      <span v-if="node.kind === 'enterprise'">
        <strong>{{ node.name }}</strong>
        <small>{{ node.industry }}, {{ node.city }}</small>
      </span>
      <span v-else>
        <strong>Control Center</strong>
        <small>Global agentic coordination of the six enterprises</small>
      </span>
    </RouterLink>

    <div v-if="node.kind === 'enterprise'" class="signin">
      <label for="eco-role">Signed in as</label>
      <Select v-model="role" input-id="eco-role" :options="node.roles" option-label="name" option-value="name" class="w-full" />
      <small v-if="ent.roleInfo">
        {{ ent.roleInfo.description }}{{ ent.roleInfo.can_approve ? '; approves contracts' : '' }}
      </small>
    </div>

    <ul class="nav">
      <li v-for="n in nav" :key="n.name">
        <RouterLink :to="n.path" exact-active-class="current"><i :class="n.icon" />{{ n.label }}</RouterLink>
      </li>
    </ul>

    <div v-if="node.kind === 'enterprise'" class="state" aria-live="polite">
      <template v-if="ent.status">
        <span class="chip" :class="ent.status.mode === 'ecosystem' ? 'accent' : ''">
          {{ ent.status.mode === 'ecosystem' ? 'Ecosystem intelligence' : 'Local intelligence' }}
        </span>
        <span class="small">{{ SCENARIO_TITLES[ent.status.scenario] ?? ent.status.scenario }}</span>
        <span class="small muted">{{ ent.status.week > 0 ? `Week ${ent.status.week} of 16` : 'Before the launch' }}</span>
      </template>
      <span v-else-if="ent.error" class="small bad">Server not reachable: {{ ent.error }}</span>
    </div>

    <div v-if="node.kind === 'control'" class="block">
      <h3>Runs</h3>
      <p v-if="!ctl.runs.length" class="caption">No run yet: start one from the overview.</p>
      <ul class="runs">
        <li v-for="r in recentRuns" :key="r.id">
          <button type="button" :class="{ current: r.id === ctl.selectedId }" :disabled="r.status !== 'done'" @click="ctl.select(r.id)">
            <span class="run-main">
              <strong>{{ r.title }}</strong>
              <small>{{ r.id }}, {{ r.mode === 'compare' ? 'local vs ecosystem' : r.mode }}, seed {{ r.seed }}</small>
            </span>
            <span v-if="r.status === 'running'" class="chip warn">playing</span>
            <span v-else-if="r.status === 'failed'" class="chip bad">failed</span>
          </button>
        </li>
      </ul>
    </div>

    <div class="block">
      <h3>{{ node.kind === 'enterprise' ? 'The ecosystem' : 'Enterprises' }}</h3>
      <ul class="links">
        <li v-if="node.kind === 'enterprise'">
          <a :href="node.control_center" target="_blank" rel="noopener"><NodeSeal control :size="16" color="var(--mm-text-2)" />Control Center</a>
        </li>
        <li v-for="d in peers" :key="d.key">
          <a :href="d.url" target="_blank" rel="noopener"><i class="dot" :style="{ background: `var(--ent-${d.key})` }" />{{ d.name }}</a>
        </li>
        <li v-for="e in controlEnterprises" :key="e.key">
          <a :href="e.url" target="_blank" rel="noopener">
            <i class="dot" :style="{ background: `var(--ent-${e.key})` }" />{{ e.name }}
            <span v-if="ctl.enterprises.length" class="online" :class="{ off: !online[e.key] }">{{ online[e.key] ? 'online' : 'offline' }}</span>
          </a>
        </li>
      </ul>
    </div>

    <div class="footer">
      <p class="caption">
        <template v-if="node.kind === 'enterprise'">
          <a href="/.well-known/agent-card.json" target="_blank" rel="noopener">Agent card</a> and
        </template>
        <a href="/api/docs" target="_blank" rel="noopener">API reference</a> of this server
      </p>
      <ThemeToggle />
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px 16px;
  min-height: 100%;
}
.brand {
  display: flex;
  gap: 11px;
  align-items: center;
  color: var(--mm-text);
  text-decoration: none;
  padding-right: 36px;
}
.brand:hover {
  text-decoration: none;
}
.brand strong {
  display: block;
  font-size: 1.14rem;
  font-weight: 760;
  font-stretch: 116%;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.brand small {
  display: block;
  color: var(--mm-muted);
  font-size: 0.74rem;
  line-height: 1.35;
  margin-top: 2px;
}
.w-full {
  width: 100%;
}
.signin {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px 12px 12px;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius);
}
.signin label {
  font-size: var(--mm-fs-xs);
  font-weight: 600;
  color: var(--mm-text-2);
}
.signin small {
  color: var(--mm-muted);
  font-size: 0.74rem;
  line-height: 1.35;
}
.nav,
.runs,
.links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.nav a {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 8px 12px;
  border-radius: var(--mm-radius-sm);
  color: var(--mm-text);
  font-weight: 540;
  text-decoration: none;
}
.nav a i {
  color: var(--mm-muted);
  font-size: 0.9rem;
  width: 1rem;
}
.nav a:hover {
  background: var(--mm-panel-2);
}
.nav a.current,
.runs button.current {
  background: var(--mm-accent-soft);
}
.nav a.current i {
  color: var(--mm-accent);
}
.nav a.current::before,
.runs button.current::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--mm-accent);
}
.state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
}
.block h3 {
  font-size: var(--mm-fs-sm);
  font-weight: 650;
  font-stretch: 104%;
  color: var(--mm-text-2);
  margin-bottom: 6px;
}
.runs button {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px 7px 12px;
  border: 0;
  border-radius: var(--mm-radius-sm);
  background: transparent;
  color: var(--mm-text);
  text-align: left;
  cursor: pointer;
}
.runs button:hover:not(:disabled) {
  background: var(--mm-panel-2);
}
.runs button:disabled {
  cursor: default;
}
.run-main {
  flex: 1;
  min-width: 0;
}
.run-main strong {
  display: block;
  font-size: 0.86rem;
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
.links a {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 10px 5px 12px;
  border-radius: var(--mm-radius-sm);
  color: var(--mm-text);
  font-size: var(--mm-fs-sm);
}
.links a:hover {
  background: var(--mm-panel-2);
  text-decoration: none;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: none;
}
.online {
  margin-left: auto;
  font-size: 0.72rem;
  color: var(--mm-good);
}
.online.off {
  color: var(--mm-bad);
}
.bad {
  color: var(--mm-bad);
}
.footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--mm-border);
}
</style>
