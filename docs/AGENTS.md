# MarketMind agent specifications

This document specifies each of the eleven pipeline agents and the on-demand Analyst Chat agent. For each one it gives the agent type and PEAS profile, the tools it may call, what it reads from and writes to the blackboard, the findings it publishes, how it uses the LLM, and what happens when it fails. It describes the code in `marketmind/agents/`. Related documents: [ARCHITECTURE.md](ARCHITECTURE.md) explains how the agents fit together, and [SCHEMAS.md](SCHEMAS.md) gives the exact shape of every artefact named here.

---

## 1. Roster

| # | Agent (class) | Module | Agent type | Learns from data | Workflow task | Critical | LLM use |
|---|---|---|---|---|---|---|---|
| 1 | Research Director (`ResearchDirectorAgent`) | `director.py` | Goal-based planner and supervisor | no | `plan` (before the graph) | yes | optional plan refinement |
| 2 | Data Collection (`DataCollectionAgent`) | `data_collector.py` | Model-based reflex | no | `collect` | yes | none |
| 3 | Data Quality (`DataQualityAgent`) | `data_quality.py` | Model-based reflex (condition-action rules) | no | `quality` | yes | none |
| 4 | Market & Trend Analyst (`MarketTrendAnalystAgent`) | `market_analyst.py` | Model-based analyst | no | `market` | no | none |
| 5 | Competitive Intelligence (`CompetitiveIntelligenceAgent`) | `competitor_analyst.py` | Utility-based scorer | no | `competition` | no | none |
| 6 | Consumer Insight (`ConsumerInsightAgent`) | `consumer_insight.py` | Learning agent (deep learning) | **yes, DL** | `consumer` | no | none |
| 7 | Consumer Segmentation (`SegmentationAgent`) | `segmentation.py` | Learning agent (unsupervised ML) | **yes, ML** | `segmentation` | no | optional persona names |
| 8 | Demand Forecasting (`DemandForecastingAgent`) | `forecaster.py` | Learning agent (supervised ML) | **yes, ML** | `forecast` | no | none |
| 9 | Strategy (`StrategyAgent`) | `strategist.py` | Utility-based | no | `strategy` | yes | optional executive summary |
| 10 | Report Writer (`ReportWriterAgent`) | `reporter.py` | Goal-based (communicative) | no | `report` | yes | optional section commentary |
| 11 | Critic (QA) (`QualityAssuranceAgent`) | `critic.py` | Utility-based evaluator | no | `qa` | see section 3.11 | none, by design |
| - | Analyst Chat (`AnalystChatAgent`) | `analyst_chat.py` | Reactive, retrieval-based | no | on demand, after a run | - | optional answer writing |

"Critical" is the `Task.critical` flag. When a critical task fails, every task that depends on it is skipped and the run ends with status `failed`. When a non-critical analysis task fails, only its own findings are missing; Strategy and the Report Writer still run with the evidence that exists.

## 2. What every agent shares

Every pipeline agent subclasses `BaseAgent` (`marketmind/core/agent.py`) and runs the same loop:

1. **Perceive.** Read inputs from the blackboard (`self.bb.require(key)` fails loudly if a key is missing; `self.bb.get(key)` returns `None`).
2. **Reason.** Record thoughts with `self.think(...)`, and optionally call the LLM with `self.ask_llm(task, facts)`.
3. **Act.** Call registered tools through `self.use(name, ...)`. Each call is traced as an `action` event and then an `observation` event.
4. **Publish.** Write artefacts with `self.put(key, value)`, publish `Finding`s with `self.publish(...)` and leave messages with `self.tell(recipient, ...)`.

