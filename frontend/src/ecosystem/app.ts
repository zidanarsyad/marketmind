// The page of an ecosystem node: the same bundle as the research app, dressed in the node's own colour and routes.
import { definePreset } from '@primeuix/themes'
import { createApp } from 'vue'
import { MarketMindPreset } from '@/preset'
import EcoApp from './EcoApp.vue'
import { applyIdentity, identityOf, rgba, scale } from './identity'
import { createEcoRouter } from './router'
import type { EcoNode } from './types'

export function createEcoApp(node: EcoNode) {
  const { accent, accent_dark: dark } = identityOf(node)
  applyIdentity(node, node.kind === 'control' ? node.enterprises : node.directory)
  document.title = node.kind === 'control' ? 'Global Agentic Control Center' : `${node.name}: ${node.industry}`
  const preset = definePreset(MarketMindPreset, {
    semantic: {
      primary: scale(accent, dark),
      colorScheme: {
        dark: { highlight: { background: rgba(dark, 0.16), focusBackground: rgba(dark, 0.24) } },
      },
    },
  })
  const app = createApp(EcoApp, { node }).use(createEcoRouter(node))
  return { app, preset }
}
