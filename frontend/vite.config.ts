/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// `npm run dev` serves the app on http://localhost:5173 and forwards /api to the FastAPI server (python -m api).
// The Host header is passed through unchanged, so the API's local-only check sees "localhost".
const apiTarget = process.env.MARKETMIND_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: 'localhost',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: false } },
  },
  build: {
    chunkSizeWarningLimit: 1600, // plotly.js (cartesian bundle) is loaded on demand in its own chunk
  },
  optimizeDeps: {
    // pre-bundled up front, so the dev server does not reload the page the first time a view needs one of them
    include: [
      'plotly.js-cartesian-dist-min',
      'markdown-it',
      ...[
        'accordion', 'accordioncontent', 'accordionheader', 'accordionpanel', 'button', 'checkbox', 'column', 'config',
        'datatable', 'drawer', 'iconfield', 'inputicon', 'inputtext', 'message', 'multiselect', 'panel',
        'progressspinner', 'select', 'selectbutton', 'skeleton', 'slider', 'textarea', 'toast', 'toastservice',
        'toggleswitch', 'tooltip', 'usetoast',
      ].map((c) => `primevue/${c}`),
    ],
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['src/test-setup.ts'],
  },
})
