# MarketMind architecture

MarketMind is a cooperative multi-agent system: a goal-based **Research Director** plans a study from a free-text brief and supervises ten specialist agents that communicate only through a shared **blackboard**. Numbers come from deterministic tools and ML/DL models; an optional LLM supplies language; a **Critic** agent verifies every number before a report is released.

This document describes the system as built. Every diagram is Mermaid (renders on GitHub, in VS Code and in `docs/diagrams/gallery.html`, which also exports SVG/PNG). Related documents: [AGENTS.md](AGENTS.md) (per-agent specifications), [SCHEMAS.md](SCHEMAS.md) (data contracts), [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [EVALUATION.md](EVALUATION.md).

---

## 1. System context

Who and what MarketMind talks to. Everything outside the box is optional except the data files.

```mermaid
flowchart LR
    MM["MarketMind<br/>multi-agent market research system"]
    MGR(["Marketing manager"]) -- "brief, questions" --> MM
    ANA(["Research analyst"]) -- "briefs, inspects evidence" --> MM
    IT(["Data / IT staff"]) -- "datasets, LLM keys" --> MM
    LEC(["Lecturer / reviewer"]) -- "scores runs" --> MM
    MM -- "report, dashboard, answers" --> MGR
    FILES[("Research datasets<br/>data/raw/*.csv")] --> MM
    WB["World Bank Open Data API<br/>(no key, cached)"] --> MM
    NEWS["GNews / NewsAPI<br/>(optional key)"] --> MM
    MM <-- "language only" --> LLM["LLM provider (optional)<br/>Gemini, Groq, OpenRouter, Ollama, Claude"]
```

## 2. Components (layered view)

```mermaid
flowchart TB
    subgraph UI["Interfaces"]
        DASH["Streamlit dashboard<br/>app/dashboard.py"]
        CLI["Command line<br/>run.py"]
        CHAT["Analyst Chat agent<br/>agents/analyst_chat.py"]
    end
    subgraph ORCH["Orchestration"]
        SYS["MarketResearchSystem<br/>system.py"]
        DIR["Research Director<br/>agents/director.py"]
        WF["Workflow engine (DAG, thread pool)<br/>core/orchestrator.py"]
    end
    subgraph AG["Specialist agents (marketmind/agents)"]
        A1["Data Collection"] --- A2["Data Quality"]
        A3["Market & Trend"] --- A4["Competitive Intelligence"]
        A5["Consumer Insight (DL)"] --- A6["Segmentation (ML)"]
        A7["Forecasting (ML)"] --- A8["Strategy"]
        A9["Report Writer"] --- A10["Critic (QA)"]
    end
    subgraph CORE["Core services (marketmind/core)"]
        BB["Blackboard<br/>shared memory"]
        TR["Tracer<br/>event log"]
        LLMC["LLM client<br/>provider-agnostic"]
        ST["Run store<br/>save / load runs"]
    end
    subgraph MLK["ML / DL toolkits (marketmind/ml)"]
        M1["text + sentiment (PyTorch)"]
        M2["topics, segmentation"]
        M3["forecasting, pricing, calendar"]
    end
    subgraph REP["Reporting (marketmind/reporting)"]
        CH["chart library (Plotly)"]
        HT["HTML report renderer"]
    end
    subgraph DATA["Data and persistence"]
        RAW[("data/raw")]
        EXT[("data/external<br/>World Bank cache")]
        OUT[("outputs/<br/>runs, models, LLM cache")]
    end
    DASH --> SYS
    CLI --> SYS
    CHAT --> ST
    SYS --> DIR --> WF --> AG
    AG <--> BB
    AG --> TR
    AG --> LLMC
    AG --> MLK
    A9 --> REP
    DASH --> CH
    DASH --> ST
    ST --> OUT
    A1 --> RAW
    A1 --> EXT
```

| Package / module | Responsibility |
|---|---|
| `marketmind/core/agent.py` | `BaseAgent` (tools, tracing, findings, LLM helper, lifecycle), `RunContext`, `AgentResult` |
| `marketmind/core/blackboard.py` | Thread-safe shared memory: artefacts with provenance, findings, agent-to-agent messages |
| `marketmind/core/events.py` | `Tracer` / `Event`: every status, thought, tool call, observation, finding, message, LLM call, warning, error |
| `marketmind/core/findings.py` | `Finding`, the unit of knowledge (statement + metrics + evidence + impact + confidence + SWOT) |
| `marketmind/core/llm.py` | Provider-agnostic LLM client: caching, throttling, model rediscovery, JSON parsing, graceful failure |
| `marketmind/core/orchestrator.py` | `Workflow` / `Task`: topological layers, parallel execution, critical vs non-critical tasks |
| `marketmind/core/store.py` | Run persistence (`save_run`, `RunData`, `list_runs`, `load_run`) |
| `marketmind/agents/` | The eleven pipeline agents and the Analyst Chat agent |
| `marketmind/ml/` | Text normalisation, sentiment models, topics, segmentation, forecasting, pricing, Indonesian calendar |
| `marketmind/reporting/` | Shared Plotly chart library (`CHARTS` registry) and the self-contained HTML report |
| `marketmind/system.py` | `MarketResearchSystem`: wires context, runs Director + workflow + QA loop, saves the run |
| `marketmind/evaluation.py` | Scores a run against the planted ground truth |
| `marketmind/sql_export.py` | Loads clean datasets and runs into the SQL model (`docs/schemas/database.sql`) |
| `app/dashboard.py` | Streamlit dashboard (12 views, live runs, chat, evaluation) |

## 3. Core classes

```mermaid
classDiagram
    direction LR
    class MarketResearchSystem {
        +run_id: str
        +blackboard: Blackboard
        +tracer: Tracer
        +llm: LLMClient
        +run() RunResult
    }
    class RunContext {
        +run_id: str
        +blackboard: Blackboard
        +tracer: Tracer
        +llm: LLMClient
        +run_dir: Path
        +options: dict
    }
    class BaseAgent {
        <<abstract>>
        +name: str
        +role: str
        +goal: str
        +ml_capability: str
        +tools: dict
        +register_tools()
        +use(name, args) Any
        +think(message)
        +publish(finding) Finding
        +put(key, value)
        +tell(recipient, content)
        +ask_llm(task, facts) str
        +execute() str
        +run() AgentResult
    }
    class ResearchDirectorAgent {
        +build_workflow() Workflow
        +quality_loop(results) dict
    }
    class Blackboard {
        +put(key, value, agent)
        +get(key) Any
        +require(key) Any
        +add_finding(finding)
        +findings(area, agent) list
        +post(sender, recipient, content)
        +inbox(recipient) list
    }
    class Finding {
        +id: str
        +agent: str
        +area: str
        +statement: str
        +metrics: dict
        +evidence: list
        +impact: int
        +confidence: float
        +swot: str
        +priority() float
    }
    class Tracer {
        +events: list
        +emit(agent, kind, message)
        +save(path)
    }
    class LLMClient {
        +provider: str
        +model: str
        +available: bool
        +complete(system, prompt) str
        +complete_json(system, prompt) dict
        +ping() tuple
    }
    class Workflow {
        +tasks: dict
        +layers: list
        +run(ctx, parallel) dict
    }
    class Task {
        +id: str
        +agent: type
        +depends_on: tuple
        +critical: bool
    }
    class AgentResult {
        +agent: str
        +status: str
        +seconds: float
        +findings: int
        +tool_calls: int
    }
    class SentimentSuite {
        +train(texts, labels) dict
        +predict_proba(texts) array
        +score_social(texts) tuple
        +evaluate_transfer(texts, labels) dict
        +score_clauses(texts) array
    }
    class DemandForecaster {
        +backtest(panel, client) dict
        +forecast(panel, method) DataFrame
    }
    MarketResearchSystem --> RunContext
    MarketResearchSystem --> ResearchDirectorAgent
    ResearchDirectorAgent --> Workflow
    Workflow "1" *-- "many" Task
    Task --> BaseAgent
    BaseAgent <|-- ResearchDirectorAgent
    BaseAgent <|-- ConsumerInsightAgent
    BaseAgent <|-- DemandForecastingAgent
    BaseAgent <|-- SegmentationAgent
    BaseAgent --> RunContext
    RunContext --> Blackboard
    RunContext --> Tracer
    RunContext --> LLMClient
    Blackboard "1" o-- "many" Finding
    BaseAgent ..> AgentResult : returns
    ConsumerInsightAgent --> SentimentSuite
    DemandForecastingAgent --> DemandForecaster
```

The other seven agents (Data Collection, Data Quality, Market & Trend Analyst, Competitive Intelligence, Strategy, Report Writer, Critic) also subclass `BaseAgent`; they are omitted from the diagram for readability.

## 4. Workflow (dependency graph)

The Director builds this graph from the plan's active modules. Data tasks are **critical** (a failure skips dependents); analysis tasks are **non-critical** (a failure leaves Strategy to work with the findings that exist).

```mermaid
flowchart LR
    P["plan<br/>Research Director"] --> C["collect<br/>Data Collection"]
    C --> Q["quality<br/>Data Quality"]
    Q --> M["market"]
    Q --> K["competition"]
    Q --> I["consumer (DL)"]
    Q --> S["segmentation (ML)"]
    Q --> F["forecast (ML)"]
    M -.-> T["strategy"]
    K -.-> T
    I -.-> T
    S -.-> T
    F -.-> T
    T --> R["report<br/>Report Writer"]
    R --> A{"qa<br/>Critic"}
    A -- "pass" --> OUT(["saved run"])
    A -- "fail (max 2)" --> R
```

Dotted edges = non-critical dependencies. Analysis agents run concurrently on a `ThreadPoolExecutor` with three workers.

## 5. A run, step by step

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant UI as Dashboard / CLI
    participant SYS as MarketResearchSystem
    participant DIR as Research Director
    participant WF as Workflow
    participant BB as Blackboard
    participant AN as Analysis agents (x5)
    participant ST as Strategy
    participant RW as Report Writer
    participant CR as Critic
    participant RS as Run store
    U->>UI: brief + options
    UI->>SYS: run()
    SYS->>DIR: run() (plan)
    DIR->>BB: put("plan")
    SYS->>DIR: build_workflow()
    DIR-->>SYS: Workflow
    SYS->>WF: run(ctx, parallel=True)
    WF->>BB: Data Collection: put datasets.raw, external.macro
    WF->>BB: Data Quality: put datasets, dq.*
    par five analysts on a thread pool
        WF->>AN: run()
        AN->>BB: read datasets, put *.tables, publish findings
    end
    WF->>ST: run()
    ST->>BB: put strategy.swot / recommendations / kpis
    WF->>RW: run()
    RW->>BB: put report.markdown / report.html
    WF->>CR: run()
    CR->>BB: put qa.result
    alt QA failed and revisions left
        DIR->>RW: message: block-level issues
        RW->>BB: revised report
        DIR->>CR: run() again
    end
    SYS->>RS: save_run (meta, findings, trace, tables, report)
    RS-->>UI: run_id
    UI-->>U: dashboard updates
```

## 6. Lifecycles

**Agent lifecycle.** Every agent goes through the same loop; each transition is a traced event.

```mermaid
stateDiagram-v2
    [*] --> Started: run()
    Started --> Perceiving: read blackboard
    Perceiving --> Reasoning: think (optionally ask the LLM)
    Reasoning --> Acting: use(tool)
    Acting --> Reasoning: observation
    Acting --> Publishing: put artefacts, publish findings
    Publishing --> Completed
    Started --> Failed: exception (traceback traced)
    Reasoning --> Failed
    Acting --> Failed
    [*] --> Skipped: a critical upstream task failed
    Completed --> [*]
    Failed --> [*]
    Skipped --> [*]
```

**Run lifecycle and the QA gate.**

```mermaid
stateDiagram-v2
    [*] --> Planning
    Planning --> Executing: plan on blackboard
    Planning --> Failed: planning error
    Executing --> QAReview: report written
    Executing --> Failed: collect, quality, strategy or report failed
    QAReview --> Released: score >= 85 and no critical issue
    QAReview --> Revising: failed and revisions < 2
    Revising --> QAReview: Report Writer replaces rejected blocks
    QAReview --> ReleasedWithIssues: failed after 2 revisions
    Released --> Saved
    ReleasedWithIssues --> Saved: open issues listed in the QA certificate
    Failed --> Saved
    Saved --> [*]
```

## 7. Data flow

Level-1 data-flow diagram: processes (circles), data stores (cylinders), external entities (rectangles).

```mermaid
flowchart LR
    BRIEF["Business brief"] --> P1(("1.0 Plan"))
    P1 --> D2[("D2 Blackboard")]
    CSV[("D1 data/raw")] --> P2(("2.0 Collect"))
    WBAPI["World Bank API"] --> P2
    P2 --> D2
    D2 --> P3(("3.0 Clean and validate"))
    P3 --> D2
    D2 --> P4(("4.0 Analyse<br/>market, competition,<br/>consumers, segments,<br/>forecast"))
    D3[("D3 Model store<br/>outputs/models")] <--> P4
    P4 --> D2
    D2 --> P5(("5.0 Synthesise<br/>SWOT, actions"))
    P5 --> D2
    D2 --> P6(("6.0 Write report"))
    LLMP["LLM provider"] <-.-> P6
    P6 --> D2
    D2 --> P7(("7.0 QA"))
    P7 -- "revision request" --> P6
    P7 --> D4[("D4 Run store<br/>outputs/runs")]
    D4 --> DASHB["Dashboard and readers"]
    D5[("D5 LLM cache")] <-.-> LLMP
```

## 8. Deployment

```mermaid
flowchart TB
    subgraph LAPTOP["Laptop / VM (Windows, macOS or Linux), Python 3.12, CPU only"]
        subgraph PROC["Python process"]
            STR["Streamlit server :8501<br/>or run.py"]
            AGENTS["Agents + workflow thread pool"]
            TORCH["PyTorch CPU / scikit-learn"]
        end
        FS[("File system<br/>data/, outputs/")]
        OLL["Ollama :11434<br/>(optional local LLM)"]
    end
    BROWSER["Web browser"] -- "HTTP" --> STR
    STR --- AGENTS --- TORCH
    AGENTS --- FS
    AGENTS -. "HTTPS" .-> WB2["api.worldbank.org"]
    AGENTS -. "HTTPS, optional" .-> LLMS["LLM APIs: Gemini, Groq, OpenRouter, Anthropic"]
    AGENTS -. "HTTPS, optional" .-> NWS["gnews.io / newsapi.org"]
    AGENTS -. "HTTP, optional" .-> OLL
```

Enterprise path: containerise the process, schedule studies (cron or a workflow orchestrator), load datasets from a warehouse with `docs/schemas/database.sql`, put the dashboard behind single sign-on, keep keys in a secrets manager.

## 9. Model architectures

**Deep-learning sentiment model** (Consumer Insight agent):

```mermaid
flowchart TB
    T["Review text (Indonesian slang, emojis)"] --> N["Normalise: slang map, elongations, emoji tokens"]
    N --> TK["Tokens (max 64), vocabulary built on training data"]
    TK --> E["Embedding, 96 dims (word dropout 10% in training)"]
    E --> D1["Dropout 0.3"]
    D1 --> G["Bidirectional GRU, one layer,<br/>64 units per direction"]
    G --> AT["Additive attention pooling<br/>(weights shown in the dashboard)"]
    AT --> D2["Dropout 0.3"]
    D2 --> L["Linear, 3 classes"]
    L --> SM["Softmax: negative / neutral / positive"]
    TF["TF-IDF word 1-2 + char 3-5 grams<br/>logistic regression"] --> ENS{"Soft-vote ensemble<br/>weight tuned on validation"}
    SM --> ENS
    ENS --> SEL["Model selection by validation macro-F1;<br/>transfer scorer chosen on 400 labelled social posts"]
```

**Demand forecaster** (Demand Forecasting agent):

```mermaid
flowchart LR
    SP["Clean sales panel"] --> PN["Monthly panel<br/>150 brand x category x channel series"]
    CAL["Ramadan / Eid / mega-sale calendar"] --> FE
    PN --> FE["Features at origin o for horizon h:<br/>momentum 1/3/6, level, calendar shifts,<br/>price, discount, stock-out changes, codes"]
    FE --> GB["HistGradientBoosting<br/>target: YoY log growth minus 3-month momentum"]
    PN --> SN["Seasonal naive, seasonal naive + drift"]
    GB --> EN["GBM + drift ensemble"]
    SN --> EN
    GB --> BT{"3 rolling-origin folds x 6 months<br/>pick lowest series WAPE"}
    SN --> BT
    EN --> BT
    BT --> FC["12-month forecast<br/>+ 80% intervals from backtest errors"]
```

**Critic numeric-grounding check:**

```mermaid
flowchart TB
    EV["Collect evidence numbers:<br/>finding statements + metrics, recommendations,<br/>KPIs, model cards, opportunities"] --> EXP["Expand: x100 for ratios,<br/>/1e3, /1e6, /1e9, /1e12 for rupiah"]
    REP["Report prose (tables, headings, quotes excluded)"] --> BL["Split into blocks:<br/>LLM blocks + deterministic text"]
    BL --> NUM["Extract numbers with written precision"]
    NUM --> CHK{"Match within 0.5 x 10^-decimals<br/>or 0.5% relative?"}
    EXP --> CHK
    CHK -- "yes" --> OK["grounded"]
    CHK -- "no, LLM block" --> CRIT["critical issue: replace block on revision"]
    CHK -- "no, deterministic text" --> MAJ["major issue"]
```

## 10. Key design decisions

| Decision | Alternatives considered | Why |
|---|---|---|
| Custom lightweight agent framework | LangGraph, CrewAI, AutoGen | Works fully offline, no LLM required for control flow, every step is inspectable for teaching and audit |
| Blackboard communication | Direct agent calls, message bus | Decouples agents, gives one place for provenance, makes parallel execution and persistence simple |
| Deterministic tools produce all numbers; LLM writes language only | LLM-driven analysis (ReAct over pandas) | Prevents hallucinated figures; the Critic can verify every number |
| Critic + bounded revision loop | Single-pass generation | Reflection catches ungrounded LLM text without unbounded loops (max 2 revisions) |
| Model selection by validation, honest test metrics | Fixed model choice | The DL model must earn its place; the ensemble or baseline wins when it is better |
| Transfer validation on a labelled social sample | Assume review-trained model transfers | An early BiGRU labelled 73% of social posts negative. The check now picks the best scorer for that domain: the ensemble reaches macro-F1 0.918 on the labelled posts, against 0.850 for the BiGRU alone |
| Direct multi-horizon residual boosting + rolling backtests | Recursive forecasting, single holdout | Recursive feedback inflated forecasts; one holdout was dominated by an unforecastable shock |
| Simulated data with recorded ground truth | Real scraped data only | Lets the whole system be scored objectively; documented schemas allow swapping in real data |
| Files for persistence, SQL model for export | Database as the primary store | Zero-setup for students; `scripts/export_sqlite.py` gives the relational view when needed |

## 11. Cross-cutting concerns

- **Concurrency:** the blackboard and tracer use locks; analysis agents share a three-worker pool; PyTorch uses up to four threads.
- **Error handling:** `BaseAgent.run()` catches exceptions, traces the traceback and returns a `failed` result; the workflow skips only critical dependents; the dashboard guards each view.
- **Caching:** the sentiment models are cached under a hash of their training data, in one folder per training mode (`--sentiment-data`); World Bank responses are cached in `data/external`; LLM responses are cached in `outputs/cache/llm`.
- **Configuration:** `.env` (LLM provider and keys, news keys, rate limit), `marketmind/config.py` (paths, dataset registry, default brief).
- **Security:** API keys travel only in request headers, never in prompts, traces, run files or reports. Streamlit listens on all network interfaces by default; set `address = "localhost"` under `[server]` in `.streamlit/config.toml` to keep the dashboard private to one machine.
- **Performance:** about 2 minutes for a first run (model training) and about 50 seconds once the models are cached (48 s for the reference run, on an 8-thread laptop CPU).
