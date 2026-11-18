<script setup lang="ts">
// The run's negotiations: alternating offers between two enterprises, and the Contract Net round for the flood
// reroute. Each side's limit stays private: only offers cross the wire.
import { computed } from 'vue'
import NegotiationCard from '../components/NegotiationCard.vue'
import { useControlStore } from '../store'

const ctl = useControlStore()
const threads = computed(() => ctl.ecosystem?.negotiations ?? [])
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Negotiations</h1>
      <p class="lede">
        With ecosystem intelligence the enterprises negotiate their terms instead of taking list prices. Each side plays
        a time-dependent tactic against a private limit; the offers are all the other side ever sees.
      </p>
    </header>

    <p v-if="!ctl.ecosystem" class="empty">Negotiations happen only with ecosystem intelligence: run a scenario in “Compare both” or “Ecosystem only”.</p>
    <p v-else-if="!threads.length" class="empty">No negotiation in this run.</p>

    <NegotiationCard v-for="t in threads" :key="t.conversation_id" :thread="t" />

    <p v-if="ctl.local" class="caption">
      In the local run of this scenario nobody negotiated: Kirana bought at MaklonNusa's list price, joined the
      campaigns on PasarNusa's standard terms, and nobody rerouted ahead of the flood.
    </p>
  </div>
</template>

<style scoped>
.hero {
  max-width: 78ch;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lede {
  margin: 0;
  color: var(--mm-text-2);
}
</style>