| Mechanism | Contract |
|---|---|
| Tools | Registered in `register_tools()` with a name and a one-line description. An agent can only act through its own tools, and the descriptions appear in the trace and the dashboard. |
| Tracing | Every status change, thought, action, observation, finding, message, LLM call, warning and error becomes an `Event` (see `trace_event.schema.json`). |
| Findings | The unit of knowledge: a statement, metrics, evidence, impact (1-5), confidence (0-1), an optional SWOT tag and topic tags. Priority = impact x confidence. |
| LLM calls | `ask_llm` builds a system prompt from the agent's name, role and goal plus the shared `GROUNDING_RULES` (use only the given facts, never invent numbers, cite finding IDs). The facts are sent as JSON, cut off at 14,000 characters. With no LLM, or if the call fails, it returns `None` and the agent continues deterministically. |
| Result | `run()` returns an `AgentResult` (`completed`, `failed` or `skipped`) with timing and counts of findings, tool calls and LLM calls. Any exception is caught, its traceback is traced, and the agent returns `failed`. |

### Task environment

| Property | MarketMind | Reason |
|---|---|---|
| Observable | Partially | Agents see samples of the market (a six-brand panel, reviews, one survey), never the whole market. |
| Agents | Multi-agent, cooperative | All agents share one goal and one blackboard. |
| Deterministic | Stochastic | Consumer behaviour and data noise are random. Models are seeded so that runs can be reproduced. |
| Episodic | Sequential | Later agents depend on earlier outputs, and the QA loop revisits the report. |
| Static | Static within a run, dynamic between runs | Each run works on a fixed snapshot of the data; external APIs and data files change between runs. |
| Discrete | Discrete actions over continuous data | Tool calls are discrete; the metrics they produce are continuous. |
| Known | Partly unknown | True elasticities, segments and sentiment have to be learned from data. |

---

## 3. Agent specifications

### 3.1 Research Director

Turns the free-text brief into a validated research plan, dispatches the specialist agents as a dependency graph and enforces the QA gate.

| Field | Specification |
|---|---|
| Type | Goal-based planner and supervisor |
| Performance measure | Every research question answered; QA gate passed within two revisions |
| Environment | The client's business brief, the available datasets, the Critic's verdicts |
| Sensors | `options.brief`, `options.client`, the dataset catalogue (scanned from `data/raw`), `qa.result` |
| Actuators | Tools below; writes `plan`; builds the `Workflow`; sends revision requests to the Report Writer |
| LLM use | `refine_plan_with_llm` (JSON). The refinement is accepted only if it returns 3-8 objectives and its questions cover every area of the rule-based plan; otherwise the rule-based plan stands. |
| On failure | The run stops with status `failed`, and the trace is saved. |

| Tool | What it does |
|---|---|
| `scan_data_catalog` | Lists the brands, categories, channels and months in the sales panel, and checks which datasets exist. |
| `parse_brief` | Rule-based parser. Finds the client (a brand named in the brief, else `--client`, else the default), the horizon (3-12 months), the modules (keyword match per area) and a concept name, and writes one templated question per active area plus a strategy question. |
| `refine_plan_with_llm` | Lets the LLM sharpen the objectives and questions (optional; validated as above). |

Planning rules: if no area keyword matches, all six areas are switched on. Pricing implies segmentation (the Van Westendorp study lives in the survey agent). Competition or consumer questions imply market context. The forecast task runs when either `forecast` or `pricing` is active.

**Supervision** (`quality_loop`): if `qa.result.passed` is false, the Director sends the Report Writer up to 20 of the Critic's issues, sets `options.revision`, and re-runs the Report Writer and then the Critic. It does this at most twice (`max_revisions=2`). If the report still fails, it is released with a warning and its open issues are listed in the QA certificate.

### 3.2 Data Collection Agent

| Field | Specification |
|---|---|
| Type | Model-based reflex |
| Performance measure | All registered datasets loaded with provenance; macro data as fresh as is reachable |
| Environment | `data/raw/*.csv`, World Bank Open Data API, GNews or NewsAPI |
| Sensors | The file system and HTTP responses |
| Actuators | Tools below; writes `datasets.raw`, `data.catalog`, `external.macro`, `external.news` |
| Findings | `DAT-01` Evidence base; `MAC-01` Macro tailwinds (only when macro data is available) |
| LLM use | None |
| On failure | Critical. Inside the agent, every source degrades gracefully: a missing file produces a warning and that dataset is skipped; if the World Bank API is unreachable it falls back to the cache in `data/external`, and then to no macro data; news is optional. |

