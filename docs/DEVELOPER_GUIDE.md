# MarketMind developer guide

This guide is for people who change MarketMind: adding agents, tools, findings, charts, datasets or LLM providers, and keeping the tests and contracts green. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the big picture, and [AGENTS.md](AGENTS.md) for what each agent does today.

---

## 1. Setting up

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt     # or requirements-lock.txt for the exact tested versions
python -m ruff check .
python -m pytest -q
npm --prefix frontend install        # the web app (Node.js 20.19+), see section 12
npm --prefix frontend test
```

The repository includes the generated datasets, so `scripts/generate_data.py` is only needed after changing the generator. The full test suite takes several minutes (8 to 19 on the development laptop, the upper end with coverage), because it runs six full studies: the shared run and five end-to-end tests (see section 9). GitHub Actions (`.github/workflows/tests.yml`) runs `ruff check` and the full suite on every push and pull request, and, in a second job, the web app's type-check, Vitest tests and production build. Use `python run.py --no-llm` for fast, deterministic runs while developing, and `--sequential` when you want trace events in a strict order.

**Dependencies.** `requirements.txt` holds compatible ranges, each capped below the next major version. `requirements-lock.txt` pins every package, including transitive ones, to the versions the suite last passed with. When you upgrade a library, run the tests, then regenerate the lock from the working environment.

**Version control.** Commit code, docs and `data/raw`. `outputs/`, `data/external/` (downloaded corpora with their own licences), `data/real/` and `.env` (API keys) are git-ignored and must stay that way, as are `frontend/node_modules/` and the built `frontend/dist/`. Commit `frontend/package-lock.json` with any dependency change. Use `python run.py --no-llm` for fast, deterministic runs while developing, and `--sequential` when you want trace events in a strict order.

## 2. Repository layout

```
run.py                       command-line entry point
app/dashboard.py             Streamlit dashboard (12 views, live runs, chat, evaluation)
api/                         FastAPI layer for the web app (section 12): app.py, runs.py, studies.py, system_info.py,
                             security.py; python -m api serves it with the built front end
frontend/                    Vue 3 web app (section 12): src/views, src/components, src/stores, src/lib; package.json
marketmind/
  config.py                  paths, dataset registry (DATASETS), default brief and client, env()
  system.py                  MarketResearchSystem: context, Director, workflow, QA loop, saving the run
  evaluation.py              25 ground-truth checks for a saved run
  sql_export.py              loads clean data and runs into docs/schemas/database.sql
  core/
    agent.py                 BaseAgent, RunContext, AgentResult, GROUNDING_RULES
    blackboard.py            Blackboard (artefacts with provenance, findings, messages)
    events.py                Tracer and Event (the trace)
    findings.py              Finding and AREAS
    llm.py                   LLMClient: providers, cache, throttling, model discovery, parse_json
    orchestrator.py          Task and Workflow (topological layers, thread pool)
    store.py                 save_run, RunData, list_runs, load_run
  agents/                    one module per agent, plus common.py (formatting and statistics helpers)
  adapters/                  tokopedia.py: real marketplace data into MarketMind's contracts (see section 7)
  ml/                        text, sentiment (PyTorch), real_reviews (real training corpus), topics, segmentation,
                             forecasting, pricing, calendar_id
  reporting/
    charts.py                Plotly chart functions, TableSource and the CHARTS registry
    html_report.py           self-contained HTML report
scripts/                     generate_data.py, evaluate_agents.py, export_sqlite.py, build_diagram_gallery.py,
                             validate_on_real_data.py, multi_seed.py, ablations.py, llm_runs.py, import_tokopedia.py
