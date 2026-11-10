# MarketMind user guide

This guide is for the people who run studies and read the results: marketing managers, research analysts, and students and lecturers using MarketMind as a case study. It covers installation, running a study from the command line or the dashboard, writing a good brief, reading the report, asking follow-up questions, switching on an LLM, scoring a run and troubleshooting. Developers should also read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

---

## 1. What you get from a study

You give MarketMind a business brief in plain English. Eleven agents then plan the study, collect and clean the data, analyse the market, competitors and consumers, forecast demand, build a strategy and write a report, and a Critic agent checks every number before the report is released. Each study produces:

- **A client report** (`report.html` and `report.md`) with an executive summary, an answer to every research question, a SWOT, prioritised recommendations with KPIs and owners, sized opportunities, limitations and a QA certificate.
- **An interactive dashboard** for exploring every analysis, the agents' reasoning trace and the evidence behind each claim.
- **A saved run folder** with every finding, table and model card, which you can reload, compare, score or export to SQL later.

The bundled scenario is the Indonesian local facial-skincare market from January 2023 to October 2026. The client is *Kirana Beauty*, competing with five other local brands. All the data is simulated and all the brands are fictional.

## 2. Installation

You need Python 3.10 or newer (MarketMind was developed and tested on 3.12) and about 2 GB of disk space for PyTorch. No GPU is needed.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/generate_data.py
```

**macOS or Linux:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py
```

`generate_data.py` writes the seven research datasets to `data/raw/`, and the hidden answers used for scoring to `data/ground_truth.json` and `data/ground_truth/`. It is seeded, so it produces the same data every time; the repository already includes its output, so this step is only needed if you delete or change the data. If PyTorch fails to install, install the CPU build from <https://pytorch.org> first and then run `pip install -r requirements.txt` again.

`requirements.txt` allows compatible version ranges. To reproduce the exact versions under which the test suite last passed, install `requirements-lock.txt` instead.

## 3. Running a study

### From the command line

```bash
python run.py
```

This runs the default brief for Kirana Beauty. It prints the agents' trace live, then a summary of every agent's status, the top recommendations and the path to the report. The first run takes about 2 minutes because it trains the deep-learning model; later runs reuse the model and take about 50 seconds.

| Option | Effect |
|---|---|
| `--brief "..."` | Use your own brief |
| `--brief-file brief.txt` | Read the brief from a text file |
| `--client "GlowNesia"` | Set the client brand: Kirana Beauty, Lumière Lab, DewiSkin, GlowNesia, Aurelia Derma or Purabotanica. Case, accents and extra spaces don't matter (`"lumiere lab"` works). An unknown name stops the run at planning, with the list of valid brands. |
| `--no-llm` | Run fully offline, even if an API key is configured |
| `--retrain` | Retrain the sentiment models instead of reusing the cached ones |
| `--sentiment-data study+real` | Train the sentiment models on the study's reviews plus about 72,000 real Shopee/Tokopedia beauty reviews; `real` uses the real reviews only, and `study` (the default) the study's reviews only. Download the real reviews first ([DATA_SOURCES.md](DATA_SOURCES.md)); each new mix trains once, for a few minutes, and is then cached. |
| `--sequential` | Run the analysis agents one at a time (slower; useful for debugging) |
| `--quiet` | Do not stream the trace |

The exit code is 0 when the run completes with its report checked by the Critic. It is 1 when the run fails, or ends `unverified` because the Critic itself did not finish. So you can schedule `run.py` from a script and alert on a non-zero exit.

### From the dashboard

```bash
streamlit run app/dashboard.py
```

Open <http://localhost:8501>. In the sidebar:

1. **Generate datasets** appears only if the data is missing.
2. **New research run**: edit the brief, pick the client brand, choose whether to use the LLM, which reviews the sentiment models learn from (shown once the real reviews are downloaded), whether to retrain the model and whether to run the analysts in parallel, then press **Run study**. A live panel shows each agent's status and trace while the study runs.
3. **LLM** shows the active provider. **Test LLM connection** sends a short test request.
4. **Saved runs** switches between past studies. Each one is labelled with its run id, QA score and client.

## 4. Writing a good brief

The Research Director reads the brief with simple rules, and refines the plan with the LLM when one is available. These parts of the brief steer the plan:

| What you write | What the Director does |
|---|---|
| A brand name from the data ("GlowNesia wants to ...") | Makes that brand the client, unless you pass `--client` |
| "next 6 months" or "6 bulan" | Sets the forecast horizon (between 3 and 12 months; the default is 12) |
| Market words (market size, trend, growth, category, channel, region) | Switches on the market analysis |
| Competition words (competitor, rival, share, position, benchmark) | Switches on the competitive analysis |
| Consumer words (consumer, sentiment, review, pain point, complaint, social) | Switches on the consumer analysis |
| Segment words (segment, persona, target, audience, concept) | Switches on segmentation |
| Price words (price, pricing, elasticity, willingness to pay) | Switches on pricing research and the forecaster |
| Forecast words (forecast, demand, outlook, projection) | Switches on the demand forecast |
| "... a barrier-repair moisturizer concept", or launch / new product | Names the concept to test |

