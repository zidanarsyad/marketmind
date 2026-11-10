# MarketMind evaluation report

This report measures how well MarketMind does its job. The question is not only "does it run?" but "does the team of agents find what is really in the market, with models that are honestly validated, a report whose every number is grounded, and in reasonable time?" The bundled data is simulated with **planted ground truth**: every market effect the generator builds in is recorded in `data/ground_truth.json` and `data/ground_truth/*.csv`. The whole multi-agent system can therefore be scored objectively, which is rarely possible with real market data.

---

## 1. Headline results

| Dimension | Measure | Result |
|---|---|---|
| Insight recall (whole system) | Planted insights recovered | **25 / 25 checks passed** |
| Deep learning: sentiment | Held-out macro-F1 / accuracy (2,924 reviews) | **0.821 / 0.906** (BiGRU-attention, selected on validation) |
| Deep learning: transfer | Macro-F1 on 400 hand-labelled social posts | **0.918** (ensemble scorer) |
| Deep learning: transfer | Accuracy against hidden labels, all 10,958 social posts | **0.913** (macro-F1 0.894) |
| External validation: real text | Macro-F1 on 3,750 real Shopee/Tokopedia beauty reviews: default models / with real reviews added to training (`--sentiment-data study+real`, which keeps 0.820 on the study's reviews and 25 / 25 checks) | **0.43-0.47 / 0.662** (section 4.6) |
| Aspect-based sentiment | Aspect precision / polarity accuracy (3,000 mentions) | **0.923 / 0.979** |
| Segmentation (ML) | Agreement with the true segments (adjusted Rand index) | **0.989** (k = 5, silhouette 0.257) |
| Forecasting (ML) | Backtest WAPE, brand x category x channel | **13.7%**, against 17.5% for the seasonal-naive benchmark |
| Price elasticity | Client estimate against truth | **-1.37** (95% CI -1.51 to -1.22) against a true -1.30 |
| Concept pricing | Recommended price against the true optimal band | **Rp 89,900**, inside Rp 80,000-100,000 |
| Data quality | Planted defects caught | **All**: 20 invalid and 145 duplicate sales rows, 180 bad survey responses |
| Governance | Critic QA score / numbers grounded | **100 / 100**, with 412 of 412 numbers in the prose traced to evidence |
| Efficiency | Wall-clock time, models cached / first run | **48 s** / about 2 minutes |

## 2. Method

**Reference run.** Run `20261104-144556`: the default brief (Kirana Beauty, all six modules), offline (no LLM), with cached sentiment models and parallel analysis agents, on an 8-thread laptop CPU with Python 3.12. The figures in this report come from that run's `evaluation.json`, model cards and tables. Section 8 explains how to reproduce them.

**What is measured.**

1. **Insight recall.** `marketmind/evaluation.py` runs 25 checks that compare the agents' published findings with the planted truth. Each check reads the machine-readable `metrics` of a finding (for example `CMP-02.metrics.channel`) rather than its prose, so it cannot be gamed by wording.
2. **Model quality.** Each learning agent is scored on held-out or hidden labels that the agents never see during the run: `data/ground_truth/social_sentiment.csv` (the true sentiment of every social post), `review_aspects.csv` (the true aspects and polarities of the reviews) and `survey_segments.csv` (the true segment of every respondent).
3. **Data quality.** The defects injected into the raw files are compared with what the Data Quality agent reports it fixed.
4. **Governance.** The Critic's QA verdict on the released report, plus the tests that prove the QA loop works (section 6).
5. **Efficiency.** Time per agent and per run, taken from the trace.
6. **External validation.** The sentiment models are also scored on two real, openly licensed Indonesian datasets (section 4.6), because results on simulated text alone cannot show how the models handle real language.

**Test plan.** The evaluation works at five levels. The first four run automatically with `python -m pytest -q`; the fifth runs with `scripts/evaluate_agents.py` or from the dashboard.

| Level | What is tested | How | Pass criterion |
|---|---|---|---|
| Unit | Text normalisation and aspect lexicon, Ramadan/Eid calendar features, LLM JSON parsing, workflow cycle detection, offline LLM behaviour | `tests/test_system.py`, 5 tests | Exact expected outputs |
| Agent logic | Each agent's core method on synthetic inputs with a known answer: Critic grounding and citations, workflow skip rules, Van Westendorp crossings, elasticity recovery, price scenarios, the complaint-spike detector, the threat index, label cleaning, the priority rule | `tests/test_agent_logic.py`, 11 tests | The known answer, e.g. the planted spike months, hand-solved price points, elasticities within 0.1 of the truth |
| Dashboard | The real Streamlit app rendering a saved run | `tests/test_dashboard.py` | All 12 tabs render with no exception or tab-level error |
| LLM client | Requests, parsing, caching, retries and fallbacks against a fake provider API | `tests/test_llm_client.py`, 6 tests | Each behaviour as specified, with no network and no key |
| Regression | The 25 ground-truth checks and the Analyst Chat on a fresh offline run | `tests/test_evaluation_and_chat.py`, 2 tests | 25 / 25 checks pass; chat answers cite relevant evidence |
| End to end | A complete offline study | `test_full_pipeline_offline` | Status completed, QA passed with a score of at least 85, key findings present, at least 3 recommendations, files saved |
| Agent cooperation | The Critic, the Director and the Report Writer reflection loop, with a scripted LLM that invents a number | `test_critic_catches_invented_numbers_and_revision_fixes_them` | First QA pass fails; the revised report passes without the invented number; a revision message was sent |
| Contracts | Every artefact, row and SQL table against the published schemas | `tests/test_schemas.py`, 5 tests | No schema errors; no foreign-key violations; brand shares sum to 1 |
| Failure paths | Unknown client, missing dataset, World Bank outage, garbled LLM output, and an analyst and the Critic crashing in one run | `tests/test_failure_paths.py`, 6 tests | Clear errors or warnings; the study completes around failed agents and is marked `unverified` when the Critic did not run |
| Acceptance | Whether the system finds the planted truth | `marketmind/evaluation.py`, 25 checks | Each check's rule in section 3 |

## 3. Insight recall: 25 / 25

| Area | Check | Planted truth | Found by the agents | Pass rule |
|---|---|---|---|---|
| Market | Fastest-growing category | Sunscreen | Sunscreen | exact match |
| Market | Fastest-growing channel | TikTok Shop | TikTok Shop | exact match |
| Market | Fastest-growing region | Kalimantan & Sulawesi | Kalimantan & Sulawesi | one of the two fastest true regions |
| Market | Rising topics | peptide, refill, skin barrier, ceramide | all 4 | recall of at least 75% |
| Market | Declining topics | niacinamide, glass skin, mugwort | all 3 | recall of at least 66% |
| Competition | Client's under-indexed channel | TikTok Shop | TikTok Shop (index 0.40) | exact match |
| Competition | Top competitive threat | GlowNesia or Lumière Lab | Lumière Lab | one of the two |
| Competition | White space | Fragrance-free ceramide moisturizer, Rp 60-120k | Fragrance-free ceramide/barrier moisturizer, Rp 60-120k | mentions fragrance-free and moisturizer |
| Consumer | Client's top pain point | Packaging (pump defect) | Packaging | exact match |
| Consumer | Timing of the pain point | Feb-Apr 2026 | Feb-Apr 2026 | the periods overlap |
| Consumer | Competitor crisis | GlowNesia authenticity, May-Jul 2026 | GlowNesia authenticity, May-Jul 2026 | brand, aspect and period |
| Consumer | Backlash after the price rise | Kirana price complaints after Jul 2025 | detected | a price-related spike or finding |
| Segmentation | Number of segments | 5 | 5 | exact match |
| Segmentation | Segment recovery | ARI of at least 0.80 | 0.989 | threshold |
| Segmentation | Concept target segment | Sensitive-Skin Minimalists | Sensitive-Skin Minimalists | the chosen segment's members are mostly that true segment |
| Pricing | Recommended concept price | Rp 80,000-100,000 | Rp 89,900 | inside the band |
| Pricing | Client price elasticity | -1.30 | -1.366 | error of at most 0.2 |
| Models | Sentiment on held-out reviews | macro-F1 of at least 0.75 | 0.821 | threshold |
| Models | Transfer to all social posts | accuracy of at least 0.85 | 0.913 | threshold |
| Models | Aspect precision / polarity | at least 0.80 / at least 0.85 | 0.923 / 0.979 | both thresholds |
| Models | Forecast against the naive benchmark | WAPE below 0.175 | 0.137 | beats seasonal naive |
| Data | Invalid sales rows caught | 20 (12 negative, 8 outliers) | 20 | all of them |
| Data | Duplicate sales rows removed | 145 | 145 | at least 95% |
| Data | Low-quality survey responses caught | 180 (72 speeders, 48 straight-liners, 60 attention fails) | 180 | at least 95% |
| Governance | Report passed the QA gate | passed | 100 / 100 | the Critic passed it |

## 4. Model evaluation

### 4.1 Consumer Insight: sentiment (deep learning)

The labels come from star ratings (1-2 negative, 3 neutral, 4-5 positive). That gives 19,487 reviews with text, with a strong imbalance: 2,840 negative, 1,669 neutral and 14,978 positive. Macro-F1 is therefore the headline metric, because accuracy alone would reward a model that always says "positive". The split is 13,640 reviews for training, 2,923 for validation and 2,924 for testing.

| Model | Validation macro-F1 | Test macro-F1 | Test accuracy | Training time |
|---|---|---|---|---|
| TF-IDF + logistic regression | 0.819 | 0.804 | 0.895 | 6.5 s |
| **BiGRU + attention (selected)** | **0.840** | **0.821** | **0.906** | 65.5 s (10 epochs, early stopping) |
| Soft-vote ensemble (weight 0.3 on linear) | 0.837 | 0.825 | 0.907 | (combines the two) |

The selection used validation only, so the test numbers are honest. The ensemble edges the BiGRU on test by 0.004, which is within noise, and the system rightly does not switch models after looking at the test set.

**Transfer to social media.** Social posts differ from reviews (hashtags, questions, no stars), so the agent checks every model on 400 hand-labelled posts before scoring the unlabelled ones:

| Model | Macro-F1 on 400 labelled posts | Accuracy |
|---|---|---|
| TF-IDF + logistic regression | 0.913 | 0.925 |
| BiGRU + attention | 0.850 | 0.892 |
| **Ensemble (chosen for social posts)** | **0.918** | **0.932** |

Against the hidden true sentiment of all 10,958 posts, the chosen scorer reaches **0.913 accuracy (macro-F1 0.894)**. This check matters: an earlier version that applied the BiGRU alone labelled 73% of social posts negative. Domain rules (hashtag stripping, a rule for questions, a neutral band of 0.2) and the transfer check fixed it.

**Aspect-based sentiment.** On 3,000 detected aspect mentions, 92.3% name an aspect that is truly present in the review (precision), and 97.9% of the non-neutral mentions have the right polarity.

### 4.2 Consumer Segmentation (machine learning)

K-Means was fitted for k = 3 to 8 on 16 standardised variables from 2,215 screened respondents. The silhouette was highest at k = 5 (0.257), which matches the 5 planted segments. The **adjusted Rand index against the true segment labels is 0.989**, close to perfect recovery. A silhouette of 0.26 looks modest, but it is typical for attitudinal survey data with overlapping segments, and the ARI shows that the structure found is the real one. The primary concept target chosen by the agent corresponds to the planted target segment (Sensitive-Skin Minimalists).

### 4.3 Demand Forecasting (machine learning)

Rolling-origin backtest: three folds of six months each, over May 2025 to October 2026, on 150 brand x category x channel series.

| Model | Series WAPE | Market MAPE | Client MAPE |
|---|---|---|---|
| **Gradient boosting + drift ensemble (selected)** | **0.137** | 0.078 | 0.143 |
| Seasonal naive with drift | 0.149 | 0.076 | 0.176 |
| Gradient boosting | 0.160 | 0.111 | 0.113 |
| Seasonal naive (benchmark) | 0.175 | 0.104 | 0.101 |

The selected model cuts the series-level error by 22% against the benchmark (13.7% against 17.5% WAPE). This error is the selection criterion, because the strategy depends on the mix across categories and channels. The table also shows what aggregation hides. At the client's total level, the plain seasonal naive is the most accurate (MAPE 0.101), because the client's 2026 packaging crisis is a shock that no model trained on history can foresee. The report states this limitation.

### 4.4 Price elasticity

Fixed-effects log-log demand model per brand (1,150 observations each, HC1 robust standard errors):

| Brand | Estimate | 95% CI | True | Error | Truth in CI | Elastic? (estimate / truth) |
|---|---|---|---|---|---|---|
| Kirana Beauty (client) | -1.37 | -1.51 to -1.22 | -1.30 | -0.07 | yes | yes / yes |
| Aurelia Derma | -0.52 | -0.64 to -0.39 | -0.60 | +0.08 | yes | no / no |
| DewiSkin | -1.80 | -1.96 to -1.64 | -1.50 | -0.30 | no | yes / yes |
| GlowNesia | -2.06 | -2.17 to -1.95 | -1.80 | -0.26 | no | yes / yes |
| Lumière Lab | -1.06 | -1.22 to -0.90 | -0.90 | -0.16 | no (just outside) | yes / **no** |
| Purabotanica | -1.04 | -1.21 to -0.88 | -1.10 | +0.06 | yes | yes / yes |

The client's elasticity, which drives the pricing recommendation, is accurate. Across brands, the mean absolute error is 0.153 and the rank correlation with the truth is 0.94, and 5 of 6 brands are correctly classified as elastic or inelastic. The intervals are too narrow, however: only 3 of 6 contain the true value, against a nominal 95%. The robust standard errors capture noise but not model misspecification, since the simulated demand also responds to promotions and stock-outs that are partly confounded with price. A cluster bootstrap would give more honest intervals.

### 4.5 Concept pricing

The Van Westendorp analysis on the two target segments (n = 832) gives an acceptable range of Rp 55,800 to 129,300 and an optimal zone of Rp 81,000 to 89,600. The recommended launch price of **Rp 89,900** lies inside the true optimal band of Rp 80,000 to 100,000.

### 4.6 Sentiment on real text (external validation)

`scripts/validate_on_real_data.py` scores the sentiment models on two real datasets described in [DATA_SOURCES.md](DATA_SOURCES.md):

- **Beauty reviews:** 76k reviews from 38 official beauty stores on Shopee and Tokopedia, Apache-2.0. Stars become labels by MarketMind's rule. The test split has 3,750 reviews after removing 63 that also appear in the train or validation split, the splits MarketMind may train on. Unlike the simulated data, this set is balanced by rating, so three-star (neutral) reviews are 21% of it.
- **IndoNLU SmSA:** a 500-sentence test set of general-topic comments, labelled by linguists.

Both were downloaded on 4 November 2026 into `data/external/`. The run option `--sentiment-data` chooses what the Consumer Insight agent learns from; each mode was trained once in a full study and then scored. Results are saved to `outputs/real_data_validation.json`.

The table gives the macro-F1 of the model that validation selects in each mode, with linear / BiGRU / ensemble in brackets.

| Training data (`--sentiment-data`) | Selected | Study reviews | Real beauty reviews (3,750) | SmSA, human labels (500) |
|---|---|---|---|---|
| `study` (default): 13,640 simulated reviews | BiGRU | **0.821** (0.804 / 0.821 / 0.825) | 0.428 (0.470 / 0.428 / 0.446) | 0.213 (0.442 / 0.213 / 0.319) |
| `study+real`: 13,641 simulated plus 50,710 real reviews | ensemble | **0.820** (0.803 / 0.809 / 0.820) | **0.662** (0.643 / 0.660 / 0.662) | 0.529 (0.559 / 0.515 / 0.529) |
| `real`: 50,710 real reviews | ensemble | 0.561 (0.559 / 0.552 / 0.561) | 0.658 (0.647 / 0.652 / 0.658) | **0.546** (0.562 / 0.535 / 0.546) |

For the first two modes, "study reviews" means the held-out study reviews (2,924 and 2,923). For `real`, it means all 19,487 study reviews, because those models never saw any of them.

The whole study was also run in each new mode and scored against the ground truth. All three reports passed the Critic's QA gate with 100 / 100.

| Mode | Ground-truth checks | Social transfer, all 10,958 posts (accuracy) | Aspect polarity accuracy | Training time (linear + BiGRU) |
|---|---|---|---|---|
| `study` (reference run) | 25 / 25 | 0.913 | 0.979 | 72 s |
| `study+real` | **25 / 25** | **0.936** | **0.982** | 369 s |
| `real` | 24 / 25: sentiment quality on the study's reviews is 0.561, below the 0.75 threshold | 0.884 | 0.916 | 230 s |

1. **Models trained only on simulated text do not transfer to real text.** In the default mode, macro-F1 falls from 0.82 on the study's reviews to 0.43-0.47 on real reviews, and the BiGRU scores 0.21 on SmSA. The simulator writes reviews from a small vocabulary (the BiGRU learned 440 words, against 13,695 once real reviews are added), so most real slang, product terms and emoji names are unknown to these models.
2. **Adding real reviews fixes this without losing anything.** `study+real` keeps the score on the study's reviews (0.820 against 0.821), and lifts real reviews from 0.43 to 0.66 and SmSA from 0.21 to 0.53. All 25 ground-truth checks still pass, and social transfer improves (accuracy 0.936 against 0.913). It is the recommended mode whenever the real reviews are available.
3. **The training data must cover the text being scored.** The `real` models mirror the default ones: good on real reviews (0.658) but weak on the simulated reviews (0.561), which fails one ground-truth check. Every other check still passes in that mode, including the client's packaging crisis and its timing, the competitor's counterfeit crisis and the price backlash. The downstream analysis therefore tolerates a weaker sentiment model.
4. **Three-star reviews are the hard class.** With real reviews in training, negative and positive real reviews are recognised well (F1 0.76 and 0.80 in `study+real`), but three-star reviews reach only 0.43, because they mix praise and complaints.
5. **Across domains, the linear model is the most robust.** On SmSA, where "neutral" means factual rather than mixed, the linear model scores 0.56 in both modes that use real reviews and beats the BiGRU. This supports keeping the TF-IDF model next to the deep one, and choosing the scorer for a new domain on labelled data from that domain.
6. **The aspect lexicon reaches real text.** It finds at least one aspect in 65.8% of the real beauty reviews, most often delivery, skin reaction, packaging, texture and effectiveness. Its precision on real text is not measured, because these reviews carry no aspect labels.

## 5. Data quality

| Dataset | Defects planted in the raw file | Result after cleaning | Quality score |
|---|---|---|---|
| Sales panel | 145 duplicate rows, 12 negative-unit rows, 8 outliers (x12), 241 channel-label variants, 483 missing discounts | 48,445 rows in, 48,280 out; 841 issues fixed (all duplicates and invalid rows removed, labels standardised, discounts imputed) | 99.3 |
| Reviews | 201 duplicate reviews; 3% rating-only | 20,307 in, 20,106 out | 98.0 |
| Survey | 72 speeders, 48 straight-liners, 60 attention-check failures, 6 invalid ages, 96 missing incomes | 2,400 in, 2,215 out (185 removed: the 180 planted low-quality responses plus invalid ages, with some overlap) | 84.5 |
| Social posts | 87 reposts | 11,046 in, 10,958 out | 98.4 |
| Catalogue, market size, social labels | none of consequence | unchanged | 99.8 to 100 |

The overall score, weighted by rows, is 98.4 / 100 after 1,406 fixes. The survey scores lowest because 7.7% of its responses had to be removed, and the report discloses the screened base (n = 2,215).

## 6. Governance: grounding and the QA loop

- **Released report:** QA score 100 / 100. Every check scored 1.0 (structure, coverage of the 7 research questions, numeric grounding, citations, recommendation evidence, disclosure). All 412 numbers in the prose were traced to tool output.
- **The reflection loop works.** `test_critic_catches_invented_numbers_and_revision_fixes_them` injects a fake LLM that writes "The market will triple to Rp 999 trillion". The Critic fails the first pass with a critical grounding issue tied to the `exec_summary` block, and the Director sends it back. The Report Writer replaces the block with grounded text, and the second pass is released without the invented figure.
- **The contracts hold.** `tests/test_schemas.py` validates every finding, recommendation, the plan, the QA verdict, the model card, the run metadata and all trace events of a fresh run against the JSON Schemas, and loads the data and the run into the SQL model with no foreign-key violations ([SCHEMAS.md](SCHEMAS.md)).

## 7. Efficiency

| Stage | Agents | Time (reference run) |
|---|---|---|
| Plan | Research Director | 0.1 s |
| Collect | Data Collection (including live World Bank calls) | 5.6 s |
| Clean | Data Quality | 0.8 s |
| Analyse, in parallel on 3 workers | Market 1.2 s, Competition 2.0 s, Consumer 29.7 s, Segmentation 27.6 s, Forecasting 39.8 s | about 40 s of wall-clock time |
| Synthesise, write, check | Strategy 0.01 s, Report Writer 1.6 s, Critic 0.01 s | 1.6 s |
| **Total** | 11 agents, 51 tool calls, 37 findings, 173 trace events | **48.0 s** |

On a first run, training the BiGRU adds about 65 s and the linear baseline 6.5 s, so a first run takes about 2 minutes. The analysis agents' own times add up to about 100 s, so running them in parallel saves roughly a minute per run. The true saving is a little smaller, because agents sharing the CPU each run somewhat slower than they would alone. With an LLM switched on, each run adds about nine calls (plan refinement, persona names, the executive summary, and commentary for six sections). Their speed depends on the provider and its rate limits, and they are cached across runs.

## 8. Reproducing these results

```bash
python scripts/generate_data.py                 # seeded: identical data every time
python run.py --no-llm                          # a new offline run
python scripts/evaluate_agents.py               # scores the latest run and writes evaluation.json
python -m pytest -q                             # unit, end-to-end, QA-loop and schema tests
python scripts/validate_on_real_data.py         # section 4.6; needs the two real datasets in data/external/
```

Small differences between runs can come from multi-threaded floating-point work in PyTorch and scikit-learn. Both runs that were scored (`20261104-142927` and the reference run) passed 25 / 25; the variance across data seeds has not been measured (section 9).

## 9. Threats to validity

- **The data was simulated by the same team that built the agents.** The checks prove that the system recovers effects of the kind that were planted. They do not prove it would find real-world effects of other kinds. The generator was written to be realistic (noise, defects, overlapping segments, slang), and the checks read machine-readable metrics, but a pilot on real data is the decisive test. The first real-data check (section 4.6) confirms the risk for text: models trained on simulated reviews do not transfer to real reviews. Adding real reviews to the training data (`--sentiment-data study+real`) fixes this without losing accuracy on the study's reviews.
- **The thresholds were set by the designers** (for example a macro-F1 of at least 0.75, an ARI of at least 0.80). They are conventional, but they are choices.
- **One reference run, one seed.** The variance across data seeds has not been measured.
- **The labels are proxies.** Star ratings are a noisy stand-in for the sentiment of the text, and the aspect lexicon covers only 9 aspects.
- **The LLM path is not in the reference run.** The offline run shows the deterministic floor. The LLM adds language, and the QA loop is tested with a scripted fake LLM, but the quality of real LLM narrative has not been scored by human raters.
- **Known weaknesses:** the elasticity intervals are too narrow (section 4.4); shocks such as the packaging crisis cannot be forecast (section 4.3); and the concept revenue relies on an explicit 5% conversion assumption.

## 10. Recommended next evaluations

1. Repeat the run over 10 data seeds and report the mean and spread of each metric.
2. Ablations: switch off the transfer check, the ensemble, or the Critic, and measure what breaks. This quantifies what each design decision buys.
3. Fault injection: make each analysis agent fail in turn, and confirm that the study completes with honest gaps.
4. LLM-on runs with two or three providers: grounding rate, revisions needed, time and cost per run.
5. Human evaluation: have marketing practitioners rate the report's usefulness and clarity, blind to whether an LLM was used.
6. A real-data pilot through the documented schemas, judged on whether the findings match what the client's team already knows.