tests/                       conftest.py (shared offline run), test_system.py, test_schemas.py
docs/                        design documents, schemas/ (JSON Schemas and SQL), diagrams/ (gallery)
data/raw/                    the seven research datasets      data/ground_truth*   hidden answers
data/real/<source>/          imported real data: raw/ + manifest.json   (git-ignored; licences forbid sharing)
outputs/                     runs/, models/, cache/llm/, marketmind.db   (git-ignored)
```

## 3. Core APIs

### BaseAgent (`core/agent.py`)

| Member | Purpose |
|---|---|
| `name`, `role`, `goal`, `ml_capability` | Class attributes. They identify the agent in traces, prompts, the roster and the report. Set `ml_capability` only for agents that train or apply models. |
| `finding_prefix` | The ID prefix of the agent's findings (`"MKT"`, `"CMP"`, ...). It names the open-question finding the agent publishes when the Director sends it back with a question it cannot answer (`MKT-91` for Q1). |
| `register_tools()` | Override this to declare tools with `self.tool(name, fn, description)` |
| `use(name, *args, **kwargs)` | Calls a tool, tracing an `action` and an `observation`. Always call tools through `use`, so the call is visible. |
| `execute() -> str` | Override with the agent's logic. Return a one-line summary. |
| `run() -> AgentResult` | The lifecycle wrapper: it traces the start and end, starts the agent's time limit (`time_limit`, set by the workflow), answers any follow-up requests after `execute()`, and turns any exception into a `failed` result. Do not override it. |
| `answer_requests()`, `run_follow_up()` | Answer the Research Director's follow-up questions (messages carrying `question`) from the agent's findings, or publish an open-question finding. `run_follow_up` does only that, without redoing the analysis. |
| `think(msg)`, `warn(msg)`, `emit(kind, msg, **data)` | Write trace events |
| `put(key, value, description)` | Writes an artefact to the blackboard with provenance |
| `publish(finding)` | Adds a finding and traces it |
| `tell(recipient, content, **data)` | Leaves a message for another agent |
| `ask_llm(task, facts, max_tokens, as_json)` | Grounded LLM call. Returns `None` when no LLM is available or the run's LLM budget (`options["budget"]`) is used up, so always keep a deterministic path. |
| `self.bb`, `self.llm`, `self.tracer`, `self.ctx`, `self.options` | The run's shared services and options |

### Blackboard (`core/blackboard.py`)

`put(key, value, agent, description)`, `get(key, default)`, `require(key)` (raises `KeyError` with a clear message), `has(key)`, `keys(prefix)`, `meta()` (who wrote each key, when, and its shape), `add_finding(f)`, `findings(area=None, agent=None)`, `post(sender, recipient, content, **data)`, `inbox(recipient, since)` and `messages()`. All of them are thread-safe.

### Workflow (`core/orchestrator.py`)

`Task(id, agent_class, depends_on=(), critical=True, retries=1, timeout=None)`. `Workflow(tasks)` sorts the tasks into layers and rejects cycles (`ValueError`). `run(ctx, parallel, max_workers=3)` runs each layer on a thread pool, retries a failed task up to `retries` times (not after `AgentTimeout` or `StudyRejected`), records the attempts in `AgentResult.attempts`, and skips a task if any of its critical dependencies did not complete. `timeout` becomes the agent's `time_limit`: the agent raises `AgentTimeout` at its next `use()` or `ask_llm()` once it is over, because Python threads cannot be stopped from outside.

### Approval gates (`core/approval.py`)

`MarketResearchSystem(approver=...)` takes any callable `approver(gate, proposal) -> Decision`, where `gate` is `"plan"` or `"recommendations"` and `Decision(approved, reviewer, comment, drop)` says what to do; `drop` lists modules or recommendation IDs to remove. `request_approval(ctx, gate, proposal, actor)` asks it, traces an `approval` event and appends the decision to the blackboard's `approvals`. Three reviewers are included: `auto_approve` (the default), `ConsoleApprover` (used by `run.py --approve`; its `ask` and `say` functions can be replaced in tests) and `ApprovalBroker`, which hands a gate from the study's thread to the dashboard's thread and waits for `decide()`. A rejection raises `StudyRejected` in the Strategy agent, or stops the run after planning, and the run ends `rejected`.

### LLMClient (`core/llm.py`)

`LLMClient(provider=None, model=None, api_key=None, ...)` resolves the provider from `LLM_PROVIDER` and the keys in `.env`. Its methods are `available`, `describe()`, `complete(system, prompt, max_tokens, json_mode, temperature, agent)`, `complete_json(...)`, `ping()` and `stats`. Every failure sets `last_error` and returns `None`; it never raises into an agent. Responses are cached under `outputs/cache/llm`, keyed by a hash of the request. `parse_json` extracts JSON from fenced or chatty replies.

The model is chosen in this order: the `model` argument, `<PROVIDER>_MODEL` (for example `GROQ_MODEL`), `LLM_MODEL`, then the provider's default; the fallback model likewise from `<PROVIDER>_FALLBACK_MODEL`, `LLM_FALLBACK_MODEL` or the default. A call makes up to five attempts. A busy model (HTTP 429 or 5xx) or a hung one (timeout, dropped connection) hands that one call to the fallback at once; a model the provider has retired (a 400 or 404 saying the model is not found, decommissioned, no longer available and so on) is replaced for good, by the fallback or, without one, by the best match in the provider's model list (preview and experimental models are skipped, `latest` aliases and higher version numbers win). `last_model` records the model that answered, and every entry in `stats.log` carries it.

### Run store (`core/store.py`)

`save_run(run_dir, blackboard, tracer, meta)` writes the run folder (see [SCHEMAS.md §2](SCHEMAS.md#2-blackboard-key-registry)). `list_runs()` returns a summary of every run, newest first. `load_run(run_id)` returns a `RunData` with `meta`, `findings`, `table(key)`, `tables(prefix)`, `json(key, default)`, `text(name)` and `trace`.

## 4. Adding an agent

As an example, here is a small Promotion Analyst that measures how much promotions lift the client's sales on each channel. It runs as written against the bundled data.

**1. Write the agent** in `marketmind/agents/promotion_analyst.py`:

```python
"""Promotion Analyst: measures how much promotions lift the client's sales."""
from __future__ import annotations