If no topic words match, every module runs. The Director always adds a strategy question ("where should the client play and how can it win?").

Example briefs:

- *"GlowNesia needs to recover from its counterfeit crisis. Assess consumer sentiment and complaints, our competitive position and the demand outlook for the next 6 months."*
- *"Purabotanica is considering a sunscreen launch. Which consumer segments should we target, at what price, and how big is the market?"*

## 5. Touring the dashboard

| Tab | What to look at |
|---|---|
| **Overview** | Headline KPIs, the top findings and the priority actions. Open "Research brief" to see the brief the study answered. |
| **Agents** | The workflow graph, the agent roster, the messages between agents, and the full trace explorer. Filter by agent or event kind to see exactly how a conclusion was reached. |
| **Market** | Market size and CAGR, growth by category, channel and region, seasonality (Ramadan/Eid, 11.11 and 12.12) and rising topics. |
| **Competition** | Shares and momentum, channel and region indices, the price-value map, share of voice, the threat index, white space and stock-out losses. |
| **Consumers (DL)** | The sentiment model card and confusion matrix, sentiment by brand and month, the aspect heatmap, complaint spikes, topics and social sentiment. Under "Try the deep-learning model" you can type any review and see the predicted sentiment, the attention weights (where the model looked) and the sentiment of each aspect. |
| **Segments** | Personas on a PCA map, what each segment values, the concept test by segment and the Van Westendorp price curves. |
| **Forecast & pricing** | Market and client forecasts with 80% intervals, backtest results, forecast drivers, elasticities and a price simulator. |
| **Strategy** | SWOT, the recommendations (each with its evidence, KPI, owner, timeline and priority) and the sized opportunities with their assumptions. |
| **Report** | The full HTML report, with download buttons for HTML and Markdown. |
| **Ask the analyst** | A chat that answers questions about this study and cites its evidence (see section 7). |
| **Evaluation** | Scores the run against the planted ground truth (see section 9). |
| **Data** | The dataset catalogue, the data quality scorecard, a preview of each dataset and, if a news key is set, the latest headlines. |

## 6. Reading the report

