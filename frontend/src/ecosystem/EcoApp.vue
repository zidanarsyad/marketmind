<script setup lang="ts">
// The frame of an ecosystem page (an enterprise's dashboard or the Control Center): the same layout as the research
// app, a sidebar on a desk, a drawer and a top bar on a phone.
import Button from 'primevue/button'
import Drawer from 'primevue/drawer'
import Toast from 'primevue/toast'
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import ThemeToggle from '@/components/ThemeToggle.vue'
import EcoSidebar from './components/EcoSidebar.vue'
import NodeSeal from './components/NodeSeal.vue'
import { usePolling } from './poll'
import { useControlStore, useEnterpriseStore } from './store'
import type { EcoNode } from './types'

const props = defineProps<{ node: EcoNode }>()
const drawerOpen = ref(false)
const route = useRoute()
watch(
  () => route.fullPath,
  () => (drawerOpen.value = false),
)

if (props.node.kind === 'enterprise') {
  const ent = useEnterpriseStore()
  ent.init(props.node)
  usePolling(ent.refresh, 2500)
} else {
  const ctl = useControlStore()
  ctl.init(props.node)
  usePolling(ctl.refreshEnterprises, 4000)
  usePolling(ctl.refreshRuns, 5000)
}
</script>

<template>
  <div class="shell">
    <aside class="shell-sidebar" aria-label="Navigation">
      <EcoSidebar :node="node" />
    </aside>

    <Drawer v-model:visible="drawerOpen" class="mm-drawer" aria-label="Navigation">
      <template #container="{ closeCallback }">
        <div class="drawer-inner">
          <Button class="drawer-close" icon="pi pi-times" text rounded severity="secondary" aria-label="Close the menu" @click="closeCallback" />
          <EcoSidebar :node="node" />
        </div>
      </template>
    </Drawer>

    <div class="shell-main">
      <header class="topbar">
        <Button icon="pi pi-bars" text rounded severity="secondary" aria-label="Open the menu" @click="drawerOpen = true" />
        <RouterLink to="/" class="topbar-brand">
          <NodeSeal v-if="node.kind === 'enterprise'" :name="node.name" :size="26" />
          <NodeSeal v-else control :size="26" />
          <span>{{ node.kind === 'enterprise' ? node.name : 'Control Center' }}</span>
        </RouterLink>
        <span class="spacer" />
        <ThemeToggle compact />
      </header>
      <main id="content">
        <RouterView />
      </main>
    </div>
    <Toast position="bottom-right" />
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  min-height: 100dvh;
}
.shell-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--mm-sidebar);
  border-right: 1px solid var(--mm-border);
  background: var(--mm-panel);
  overflow-y: auto;
  z-index: 10;
}
.shell-main {
  margin-left: var(--mm-sidebar);
  min-width: 0;
  overflow-x: clip;
}
.topbar {
  display: none;
}
.drawer-inner {
  position: relative;
  height: 100%;
  overflow-y: auto;
}
.drawer-close {
  position: absolute !important;
  top: 10px;
  right: 8px;
  z-index: 2;
}
@media (max-width: 1023px) {
  .shell-sidebar {
    display: none;
  }
  .shell-main {
    margin-left: 0;
  }
  .topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    padding-top: max(6px, env(safe-area-inset-top));
    background: color-mix(in srgb, var(--mm-panel) 92%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--mm-border);
  }
  .topbar-brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 650;
    color: var(--mm-text);
    text-decoration: none;
  }
  .spacer {
    flex: 1;
  }
}
</style>

<style>
.mm-drawer.p-drawer {
  width: min(320px, 88vw) !important;
  background: var(--mm-panel);
}
</style>
