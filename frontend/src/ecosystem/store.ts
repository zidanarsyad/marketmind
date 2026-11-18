// The state of an ecosystem page: one enterprise's live status and the signed-in role, or the Control Center's
// enterprises, runs and the run on screen.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { errorText } from '@/api'
import { controlApi, enterpriseApi } from './api'
import { loadRole, saveRole } from './poll'
import type { ControlNode, EnterpriseNode, EnterpriseStatus, Mode, RunRecord } from './types'

export const useEnterpriseStore = defineStore('enterprise', () => {
  const node = ref<EnterpriseNode | null>(null)
  const status = ref<EnterpriseStatus | null>(null)
  const error = ref('')
  const role = ref('')

  function init(n: EnterpriseNode) {
    node.value = n
    role.value = loadRole(n.key, n.roles[0]?.name ?? '')
    if (!n.roles.some((r) => r.name === role.value)) role.value = n.roles[0]?.name ?? ''
  }

  async function refresh() {
    try {
      status.value = await enterpriseApi.status()
      error.value = ''
    } catch (e) {
      error.value = errorText(e)
    }
  }

  function setRole(name: string) {
    role.value = name
    if (node.value) saveRole(node.value.key, name)
  }

  /** Changes whenever the simulation moves (a new run, mode or week): views reload their records on it. */
  const revision = computed(() => (status.value ? `${status.value.mode}|${status.value.scenario}|${status.value.week}` : ''))
  const roleInfo = computed(() => node.value?.roles.find((r) => r.name === role.value) ?? null)

  return { node, status, error, role, roleInfo, revision, init, refresh, setRole }
})

export const useControlStore = defineStore('control', () => {
  const node = ref<ControlNode | null>(null)
  const enterprises = ref<EnterpriseStatus[]>([])
  const enterprisesError = ref('')
  const runs = ref<RunRecord[]>([])
  const busy = ref<string | null>(null)
  const live = ref<RunRecord | null>(null)
  const selectedId = ref('')
  const run = ref<RunRecord | null>(null)
  const runError = ref('')
  const startError = ref('')
  let following = 0

  function init(n: ControlNode) {
    node.value = n
  }

  async function refreshEnterprises() {
    try {
      enterprises.value = (await controlApi.enterprises()).enterprises
      enterprisesError.value = ''
    } catch (e) {
      enterprisesError.value = errorText(e)
    }
  }

  async function refreshRuns() {
    try {
      const r = await controlApi.runs()
      runs.value = r.runs
      busy.value = r.busy
      if (r.busy && !following) void follow(r.busy)
      if (!selectedId.value) {
        const done = r.runs.find((x) => x.status === 'done')
        if (done) await select(done.id)
      }
    } catch (e) {
      runError.value = errorText(e)
    }
  }

  async function select(id: string) {
    if (!id) return
    selectedId.value = id
    if (run.value?.id === id && run.value.status !== 'running') return
    try {
      run.value = await controlApi.run(id)
      runError.value = ''
    } catch (e) {
      runError.value = errorText(e)
    }
  }

  /** Follow a running run's progress until it finishes, then show it. */
  async function follow(id: string) {
    const mine = ++following
    try {
      for (;;) {
        const rec = await controlApi.run(id)
        if (mine !== following) return
        live.value = rec
        if (rec.status !== 'running') break
        await new Promise((r) => setTimeout(r, 600))
      }
      busy.value = null
      await refreshRuns()
      selectedId.value = ''
      await select(id)
    } catch (e) {
      runError.value = errorText(e)
    } finally {
      if (mine === following) following = 0
    }
  }

  async function start(scenario: string, mode: Mode | 'compare', seed: number) {
    startError.value = ''
    try {
      const r = await controlApi.start(scenario, mode, seed)
      busy.value = r.id
      live.value = { id: r.id, scenario, title: scenario, mode, seed, status: 'running', started: Date.now() / 1000 }
      void follow(r.id)
      void refreshRuns()
    } catch (e) {
      startError.value = errorText(e)
    }
  }

  const ecosystem = computed(() => run.value?.results?.ecosystem ?? null)
  const local = computed(() => run.value?.results?.local ?? null)
  const enterpriseRefs = computed(() => node.value?.enterprises ?? [])

  return {
    node, enterprises, enterprisesError, runs, busy, live, selectedId, run, runError, startError,
    ecosystem, local, enterpriseRefs, init, refreshEnterprises, refreshRuns, select, start,
  }
})
