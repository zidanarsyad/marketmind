// Light / dark theme. The preference (system, light or dark) is kept in localStorage; "system" follows the OS.
// The `app-dark` class on <html> switches both the app's CSS variables and PrimeVue's dark tokens.
import { computed, ref, watch } from 'vue'

export type ThemePref = 'system' | 'light' | 'dark'
const KEY = 'mm-theme'

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

const media = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
const pref = ref<ThemePref>(readPref())
const systemDark = ref(media?.matches ?? false)
media?.addEventListener?.('change', (e) => (systemDark.value = e.matches))

const mode = computed<'light' | 'dark'>(() =>
  pref.value === 'dark' || (pref.value === 'system' && systemDark.value) ? 'dark' : 'light',
)

function apply() {
  if (typeof document !== 'undefined') document.documentElement.classList.toggle('app-dark', mode.value === 'dark')
}

export function setTheme(p: ThemePref) {
  pref.value = p
  try {
    if (p === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, p)
  } catch {
    /* storage blocked: the choice lasts until the page closes */
  }
  apply()
}

export function useTheme() {
  return { pref, mode, setTheme }
}

export function initTheme() {
  watch(mode, apply, { immediate: true })
}
