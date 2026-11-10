<script setup lang="ts">
import Button from 'primevue/button'
import Drawer from 'primevue/drawer'
import Toast from 'primevue/toast'
import { onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import BrandMark from './components/BrandMark.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import { useAppStore } from './stores/app'

const app = useAppStore()
const route = useRoute()

onMounted(() => {
  void app.loadConfig()
  void app.loadRuns()
  app.watchStudies()
})

// the drawer closes once a link in it has been followed
watch(
  () => route.fullPath,
  () => (app.drawerOpen = false),
)
</script>

<template>
  <div class="shell">
    <aside class="shell-sidebar" aria-label="Navigation">
      <AppSidebar />
    </aside>

    <Drawer v-model:visible="app.drawerOpen" class="mm-drawer" :show-close-icon="true" aria-label="Navigation">
      <template #container="{ closeCallback }">
        <div class="drawer-inner">
          <Button
            class="drawer-close"
            icon="pi pi-times"
            text
            rounded
            severity="secondary"
            aria-label="Close the menu"
            @click="closeCallback"
          />
          <AppSidebar />
        </div>
      </template>
    </Drawer>

    <div class="shell-main">
      <header class="topbar">
        <Button icon="pi pi-bars" text rounded severity="secondary" aria-label="Open the menu" @click="app.drawerOpen = true" />
        <RouterLink to="/" class="topbar-brand"><BrandMark :size="26" /><span>MarketMind</span></RouterLink>
        <span class="spacer" />
        <RouterLink
          v-if="app.activeStudy"
          :to="`/studies/${app.activeStudy.id}`"
          class="topbar-study"
          :class="{ waiting: app.activeStudy.state === 'waiting' }"
          :aria-label="app.activeStudy.state === 'waiting' ? 'A study waits for your approval' : 'A study is running'"
        >
          <span class="pulse" />{{ app.activeStudy.state === 'waiting' ? 'Approve' : 'Running' }}
        </RouterLink>
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
  .topbar-study {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--mm-accent-soft);
    color: var(--mm-accent);
    text-decoration: none;
  }
  .topbar-study.waiting {
    background: var(--mm-warn-soft);
    color: var(--mm-warn);
  }
}
.pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}
</style>

<style>
.mm-drawer.p-drawer {
  width: min(320px, 88vw) !important;
  background: var(--mm-panel);
}
</style>
