import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import { createApp } from 'vue'
import 'primeicons/primeicons.css'
import App from './App.vue'
import { initTheme } from './lib/theme'
import { MarketMindPreset } from './preset'
import { router } from './router'
import './styles/main.css'

initTheme()

createApp(App)
  .use(createPinia())
  .use(router)
  .use(PrimeVue, { theme: { preset: MarketMindPreset, options: { darkModeSelector: '.app-dark', cssLayer: false } } })
  .use(ToastService)
  .directive('tooltip', Tooltip)
  .mount('#app')