| Tool | What it does |
|---|---|
| `load_internal_datasets` | Reads every dataset in `config.DATASETS` and builds a catalogue (rows, columns, coverage, size, source, modified date). |
| `fetch_world_bank_indicators` | Eight indicators for Indonesia, 2015-2025: GDP per capita, real GDP growth, population, urban share, inflation, internet users, household consumption growth and working-age share. Saves each successful response to the cache. |
| `fetch_news_headlines` | Recent Indonesian skincare headlines, only if `GNEWS_API_KEY` or `NEWSAPI_KEY` is set. |

### 3.3 Data Quality Agent

| Field | Specification |
|---|---|
| Type | Model-based reflex (condition-action cleaning rules) |
| Performance measure | Defects caught and documented; quality score per dataset |
| Environment | Raw tables carrying planted defects |
| Sensors | `datasets.raw` |
| Actuators | Tools below; writes `datasets`, `dq.report`, `dq.scorecard`, `dq.caveats` |
| Findings | `DAT-02` Data quality |
| LLM use | None |
| On failure | Critical. All analysis agents depend on the cleaned `datasets`. |

| Tool | What it does |
|---|---|
| `clean_sales_panel` | Standardises labels (stray spaces, letter case), drops duplicates, non-positive units and outliers, and imputes missing discounts. |
| `clean_reviews` | De-duplicates reviews, parses dates and flags rating-only reviews (`has_text`). |
| `screen_survey_responses` | Removes speeders, straight-liners, respondents who fail the attention check, and invalid ages. |
| `clean_social_posts` | Removes reposts and normalises fields. |
| `validate_reference_data` | Validates the product catalogue and the market-size table. |

Any other table (such as `social_labels`) is passed through after de-duplication. Quality score per dataset = 100 - 200 x (share of rows removed) - 50 x (1 - completeness) - 2 x (number of warnings), clipped to 0-100. The overall score is weighted by input rows. The caveats (simulated data, a panel of tracked brands only, star ratings as noisy labels, the survey base after screening) are carried into the report's limitations section.

### 3.4 Market & Trend Analyst

| Field | Specification |
|---|---|
| Type | Model-based analyst |
| Performance measure | Market size, growth drivers and seasonality explained with evidence |
| Environment | Clean sales panel, market-size estimates, social posts, macro indicators |
| Sensors | `datasets` (`sales`, `market_size`, `social`), `external.macro` |
| Actuators | Tools below; writes `market.tables` (12 tables) |
| Findings | `MKT-01` to `MKT-06` |
| LLM use | None |
| On failure | Not critical. Without it, the market questions go unanswered and the Critic's coverage check flags them. |

| Tool | What it does |
|---|---|
| `size_market` | Market size, CAGR, and the trends in local-brand share and online share. |
| `decompose_growth` | Growth over the last 12 months by category, channel and region. |
| `estimate_seasonality` | Monthly seasonal index, and the uplift from Ramadan/Eid and mega-sales (11.11, 12.12). |
| `detect_social_trends` | Momentum in the share of voice of each skincare topic. |

### 3.5 Competitive Intelligence Agent

| Field | Specification |
|---|---|
| Type | Utility-based scorer |
| Performance measure | Threats and white spaces correctly ranked |
| Environment | Sales, catalogue, reviews, social posts, survey |
| Sensors | `datasets`, `plan.client` |
| Actuators | Tools below; writes `competition.tables` (10 tables) |
| Findings | `CMP-01` to `CMP-09` |
| LLM use | None |
| On failure | Not critical. The recommendations that depend on its findings (channel, regions, threat, stock) do not fire. |

