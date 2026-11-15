<script setup lang="ts">
// One finding as a ledger row: its evidence ID as a stamp (coloured by its SWOT side), the claim, and its weight.
import { computed } from 'vue'
import type { Finding } from '@/types'

const props = defineProps<{ finding: Finding; showAgent?: boolean }>()

const SWOT: Record<string, string> = { S: 'Strength', W: 'Weakness', O: 'Opportunity', T: 'Threat' }
const impact = computed(() => Math.max(0, Math.min(5, Math.round(props.finding.impact))))
const confidence = computed(() => Math.round(props.finding.confidence * 100))
</script>

<template>
  <article class="finding">
    <span class="stamp" :class="finding.swot ? `swot-${finding.swot}` : ''">{{ finding.id }}</span>
    <b>{{ finding.title }}</b>
    <p>{{ finding.statement }}</p>
    <div class="meta">
      <span v-if="finding.swot" class="swot-word" :class="`swot-${finding.swot}`">{{ SWOT[finding.swot] }}</span>
      <span class="impact">
        <span class="pips" role="img" :aria-label="`Impact ${impact} of 5`">
          <i v-for="n in 5" :key="n" :class="{ on: n <= impact }" />
        </span>
        <span aria-hidden="true">impact</span>
      </span>
      <span>{{ confidence }}% confidence</span>
      <span v-if="showAgent">from the {{ finding.agent }}</span>
    </div>
  </article>
</template>

<style scoped>
.impact {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.swot-word {
  font-weight: 600;
  color: var(--mm-accent);
}
.swot-word.swot-S {
  color: var(--mm-good);
}
.swot-word.swot-W {
  color: var(--mm-bad);
}
.swot-word.swot-T {
  color: var(--mm-warn);
}
</style>