import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from .common import pct


class PromotionAnalystAgent(BaseAgent):
    name = "Promotion Analyst"
    role = "Trade-marketing analyst. Measures the sales uplift from promotions."
    goal = "Show where promotions pay off for the client and where they do not."

    def register_tools(self):
        self.tool("measure_promo_uplift", self._uplift, "average units per row with and without a promotion, by channel")

    def execute(self) -> str:
        sales = self.bb.require("datasets")["sales"]
        client = self.bb.require("plan")["client"]
        uplift = self.use("measure_promo_uplift", sales[sales["brand"] == client])
        self.put("promotion.tables", {"uplift": uplift}, "Promotion uplift by channel")
        best = uplift.iloc[0]
        self.publish(Finding(
            id="PRM-01", agent=self.name, area="market", title="Where promotions pay off",
            statement=(f"Promotions lift {client}'s units most on {best['channel']} "
                       f"({pct(best['uplift'])} per listing-month versus no promotion)."),
            metrics=dict(channel=best["channel"], uplift=round(float(best["uplift"]), 4)),
            evidence=["market_sales_panel.csv"], impact=3, confidence=0.7, swot="O", tags=["promotion", "channel"]))
        return f"Promotion uplift measured on {len(uplift)} channels"

    def _uplift(self, sales: pd.DataFrame) -> pd.DataFrame:
        units = sales.assign(promo=sales["promo_flag"].astype(bool)).groupby(["channel", "promo"])["units"].mean().unstack()
        uplift = (units[True] / units[False] - 1).rename("uplift").reset_index()
        return uplift.sort_values("uplift", ascending=False).reset_index(drop=True)
```

With the bundled data it publishes: *"Promotions lift Kirana Beauty's units most on Tokopedia (+29.4% per listing-month versus no promotion)."*

**2. Register it.** Import it in `marketmind/agents/__init__.py` and add it to `PIPELINE_AGENTS`, which feeds the roster saved with every run.

**3. Schedule it.** In `ResearchDirectorAgent.build_workflow`, add `Task("promotion", PromotionAnalystAgent, ("quality",), critical=False)` and include `"promotion"` in the Strategy task's dependencies. Analysis agents should be non-critical, so that a failure degrades the study instead of stopping it. If it should run only for some briefs, add an area and keywords in `director.py` (`AREAS`, `AREA_KEYWORDS`, `QUESTION_TEMPLATES`).

**4. Connect its output.** What you need depends on how far the new evidence should reach:

| To make the new evidence ... | Change |
|---|---|
| Appear in the report | Nothing, if it uses an existing area: the Report Writer lists every finding of an area in that area's section. A new area needs an entry in `findings.AREAS`, `AREA_SECTIONS` in `reporter.py`, the section check in `critic.py` and the area enum in `finding.schema.json`. |
| Drive a recommendation | Add a play to `StrategyAgent._playbook` with `add(..., evidence=["PRM-01", ...])`. The play fires only when its evidence exists. |
| Count as grounded numbers | Nothing: the Critic reads every finding's statement and metrics. If the report prints numbers from a new artefact, add that key to `_allowed_numbers` in `critic.py`. |
| Show in the dashboard | Add a chart (section 6) and render it in a tab of `app/dashboard.py`. |
| Be answerable in chat | Nothing: the Analyst Chat retrieves every finding. Add an intent pattern to `INTENTS` in `analyst_chat.py` if its questions use new words. |

**5. Test it** (section 9), and add a row for it to the roster and finding registry in [AGENTS.md](AGENTS.md).

### Rules every agent follows

- **Numbers come from tools.** Compute every number in code. An LLM may phrase a sentence, never produce a figure. The Critic rejects any number in the prose that it cannot trace to the evidence.
- **Read through `require`, write through `put`.** Never reach into another agent's object, and never mutate a DataFrame you read from the blackboard; work on a copy.
- **Findings are self-contained.** The statement holds the numbers, `metrics` holds the same values in machine-readable form, and `evidence` names the sources. Choose impact and confidence honestly, because they drive priority.
- **Keep an offline path.** Treat `ask_llm` returning `None` as normal.
- **Fail loudly, degrade gracefully.** Raise on broken inputs; the framework records the failure, retries once, and the rest of the study continues.
- **Set `finding_prefix`** for an analysis agent, and map its area and report section in `AREA_TASKS` and `SECTION_TASKS` (`agents/director.py`), so the Director can send it back for questions the report leaves open.

## 5. Adding a tool to an existing agent

Register it in `register_tools()` with a short description of what it does (the description appears in traces and in the dashboard), and call it from `execute()` through `self.use(...)`. Keep the heavy computation in `marketmind/ml/` or as a pure function, so it can be unit-tested without a blackboard.

## 6. Adding a chart

Chart functions in `reporting/charts.py` take DataFrames and a theme mode and return a Plotly figure. Register each chart in `CHARTS` with a lambda that pulls its tables from a `TableSource`, which reads from either a live blackboard or a saved run:

```python
# in the CHARTS dict: reuse the horizontal growth-bar chart for the Promotion Analyst's table
"promo_uplift": _safe(lambda s, m: growth_bars(s.t("promotion", "uplift").rename(columns={"uplift": "growth"}),
                                               "channel", "Promotion uplift by channel", m)),
