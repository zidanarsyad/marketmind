# MarketMind user guide

This guide is for the people who run studies and read the results: marketing managers, research analysts, and students and lecturers using MarketMind as a case study. It covers installation, running a study from the command line, the dashboard or the web app, writing a good brief, reading the report, asking follow-up questions, switching on an LLM, scoring a run and troubleshooting. Developers should also read [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

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

The web app (section 3, "From the web app") also needs [Node.js](https://nodejs.org) 20.19 or newer, once, to build its pages: `npm --prefix frontend install` and then `npm --prefix frontend run build`. Running it afterwards needs only Python.

## 3. Running a study

### From the command line

```bash
python run.py
```

This runs the default brief for Kirana Beauty. It prints the agents' trace live, then a summary of every agent's status, the approval decisions, any follow-ups the Research Director sent, the top recommendations and the path to the report. The first run takes 3 to 4 minutes because it trains the deep-learning model; later runs reuse the model and take about 1 to 2 minutes on a laptop.

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
| `--approve` | Review the research plan and the recommendations yourself, at the terminal (section 3, "Approving the plan and the recommendations") |
| `--retries 1` | Extra attempts for an agent that fails (default 1; `0` turns retries off) |
| `--agent-timeout 900` | Time limit per agent, in seconds (default 900). An agent over its limit stops at its next step and is reported as failed |
| `--max-llm-calls 40`, `--max-llm-tokens 300000` | The LLM budget for one run (these are the defaults). Past it, the agents carry on without the LLM |
| `--data-dir data/real/tokopedia-2025` | Study another data folder, for example imported real data (section 11) |

The exit code is 0 when the run completes with its report checked by the Critic. It is 1 when the run fails, ends `unverified` because the Critic itself did not finish, or is rejected by a reviewer. So you can schedule `run.py` from a script and alert on a non-zero exit.

### Approving the plan and the recommendations

A study has two approval gates. The first comes after the Research Director has planned, before any analysis runs; the second after the Strategy agent has drafted its recommendations, before the executive summary and the report are written. At each gate you can approve, trim, or stop the study:

| Gate | Approve | Trim | Reject |
|---|---|---|---|
| Plan | the study runs as planned | leave modules out (for example `pricing,forecast`); their questions go. Leaving out segmentation also leaves out pricing | the study stops with status `rejected` and no report |
| Recommendations | all of them go into the report | drop some by ID (for example `R2,R5`); the rest are renumbered, and the report lists the dropped ones under its limitations | the study stops with status `rejected` and no report |

With `python run.py --approve`, the terminal shows each proposal and waits: press Enter to approve, type `n` to reject, or type the modules or IDs to drop; you can add a comment. In the dashboard, switch on **Review the plan and recommendations myself** before **Run study**: the live panel pauses at each gate with a form, and the study resumes when you press **Approve** or **Reject the study**. A gate left unanswered in the dashboard for 30 minutes approves automatically.

Without a reviewer, both gates approve automatically, and the report says that no reviewer was asked. Every decision, with the reviewer, the time, what was dropped and the comment, is kept in the report's Appendix D, in the Agents tab and in `run_meta.json`.

### When the team goes back for more

After the Critic's first check, the Research Director looks for research questions that no finding answers and analysis sections missing from the report, for example because an agent failed. It sends the responsible agent back with the question: an agent that failed runs again, and one that finished answers from its findings or says plainly that the question stays open. The strategy, the report and the check are then redone. Each agent is sent back at most once. The report's methodology and Appendix D say who was sent back and why, and open questions are listed under the limitations.

### From the dashboard

```bash
streamlit run app/dashboard.py
```

Open <http://localhost:8501>. In the sidebar:

1. **Generate datasets** appears only if the data is missing.
2. **New research run**: edit the brief, pick the client brand, choose whether to use the LLM, which reviews the sentiment models learn from (shown once the real reviews are downloaded), whether to retrain the model, whether to run the analysts in parallel, and whether to review the plan and recommendations yourself, then press **Run study**. A live panel shows each agent's status and trace while the study runs, and pauses with a form at each approval gate if you chose to review. **Run study** stays disabled until the study ends.
3. **LLM** shows the active provider. **Test LLM connection** sends a short test request.
4. **Saved runs** switches between past studies. Each one is labelled with its run id, QA score and client.

### From the web app

The web app shows the same studies in a responsive interface that also works on a phone, in a light or a dark theme. Build it once (section 2), then start it:

```bash
python -m api
```

Open <http://localhost:8000>. It opens on the newest run with a report. In the sidebar (on a phone, behind the menu button at the top left):

1. **New study** opens the study form: the brief, the client brand, the LLM switch, which reviews the sentiment models learn from, retraining, parallel analysts, and **Review the plan and recommendations myself**. **Run study** starts the study on the server and opens its live view. If the data is missing, the form offers **Generate datasets** first.
2. The live view lists each agent's status and streams the trace as the agents think, call tools and publish findings. If you chose to review, the study pauses at each gate with a form: untick modules (plan) or recommendations to leave them out, add a comment, and press **Approve** or **Reject the study**. When the study ends, the app opens its results.
3. **Saved runs** lists the latest studies with their QA score; **All** opens the full list, which you can filter by client, run or LLM. Switching runs keeps the view you are on.
4. **LLM** shows the active provider, and **Test LLM connection** sends a short test request. The three buttons at the bottom choose a light, system or dark theme.

The study runs on the server, not in the page. Reloading the page, closing it, or opening the app in another tab finds it again under **Study running** (or **Waiting for your approval**) at the top of the sidebar. A gate left unanswered for 30 minutes approves automatically, as in the dashboard. One study runs at a time.

The app only answers on this computer. `python -m api --host 0.0.0.0` shares it on your network; anyone who can reach it can then read the runs and start studies, but API keys stay in `.env` on your computer and are never sent to a browser. `python -m api --port 8080` uses another port. The Streamlit dashboard keeps working beside it, on its own port.

## 4. Writing a good brief

The Research Director reads the brief with simple rules, and refines the plan with the LLM when one is available. These parts of the brief steer the plan:

| What you write | What the Director does |
|---|---|
| A brand name from the data ("GlowNesia wants to ...") | Makes that brand the client, unless you pass `--client`. In the dashboard the **Client brand** menu always decides, so pick the brand there |
| "next 6 months" or "6 bulan" | Sets the forecast horizon (between 3 and 12 months; the default is 12). Growth is then measured against the same months a year earlier, and the report and dashboard label the forecast with the horizon |
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

The web app has the same twelve views, as tabs under the run's title (on a phone, swipe the tab strip sideways). Tables open from the cards titled like the dashboard's expanders, and wide tables and charts scroll inside their card.

| Tab | What to look at |
|---|---|
| **Overview** | Headline KPIs, the top findings and the priority actions. Open "Research brief" to see the brief the study answered. |
| **Agents** | The workflow graph, the agent roster, the messages between agents, the approval decisions and the Director's follow-ups, and the full trace explorer. Filter by agent or event kind (for example `approval`) to see exactly how a conclusion was reached. |
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
| Google Gemini | free tier | `GEMINI_API_KEY=...` (default model `gemini-flash-latest`, fallback `gemini-flash-lite-latest`) | <https://aistudio.google.com/apikey> |
| Groq | free tier | `GROQ_API_KEY=...` (default `qwen/qwen3.8-27b`) | <https://console.groq.com/keys> |
| OpenRouter (`:free` models) | free | `OPENROUTER_API_KEY=...` (default `nvidia/nemotron-3.5-super-vl:free`, fallback `google/gemma-4-26b-a4b-it:free`) | <https://openrouter.ai/keys> |
| Ollama (runs locally) | free | `LLM_PROVIDER=ollama` | <https://ollama.com> |
| Any OpenAI-compatible endpoint | varies | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | |
| Claude (Anthropic SDK) | paid | `ANTHROPIC_API_KEY=...` | <https://console.anthropic.com> |

With `LLM_PROVIDER=auto` (the default), MarketMind uses the first key it finds, in the order Groq, Gemini, OpenRouter, Claude. Groq comes first because it was the fastest in the real-LLM runs (about 1 s per call) with every number grounded; set `LLM_PROVIDER` to use another. To choose models, set `<PROVIDER>_MODEL` and `<PROVIDER>_FALLBACK_MODEL` (for example `OPENROUTER_MODEL`), or `LLM_MODEL` and `LLM_FALLBACK_MODEL` for whichever provider is used. The fallback answers when the main model is busy, rate-limited or hung, and replaces it for good if the provider has retired it; with no fallback, MarketMind picks a replacement from the provider's model list. Free model line-ups change often: if a model you set stops working, check the provider's list (for OpenRouter, <https://openrouter.ai/models?q=:free>). Paste only the key after the `=`; a line such as `OPENROUTER_API_KEY=OPENROUTER_API_KEY=sk-or-...` is rejected by the provider. `LLM_MIN_INTERVAL` sets the number of seconds between calls, for free tiers with per-minute limits. Responses are cached in `outputs/cache/llm`, so re-running the same study does not use up your quota. Restart the dashboard after editing `.env`, then use **Test LLM connection**.

**Privacy.** When an LLM is on, the brief, the plan, the findings, the recommendations, aggregate segment profiles and your chat questions are sent to that provider. The raw datasets are never sent. To keep everything on your machine, use Ollama or `--no-llm`.

## 9. Scoring a run against the ground truth

Because the data is simulated, the true answers are known, so you can check whether the agents found them:

```bash
python scripts/evaluate_agents.py
```

This scores the latest run. To score an earlier one, add its run id (for example `python scripts/evaluate_agents.py 20261110-182213`). The Evaluation tab does the same. The 25 checks, and the results of the reference run, are described in [EVALUATION.md](EVALUATION.md). The scores are saved to `evaluation.json` in the run folder.

One run is one sample. Three scripts measure more: `python scripts/multi_seed.py` regenerates the market with five other random seeds and runs the study on each (5 to 10 minutes per seed, since each new dataset trains its own models), `python scripts/ablations.py` switches off one design choice at a time, and `python scripts/llm_runs.py` runs the study with each LLM provider that has a key and records what the Critic caught. Their results are in [EVALUATION.md](EVALUATION.md).

## 10. Exporting to SQL

```bash
python scripts/export_sqlite.py
```

This builds `outputs/marketmind.db`, a SQLite database containing the clean datasets and the latest run. Add `--all-runs` to load every saved run. Open it with any SQLite tool (for example DB Browser for SQLite) or connect it to a BI tool. [SCHEMAS.md §5](SCHEMAS.md#5-relational-model) describes the tables and gives example queries.

## 11. Studying real data

A study can run on real data kept in its own folder, next to the bundled simulated data. Real reviews from Tokopedia take three steps ([DATA_SOURCES.md §8](DATA_SOURCES.md#8-studying-real-data) has the details):

1. Download `archive.zip` of the Tokopedia Product and Review Dataset from Kaggle (an account is needed; CC BY-NC 4.0, research and education only).
2. Import it: `python scripts/import_tokopedia.py path/to/archive.zip`. This writes `data/real/tokopedia-2025/` with the facial-skincare reviews and products in MarketMind's formats, checks every row, and lists the brands with the most reviews.
3. Study it: `python run.py --data-dir data/real/tokopedia-2025 --client "<one of those brands>"`. For the dashboard, set the folder first: `MARKETMIND_DATA_DIR=data/real/tokopedia-2025 streamlit run app/dashboard.py`.

What changes with real data:

- **Only the modules the data supports run.** Reviews and a product catalogue support the consumer analysis: sentiment, aspects, complaint spikes, competitor crises and complaint topics. The market, competition, segmentation, pricing and forecast modules need a sales panel, market sizes or a survey; the Research Director leaves them out, and the report says which ones and why. If the brief asks only for modules the data cannot support, the Director studies what it can and says so.
- **The report states the source and its caveats**, for example that brands were derived from product names and that the region is the seller's location, under Methodology and Risks and Limitations.
- **The sentiment models learn from the real reviews themselves.** By contrast, a study on the simulated data trains them on simulated reviews only, and the model card, the report and the dashboard's model tester warn that such models do not transfer to real text (use `--sentiment-data study+real` for that).
- **There is no ground truth.** The Evaluation tab and `scripts/evaluate_agents.py` say so instead of scoring. Judge the results by the evidence each finding cites and by the QA certificate.
- **The data stays private.** `data/real/` is git-ignored; the licence forbids redistribution.

You can also bring your own files: put any of the seven CSV files in a folder's `raw/`, with the columns in [DATA_DICTIONARY.md](DATA_DICTIONARY.md) and the types in `docs/schemas/datasets/`, add a `manifest.json` with `"kind": "real"`, `"source"` and `"licence"`, and run with `--data-dir`. The categories, channels and regions must match the lists in the data dictionary, or the code that relies on them must be extended (see the developer guide). [DATA_SOURCES.md](DATA_SOURCES.md) lists real public datasets that fit each file, with their licences.

## 12. Where files are kept

| Path | Contents |
|---|---|
| `outputs/runs/<run_id>/` | One folder per study: `report.html`, `report.md`, `findings.json`, `run_meta.json`, `trace.jsonl`, `tables/*.csv`, `json/*.json` and, once scored, `evaluation.json` |
| `outputs/models/` | Cached sentiment models, reused while the review data is unchanged |
| `outputs/cache/llm/` | Cached LLM responses |
| `outputs/marketmind.db` | The SQLite export |
| `data/external/` | The cached World Bank data and downloaded real corpora |
| `data/real/<source>/` | Imported real data: `raw/` and `manifest.json` (never committed) |

Old runs are never deleted automatically. Delete a run's folder under `outputs/runs/` to remove it from the dashboard.

## 13. Troubleshooting

| Symptom | What to do |
|---|---|
| "Datasets not found" in the dashboard | Press **Generate datasets**, or run `python scripts/generate_data.py`. |
| "Too few labelled reviews to train the sentiment models" | The data folder has fewer than 100 reviews with text, or a sentiment class is nearly empty. Import more products (lower `--min-reviews`), or use `--sentiment-data real`. |
| A real-data study left most modules out | Expected: they need a sales panel, market sizes or a survey, which review data does not have. The report lists them under Methodology. |
| The first run is slow | It is training the deep-learning model (about 2 minutes on a laptop CPU). Later runs reuse it. |
| LLM shows "offline (deterministic reasoning)" | There is no key in `.env`, or the key is wrong. Fix `.env`, restart, and use **Test LLM connection**. The text after "offline" gives the reason. |
| "rate limited, retrying ..." in the trace | The free tier's per-minute limit was reached. MarketMind waits and retries; set `LLM_MIN_INTERVAL` (for example `4`) to space out calls. |
| "World Bank API unreachable" warning | You are offline. MarketMind uses the cached data, or continues without macro indicators; the rest of the study is unaffected. |
| The run stops at planning with "Unknown client" | The name matches no brand in the sales data, even ignoring case and accents. Use one of the brands the message lists. |
| The run ends `rejected` | A reviewer rejected the plan or the recommendations. The dashboard shows who and why; no report was written. Run the study again with a revised brief. |
| "LLM budget for this run is used up" in the trace | The run reached `--max-llm-calls` or `--max-llm-tokens`. The remaining text is written without the LLM; raise the limits if you need more. |
| An agent fails with `AgentTimeout` | It ran past `--agent-timeout` (900 s by default). On a slow machine, a first run's model training can take longer; raise the limit. |
| The run ends `unverified` and the report says "NOT VERIFIED" | The Critic agent crashed, so the report's numbers, citations and coverage were not checked. The Agents tab and `trace.jsonl` show the error; fix it and run the study again before relying on the report. |
| An analysis agent shows "failed" but the study completes | That is graceful degradation: the other agents carry on. The Agents tab shows the error and its traceback in the trace. |
| QA certificate says NOT PASSED | Read the open issues in the certificate; each names the failing check. LLM text that fails a check is replaced during the revisions, so issues that remain usually come from the deterministic report: a missing section, a research question no finding answers (often because an analysis agent failed), or fewer than three recommendations. |
| Port 8501 is already in use | `streamlit run app/dashboard.py --server.port 8502` |
| The web app says "The web app has not been built yet" | Build it once: `npm --prefix frontend install`, then `npm --prefix frontend run build`, and reload the page. |
| Port 8000 is already in use | `python -m api --port 8080` |
| The web app says a study "is not running on the server" | The server was restarted while the study ran, so the study stopped. Saved runs are not affected; start the study again. |
| The web app answers "This server only answers on this computer" | You opened it under a name other than `localhost` or `127.0.0.1`. Use <http://localhost:8000>, or start it with `--host 0.0.0.0` to share it. |
| Colleagues on your network cannot open the dashboard or the web app | By design: both only answer on this machine. To share them, run `streamlit run app/dashboard.py --server.address 0.0.0.0` or `python -m api --host 0.0.0.0`. |
| `python -m pytest` takes a minute or two | The end-to-end tests run the whole pipeline. That is expected. |
