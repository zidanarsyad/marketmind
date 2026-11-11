# MarketMind documentation

The [design proposal](https://claude.ai/artifact/QY1WcVtyNZYJ5pHcy2nUEB), a Claude Doc with 16 sections and 4 diagrams, explains why MarketMind is built the way it is. Only people it has been shared with can open it. The documents in this folder describe how MarketMind is built and how to use it.

| Document | Read it to ... | Audience |
|---|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | Install MarketMind, run studies, write briefs, tour the dashboard, read the report, switch on an LLM, troubleshoot | Analysts, managers, students |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Understand the system: context, components, classes, workflow, run sequence, lifecycles, data flow, deployment, model architectures, design decisions | Everyone technical, reviewers |
| [AGENTS.md](AGENTS.md) | See each agent's type, PEAS profile, tools, inputs and outputs, findings, LLM use and failure behaviour, plus the finding registry | Developers, reviewers |
| [SCHEMAS.md](SCHEMAS.md) | Look up the data contracts: JSON Schemas for every artefact and message, the blackboard key registry, dataset row contracts, the SQL model and how to validate | Developers, data engineers |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Look up every column of the seven research datasets | Analysts, data engineers |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Find real public datasets and statistics that can replace, validate or calibrate the simulated data, with licences and a simulated-versus-real comparison | Analysts, data engineers, reviewers |
| [EVALUATION.md](EVALUATION.md) | See how well the system works: 25 ground-truth checks, model metrics, robustness across data seeds, ablations, real-LLM runs, data quality, governance, timings and threats to validity (raw results in `results/`) | Reviewers, lecturers |
| [SECURITY.md](SECURITY.md) | See what keeps the results trustworthy and the system safe: grounding, the QA gate, approval gates, the audit trail, credential redaction, local-only servers and the access token, input checks, privacy, dependency audits, and the limits that remain | Reviewers, lecturers, developers |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Extend MarketMind: core APIs, adding agents, tools, charts, datasets and LLM providers, testing, debugging | Developers |
| [schemas/](schemas/) | The machine-readable contracts: 15 JSON Schemas and `database.sql` | Tools and tests |
| [diagrams/gallery.html](diagrams/gallery.html) | All 16 diagrams on one page, with SVG and PNG export (open it in a browser) | Everyone |

## Diagrams

| Diagram | Kind | Where |
|---|---|---|
| Agent pipeline overview | flowchart | [README](../README.md#architecture) |
| System context | flowchart | [ARCHITECTURE §1](ARCHITECTURE.md#1-system-context) |
| Components (layered view) | flowchart | [ARCHITECTURE §2](ARCHITECTURE.md#2-components-layered-view) |
| The agentic-RAG chat loop; the ReAct data agent loop | flowcharts | [ARCHITECTURE §2](ARCHITECTURE.md#the-on-demand-agents-agentic-rag-and-react) |
| Core classes | class diagram | [ARCHITECTURE §3](ARCHITECTURE.md#3-core-classes) |
| Workflow (dependency graph) | flowchart | [ARCHITECTURE §4](ARCHITECTURE.md#4-workflow-dependency-graph) |
| A run, step by step | sequence diagram | [ARCHITECTURE §5](ARCHITECTURE.md#5-a-run-step-by-step) |
| Agent lifecycle; run lifecycle and the QA gate | state diagrams | [ARCHITECTURE §6](ARCHITECTURE.md#6-lifecycles) |
| Data flow (level 1) | flowchart | [ARCHITECTURE §7](ARCHITECTURE.md#7-data-flow) |
| Deployment | flowchart | [ARCHITECTURE §8](ARCHITECTURE.md#8-deployment) |
| BiGRU sentiment model; demand forecaster; Critic grounding check | flowcharts | [ARCHITECTURE §9](ARCHITECTURE.md#9-model-architectures) |
| Relational model | ER diagram | [SCHEMAS §5](SCHEMAS.md#5-relational-model) |

The diagrams are Mermaid code blocks, so they render on GitHub and in VS Code and are versioned with the code. After editing one, run `python scripts/build_diagram_gallery.py` to refresh the gallery.

## Keeping the documents true

- `tests/test_schemas.py` fails if the system's output stops matching `docs/schemas/`.
- `scripts/evaluate_agents.py` recomputes every number in [EVALUATION.md](EVALUATION.md) for a new run.
- The agent tables in [AGENTS.md](AGENTS.md) list tool names exactly as they are registered in code, so a search for a tool name finds both its documentation and its implementation.
