<script setup lang="ts">
import { type ThemePref, useTheme } from '@/lib/theme'

// The full control (light, follow the system, dark) sits in the sidebar; the phone's top bar has room for one button
// that flips between light and dark.
defineProps<{ compact?: boolean }>()
const { pref, mode, setTheme } = useTheme()
const options: { value: ThemePref; icon: string; label: string }[] = [
  { value: 'light', icon: 'pi pi-sun', label: 'Light theme' },
  { value: 'system', icon: 'pi pi-desktop', label: 'Follow the system theme' },
  { value: 'dark', icon: 'pi pi-moon', label: 'Dark theme' },
]
</script>

<template>
  <button
    v-if="compact"
    type="button"
    class="theme-flip"
    :aria-label="mode === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'"
    :title="mode === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'"
    @click="setTheme(mode === 'dark' ? 'light' : 'dark')"
  >
    <i :class="mode === 'dark' ? 'pi pi-sun' : 'pi pi-moon'" />
  </button>
  <div v-else class="theme-toggle" role="group" aria-label="Colour theme">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      :class="{ on: pref === o.value }"
      :aria-pressed="pref === o.value"
      :aria-label="o.label"
      :title="o.label"
      @click="setTheme(o.value)"
    >
      <i :class="o.icon" />
    </button>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-self: flex-start;
  border: 1px solid var(--mm-border);
  border-radius: 999px;
  padding: 2px;
  background: var(--mm-panel-2);
}
.theme-toggle button {
  border: 0;
  background: transparent;
  color: var(--mm-muted);
  width: 36px;
  height: 30px;
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.theme-toggle button:hover {
  color: var(--mm-text);
}
.theme-toggle button.on {
  background: var(--mm-panel);
  color: var(--mm-accent);
  box-shadow: 0 0 0 1px var(--mm-border);
}
.theme-toggle i {
  font-size: 0.85rem;
}
.theme-flip {
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--mm-text-2);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.theme-flip:hover {
  background: var(--mm-panel-2);
  color: var(--mm-text);
}
.theme-flip i {
  font-size: 1rem;
}
</style>
