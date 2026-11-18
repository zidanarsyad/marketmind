import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import { type App as VueApp, createApp } from 'vue'
import '@fontsource-variable/archivo/wdth.css' // Archivo with its weight and width axes, served with the app (works offline)
import 'primeicons/primeicons.css'
import App from './App.vue'
import { detectNode } from './ecosystem/api'
import { initTheme } from './lib/theme'
import { MarketMindPreset } from './preset'
import { router } from './router'
import './styles/main.css'

initTheme()

// The same build serves the MarketMind research app (python -m api) and every node of the multi-enterprise ecosystem
// (python -m marketmind.ecosystem up): an enterprise's dashboard or the Global Control Center, each on its own port.
// The page asks its server which one it is.
async function boot() {
  const node = await detectNode()
  let app: VueApp
  let preset = MarketMindPreset
  if (node) {
    const eco = (await import('./ecosystem/app')).createEcoApp(node)
    app = eco.app
    preset = eco.preset
  } else {
    app = createApp(App).use(router)
  }
  app
    .use(createPinia())
    .use(PrimeVue, { theme: { preset, options: { darkModeSelector: '.app-dark', cssLayer: false } } })
    .use(ToastService)
    .directive('tooltip', Tooltip)
    .mount('#app')
}

void boot()
