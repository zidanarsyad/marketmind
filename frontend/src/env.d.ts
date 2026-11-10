/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

// plotly.js ships no types for its prebuilt bundles; the app only uses these calls
declare module 'plotly.js-cartesian-dist-min' {
  const Plotly: {
    react(el: HTMLElement, data: unknown[], layout: Record<string, unknown>, config?: Record<string, unknown>): Promise<unknown>
    purge(el: HTMLElement): void
    Plots: { resize(el: HTMLElement): void }
  }
  export default Plotly
}
