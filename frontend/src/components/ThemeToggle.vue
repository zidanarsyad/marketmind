<script setup lang="ts">
import { type ThemePref, useTheme } from '@/lib/theme'

defineProps<{ compact?: boolean }>()
const { pref, setTheme } = useTheme()
const options: { value: ThemePref; icon: string; label: string }[] = [
  { value: 'light', icon: 'pi pi-sun', label: 'Light theme' },
  { value: 'system', icon: 'pi pi-desktop', label: 'Follow the system theme' },
  { value: 'dark', icon: 'pi pi-moon', label: 'Dark theme' },
]
</script>

<template>
  <div class="theme-toggle" :class="{ compact }" role="group" aria-label="Colour theme">
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
  border: 1px solid var(--mm-border);
  border-radius: 999px;
  padding: 2px;
  background: var(--mm-panel-2);
}
.theme-toggle button {
  border: 0;
  background: transparent;
  color: var(--mm-muted);
  width: 32px;
  height: 28px;
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.theme-toggle.compact button {
  width: 30px;
  height: 26px;
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
</style>