```

`s.t(group, name)` reads table `name` from the `<group>.tables` artefact, `s.j(key)` reads a JSON artefact, `s.df(key)` reads a single DataFrame artefact, and `s.client` is the client brand. `_safe` turns a missing table into "no chart" instead of an error. To use the chart in the report, list its key in the `charts` argument of the section's `add(...)` call in `reporter.py`. In the dashboard, call `chart(src, "<key>")`; in the web app, add `<PlotlyChart :run-id="id" name="<key>" />` to the view (the API serves every chart in `CHARTS` by its key, in both themes). Follow the existing palette tokens (`tk(mode)`, `brand_colors`): the client in the accent colour, competitors in greys, legends below the plot.

## 7. Adding or replacing a dataset

1. Add an entry to `DATASETS` in `config.py`: the file, `date_col` (or `None`), source and description.
2. Clean it in `DataQualityAgent`: add a tool and a step in `execute()`. Unknown tables pass through after de-duplication.
3. Write a row contract in `docs/schemas/datasets/`, and add it to `DATASET_SCHEMAS` in `tests/test_schemas.py`.
4. If it should be exported, add a table to `docs/schemas/database.sql` and a loader to `sql_export.load_datasets`.
5. Document the columns in `docs/DATA_DICTIONARY.md`.

If you replace the bundled data with real data, keep the column names and the category, channel and region labels, or update the code that relies on them: the enums in the schemas, `calendar_id.py` for the Ramadan dates, and the aspect lexicon in `ml/text.py`.

**Real-data folders and adapters.** Rather than overwrite `data/raw`, write real data to its own folder: `<folder>/raw/` with any of the seven files in their row contracts, and `<folder>/manifest.json`. `config.data_manifest()` reads the manifest; without one, the data counts as simulated. The manifest needs `kind: "real"`, `source` and `licence`, and may add `datasets` (per dataset: `source`, how fields were `derived`, which are `unknown`), `caveats` (sentences the report repeats under its limitations), `stats` and `brands`. `marketmind/adapters/tokopedia.py` is the worked example: it reads the source without downloading anything, maps it to the contracts, marks unknown fields as null instead of guessing, and writes the manifest. `scripts/import_tokopedia.py` wraps it and checks every row against the contracts. Studies then run with `python run.py --data-dir <folder>` (or `MARKETMIND_DATA_DIR`), and the agents need no changes:

- each analysis agent declares `requires`, the datasets it cannot work without (`("sales",)` for the forecaster);
- the Director's `_scan_catalog` reads brands and the period from the sales panel, or the reviews or catalogue without one, and `_drop_unavailable` leaves out the modules whose data is missing, recording why in `plan["unavailable"]`; if none of the modules the brief asks for can run, it runs those the data supports;
- agents read the folder from `config.DATA_RAW` at run time, so tests can point them elsewhere with `monkeypatch.setattr(config, "DATA_RAW", path)`;
- the run records `options["data_dir"]`, and `evaluation.evaluate` scores a run against that folder's ground truth, or reports that it has none.

## 8. Adding an LLM provider

An OpenAI-compatible provider needs only one entry in `OPENAI_STYLE` in `core/llm.py`: `base_url`, `key_env`, a default `model`, a `fallback` model (or `None`), `prefer` (substrings used to pick a replacement when the default model is retired) and `min_interval` (seconds between calls). Then add it to `AUTO_ORDER` if it should be picked automatically, and add its key to `.env.example`. Other APIs need their own `_call_<provider>` method. Follow `_call_anthropic`: lazy import, mapping every error to `last_error` and returning `None`, and recording token usage in `self.stats`. The Anthropic path uses the official SDK with `claude-opus-5-5`, `output_config={"effort": "medium"}` and the server-side fallback beta.

## 9. Testing

| Test | What it covers | Time |
|---|---|---|
| `test_text_normalisation_and_aspects`, `test_ramadan_calendar_features`, `test_parse_json_tolerates_fences`, `test_workflow_detects_cycles`, `test_offline_llm_is_unavailable` | Units: slang normalisation and aspect lexicon, the Islamic-calendar features, LLM JSON parsing, cycle detection, offline behaviour | seconds |
| `test_full_pipeline_offline` | The whole study offline: completed, QA passed with at least 85, key findings present, at least 3 recommendations, files saved | shared run |
| `test_critic_catches_invented_numbers_and_revision_fixes_them` | The reflection loop. A `FakeLLM` writes "Rp 999 trillion"; the Critic must fail it, the Director must send it back, and the revised report must pass without it. | about 1 minute |
| `tests/test_schemas.py` (5 tests) | The contracts in [SCHEMAS.md](SCHEMAS.md) | shared run |
| `tests/test_real_reviews.py` (6 tests) | The `--sentiment-data` option: emoji conversion, the three training modes on a small stand-in corpus, an unchanged cache key in the default mode, rejection of unknown modes, test metrics per source, and the model cache recorded so that the dashboard and the web API find it whether `MARKETMIND_OUTPUTS` lies inside the project or outside | seconds |
| `tests/test_failure_paths.py` (6 tests) | Graceful degradation: client names matched ignoring case and accents; an unknown client stopping the run at planning; a missing dataset skipped with a warning; a World Bank outage falling back to the cache, then to nothing; garbled LLM output leaving the rule-based plan in place; and an end-to-end run where an analyst and the Critic crash, which must still save a schema-valid run marked `unverified` with a "NOT VERIFIED" report | about 1 minute |
| `tests/test_agent_logic.py` (19 tests) | Each agent's core method on small synthetic inputs with a known answer: the Critic's number parsing, grounding at written precision (percentages, rupiah units, years, LLM blocks, code spans) and citation checks; the workflow's skip rules; Van Westendorp crossings against hand-solved values, the middle of a tied stretch of curves, the bootstrap of the recommended price and the count of answers that place the optimal price point; elasticity estimates recovering known slopes, with standard errors equal to a cluster-robust value worked out by hand and a brand whose price never moves reported as not identified; the constant-elasticity price scenarios; forecast growth for 3-, 6- and 12-month horizons (a flat market must grow 0%, measured against the same months a year earlier); the complaint-spike detector finding exactly the planted episode; the threat index; label canonicalisation; and the Strategy agent's priority rule | seconds, plus the shared run |
| `tests/test_dashboard.py` (2 tests) | Streamlit's test runner renders the real dashboard for the shared run: all 12 tabs, no exception and no tab-level error; and a rejected run shows who stopped it and why | about 45 s, plus the shared run |
| `tests/test_real_data.py` (3 tests) | The Tokopedia importer on a small archive in the dataset's exact layout (beauty filter, categories from names, brands and their spellings, prices, SPF, pack size, unknown fields left null, one row per dated review, the seller's region, contract checks, manifest, brand map); the Director planning around missing data (modules left out with reasons, the most-reviewed brand as default client, falling back to what the data supports, nothing to study); and an end-to-end study on a real-data folder with only reviews and a catalogue (consumer module only, report discloses gaps and source and never calls the data simulated, no ground-truth score) | about 1 minute |
| `tests/test_agentic.py` (13 tests) | Retries (a flaky agent recovers; a broken one fails after two attempts), the time limit (stops at the next tool call, not retried), the LLM budget, the console reviewer, decision tracing and a crashing reviewer, the dashboard broker across threads, the plan gate (modules left out, questions renumbered) and the recommendation gate (drop, renumber, reuse an unchanged decision, reject), the Director's mapping of open questions to agents, open-question answers, the Critic's half credit; and two end-to-end studies: the market analyst fails until the Director sends it back while a reviewer drops a recommendation, and a rejected plan stops the study before any analysis | about 2 minutes |
| `tests/test_llm_client.py` (12 tests) | The LLM client against a fake OpenAI-style API, with no network or key: the request sent, response parsing, token counts, caching (and that the key never reaches the cache), the retry after a rate limit, dropping JSON mode when a provider rejects it, per-provider model settings winning over the global ones, a busy (503) or hung (timeout) model handing the call to the fallback, a retired model replaced for good, an unrelated bad request that mentions the model leaving it in place, rediscovery preferring `latest` aliases over previews, soft failure on HTTP errors, and offline mode without a key | under a second |
| `tests/test_api.py` (11 tests) | The web API with FastAPI's `TestClient`, offline: the local-only guards (other hosts, non-JSON and cross-origin posts refused), API keys scrubbed from responses, 404s and path traversal, serving a built front end with client-side routes, request validation; the approval gates driven by a stub study (wrong gate, unknown items, nothing left, a double submit, the decisions handed over, the SSE stream and its resumption from `Last-Event-ID`); every read endpoint and all 32 charts in both themes on the shared run, the evaluation, the analyst chat and the sentiment tester; and one more study through both gates over HTTP (segmentation and a recommendation left out) | seconds; about 1 minute for the study, plus the shared run |
| `frontend/src/**/*.test.ts` (Vitest, 13 tests) | The overview tiles (skipped modules leave no tile, the forecast label follows the horizon), the price simulator, the model-card scores, number formatting; the KPI tiles, the approval form (left-out items, nothing left, reject) and Ask the analyst (one request per question, the conversation restored after a reload without asking again, raw HTML escaped) mounted in jsdom | a few seconds |
| `tests/test_evaluation_and_chat.py` (2 tests) | The ground-truth evaluation on the shared run, which must recover every planted insight (a regression guard for the whole system). The one exception is the concept price, a documented noise-driven miss on the bundled data ([EVALUATION.md §4.5](EVALUATION.md#45-concept-pricing)); when it misses, SEG-04 must say the pick is not settled and name a runner-up inside the true band; and the Analyst Chat's offline retrieval: a pain-point question answered from weaknesses or threats with citations, a pricing question from pricing evidence, nonsense answered with "no evidence" | seconds, plus the shared run |

Tests that run the pipeline or the dashboard are marked `slow`: `tests/conftest.py` marks every test that uses `offline_run`, and the six other end-to-end tests (the revision loop, the crashing analyst and Critic, the two agentic studies, the real-data study and the study run over the web API) carry `@pytest.mark.slow`. `python -m pytest -q -m "not slow"` runs everything else in about half a minute, which is the loop to use while coding.

`tests/conftest.py` provides the session fixture `offline_run`: one complete offline study, saved to a temporary folder (never to `outputs/runs`) and shared by every test that needs a run. Use it in new tests rather than starting another pipeline run:

```python
def test_promotion_finding(offline_run):
    system, result, run = offline_run      # MarketResearchSystem, RunResult, RunData
    assert "PRM-01" in {f.id for f in system.blackboard.findings()}
