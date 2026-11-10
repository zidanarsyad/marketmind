<script setup lang="ts">
// The HTML report the Report Writer produced, in a sandboxed frame: its chart scripts run, but it cannot reach the
// app or the API.
import Button from 'primevue/button'
import Message from 'primevue/message'
import { computed } from 'vue'
import { api } from '@/api'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
const summary = computed(() => run.bundle?.summary)
</script>

<template>
  <div class="stack">
    <div v-if="summary?.has_report || summary?.has_markdown" class="actions">
      <Button v-if="summary?.has_report" as="a" :href="api.reportUrl(id, 'html', true)" download label="Download HTML report" icon="pi pi-download" />
      <Button
        v-if="summary?.has_markdown"
        as="a"
        :href="api.reportUrl(id, 'md', true)"
        download
        label="Download Markdown"
        icon="pi pi-file"
        severity="secondary"
        outlined
      />
      <Button
        v-if="summary?.has_report"
        as="a"
        :href="api.reportUrl(id, 'html')"
        target="_blank"
        rel="noopener"
        label="Open in a new tab"
        icon="pi pi-external-link"
        severity="secondary"
        text
      />
    </div>
    <iframe
      v-if="summary?.has_report"
      :src="api.reportUrl(id, 'html')"
      title="Market research report"
      class="report"
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      loading="lazy"
    />
    <Message v-else severity="info">No report in this run.</Message>
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.actions :deep(a.p-button) {
  text-decoration: none;
}
.report {
  width: 100%;
  height: max(640px, calc(100vh - 220px));
  height: max(640px, calc(100dvh - 220px));
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius);
  background: #fff;
}
</style>
