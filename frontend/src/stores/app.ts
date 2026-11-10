// App-wide state: configuration, the saved runs and the studies running on the server.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, errorText } from '@/api'
import type { AppConfig, RunListItem, StudySnapshot } from '@/types'

export const useAppStore = defineStore('app', () => {
  const config = ref<AppConfig | null>(null)
  const configError = ref<string | null>(null)
  const runs = ref<RunListItem[]>([])
  const runsLoaded = ref(false)
  const runsError = ref<string | null>(null)
  const studies = ref<StudySnapshot[]>([])
  const drawerOpen = ref(false)

  /** A study running or paused at a gate on the server (one at a time), whichever tab started it. */
  const activeStudy = computed(
    () => studies.value.find((s) => s.state === 'running' || s.state === 'waiting' || s.state === 'starting') ?? null,
  )

  async function loadConfig() {
    try {
      config.value = await api.config()
      configError.value = null
    } catch (e) {
      configError.value = errorText(e)
    }
  }

  async function loadRuns() {
    try {
      runs.value = await api.runs()
      runsError.value = null
    } catch (e) {
      runsError.value = errorText(e)
    } finally {
      runsLoaded.value = true
    }
  }

  async function loadStudies() {
    try {
      const before = activeStudy.value?.id
      studies.value = await api.studies()
      // a study finished since the last look: its run is saved now
      if (before && !activeStudy.value) await loadRuns()
    } catch {
      /* the server is restarting; keep the last list */
    }
  }

  let timer: ReturnType<typeof setTimeout> | null = null
  /** Keep the studies list fresh: every 3 s while one runs, else every 15 s (to notice one started elsewhere). */
  function watchStudies() {
    if (timer) return
    const tick = async () => {
      await loadStudies()
      timer = setTimeout(tick, activeStudy.value ? 3000 : 15000)
    }
    void tick()
  }

  function upsertStudy(s: StudySnapshot) {
    const i = studies.value.findIndex((x) => x.id === s.id)
    if (i >= 0) studies.value.splice(i, 1, s)
    else studies.value.unshift(s)
  }

  return {
    config,
    configError,
    runs,
    runsLoaded,
    runsError,
    studies,
    drawerOpen,
    activeStudy,
    loadConfig,
    loadRuns,
    loadStudies,
    watchStudies,
    upsertStudy,
  }
})