```

To test LLM behaviour without a network, subclass `LLMClient` as `FakeLLM` does in `tests/test_system.py`: override `available` and `complete` to return scripted text based on the prompt.

Useful commands:

```bash
python -m pytest -q -m "not slow"                    # fast tests, about half a minute
python -m pytest -q                                  # everything (several minutes)
python -m pytest -q --cov --cov-report=term          # everything, with line coverage of marketmind/
python -m pytest -q tests/test_schemas.py            # contracts
python -m pytest -q tests/test_api.py -m "not slow"  # the web API's fast tests
npm --prefix frontend test                           # the web app's component tests (Vitest)
python scripts/evaluate_agents.py                    # ground-truth score of the latest run
```

**Evaluation studies.** Three scripts measure more than one run can ([EVALUATION.md](EVALUATION.md) reports their results):

```bash
python scripts/multi_seed.py                         # regenerate the data with seeds 1-5 and re-run the study on each
python scripts/ablations.py                          # switch off one design choice at a time
python scripts/llm_runs.py --providers gemini groq   # full studies with real LLMs; what the Critic catches
```

`multi_seed.py` keeps every seed apart through two environment variables that `marketmind/config.py` reads: `MARKETMIND_DATA_DIR` (the folder holding `raw/` and the ground truth) and `MARKETMIND_OUTPUTS` (runs, model cache, LLM cache). Use them for any experiment that must not touch the bundled data or its runs; `scripts/generate_data.py --seed N --out <folder>/raw` writes a fresh dataset with the same planted effects. Each script writes a `summary.json` under `outputs/seeds`, `outputs/ablations` or `outputs/llm_runs`.

## 10. Debugging

- **Read the trace.** `outputs/runs/<id>/trace.jsonl` has every thought, tool call, observation, warning and error (with traceback) in order. The dashboard's Agents tab filters it by agent and event kind.
- **Run sequentially.** `python run.py --no-llm --sequential` removes thread interleaving.
- **Inspect the blackboard.** After `system.run()`, `system.blackboard.meta()` shows every key, its writer and its shape. Findings are in `system.blackboard.findings()`.
- **Reproduce a failing agent alone.** Build a `RunContext` with a `Blackboard` that holds `plan` and `datasets` (use `sql_export.clean_datasets()` for the cleaned data) and call `YourAgent(ctx).run()`. This is how the example in section 4 was checked.
- **Retrain only when needed.** The sentiment cache is keyed by a hash of the review data. Use `--retrain` after changing `ml/sentiment.py`.

## 11. Documentation and diagrams

The diagrams in `docs/*.md` are Mermaid code blocks. After editing them, rebuild the gallery, which renders every diagram on one page with SVG and PNG export:

```bash
python scripts/build_diagram_gallery.py
```

It writes `docs/diagrams/gallery.html`; open it in a browser. When you change an agent, a schema or a metric, update the matching document: [AGENTS.md](AGENTS.md) for agents, tools and findings; [SCHEMAS.md](SCHEMAS.md) and `docs/schemas/` for contracts; [EVALUATION.md](EVALUATION.md) for metrics; and the README for user-facing behaviour.

## 12. The web API and the Vue front end

The web app is a second interface beside the Streamlit dashboard, which keeps working until the web app replaces it. It changes nothing in the agent system or the run store: `api/` reads runs through `marketmind.core.store` and starts studies with `MarketResearchSystem`, exactly as `app/dashboard.py` does.

```
browser (Vue 3 app)  --JSON, SSE-->  api/ (FastAPI)  --->  marketmind (store, charts, system, approval broker)
                                          |
                                          +--> frontend/dist (the built app, same origin)
```

### Running it while developing

Two terminals, one for each server:

```bash
python -m api --reload                 # the API on http://localhost:8000, restarting on Python changes
```

```bash
npm --prefix frontend run dev          # the app on http://localhost:5173 with hot reload; /api goes to port 8000
```

Open <http://localhost:5173>. Set `MARKETMIND_API` to point the dev server at an API on another address. For the production build, `npm --prefix frontend run build` type-checks (`vue-tsc`) and writes `frontend/dist/`, which `python -m api` serves at <http://localhost:8000>; without a build it serves a page saying how to make one. The API is documented at `/api/docs` (OpenAPI).

### The API (`api/`)

| Endpoint | Purpose |
|---|---|
| `GET /api/config`, `GET /api/llm`, `POST /api/llm/ping` | The data folder (real or simulated, ready or not), brands, default brief, sentiment-data options and datasets; the LLM's status; a test request |
| `POST /api/data/generate` | Run `scripts/generate_data.py` when the data folder is empty |
| `GET /api/runs` | `list_runs()`, with each run's duration, LLM use and review mode |
| `GET /api/runs/{id}` | The run's `run_meta.json`, its KPIs (`strategy.kpis`), the forecast horizon, counts and the table keys it holds |
| `GET /api/runs/{id}/kpis`, `/findings`, `/recommendations`, `/swot`, `/trace` | The run's artefacts as saved |
| `GET /api/runs/{id}/tables`, `/tables/{key}?limit=&offset=`, `/json/{key}` | Any table (as `{columns, data, total, truncated}`, NaN as null) or JSON artefact |
| `GET /api/runs/{id}/charts/{name}?theme=light` (or `dark`) | `CHARTS[name](TableSource.from_run(run), theme).to_json()`, or `null` when the run has no data for it; cached per run |
| `GET /api/runs/{id}/report.html`, `/report.md` (`?download=true`) | The report; the HTML is sent with a `sandbox` Content-Security-Policy |
| `GET`/`POST /api/runs/{id}/evaluation` | The saved ground-truth evaluation; `POST` runs `evaluate(run)` and saves `evaluation.json` |
| `POST /api/runs/{id}/chat` | `AnalystChatAgent.answer(question, history)`: one question per call |
| `GET`/`POST /api/runs/{id}/sentiment` | Whether the run's sentiment models are on disk; score a text (label, probabilities, attention, aspects) |
| `GET /api/runs/{id}/datasets/{name}` | The first rows of a raw dataset the run studied |
| `GET /api/studies`, `POST /api/studies`, `GET /api/studies/{id}` | Studies started by this server; start one (409 while another runs) |
| `GET /api/studies/{id}/events` | Server-sent events: `trace` (each trace event, its index as the event id), `state` (when the state or a waiting gate changes) and `end` |
| `GET`/`POST /api/studies/{id}/approval` | The proposal waiting at a gate; the decision (`gate`, `approved`, `comment`, `drop`) |

**Studies.** `studies.StudyRegistry` keeps every study the server started, in the server rather than in a browser session: a reload or another tab finds a running study, and one waiting at a gate. A study runs `MarketResearchSystem.run()` in a daemon thread with an `ApprovalBroker` (reviewer `web reviewer`, 30-minute timeout) when review is on. One study runs at a time, which also keeps the second-resolution run ids unique. A decision must name the gate that is waiting and only items from its proposal, and must leave at least one item. Once a proposal is answered, a second answer to it is refused, so a double click cannot answer the next gate. The event stream polls the study's tracer every 0.4 s. A browser that reconnects sends `Last-Event-ID` and gets only the events it missed. The registry is in memory: a server restart stops running studies, and saved runs are unaffected.

**Safety.** `security.LocalOnlyMiddleware` answers only requests whose Host is `localhost`, `127.0.0.1` or `::1`, which keeps pages that rebind their domain to 127.0.0.1 out. It also accepts changes (POST) only as JSON and, when the browser sends an Origin, only from the same origin, so no other site can start a study. `python -m api --host 0.0.0.0` turns the host check off (`MARKETMIND_ALLOWED_HOSTS=*`) and warns. `SafeJSONResponse` and the event stream replace the value of every credential variable in the environment (`*_API_KEY`, `*_KEY`, `*_TOKEN`, `*_SECRET`) with `[redacted]`. No endpoint returns a key: this only guards against one echoed in a provider's error message.

### The front end (`frontend/`)

Vue 3 with `<script setup>` and TypeScript, Vite, Vue Router, Pinia, PrimeVue 4 (the Aura theme recoloured to the chart palette in `src/preset.ts`) and plotly.js (the cartesian bundle, loaded on demand). PrimeVue is pinned to 4.5.5, the last MIT-licensed release; PrimeVue 5 needs a licence key.

```
src/main.ts, App.vue         app shell: sidebar (a drawer below 1024 px), top bar on small screens, toasts
src/router.ts                routes; RUN_VIEWS lists the twelve run views in the dashboard's order
src/api.ts, src/types.ts     typed API client and response types
src/stores/app.ts            config, saved runs, the studies on the server (polled every 3 s while one runs)
src/stores/run.ts            the run on screen: summary, findings, recommendations, SWOT (cached per run)
src/views/                   Home, Runs, NewStudy, Study (live view), RunLayout (header + tabs), NotFound
src/views/run/               Overview, Agents, Market, Competition, Consumers, Segments, Forecast, Strategy,
                             Report, Ask, Evaluation, Data
src/components/              PlotlyChart, DataGrid, TableCard, FindingsList, KpiTiles, ApprovalForm, AnalystChat,
                             SentimentTester, WorkflowGraph, SkippedNotice, RunStatus, AppSidebar, ThemeToggle
src/lib/                     format.ts, kpis.ts (tiles, model card, price simulator), theme.ts, markdown.ts,
                             storage.ts (chat history), tables.ts, chat.ts
src/styles/main.css          layout, cards, tiles, chips; CSS variables for both themes
```

- **Charts.** `PlotlyChart` fetches a figure when it scrolls near the screen, moves the figure's title into the card heading (HTML wraps on a phone, a Plotly title does not), and fetches the dark or light figure again when the theme changes. Give dense charts `:min-width` so that they scroll sideways on a phone instead of shrinking. A chart without data in the run shows a short note, as the dashboard does.
- **Tables.** `TableCard` is a collapsible card for one table artefact. It loads when opened and stays hidden if the run has no such table. `DataGrid` is the sortable, scrollable PrimeVue table underneath.
- **Themes.** `lib/theme.ts` keeps the choice (system, light or dark) in `localStorage` and sets the `app-dark` class on `<html>`, which switches the CSS variables in `main.css` and PrimeVue's dark tokens. An inline script in `index.html` applies it before the first paint.
- **Lessons from the dashboard's dry run, built in.** A study belongs to the server, not to the tab that started it. A chat question is sent once, when asked, and the conversation is kept in `localStorage`, so a reload never asks the LLM again. A tile appears only when the study produced its value (`overviewTiles` skips the rest), and a view whose module the plan left out says so (`SkippedNotice`). Forecast labels use the run's `horizon_months`.

**Adding a view.** Add a component under `src/views/run/`, an entry to `RUN_VIEWS` and to the `views` map in `src/router.ts`. Read the run from `useRunStore()` and draw charts with `PlotlyChart` and tables with `TableCard`. If the view needs an artefact the API does not serve yet, prefer the generic `tables/{key}` and `json/{key}` endpoints to a new one.

**Tests.** `tests/test_api.py` covers the API (section 9). `npm --prefix frontend test` runs the Vitest tests (`src/**/*.test.ts`, jsdom, with stand-ins for `ResizeObserver` and `scrollIntoView` in `src/test-setup.ts`), and `npm --prefix frontend run typecheck` runs the type-check alone.