| Tool | What it does |
|---|---|
| `compute_market_share` | Value and volume share, momentum and share trend for each brand. |
| `channel_region_index` | Where the client over- or under-indexes, by channel, category and region (index = client mix / market mix). |
| `price_value_map` | Price index against rating and sentiment for each brand. |
| `share_of_voice` | Each brand's share of social conversation, by platform. |
| `score_threats` | Threat index = weighted sum of min-max scaled factors: growth 0.25, share 0.20, share gain 0.15, price proximity 0.15, category overlap 0.10, social share of voice 0.10 and channel overlap 0.05. The overlaps are cosine similarities between the rival's mix and the client's. |
| `find_white_space` | Matches consumer needs and trend momentum against the supply of SKUs. Topics are weighted by attention (mean share of voice), so that a small emerging topic does not dominate. |
| `estimate_stockout_loss` | Estimates the sales lost to stock-outs. |

### 3.6 Consumer Insight Agent (deep learning)

The system's deep-learning agent. It learns sentiment from reviews, checks that the model transfers to social media, and turns text into insight about aspects, anomalies and topics.

| Field | Specification |
|---|---|
| Type | Learning agent (supervised deep learning plus unsupervised text mining) |
| Performance measure | Held-out macro-F1 on reviews; transfer macro-F1 on hand-labelled social posts; precision of complaint-spike detection |
| Environment | Indonesian reviews (slang, emojis), social posts, a labelled social sample, survey, catalogue |
| Sensors | `datasets` (`reviews`, `social`, `social_labels`, `survey`, `catalog`), `plan.client`, `options.sentiment_data`; with that option, the real review corpus in `data/external/ulasan-beauty-products` |
| Actuators | Tools below; writes `consumer.tables` (15 tables) and `consumer.model_card`; caches trained models per training mode in `outputs/models/sentiment`, `sentiment_study_real` or `sentiment_real` |
| Findings | `CON-01` to `CON-09` |
| LLM use | None. All language understanding runs in local models. |
| On failure | Not critical. Without it there is no pain-point evidence, so the Strategy agent's "fix the issue" play does not fire. |

| Tool | What it does |
|---|---|
| `train_sentiment_models` | Trains a TF-IDF + logistic regression baseline and the BiGRU-attention network, tunes a soft-vote ensemble, and selects the best model by validation macro-F1. |
| `validate_transfer` | Scores each model on 400 hand-labelled social posts (out of domain) and picks the scorer for social posts and review clauses. Runs when at least 50 labelled posts are available. |
| `score_reviews` | Predicts sentiment for every review that has text. |
| `aspect_based_sentiment` | Splits reviews into clauses, detects 9 Indonesian aspects with a lexicon, and scores each clause. |
| `detect_complaint_spikes` | Flags months where an aspect's complaint rate rises above its baseline, using a Poisson test plus thresholds on counts and rates. |
| `mine_complaint_topics` | NMF topic model over the client's negative reviews. |
| `score_social_posts` | Applies the chosen model to the unlabelled social posts, with domain rules (hashtag stripping, a rule for questions, a neutral band of 0.2). |
| `analyse_skin_type_fit` | Compares reviews from people with sensitive skin of fragranced and fragrance-free products. |

**Learning protocol.** Labels come from star ratings (weak supervision: 1-2 stars negative, 3 neutral, 4-5 positive). The data is split into train, validation and test sets. The BiGRU uses length-bucketed batches, word dropout of 10% and early stopping on validation macro-F1 (patience 3). The ensemble weight is tuned on validation (0.3 to 0.7). The selection uses validation macro-F1 only; the test set is touched once, to report metrics for all three candidates. This keeps the reported score honest: in the reference run ([EVALUATION.md](EVALUATION.md)) the ensemble scores slightly higher on test, but the BiGRU won on validation and stays selected. A trained model is cached under a hash of its training data and is reused until that data changes or `--retrain` is passed. The model card records the metrics of every candidate, the selection, the training history and the transfer results.