- **Citations.** Text such as `[CMP-02]` refers to a finding. Every finding has an ID, a statement with its numbers, the evidence it came from, an impact score (1-5) and a confidence score (0-1). The Strategy tab and `findings.json` list them all. [AGENTS.md §5](AGENTS.md#5-finding-registry) explains what each ID means.
- **Recommendations** are ranked by priority = impact x confidence x effort factor. They are grouped as Quick wins (0-3 months), Core moves (0-6 or 0-12 months) and Strategic bets.
- **Analyst commentary** blocks and an LLM-written executive summary appear only when an LLM is switched on. They are checked like the rest of the report.
- **The QA certificate** at the end gives the Critic's verdict, its score out of 100, how many numbers in the prose were traced to evidence, and any open issues. A report passes with a score of at least 85 and no critical issue. "NOT PASSED" means the report was released after two revisions with issues still open; read them before you use the report. "NOT VERIFIED" means the Critic itself did not finish, so nothing in the report was checked.
- **Risks and Limitations** lists the caveats the Data Quality agent recorded, for example that the data is simulated and that shares are shares of the tracked panel.

## 7. Asking the analyst

The **Ask the analyst** tab answers questions about the selected run, using only that run's findings and recommendations, and lists the sources it used. Example questions:

- "What is our biggest problem?"
- "Who is the main competitive threat and why?"
- "What price should we launch the concept at?"
- "Which channel should we invest in?"
- "What does the forecast say for next year?"

Without an LLM it quotes the three most relevant pieces of evidence. With an LLM it writes a short answer from the same evidence and cites the IDs. If nothing relevant is found, it says so rather than guessing.

## 8. Switching on an LLM (optional)

MarketMind works completely without an LLM. With one, the Director refines the plan, the Strategy agent drafts a narrative executive summary, the Report Writer adds commentary, the Segmentation agent names the personas, and the analyst chat answers in natural language. Numbers still come only from the analysis tools, and the Critic checks every number the LLM writes.

Copy `.env.example` to `.env` and set **one** of these:

| Provider | Cost | Setting | Get a key |
|---|---|---|---|
| Google Gemini | free tier | `GEMINI_API_KEY=...` | <https://aistudio.google.com/apikey> |
| Groq | free tier | `GROQ_API_KEY=...` | <https://console.groq.com/keys> |
| OpenRouter (`:free` models) | free | `OPENROUTER_API_KEY=...` | <https://openrouter.ai/keys> |
| Ollama (runs locally) | free | `LLM_PROVIDER=ollama` | <https://ollama.com> |
| Any OpenAI-compatible endpoint | varies | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | |
| Claude (Anthropic SDK) | paid | `ANTHROPIC_API_KEY=...` | <https://console.anthropic.com> |

With `LLM_PROVIDER=auto` (the default), MarketMind uses the first key it finds. `LLM_MODEL` overrides the provider's default model, and `LLM_MIN_INTERVAL` sets the number of seconds between calls, for free tiers with per-minute limits. Responses are cached in `outputs/cache/llm`, so re-running the same study does not use up your quota. Restart the dashboard after editing `.env`, then use **Test LLM connection**.

**Privacy.** When an LLM is on, the brief, the plan, the findings, the recommendations, aggregate segment profiles and your chat questions are sent to that provider. The raw datasets are never sent. To keep everything on your machine, use Ollama or `--no-llm`.

## 9. Scoring a run against the ground truth

Because the data is simulated, the true answers are known, so you can check whether the agents found them:

```bash
python scripts/evaluate_agents.py
```

This scores the latest run. To score an earlier one, add its run id (for example `python scripts/evaluate_agents.py 20261104-144556`). The Evaluation tab does the same. The 25 checks, and the results of the reference run, are described in [EVALUATION.md](EVALUATION.md). The scores are saved to `evaluation.json` in the run folder.

## 10. Exporting to SQL

```bash
python scripts/export_sqlite.py
```

This builds `outputs/marketmind.db`, a SQLite database containing the clean datasets and the latest run. Add `--all-runs` to load every saved run. Open it with any SQLite tool (for example DB Browser for SQLite) or connect it to a BI tool. [SCHEMAS.md §5](SCHEMAS.md#5-relational-model) describes the tables and gives example queries.

## 11. Using your own data

1. Replace the CSV files in `data/raw/` with your own, keeping the file names and columns described in [DATA_DICTIONARY.md](DATA_DICTIONARY.md). The row contracts in `docs/schemas/datasets/` give the exact types and allowed values.
2. Make sure the categories, channels and regions match the lists in the data dictionary, or extend the code that relies on them (see the developer guide).
3. Run a study with your client brand. The Data Quality agent cleans the files and records what it fixed.

The ground-truth evaluation applies only to the bundled simulated data. With real data, judge the results by the evidence each finding cites and by the QA certificate. [DATA_SOURCES.md](DATA_SOURCES.md) lists real public datasets that fit each file, with their licences.

## 12. Where files are kept

| Path | Contents |
|---|---|
| `outputs/runs/<run_id>/` | One folder per study: `report.html`, `report.md`, `findings.json`, `run_meta.json`, `trace.jsonl`, `tables/*.csv`, `json/*.json` and, once scored, `evaluation.json` |
| `outputs/models/` | Cached sentiment models, reused while the review data is unchanged |
| `outputs/cache/llm/` | Cached LLM responses |
| `outputs/marketmind.db` | The SQLite export |
| `data/external/` | The cached World Bank data |

Old runs are never deleted automatically. Delete a run's folder under `outputs/runs/` to remove it from the dashboard.

## 13. Troubleshooting

| Symptom | What to do |
|---|---|
| "Datasets not found" in the dashboard | Press **Generate datasets**, or run `python scripts/generate_data.py`. |
| The first run is slow | It is training the deep-learning model (about 2 minutes on a laptop CPU). Later runs reuse it. |
| LLM shows "offline (deterministic reasoning)" | There is no key in `.env`, or the key is wrong. Fix `.env`, restart, and use **Test LLM connection**. The text after "offline" gives the reason. |
| "rate limited, retrying ..." in the trace | The free tier's per-minute limit was reached. MarketMind waits and retries; set `LLM_MIN_INTERVAL` (for example `4`) to space out calls. |
| "World Bank API unreachable" warning | You are offline. MarketMind uses the cached data, or continues without macro indicators; the rest of the study is unaffected. |
| The run stops at planning with "Unknown client" | The name matches no brand in the sales data, even ignoring case and accents. Use one of the brands the message lists. |
| The run ends `unverified` and the report says "NOT VERIFIED" | The Critic agent crashed, so the report's numbers, citations and coverage were not checked. The Agents tab and `trace.jsonl` show the error; fix it and run the study again before relying on the report. |
| An analysis agent shows "failed" but the study completes | That is graceful degradation: the other agents carry on. The Agents tab shows the error and its traceback in the trace. |
| QA certificate says NOT PASSED | Read the open issues in the certificate; each names the failing check. LLM text that fails a check is replaced during the revisions, so issues that remain usually come from the deterministic report: a missing section, a research question no finding answers (often because an analysis agent failed), or fewer than three recommendations. |
| Port 8501 is already in use | `streamlit run app/dashboard.py --server.port 8502` |
| Colleagues on your network cannot open the dashboard | By design: `.streamlit/config.toml` limits it to this machine. To share it, run `streamlit run app/dashboard.py --server.address 0.0.0.0`. |
| `python -m pytest` takes a minute or two | The end-to-end tests run the whole pipeline. That is expected. |
