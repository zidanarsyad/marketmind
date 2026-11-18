import { onBeforeUnmount, onMounted } from 'vue'

/** Call ``fn`` now and then every ``ms`` while the page is on screen (a hidden tab does not poll the server). */
export function usePolling(fn: () => unknown, ms: number, immediate = true): void {
  let timer = 0
  const tick = () => {
    if (typeof document === 'undefined' || document.visibilityState === 'visible') void fn()
  }
  const onVisible = () => document.visibilityState === 'visible' && void fn()
  onMounted(() => {
    if (immediate) void fn()
    timer = window.setInterval(tick, ms)
    document.addEventListener('visibilitychange', onVisible)
  })
  onBeforeUnmount(() => {
    window.clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
  })
}

const KEY = (enterprise: string) => `eco-role-${enterprise}`

export function loadRole(enterprise: string, fallback: string): string {
  try {
    return localStorage.getItem(KEY(enterprise)) || fallback
  } catch {
    return fallback
  }
}

export function saveRole(enterprise: string, role: string): void {
  try {
    localStorage.setItem(KEY(enterprise), role)
  } catch {
    /* storage blocked: the role lasts until the page closes */
  }
}