**Training data option** (`--sentiment-data`, or the dashboard's "Sentiment training data"). `study`, the default, trains on the study's own reviews. `study+real` adds the train and validation splits of a real corpus of about 72,000 Shopee/Tokopedia beauty reviews (`marketmind/ml/real_reviews.py`); the splits are then stratified by source and label, and the card adds test metrics per source. `real` trains on the real reviews only, and scores the model against the star ratings of all the study's reviews, which it never saw (`study_reviews_check`). If the corpus has not been downloaded, the agent warns and falls back to `study`. CON-01 and the ground-truth evaluation always report the score on the study's reviews, so the modes can be compared. The architecture diagram is in [ARCHITECTURE.md §9](ARCHITECTURE.md#9-model-architectures).

### 3.7 Consumer Segmentation Agent (machine learning)

| Field | Specification |
|---|---|
| Type | Learning agent (unsupervised machine learning) |
| Performance measure | Silhouette score; segments that are distinct and actionable; a defensible launch price |
| Environment | Survey responses (attitudes, behaviours, concept test, Van Westendorp questions) |
| Sensors | `datasets.survey`, `plan.client` |
| Actuators | Tools below; writes `segmentation.tables` (8 tables) and `segmentation.model_card` |
| Findings | `SEG-01` to `SEG-05` |
| LLM use | Optional persona names (JSON). They are accepted only if every segment gets a unique name of 2-40 characters; otherwise the rule-based names stay. |
| On failure | Not critical. Without it, the concept-launch recommendation does not fire. |

| Tool | What it does |
|---|---|
| `choose_number_of_segments` | Fits K-Means for k = 3 to 8 and compares the silhouette, Calinski-Harabasz and Davies-Bouldin scores. The k with the highest silhouette wins. |
| `fit_segments` | Fits the final K-Means model (k-means++, `n_init=20`) on standardised features. |
| `profile_personas` | Profiles each segment (demographics, spend, concerns, channels, brands, distinctive drivers) and names it. |
| `evaluate_concept` | Concept purchase intent by segment. Primary target = the segment with the highest intent among those holding at least 10% of consumers. Secondary target = the largest remaining pool of likely buyers (segment share x top-2-box intent). |
| `price_sensitivity_meter` | Van Westendorp analysis on the target segments: the acceptable range (PMC to PME), the optimal and indifference prices, and a recommended price point. |

### 3.8 Demand Forecasting Agent (machine learning)

| Field | Specification |
|---|---|
| Type | Learning agent (supervised machine learning and econometrics) |
| Performance measure | Backtest error (WAPE) against the seasonal-naive baseline; how close the estimated elasticity is to the truth |
| Environment | Monthly sales panel, Indonesian retail calendar |
| Sensors | `datasets.sales`, `plan.client`, `plan.horizon_months` |
| Actuators | Tools below; writes `forecast.tables` (14 tables) and `forecast.model_card` |
| Findings | `FCT-01` to `FCT-05` |
| LLM use | None |
| On failure | Not critical. Without it, the pricing recommendation does not fire and the market outlook is missing. |

| Tool | What it does |
|---|---|
| `build_monthly_panel` | Aggregates sales to about 150 monthly series (brand x category x channel), with calendar features. |
| `estimate_price_elasticity` | Fixed-effects log-log demand regression for each brand, with HC1 robust standard errors. |
| `backtest_models` | Rolling-origin backtest (3 folds x 6 months) of four candidates: gradient boosting, seasonal naive, seasonal naive with drift, and a gradient boosting + drift ensemble. The candidate with the lowest series WAPE wins. |
| `forecast_demand` | Forecasts the next `horizon_months` months with the winning model, with 80% intervals derived from the backtest errors. |
| `simulate_price_scenarios` | Uses the client's elasticity to estimate the effect of price changes on volume, revenue and profit. |

The gradient-boosting model is a global, direct multi-horizon `HistGradientBoostingRegressor`. Its target is year-on-year log growth minus 3-month momentum (a residual), and it uses 17 features: momentum, level, Ramadan/Eid and mega-sale calendar shifts, price, discount, changes in stock-outs, and category and channel codes. Direct (rather than recursive) prediction avoids feeding errors back into later horizons.

### 3.9 Strategy Agent

| Field | Specification |
|---|---|
| Type | Utility-based |
| Performance measure | Recommendation priority = impact x confidence x effort factor; every recommendation backed by evidence |
| Environment | Every finding and table the analysts produced |
| Sensors | All findings, `plan`, `market.tables`, `competition.tables`, `consumer.tables`, `segmentation.tables`, `forecast.tables`, `datasets.market_size` |
| Actuators | Tools below; writes `strategy.swot`, `strategy.opportunities`, `strategy.recommendations`, `strategy.kpis`, `strategy.exec_summary` and, when an LLM is available, `strategy.exec_summary_llm` |
| Findings | None. It synthesises findings rather than producing new ones. |
| LLM use | Optional executive summary (5-7 bullets, 120-220 words, each claim cited). It is stored separately and the Critic checks it. |
| On failure | Critical. Without it the report cannot be written. |

| Tool | What it does |
|---|---|
| `rank_findings` | Sorts all findings by priority (impact x confidence). |
| `build_swot` | Maps the findings tagged S, W, O or T into a SWOT, with up to five items per quadrant. |
| `size_opportunities` | Puts a rupiah value on each opportunity (`OPP-1` to `OPP-5`) and states the basis for it. The concept opportunity assumes 5% year-1 conversion among top-2-box intenders, and the report states this assumption. |
| `apply_strategy_playbook` | Evidence-triggered rules. Each play fires only if at least one of its evidence findings exists. Its impact is the highest impact among that evidence, and its confidence is the mean confidence. The effort factor is 1.0 for Low, 0.85 for Medium and 0.7 for High effort. Recommendations are numbered R1, R2, ... in order of priority and placed on a horizon: Quick win (0-3 months), Core move (0-6 or 0-12 months) or Strategic bet. |
| `draft_executive_summary` | Writes a deterministic summary from the key findings, and optionally an LLM version. |

Playbook rules (each fires only when its evidence exists): channel growth engine (CMP-02, MKT-03, CMP-07); fix the pain point (CON-03, CON-09); launch the concept at the Van Westendorp price (SEG-02, SEG-04, CMP-08, CON-07, MKT-06); hold list prices if demand is elastic (FCT-04, CON-06); expand distribution in growth regions (CMP-04, MKT-04); defend against the top threat (CMP-05, SEG-05); win over a competitor's customers during its crisis (CON-05, SEG-05); plan stock and campaigns around Ramadan (MKT-05, CMP-09, FCT-01).

### 3.10 Report Writer Agent

| Field | Specification |
|---|---|
| Type | Goal-based (communicative) |
| Performance measure | All required sections present; every claim traceable to evidence |
| Environment | Plan, findings, strategy outputs, analysis tables, model cards, Critic feedback |
| Sensors | `plan`, all findings, `strategy.*`, `*.tables`, `*.model_card`, `data.catalog`, `dq.scorecard`, `dq.caveats`, its inbox |
| Actuators | Tools below; writes `report.commentary`, `report.sections`, `report.markdown`, `report.html` |
| Findings | None |
| LLM use | Optional "so what" commentary, 2-3 sentences per section, and the LLM executive summary. Each LLM text is wrapped in `<!-- llm:<key> -->` ... `<!-- /llm -->` markers so that the Critic can check it block by block. |
| On failure | Critical. If the report cannot be written, the run fails. |

| Tool | What it does |
|---|---|
| `compose_report` | Assembles the numbered sections: Executive Summary, Research Objectives and Answers, Methodology and Data, one section per active area (Market Overview, Competitive Landscape, Consumer Insights, Segments and Personas, Pricing, Demand Forecast), SWOT Analysis, Recommendations, Sized Opportunities, Risks and Limitations, and an Appendix. The text is built from finding statements, so it is grounded by construction. |
| `write_section_commentary` | Asks the LLM for commentary, once per area that has findings. |
| `render_html_report` | Renders a self-contained HTML report with interactive Plotly charts (from the shared chart library). |

**Revision behaviour.** On a revision (`options.revision` > 0), the agent reads the Critic's and the Director's messages, collects the `block` keys of the rejected LLM blocks, and replaces each of them with its deterministic equivalent. Rejected blocks build up across revisions, so a block that was rejected once never comes back.

### 3.11 Critic Agent (QA)

The Critic checks the work of the generators. It is fully deterministic, so the checker never shares the failure modes of the LLM it checks.

| Field | Specification |
|---|---|
| Type | Utility-based evaluator |
| Performance measure | QA score out of 100; no unsupported number released |
| Environment | The report text, and every number the tools produced |
| Sensors | `report.markdown`, all findings, `plan`, `strategy.*`, the model cards |
| Actuators | Tools below; writes `qa.result` and `qa.history`; sends issues to the Report Writer when the report fails |
| Findings | None |
| LLM use | None, by design |
| On failure | The QA gate is skipped and the report is saved without a QA certificate. The run status is still `completed` (the system treats only `collect`, `quality`, `strategy` and `report` as essential), but the run's metadata shows no QA score, so it is visible as unverified. |

| Tool | What it does |
|---|---|
| `collect_evidence_numbers` | Gathers every number in the finding statements and metrics, the recommendations, KPIs, SWOT, plan, model cards and sized opportunities. Each number is expanded with x100 (for ratios of 3 or less) and /10^3, /10^6, /10^9 and /10^12 (for rupiah values). |
| `check_numeric_grounding` | Extracts every number in the prose (tables, headings and quotes are excluded) and checks it against the evidence. A number is grounded if it lies within half a unit of its last written decimal place, or within 0.5% relative. Integers from 0 to 12 and years from 1990 to 2035 always pass. An ungrounded number in an LLM block is a critical issue tied to that block; in deterministic text it is a major issue. |
| `check_structure_and_coverage` | Checks the required sections, a section for every active module, an answer to every research question (some finding in its area), and the disclosure of simulated data and limitations. |
| `check_citations_and_evidence` | Every `[XXX-NN]` citation must name a real finding; an invented citation inside an LLM block is critical. Every recommendation must cite valid evidence, and there must be at least three recommendations. |

Score = 15 x structure + 20 x coverage + 35 x grounding + 10 x citations + 15 x recommendations + 5 x disclosure, where each check scores 0-1 (grounding scores 1.0 once at least 98% of numbers are grounded). **Pass = a score of at least 85 and no critical issue.**

---

## 4. Analyst Chat Agent (on demand)

Answers follow-up questions about a finished run, in the dashboard's "Ask the analyst" tab, using retrieval-augmented generation over that run's evidence.

| Field | Specification |
|---|---|
| Type | Reactive, retrieval-based |
| Performance measure | The answer is relevant and every claim is cited |
| Environment | One saved run (findings and recommendations) and the user's questions |
| Sensors | `RunData.findings`, `strategy.recommendations`, the question and the last 6 turns of the conversation |
| Actuators | Writes an answer and its sources (shown in the dashboard) |
| LLM use | Optional. Writes a 2-5 sentence answer using only the retrieved evidence, with citations. Offline, it quotes the top three pieces of evidence. |
| On failure | If retrieval finds nothing relevant, it says so and suggests topics it can answer. |

Retrieval score for each evidence item = TF-IDF cosine similarity (1-2 grams, sublinear term frequency) + 0.35 for each question intent the item matches (for example "problem" favours weaknesses and pain points, "price" favours the pricing area) + a small priority bonus when an intent matched. It returns the top 5 items scoring above 0.05.

## 5. Finding registry

Findings marked † are published only when the evidence meets the agent's threshold (for example, a complaint spike that passes the Poisson test). When a finding is absent, the recommendations that depend on it do not fire. Titles in angle brackets are filled in at run time.

| ID | Agent | Area | Title |
|---|---|---|---|
| DAT-01 | Data Collection | data | Evidence base |
| MAC-01 † | Data Collection | market | Macro tailwinds |
| DAT-02 | Data Quality | data | Data quality |
| MKT-01 | Market & Trend | market | Market size and growth |
| MKT-02 | Market & Trend | market | Fastest-growing categories |
| MKT-03 | Market & Trend | market | Channel shift to social commerce |
| MKT-04 | Market & Trend | market | Regional growth outside Java's core |
| MKT-05 | Market & Trend | market | Seasonality: Ramadan and mega-sales |
| MKT-06 † | Market & Trend | market | Rising consumer conversation topics |
| CMP-01 | Competitive Intelligence | competition | \<Client\> market position |
| CMP-02 † | Competitive Intelligence | competition | Under-indexed on \<fastest channel\> |
| CMP-03 | Competitive Intelligence | competition | Channel stronghold: \<channel\> |
| CMP-04 † | Competitive Intelligence | competition | Weak presence in fast-growing regions |
| CMP-05 | Competitive Intelligence | competition | Top competitive threat: \<brand\> |
| CMP-06 | Competitive Intelligence | competition | Price positioning |
| CMP-07 † | Competitive Intelligence | competition | Share of voice |
| CMP-08 † | Competitive Intelligence | competition | White space |
| CMP-09 † | Competitive Intelligence | competition | Sales lost to stock-outs |
| CON-01 | Consumer Insight | consumer | Deep-learning sentiment model |
| CON-02 † | Consumer Insight | consumer | What consumers love about \<client\> |
| CON-03 † | Consumer Insight | consumer | Complaint spike: \<aspect\> |
| CON-04 † | Consumer Insight | consumer | Second complaint spike: \<aspect\> |
| CON-05 † | Consumer Insight | consumer | Competitor crisis: \<brand\> |
| CON-06 † | Consumer Insight | consumer | Value-for-money perception is slipping |
| CON-07 † | Consumer Insight | consumer | Sensitive skin needs fragrance-free |
| CON-08 † | Consumer Insight | consumer | Loyalty and social sentiment |
| CON-09 † | Consumer Insight | consumer | Complaint themes in \<client\>'s negative reviews |
| SEG-01 | Segmentation | segmentation | \<k\> consumer segments |
| SEG-02 | Segmentation | segmentation | Primary target: \<persona\> |
| SEG-03 | Segmentation | segmentation | Secondary target: \<persona\> |
| SEG-04 | Segmentation | pricing | Concept price research (Van Westendorp) |
| SEG-05 † | Segmentation | segmentation | \<Rival\> owns '\<persona\>' |
| FCT-01 | Demand Forecasting | forecast | Market outlook |
| FCT-02 | Demand Forecasting | forecast | \<Client\> baseline outlook |
| FCT-03 | Demand Forecasting | forecast | Category outlook |
| FCT-04 | Demand Forecasting | pricing | \<Client\> price elasticity |
| FCT-05 | Demand Forecasting | forecast | Forecast model quality |

With the bundled data, all 37 findings are published.

## 6. Messages between agents

Agents never call each other directly. Apart from shared artefacts, the only direct communication is a message left on the blackboard (`Blackboard.post`, read with `inbox(recipient)`).

| Sender to recipient | When | Content | `data` payload |
|---|---|---|---|
| Critic to Report Writer | The QA verdict fails | "QA failed with score S; N issues to fix" | `issues`: every issue |
| Research Director to Report Writer | Before each revision | "Revise the report to resolve the QA issues" | `issues`: the first 20 issues |

Each issue is an object `{check, severity, block, message}`. `check` is one of `structure`, `coverage`, `grounding`, `citations`, `recommendations` or `disclosure`; `severity` is `critical` or `major`; `block` names the LLM block to replace, or is `null` for issues in deterministic text. See `qa_result.schema.json`.

## 7. Adding or changing an agent

See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md#4-adding-an-agent). In short: subclass `BaseAgent`, register tools, read inputs with `require`, publish findings with a new ID prefix, add a `Task` in `ResearchDirectorAgent.build_workflow`, add the class to `PIPELINE_AGENTS`, and extend the Strategy playbook and the Report Writer if the new findings should affect recommendations or report sections.
