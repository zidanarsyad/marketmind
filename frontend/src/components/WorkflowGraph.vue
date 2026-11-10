<script setup lang="ts">
// The agent workflow as a layered diagram: the Research Director, then each layer of tasks the workflow ran (from
// run_meta.json's workflow.layers and edges), coloured by how each agent finished, with the QA loop back to the
// Director. Drawn as SVG; on a phone it scrolls sideways.
import { computed } from 'vue'
import type { AgentResult } from '@/types'

const props = defineProps<{
  layers: string[][]
  edges: [string, string][]
  tasks: Record<string, string>
  agents: Record<string, AgentResult>
}>()

const W = 140
const H = 48
const GAP_X = 34
const GAP_Y = 12
const PAD = 10

interface Node {
  id: string
  x: number
  y: number
  lines: string[]
  status: string
  seconds: string
}

function split(name: string): string[] {
  const n = name.replace(' (QA)', ' (QA)')
  if (n.length <= 21) return [n]
  const words = n.split(' ')
  let first = ''
  while (words.length && (first + ' ' + words[0]).trim().length <= 21) first = (first + ' ' + words.shift()).trim()
  return [first, words.join(' ')]
}

const graph = computed(() => {
  const columns: string[][] = [['plan'], ...props.layers]
  const tallest = Math.max(...columns.map((c) => c.length))
  const height = tallest * H + (tallest - 1) * GAP_Y
  const nodes: Record<string, Node> = {}
  columns.forEach((col, ci) => {
    const colHeight = col.length * H + (col.length - 1) * GAP_Y
    col.forEach((id, ri) => {
      const res = props.agents[id]
      const name = id === 'plan' ? 'Research Director' : (props.tasks[id] ?? id)
      nodes[id] = {
        id,
        x: PAD + ci * (W + GAP_X),
        y: PAD + (height - colHeight) / 2 + ri * (H + GAP_Y),
        lines: id === 'plan' ? ['Research Director', 'plan + supervise'] : split(name),
        status: res?.status ?? (id === 'plan' ? 'completed' : 'not run'),
        seconds: res?.seconds !== undefined ? `${res.seconds}s` : '',
      }
    })
  })
  const curve = (a: Node, b: Node) => {
    const x1 = a.x + W
    const y1 = a.y + H / 2
    const x2 = b.x
    const y2 = b.y + H / 2
    const dx = (x2 - x1) / 2
    return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`
  }
  const first = props.layers[0]?.[0]
  const links = [
    ...(first && nodes.plan && nodes[first] ? [curve(nodes.plan, nodes[first])] : []),
    ...props.edges.filter(([a, b]) => nodes[a] && nodes[b]).map(([a, b]) => curve(nodes[a], nodes[b])),
  ]
  const width = PAD * 2 + columns.length * W + (columns.length - 1) * GAP_X
  const qa = nodes.qa
  const loopY = PAD + height + 26
  const loop =
    qa && nodes.plan
      ? `M${qa.x + W / 2},${qa.y + H} C${qa.x + W / 2},${loopY} ${qa.x + W / 2},${loopY} ${qa.x},${loopY} ` +
        `L${nodes.plan.x + W},${loopY} C${nodes.plan.x + W / 2},${loopY} ${nodes.plan.x + W / 2},${loopY} ${nodes.plan.x + W / 2},${nodes.plan.y + H}`
      : ''
  return { nodes: Object.values(nodes), links, width, height: PAD * 2 + height + (loop ? 44 : 0), loop, loopY }
})

// on a phone the diagram becomes a list of steps; agents in one step ran side by side
const steps = computed(() =>
  [['plan'], ...props.layers].map((layer) =>
    layer.map((id) => ({
      id,
      name: id === 'plan' ? 'Research Director (plan + supervise)' : (props.tasks[id] ?? id),
      status: props.agents[id]?.status ?? (id === 'plan' ? 'completed' : 'not run'),
      seconds: props.agents[id]?.seconds,
    })),
  ),
)
</script>

<template>
  <div class="scroll-x diagram">
    <svg
      class="workflow"
      :viewBox="`0 0 ${graph.width} ${graph.height}`"
      :style="{ minWidth: `${Math.round(graph.width * 0.8)}px`, maxWidth: `${graph.width}px` }"
      role="img"
      aria-label="Agent workflow: the Research Director plans, the agents run layer by layer, the Critic checks the report"
    >
      <defs>
        <marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" class="arrow" />
        </marker>
      </defs>
      <path v-for="(d, i) in graph.links" :key="i" :d="d" class="link" marker-end="url(#wf-arrow)" />
      <template v-if="graph.loop">
        <path :d="graph.loop" class="link loop" marker-end="url(#wf-arrow)" />
        <text :x="graph.width / 2" :y="graph.loopY - 6" class="loop-label" text-anchor="middle">QA verdict / revision loop</text>
      </template>
      <g v-for="n in graph.nodes" :key="n.id" :class="['node', n.status.replace(' ', '-')]">
        <title>{{ n.lines.join(' ') }}: {{ n.status }} {{ n.seconds }}</title>
        <rect :x="n.x" :y="n.y" :width="W" :height="H" rx="9" />
        <text :x="n.x + W / 2" :y="n.y + (n.lines.length > 1 ? 18 : 23)" text-anchor="middle" class="name">
          <tspan v-for="(l, i) in n.lines" :key="i" :x="n.x + W / 2" :dy="i ? 13 : 0">{{ l }}</tspan>
        </text>
        <text :x="n.x + W / 2" :y="n.y + H - 7" text-anchor="middle" class="secs">{{ n.status === 'completed' ? n.seconds : n.status }}</text>
      </g>
    </svg>
  </div>
  <ol class="steps">
    <li v-for="(layer, i) in steps" :key="i">
      <span class="step-no">{{ i + 1 }}</span>
      <ul>
        <li v-for="a in layer" :key="a.id" :class="['step', a.status.replace(' ', '-')]">
          <span>{{ a.name }}</span>
          <small>{{ a.status === 'completed' ? `${a.seconds ?? ''}s` : a.status }}</small>
        </li>
      </ul>
    </li>
    <li v-if="graph.loop" class="loop-note">The Critic's QA verdict goes back to the Research Director, who can send agents back for revisions.</li>
  </ol>
  <div class="legend">
    <span><i class="sw completed" />completed</span>
    <span><i class="sw failed" />failed</span>
    <span><i class="sw skipped" />skipped</span>
  </div>
</template>

<style scoped>
.workflow {
  width: 100%;
  height: auto;
  display: block;
  font-family: var(--mm-font);
}
.link {
  fill: none;
  stroke: var(--mm-border-strong);
  stroke-width: 1.4;
}
.link.loop {
  stroke-dasharray: 5 4;
}
.arrow {
  fill: var(--mm-border-strong);
}
.loop-label {
  font-size: 10px;
  fill: var(--mm-muted);
}
.node rect {
  fill: var(--mm-panel-2);
  stroke: var(--mm-border-strong);
}
.node.completed rect {
  fill: var(--mm-good-soft);
  stroke: color-mix(in srgb, var(--mm-good) 45%, transparent);
}
.node.failed rect {
  fill: var(--mm-bad-soft);
  stroke: var(--mm-bad);
}
.node.skipped rect,
.node.not-run rect {
  fill: var(--mm-skip-soft);
  stroke-dasharray: 4 3;
}
.name {
  font-size: 11px;
  font-weight: 600;
  fill: var(--mm-text);
}
.secs {
  font-size: 10px;
  fill: var(--mm-muted);
}
.steps {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
}
.steps > li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 6px 0;
}
.step-no {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--mm-accent-soft);
  color: var(--mm-accent);
  font-size: 0.75rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 4px;
}
.steps ul {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.step {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid var(--mm-border-strong);
  background: var(--mm-panel-2);
  font-size: 0.86rem;
  font-weight: 550;
}
.step small {
  color: var(--mm-muted);
  font-weight: 400;
}
.step.completed {
  background: var(--mm-good-soft);
}
.step.failed {
  background: var(--mm-bad-soft);
}
.step.skipped,
.step.not-run {
  background: var(--mm-skip-soft);
  border-style: dashed;
}
.loop-note {
  font-size: 0.8rem;
  color: var(--mm-muted);
}
@media (max-width: 640px) {
  .diagram {
    display: none;
  }
  .steps {
    display: block;
  }
}
.legend {
  display: flex;
  gap: 14px;
  font-size: 0.78rem;
  color: var(--mm-muted);
  margin-top: 6px;
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.sw {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  display: inline-block;
  border: 1px solid var(--mm-border-strong);
}
.sw.completed {
  background: var(--mm-good-soft);
}
.sw.failed {
  background: var(--mm-bad-soft);
}
.sw.skipped {
  background: var(--mm-skip-soft);
}
</style>
