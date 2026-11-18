// Each node of the ecosystem wears its own colour: an enterprise its identity colour, the Control Center a neutral ink,
// so that in the Control Center the six enterprise colours are the only hues on screen. The colours were validated as
// chart colours (light and dark) for every pair of enterprises that negotiate with each other (docs/ECOSYSTEM.md).
import type { EcoNode, EnterpriseRef } from './types'

export const CONTROL_IDENTITY = { accent: '#2f3b45', accent_dark: '#c3ced6' }

export function identityOf(node: EcoNode): { accent: string; accent_dark: string } {
  return node.kind === 'enterprise' ? { accent: node.accent, accent_dark: node.accent_dark } : CONTROL_IDENTITY
}

/** Two letters for the enterprise's seal: "Kirana Beauty" -> KB, "MaklonNusa" -> MN. */
export function initials(name: string): string {
  const caps = name.match(/[A-Z]/g) ?? []
  return (caps.length >= 2 ? caps.slice(0, 2).join('') : name.slice(0, 2)).toUpperCase()
}

function rgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]
}

function mix(a: string, b: string, t: number): string {
  const [x, y] = [rgb(a), rgb(b)]
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('')}`
}

export function rgba(hex: string, alpha: number): string {
  return `rgba(${rgb(hex).join(', ')}, ${alpha})`
}

/** A PrimeVue primary scale around the node's colour: 600 is the light-theme accent, 400 the dark-theme one. */
export function scale(accent: string, dark: string): Record<number, string> {
  return {
    50: mix(accent, '#ffffff', 0.92),
    100: mix(accent, '#ffffff', 0.84),
    200: mix(accent, '#ffffff', 0.66),
    300: mix(dark, '#ffffff', 0.32),
    400: dark,
    500: mix(dark, accent, 0.5),
    600: accent,
    700: mix(accent, '#000000', 0.18),
    800: mix(accent, '#000000', 0.34),
    900: mix(accent, '#000000', 0.5),
    950: mix(accent, '#000000', 0.68),
  }
}

/** The app's colour variables for this node, plus one variable per enterprise (--ent-kirana ...) for the views that
 * show several enterprises side by side. */
export function applyIdentity(node: EcoNode, enterprises: EnterpriseRef[] = []): void {
  const { accent, accent_dark: dark } = identityOf(node)
  const ents = (theme: 'light' | 'dark') =>
    enterprises.map((e) => `--ent-${e.key}: ${theme === 'light' ? e.accent : e.accent_dark};`).join(' ')
  const css = `
:root { --mm-accent: ${accent}; --mm-accent-strong: ${mix(accent, '#000000', 0.18)}; --mm-accent-soft: ${rgba(accent, 0.09)};
  --mm-attn: ${rgb(accent).join(', ')}; ${ents('light')} }
:root.app-dark { --mm-accent: ${dark}; --mm-accent-strong: ${mix(dark, '#ffffff', 0.32)}; --mm-accent-soft: ${rgba(dark, 0.14)};
  --mm-attn: ${rgb(dark).join(', ')}; ${ents('dark')} }`
  let el = document.getElementById('eco-identity') as HTMLStyleElement | null
  if (!el) {
    el = document.createElement('style')
    el.id = 'eco-identity'
    document.head.appendChild(el)
  }
  el.textContent = css
}

/** The colour a chart should draw an enterprise in, in the theme on screen now. */
export function entColor(key: string, fallback = '#5e716c'): string {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--ent-${key}`).trim()
  return v || fallback
}

export function cssVar(name: string, fallback = ''): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}
