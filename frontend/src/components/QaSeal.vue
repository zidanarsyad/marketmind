<script setup lang="ts">
import { computed } from 'vue'

// The Critic agent's verdict, set on the dossier as a seal: the QA score when it checked the run, else how the run
// ended. Words always sit inside the seal, so its colour is never the only signal.
const props = defineProps<{ status: string; score?: number | null; passed?: boolean | null; revisions?: number }>()

const view = computed(() => {
  if (props.status === 'rejected')
    return { cls: 'bad', top: 'Study', big: 'Stopped', word: true, bottom: 'no report', label: 'Study stopped at an approval gate. No report was released.' }
  if (props.score === null || props.score === undefined)
    return { cls: 'idle', top: 'QA', big: 'Not run', word: true, bottom: 'unverified', label: 'QA did not run, so the report is unverified.' }
  const s = Math.round(props.score)
  const ok = !!props.passed
  const rev = props.revisions ?? 0
  const after = rev ? ` after ${rev} revision${rev === 1 ? '' : 's'}` : ' on the first draft'
  return {
    cls: ok ? 'good' : 'warn',
    top: 'QA',
    big: String(s),
    word: false,
    bottom: ok ? 'passed' : 'not passed',
    label: `The Critic agent scored the report ${s} out of 100: ${ok ? 'passed' : 'not passed'}${after}.`,
  }
})
</script>

<template>
  <div class="seal" :class="view.cls" role="img" :aria-label="view.label" :title="view.label">
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <circle class="face" cx="50" cy="50" r="41" />
      <circle class="teeth" cx="50" cy="50" r="46.5" pathLength="360" />
      <circle class="ring" cx="50" cy="50" r="40" />
    </svg>
    <span class="body" aria-hidden="true">
      <small>{{ view.top }}</small>
      <strong :class="{ word: view.word }">{{ view.big }}</strong>
      <small>{{ view.bottom }}</small>
    </span>
  </div>
</template>

<style scoped>
.seal {
  --seal: var(--mm-accent);
  --seal-soft: var(--mm-accent-soft);
  position: relative;
  flex: none;
  width: 112px;
  height: 112px;
  color: var(--seal);
  /* the one moment of motion on the page: the seal is pressed onto the dossier when the run opens */
  animation: press 460ms cubic-bezier(0.2, 0.9, 0.25, 1) backwards;
}
.seal.warn {
  --seal: var(--mm-warn);
  --seal-soft: var(--mm-warn-soft);
}
.seal.bad {
  --seal: var(--mm-bad);
  --seal-soft: var(--mm-bad-soft);
}
.seal.idle {
  --seal: var(--mm-muted);
  --seal-soft: var(--mm-skip-soft);
}
svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.face {
  fill: var(--seal-soft);
}
.teeth {
  fill: none;
  stroke: currentColor;
  stroke-width: 4.5;
  stroke-dasharray: 2.1 2.4;
}
.ring {
  fill: none;
  stroke: currentColor;
  stroke-width: 0.9;
  opacity: 0.55;
}
.seal.idle .teeth {
  stroke-dasharray: 1 3.5;
}
.body {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 1.05;
}
.body small {
  font-size: var(--mm-fs-xs);
  font-weight: 600;
  color: var(--mm-text-2);
}
.body strong {
  font-size: 2.05rem;
  font-weight: 760;
  font-stretch: 86%;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums lining-nums;
  line-height: 1;
  margin: 1px 0 2px;
}
.body strong.word {
  font-size: 1.02rem;
  font-stretch: 100%;
  letter-spacing: 0;
  margin: 3px 0 4px;
}
@keyframes press {
  from {
    opacity: 0;
    transform: scale(1.15) rotate(-8deg);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (max-width: 720px) {
  .seal {
    width: 88px;
    height: 88px;
  }
  .body small {
    font-size: 0.7rem;
  }
  .body strong {
    font-size: 1.6rem;
  }
  .body strong.word {
    font-size: 0.86rem;
  }
}
</style>
