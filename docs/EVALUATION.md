# MarketMind evaluation report

This report measures how well MarketMind does its job. The question is not only "does it run?" but "does the team of agents find what is really in the market, with models that are honestly validated, a report whose every number is grounded, and in reasonable time?" The bundled data is simulated with **planted ground truth**: every market effect the generator builds in is recorded in `data/ground_truth.json` and `data/ground_truth/*.csv`. The whole multi-agent system can therefore be scored objectively, which is rarely possible with real market data.

One run on one dataset is a single sample, so the report also measures how the results hold up across five more data seeds (section 7), what each design choice contributes (section 8), and what happens when real LLMs write part of the report (section 9).

---

## 1. Headline results

| Dimension | Measure | Result |
|---|---|---|
| Insight recall (whole system) | Planted insights recovered, reference data | **24 / 25 checks passed**. The miss: the concept price lands Rp 100 below the true band, and the agent itself reports the pick as not settled (section 4.5) |
| Robustness | The same 25 checks on five more data seeds | **23.6 / 25 on average** (22 to 25); 21 of the 25 checks passed in every dataset. The misses: the concept price (3 of 5 seeds), declining topics (2), rising topics (1) and the fastest-growing category (1) (section 7) |
| Deep learning: sentiment | Held-out macro-F1 / accuracy (2,929 reviews) | **0.817 / 0.900** (soft-vote ensemble, selected on validation) |
| Deep learning: transfer | Macro-F1 on 400 hand-labelled social posts | **0.910** (ensemble scorer) |
| Deep learning: transfer | Accuracy against hidden labels, all 10,912 social posts | **0.940** (macro-F1 0.920) |
| External validation: real text | Macro-F1 on 3,750 real Shopee/Tokopedia beauty reviews: default models / with real reviews added to training (`--sentiment-data study+real`) | **0.43-0.47 / 0.662** (section 4.6, measured before the recalibration) |
| Aspect-based sentiment | Aspect precision / polarity accuracy (3,000 mentions) | **0.906 / 0.987** |
| Segmentation (ML) | Agreement with the true segments (adjusted Rand index) | **0.985** (k = 5, silhouette 0.242) |
| Forecasting (ML) | Backtest WAPE, brand x category x channel | **13.5%**, against 17.5% for the seasonal-naive benchmark |
| Price elasticity | Client estimate against truth; error across the six brands | **-1.29** (95% CI -1.38 to -1.20) against a true -1.30; mean absolute error 0.067 |
| Concept pricing | Recommended price against the true optimal band | **Rp 79,900** against Rp 80,000-100,000. The agent flags the pick as not settled (the optimal price point rests on 3 and 1 answers) and recommends testing Rp 89,900 too |
| Data quality | Planted defects caught | **All**: 20 invalid and 145 duplicate sales rows, 180 bad survey responses |
| Governance | Critic QA score / numbers grounded | **100 / 100**, with 438 of 438 numbers in the prose traced to evidence |
| Real LLMs | Studies run with Gemini, Groq and OpenRouter | **All three passed the Critic on the first try**: 209 numbers written by the LLMs, all grounded; no revisions; the same 24 / 25 checks as offline (section 9) |
| Efficiency | Wall-clock time, models cached / first run | **114 s** with cached models (114-134 s across today's runs on one laptop); about 3.5 minutes on a first run |

## 2. Method

**Reference run.** Run `20261110-182213`: the default brief (Kirana Beauty, all six modules), offline (no LLM), with cached sentiment models and parallel analysis agents, on an 8-thread laptop CPU with Python 3.12. The figures in sections 3 to 6 come from that run's `evaluation.json`, model cards and tables. Section 11 explains how to reproduce them.

**Data version.** The simulator was recalibrated on 10 November 2026 against real Indonesian benchmarks: online channel shares, the importance of a halal claim, and Lazada as a preferred channel ([DATA_SOURCES.md §7](DATA_SOURCES.md#7-how-the-simulated-data-compares)). The planted effects that the checks look for did not change, but every dataset was regenerated, so the numbers here differ from earlier versions of this report.

**What is measured.**

1. **Insight recall.** `marketmind/evaluation.py` runs 25 checks that compare the agents' published findings with the planted truth. Each check reads the machine-readable `metrics` of a finding (for example `CMP-02.metrics.channel`) rather than its prose, so it cannot be gamed by wording.
2. **Model quality.** Each learning agent is scored on held-out or hidden labels that the agents never see during the run: `data/ground_truth/social_sentiment.csv` (the true sentiment of every social post), `review_aspects.csv` (the true aspects and polarities of the reviews) and `survey_segments.csv` (the true segment of every respondent).
3. **Data quality.** The defects injected into the raw files are compared with what the Data Quality agent reports it fixed.
4. **Governance.** The Critic's QA verdict on the released report, plus the tests that prove the QA loop works (section 6).
5. **External validation.** The sentiment models are also scored on two real, openly licensed Indonesian datasets (section 4.6), because results on simulated text alone cannot show how the models handle real language.
6. **Robustness.** `scripts/multi_seed.py` regenerates the market with five other random seeds (the same planted effects, different noise) and runs and scores the whole study on each (section 7).
7. **Ablations.** `scripts/ablations.py` switches off one design choice at a time on the reference data (section 8).
8. **Real LLMs.** `scripts/llm_runs.py` runs the full study with each free LLM provider and records what the Critic catches before the report is released (section 9).
9. **Efficiency.** Time per agent and per run, taken from the trace (section 10).

**Test plan.** Every level below runs automatically with `python -m pytest -q`: 72 tests that cover 94% of the lines in `marketmind/`. The acceptance checks can also be run on any saved run with `scripts/evaluate_agents.py` or from the dashboard.

| Level | What is tested | How | Pass criterion |
|---|---|---|---|
| Unit | Text normalisation and aspect lexicon, Ramadan/Eid calendar features, LLM JSON parsing, workflow cycle detection, offline LLM behaviour | `tests/test_system.py`, 5 tests | Exact expected outputs |
| Agent logic | Each agent's core method on synthetic inputs with a known answer: Critic grounding and citations, workflow skip rules, Van Westendorp crossings (including tied stretches), the price bootstrap and tail counts, elasticity recovery, price scenarios, the complaint-spike detector, the threat index, label cleaning, the priority rule | `tests/test_agent_logic.py`, 14 tests | The known answer, e.g. the planted spike months, hand-solved price points, elasticities within 0.1 of the truth |
| Dashboard | The real Streamlit app rendering a saved run | `tests/test_dashboard.py` | All 12 tabs render with no exception or tab-level error |
| LLM client | Requests, parsing, caching, retries, per-provider models, fallbacks for busy, hung and retired models, against a fake provider API | `tests/test_llm_client.py`, 12 tests | Each behaviour as specified, with no network and no key |
| Regression | The 25 ground-truth checks and the Analyst Chat on a fresh offline run | `tests/test_evaluation_and_chat.py`, 2 tests | Every check passes except the documented concept-price miss, which must be flagged as not settled with a runner-up inside the true band; chat answers cite relevant evidence |
| End to end | A complete offline study | `test_full_pipeline_offline` | Status completed, QA passed with a score of at least 85, key findings present, at least 3 recommendations, files saved |
| Agent cooperation | The Critic, the Director and the Report Writer reflection loop, with a scripted LLM that invents a number | `test_critic_catches_invented_numbers_and_revision_fixes_them` | First QA pass fails; the revised report passes without the invented number; a revision message was sent |
| Contracts | Every artefact, row and SQL table against the published schemas | `tests/test_schemas.py`, 5 tests | No schema errors; no foreign-key violations; brand shares sum to 1 |
| Failure paths | Unknown client, missing dataset, World Bank outage, garbled LLM output, and an analyst and the Critic crashing in one run | `tests/test_failure_paths.py`, 6 tests | Clear errors or warnings; the study completes around failed agents and is marked `unverified` when the Critic did not run |
| Agentic behaviour | Retries and time limits, the LLM budget, the two human approval gates (terminal, dashboard and programmatic reviewers), the Director's follow-ups, open questions; end to end, a market analyst that fails twice and a reviewer who drops a recommendation, and a rejected plan | `tests/test_agentic.py`, 13 tests; `tests/test_dashboard.py` (rejected run) | A flaky agent recovers on retry; a slow one stops at its limit; the Director re-dispatches the failed analyst and the final report has its section and passes QA; the dropped recommendation is gone; a rejected study writes no report |
| Real-data readiness | The Tokopedia importer on an archive in the dataset's layout; planning around missing data; a study on a folder with only reviews and a catalogue, marked as real data | `tests/test_real_data.py`, 3 tests | Every imported row meets the row contracts and unknown fields stay null; only the modules the data supports run, with the others named in the report; QA passes; the evaluation reports that real data has no ground truth |
| Acceptance | Whether the system finds the planted truth | `marketmind/evaluation.py`, 25 checks | Each check's rule in section 3 |

## 3. Insight recall: 24 / 25

| Area | Check | Planted truth | Found by the agents | Pass rule |
|---|---|---|---|---|
| Market | Fastest-growing category | Sunscreen | Sunscreen | exact match |
| Market | Fastest-growing channel | TikTok Shop | TikTok Shop | exact match |
| Market | Fastest-growing region | Kalimantan & Sulawesi | Kalimantan & Sulawesi | one of the two fastest true regions |
| Market | Rising topics | peptide, refill, skin barrier, ceramide | peptide, skin barrier, refill (plus "dupe") | recall of at least 75% |
| Market | Declining topics | niacinamide, glass skin, mugwort | all 3 | recall of at least 66% |
| Competition | Client's under-indexed channel | TikTok Shop | TikTok Shop (index 0.40) | exact match |
| Competition | Top competitive threat | GlowNesia or Lumière Lab | Lumière Lab | one of the two |
| Competition | White space | Fragrance-free ceramide moisturizer, Rp 60-120k | Fragrance-free ceramide/barrier moisturizer, Rp 60-120k | mentions fragrance-free and moisturizer |
| Consumer | Client's top pain point | Packaging (pump defect) | Packaging | exact match |
| Consumer | Timing of the pain point | Feb-Apr 2026 | Feb-Apr 2026 | the periods overlap |
| Consumer | Competitor crisis | GlowNesia authenticity, May-Jul 2026 | GlowNesia authenticity, May-Jul 2026 | brand, aspect and period |
| Consumer | Backlash after the price rise | Kirana price complaints after Jul 2025 | net price/value sentiment fell from +0.11 to -0.23 (CON-06) | a price-related spike or finding |
| Segmentation | Number of segments | 5 | 5 | exact match |
| Segmentation | Segment recovery | ARI of at least 0.80 | 0.985 | threshold |
| Segmentation | Concept target segment | Sensitive-Skin Minimalists | Sensitive-Skin Minimalists | the chosen segment's members are mostly that true segment |
| Pricing | Recommended concept price | Rp 80,000-100,000 | **Rp 79,900: fail** (runner-up Rp 89,900) | inside the band |
| Pricing | Client price elasticity | -1.30 | -1.291 | error of at most 0.2 |
| Models | Sentiment on held-out reviews | macro-F1 of at least 0.75 | 0.817 | threshold |
| Models | Transfer to all social posts | accuracy of at least 0.85 | 0.940 | threshold |
| Models | Aspect precision / polarity | at least 0.80 / at least 0.85 | 0.906 / 0.987 | both thresholds |
| Models | Forecast against the naive benchmark | WAPE below 0.175 | 0.135 | beats seasonal naive |
| Data | Invalid sales rows caught | 20 (12 negative, 8 outliers) | 20 | all of them |
| Data | Duplicate sales rows removed | 145 | 145 | at least 95% |
| Data | Low-quality survey responses caught | 180 (72 speeders, 48 straight-liners, 60 attention fails) | 180 | at least 95% |
| Governance | Report passed the QA gate | passed | 100 / 100 | the Critic passed it |

Two checks changed between data versions. The backlash check now finds CON-06, the Consumer Insight agent's "value-for-money is slipping" finding, which carries the aspect label "Price / value"; before the recalibration a price-complaint spike happened to satisfy it, and on the new data that spike is below the detector's threshold. The concept-price miss is explained in section 4.5.

## 4. Model evaluation

### 4.1 Consumer Insight: sentiment (deep learning)

The labels come from star ratings (1-2 negative, 3 neutral, 4-5 positive). That gives 19,526 reviews with text, with a strong imbalance: 2,907 negative, 1,613 neutral and 15,006 positive. Macro-F1 is therefore the headline metric, because accuracy alone would reward a model that always says "positive". The split is 13,668 reviews for training, 2,929 for validation and 2,929 for testing.

| Model | Validation macro-F1 | Test macro-F1 | Test accuracy | Training time |
|---|---|---|---|---|
| TF-IDF + logistic regression | 0.800 | 0.801 | 0.890 | 15.1 s |
| BiGRU + attention | 0.828 | 0.816 | 0.902 | 78.7 s (stopped after 6 of 10 epochs) |
| **Soft-vote ensemble, weight 0.4 on linear (selected)** | **0.832** | **0.817** | **0.900** | (combines the two) |

The selection used validation only, so the test numbers are honest. On test the ensemble and the BiGRU are level (0.8165 against 0.8163); the deep model carries most of the gain over the linear baseline.

**Transfer to social media.** Social posts differ from reviews (hashtags, questions, no stars), so the agent checks every model on 400 hand-labelled posts before scoring the unlabelled ones:

| Model | Macro-F1 on 400 labelled posts | Accuracy |
|---|---|---|
| TF-IDF + logistic regression | 0.898 | 0.918 |
| BiGRU + attention | 0.883 | 0.888 |
| **Ensemble (chosen for social posts)** | **0.910** | **0.923** |

Against the hidden true sentiment of all 10,912 posts, the chosen scorer reaches **0.940 accuracy (macro-F1 0.920)**. This check matters: an earlier version that applied the BiGRU alone labelled 73% of social posts negative. Domain rules (hashtag stripping, a rule for questions, a neutral band of 0.2) and the transfer check fixed it. Section 8 measures what the check is worth on this data.

**Aspect-based sentiment.** On 3,000 detected aspect mentions, 90.6% name an aspect that is truly present in the review (precision), and 98.7% of the non-neutral mentions have the right polarity.

### 4.2 Consumer Segmentation (machine learning)

K-Means was fitted for k = 3 to 8 on 16 standardised variables from 2,214 screened respondents. The silhouette was highest at k = 5 (0.242), which matches the 5 planted segments. The **adjusted Rand index against the true segment labels is 0.985**, close to perfect recovery. A silhouette of 0.24 looks modest, but it is typical for attitudinal survey data with overlapping segments, and the ARI shows that the structure found is the real one. The primary concept target chosen by the agent corresponds to the planted target segment (Sensitive-Skin Minimalists).

### 4.3 Demand Forecasting (machine learning)

Rolling-origin backtest: three folds of six months each, over May 2025 to October 2026, on 150 brand x category x channel series.

| Model | Series WAPE | Market MAPE | Client MAPE |
|---|---|---|---|
| **Gradient boosting + drift ensemble (selected)** | **0.135** | 0.076 | 0.143 |
| Seasonal naive with drift | 0.150 | 0.078 | 0.173 |
| Gradient boosting | 0.155 | 0.105 | 0.115 |
| Seasonal naive (benchmark) | 0.175 | 0.105 | 0.099 |

The selected model cuts the series-level error by 23% against the benchmark (13.5% against 17.5% WAPE). This error is the selection criterion, because the strategy depends on the mix across categories and channels. At the client's total level, however, the plain seasonal naive is the most accurate (MAPE 0.099, best in 2 of 3 folds), because the client's 2026 packaging crisis is a shock that no model trained on history can foresee. The agent now detects this itself: the backtest records the best model for the client's total, and FCT-05 states that "the client-level outlook is less certain than the market view" whenever that model differs from the selected one.

### 4.4 Price elasticity

Fixed-effects log-log demand model per brand (1,150 observations each): series effects, month x channel effects, a quadratic trend per brand and a stock-out term, with standard errors clustered by series.

| Brand | Estimate | 95% CI | True | Error | Truth in CI | Elastic? (estimate / truth) |
|---|---|---|---|---|---|---|
| Kirana Beauty (client) | -1.29 | -1.38 to -1.20 | -1.30 | +0.01 | yes | yes / yes |
| Aurelia Derma | -0.57 | -0.63 to -0.51 | -0.60 | +0.03 | yes | no / no |
| DewiSkin | -1.61 | -1.70 to -1.51 | -1.50 | -0.11 | no | yes / yes |
| GlowNesia | -1.98 | -2.05 to -1.92 | -1.80 | -0.18 | no | yes / yes |
| Lumière Lab | -0.88 | -0.99 to -0.77 | -0.90 | +0.02 | yes | no / no |
| Purabotanica | -1.15 | -1.22 to -1.09 | -1.10 | -0.05 | yes | yes / yes |

The client's elasticity, which drives the pricing recommendation, is accurate (error +0.01). Across brands, the mean absolute error is 0.067, the ranking matches the truth exactly, and all 6 brands are correctly classified as elastic or inelastic.

**What changed, and why.** The earlier specification used month x online/offline effects and HC1 robust standard errors. Its estimates were biased (mean error 0.15), because seasonal and campaign peaks differ between channels (TikTok Shop's mega-sales, offline Ramadan buying) and the brands' channel mixes differ, so part of each channel's peak leaked into the price coefficients. Clustering the standard errors alone did not help, since the problem was bias, not noise. Month x channel effects remove it. On the same, recalibrated data the old specification has a mean error of 0.162 (worst 0.326), the new one 0.067 (worst 0.181), with intervals half as wide.

**What remains.** Only 4 of 6 intervals contain the true value, against a nominal 95%. DewiSkin and GlowNesia are estimated as more elastic than they are, by more than their standard errors allow. That is bias, which no choice of standard errors can fix. The fixed effects absorb whatever is common to a channel in a month, but not demand events that vary by brand and month at once, such as GlowNesia's viral TikTok campaign and its counterfeit crisis; where such events coincide with price changes, they leak into the estimate. Section 7 gives the coverage across five more data seeds.

### 4.5 Concept pricing

The Van Westendorp analysis on the two target segments (n = 830) gives an acceptable range of Rp 55,800 to 129,300 and an optimal zone of Rp 77,500 (OPP) to 89,600 (IPP). The rule recommends the charm price nearest the middle of that zone, Rp 83,550, which is **Rp 79,900**: Rp 100 below the true optimal band of Rp 80,000 to 100,000. The previous data version gave Rp 89,900.

**Why it misses: the data cannot place the OPP.** The OPP is the price where the share of respondents who call it too cheap meets the share who call it too expensive. In this survey the two groups barely overlap. Near Rp 77,500, only 3 of the 830 target respondents still call the price too cheap and only 1 already calls it too expensive. The OPP therefore rests on a handful of answers, and one or two respondents decide on which side of Rp 84,900, the cut between the two nearest charm prices, the zone's middle falls. The same holds in all five extra datasets (section 7): 2 to 7 answers on one side and 1 to 3 on the other.

Two things then tip the balance:

1. **A thin margin.** A simulation of the planted answer thresholds, without the rounding to Rp 5,000 that respondents use, gives a true OPP of Rp 82,000 and IPP of Rp 89,300. Their midpoint, Rp 85,650, is only Rp 750 above the cut, so the right answer is Rp 89,900, but narrowly. Even with perfectly pure segments, 27% of 400 simulated surveys of this size landed on Rp 79,900.
2. **Misassigned respondents.** The clustering recovers the segments almost perfectly (ARI 0.985), but it put four respondents from other segments (two Budget Acne Fighters, two Halal Value Seekers) into the target clusters. They find Rp 80,000 to 115,000 too expensive, which is enough to pull the OPP from Rp 82,500 to 77,500; without them the rule gives Rp 89,900. In seeds 1, 3 and 4 the pick stays at Rp 79,900 even without the misassigned respondents, so they are not the whole story.

The IPP, by contrast, is well determined (Rp 85,900 to 89,900 across the six datasets) and lies inside the true band, because it is where two dense curves cross ("cheap" and "expensive"), not two sparse tails.

**What was improved.** Three changes make the agent's answer more honest rather than luckier:

1. **Tied stretches.** When the two curves sit at the same level over a stretch of prices, the crossing is now taken at the middle of that stretch instead of its left end. The left end biased the OPP low; in 300 simulated surveys of 1,100 respondents the mean error of the OPP moved from -520 to +600 rupiah and its spread narrowed by 9%.
2. **Bootstrap stability.** The agent resamples the respondents 200 times and reports how often each price wins: here Rp 79,900 wins 82% of resamples and Rp 89,900 18%. The bootstrap has a blind spot, though. It can only resample the extreme answers that exist, so it cannot show that only a few exist; in seed 1 the wrong price won 91% of resamples.
3. **Tail counts.** SEG-04 now counts the answers that place the OPP (the "too cheap" and "too expensive" answers within 5% of it). With fewer than 10 on either side, a conventional minimum base, it states that the OPP is poorly determined. It then calls the pick not settled whatever the bootstrap says, names the runner-up and lowers its confidence from 0.75 to 0.6. Here: "only 3 'too cheap' and 1 'too expensive' answers fall near it ... test Rp 79,900 against Rp 89,900". The Strategy agent's launch recommendation adds a test of both price points in the first month before fixing the list price. That is the right business advice on this evidence, and it would have been given in all six datasets, including the two where Rp 89,900 was picked.

The check was kept strict. Widening the band, or switching the rule to the IPP because it happens to sit inside the planted band, would have turned this run into a pass without the evidence to justify it. Section 13 lists the next step.

### 4.6 Sentiment on real text (external validation)

`scripts/validate_on_real_data.py` scores the sentiment models on two real datasets described in [DATA_SOURCES.md](DATA_SOURCES.md):

- **Beauty reviews:** 76k reviews from 38 official beauty stores on Shopee and Tokopedia, Apache-2.0. Stars become labels by MarketMind's rule. The test split has 3,750 reviews after removing 63 that also appear in the train or validation split, the splits MarketMind may train on. Unlike the simulated data, this set is balanced by rating, so three-star (neutral) reviews are 21% of it.
- **IndoNLU SmSA:** a 500-sentence test set of general-topic comments, labelled by linguists.

Both were downloaded on 4 November 2026 into `data/external/`. The run option `--sentiment-data` chooses what the Consumer Insight agent learns from; each mode was trained once in a full study and then scored. Results are saved to `outputs/real_data_validation.json`. **These figures were measured on 4 November 2026, before the simulator was recalibrated.** The recalibration changed channel mixes and survey answers, not how reviews are written, but the regenerated study reviews are a new random sample, so the "study reviews" column would move slightly if re-measured; the real-text columns depend on the study reviews only through training.

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
| `study` (reference run at the time) | 25 / 25 | 0.913 | 0.979 | 72 s |
| `study+real` | **25 / 25** | **0.936** | **0.982** | 369 s |
| `real` | 24 / 25: sentiment quality on the study's reviews is 0.561, below the 0.75 threshold | 0.884 | 0.916 | 230 s |

1. **Models trained only on simulated text do not transfer to real text.** In the default mode, macro-F1 falls from 0.82 on the study's reviews to 0.43-0.47 on real reviews, and the BiGRU scores 0.21 on SmSA. The simulator writes reviews from a small vocabulary (the BiGRU learned 440 words, against 13,695 once real reviews are added), so most real slang, product terms and emoji names are unknown to these models.
2. **Adding real reviews fixes this without losing anything.** `study+real` keeps the score on the study's reviews (0.820 against 0.821), and lifts real reviews from 0.43 to 0.66 and SmSA from 0.21 to 0.53. All 25 ground-truth checks still passed, and social transfer improved (accuracy 0.936 against 0.913). It is the recommended mode whenever the real reviews are available.
3. **The training data must cover the text being scored.** The `real` models mirror the default ones: good on real reviews (0.658) but weak on the simulated reviews (0.561), which fails one ground-truth check. Every other check still passed in that mode, including the client's packaging crisis and its timing, the competitor's counterfeit crisis and the price backlash. The downstream analysis therefore tolerates a weaker sentiment model.
4. **Three-star reviews are the hard class.** With real reviews in training, negative and positive real reviews are recognised well (F1 0.76 and 0.80 in `study+real`), but three-star reviews reach only 0.43, because they mix praise and complaints.
5. **Across domains, the linear model is the most robust.** On SmSA, where "neutral" means factual rather than mixed, the linear model scores 0.56 in both modes that use real reviews and beats the BiGRU. This supports keeping the TF-IDF model next to the deep one, and choosing the scorer for a new domain on labelled data from that domain.
6. **The aspect lexicon reaches real text.** It finds at least one aspect in 65.8% of the real beauty reviews, most often delivery, skin reaction, packaging, texture and effectiveness. Its precision on real text is not measured, because these reviews carry no aspect labels.

## 5. Data quality

| Dataset | Defects planted in the raw file | Result after cleaning | Quality score |
|---|---|---|---|
| Sales panel | 145 duplicate rows, 12 negative-unit rows, 8 outliers (x12), 193 channel-label variants, 483 missing discounts | 48,445 rows in, 48,280 out; 841 issues fixed (all duplicates and invalid rows removed, labels standardised, discounts imputed) | 99.3 |
| Reviews | 202 duplicate reviews; 656 rating-only | 20,384 in, 20,182 out | 98.0 |
| Survey | 72 speeders, 48 straight-liners, 60 attention-check failures, 6 invalid ages, 92 missing incomes | 2,400 in, 2,214 out (186 removed: the 180 planted low-quality responses plus 6 invalid ages) | 84.4 |
| Social posts | 87 reposts | 10,999 in, 10,912 out | 98.4 |
| Catalogue, market size, social labels | none of consequence | unchanged | 99.8 to 100 |

The overall score, weighted by rows, is 98.4 / 100 after 1,411 fixes. The survey scores lowest because 7.8% of its responses had to be removed, and the report discloses the screened base (n = 2,214).

## 6. Governance: grounding and the QA loop

- **Released report:** QA score 100 / 100. Every check scored 1.0 (structure, coverage of the 7 research questions, numeric grounding, citations, recommendation evidence, disclosure). All 438 numbers in the prose were traced to tool output, and the report's 81 citations name 36 distinct findings, all of which exist.
- **The reflection loop works.** `test_critic_catches_invented_numbers_and_revision_fixes_them` injects a fake LLM that writes "The market will triple to Rp 999 trillion". The Critic fails the first pass with a critical grounding issue tied to the `exec_summary` block, and the Director sends it back. The Report Writer replaces the block with grounded text, and the second pass is released without the invented figure. Section 9 shows the same loop with real LLMs.
- **The contracts hold.** `tests/test_schemas.py` validates every finding, recommendation, the plan, the QA verdict, the model card, the run metadata and all trace events of a fresh run against the JSON Schemas, and loads the data and the run into the SQL model with no foreign-key violations ([SCHEMAS.md](SCHEMAS.md)).

## 7. Robustness across data seeds

`scripts/multi_seed.py` regenerated the market with seeds 1 to 5. Each dataset has the same planted effects as the reference data (seed 2026) but different random noise in every sales row, review, post and survey answer. Each was cleaned, analysed and reported by a full offline study in its own folders, and scored against its own ground truth.

| Dataset | Checks | Checks that failed |
|---|---|---|
| Seed 2026 (reference) | 24 / 25 | Concept price |
| Seed 1 | 22 / 25 | Fastest-growing category, declining topics, concept price |
| Seed 2 | **25 / 25** | none |
| Seed 3 | 24 / 25 | Concept price |
| Seed 4 | 22 / 25 | Rising topics, declining topics, concept price |
| Seed 5 | **25 / 25** | none |

Across seeds 1 to 5 the system passed 23.6 checks on average (22 to 25), and all 25 in 2 of the 5 seeds. **21 of the 25 checks passed in every dataset**: all the data-quality, model-quality, segmentation and competition checks, the consumer pain points and crises, the client elasticity and the QA gate.

| Metric (seeds 1-5) | Mean | Spread (sd) | Worst |
|---|---|---|---|
| Sentiment macro-F1, held-out reviews | 0.824 | 0.009 | 0.814 |
| Transfer macro-F1, 400 labelled posts | 0.896 | 0.018 | 0.873 |
| Social accuracy, all posts (hidden labels) | 0.919 | 0.014 | 0.901 |
| Aspect precision / polarity accuracy | 0.913 / 0.983 | 0.007 / 0.007 | 0.907 / 0.975 |
| Segment recovery (ARI) | 0.985 | 0.003 | 0.981 |
| Forecast WAPE (seasonal-naive benchmark) | 0.147 (0.178) | 0.004 | 0.150 |
| Client elasticity error | -0.061 | 0.048 | -0.132 |
| Elasticity mean absolute error, six brands | 0.060 | 0.010 | 0.075 |
| Elasticity 95% intervals that contain the truth | 4.2 of 6 (70%) | 1.1 | 3 of 6 |
| Critic QA score | 100 | 0 | 100 |

**The four checks that failed.** Each is a case where the planted effect is small next to the noise, which one run could not reveal:

1. **Concept price, 3 of 5 seeds (4 of 6 datasets with the reference).** The optimal price point rests on 2 to 7 "too cheap" and 1 to 3 "too expensive" answers in every dataset, so single respondents decide between Rp 79,900 and Rp 89,900 (section 4.5). The tail-count check added to SEG-04 flags the pick as not settled in all six.
2. **Declining topics, 2 of 5 (recall below 66%).** The planted declines are gentle. Niacinamide's weight falls 30% over almost four years, about 10% between the last two years, while a stable topic's share moved by up to 26% between years from noise alone (vitamin C in seed 4). When the noise outruns the trend, a stable topic takes one of the three "fading" slots.
3. **Rising topics, 1 of 5 (seed 4).** Only peptide and refill passed the agent's momentum threshold; ceramide and skin barrier grew too little that year.
4. **Fastest-growing category, 1 of 5 (seed 1).** Serum grew 20.2% and sunscreen 19.6% over the last 12 months. Sunscreen's planted lead is driven by its category trend, and brand-level noise closed the gap.

**What this adds to the single run.** The reference run's 24 / 25 is typical rather than lucky or unlucky. Model quality hardly moves between seeds (spreads of 0.003 to 0.018), so the model results in section 4 can be trusted beyond one dataset. The elasticity intervals are too narrow: they contain the true value 70% of the time against a nominal 95%. Clustered standard errors capture noise but not the bias described in section 4.4, and the client's estimate errs on the elastic side in every seed (mean -0.06). The results are in [docs/results/multi_seed.json](results/multi_seed.json).

## 8. Ablations

`scripts/ablations.py` switches off one design choice at a time and re-runs the offline study on the reference data. The trained models are cached, so only the choice changes between variants.

| Variant | What changes | Checks | Review macro-F1 | Social accuracy, all 10,912 posts | Aspect polarity |
|---|---|---|---|---|---|
| Full system | (none) | 24 / 25 | 0.817 | 0.940 | 0.987 |
| No transfer check | The model selected on reviews also scores the social posts | 24 / 25 | 0.817 | 0.940 | 0.987 |
| BiGRU only | The deep model for everything | 24 / 25 | 0.816 | 0.930 | 0.979 |
| Linear model only | No deep learning | 24 / 25 | 0.801 | 0.916 | 0.979 |
| No social-media rules | No hashtag stripping, question rule or neutral band | **23 / 25** | 0.817 | **0.726** | 0.979 |

1. **The social-media rules are the decisive design choice.** Without them, accuracy on social posts falls from 0.940 to 0.726 and the transfer check (accuracy of at least 0.85) fails. On the 400 hand-labelled posts, macro-F1 drops from 0.88-0.91 to 0.47-0.55 for every model: models trained on reviews read hashtags and questions as sentiment.
2. **Deep learning adds a modest, consistent gain.** The ensemble beats the linear model by 0.016 macro-F1 on reviews, 2.4 points of social accuracy and 0.8 points of aspect polarity. No downstream conclusion changes.
3. **The transfer check changes nothing on this data,** because the ensemble wins on both reviews and social posts. It earns its place when the two disagree: without the rules it chose the BiGRU for social posts, and on the previous data version the BiGRU won on reviews while the ensemble transferred better (0.918 against 0.850 macro-F1).
4. **The other agents do not depend on these choices.** The market, competition, segmentation and forecasting checks do not use the sentiment models, and the concept-price miss is present in every variant.

Switching the Critic off offline would measure nothing, because offline every number comes from the tools; its contribution is measured with real LLMs in section 9 and with a scripted LLM in section 6. The results are in [docs/results/ablations.json](results/ablations.json).

## 9. Real-LLM runs

`scripts/llm_runs.py` ran the full study once with each free provider on 10 November 2026, with nothing cached. The analysis is the same deterministic pipeline as the reference run; the LLM refines the plan, names the personas, and writes the executive summary and the commentary for six report sections, each in a marked block that the Critic checks separately.

| Provider | Model that answered | Calls (failed) | LLM time | Tokens in / out | LLM text in the report | Numbers the LLM wrote | Citations | First QA pass | Revisions | Checks |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini | `gemini-flash-lite-latest`, the fallback: the main model, `gemini-flash-latest`, answered HTTP 503 (overloaded) to every call | 9 (0) | 234 s | 16,285 / 1,804 | 7 blocks, 747 words | 75, all grounded | 24 | 100, no issues | 0 | 24 / 25 |
| Groq | `qwen/qwen3.8-27b` (one rate-limit wait of 6 s) | 9 (0) | 74 s | 16,080 / 1,731 | 7 blocks, 727 words | 50, all grounded | 29 | 100, no issues | 0 | 24 / 25 |
| OpenRouter | `nvidia/nemotron-3.5-super-vl:free` | 9 (0) | 252 s | 52,794 / 27,651 | 7 blocks, 823 words | 84, all grounded | 48 | 100, no issues | 0 | 24 / 25 |

1. **No invented numbers reached the Critic.** Across 27 calls the three models wrote 209 numbers and 101 citations, and every number traced to tool output and every citation to a real finding. No report needed a revision. With the facts passed in the prompt and the grounding rules in the system prompt, these models did not make up figures in this task. The Critic's ability to catch an invented number and have it rewritten is therefore shown by the scripted test in section 6, not by these runs; what these runs show is that the check does not get in the way of good LLM text (no false alarms on 209 numbers).
2. **The guardrails that did act were elsewhere.** Gemini's main model was overloaded for the whole run, and the fallback model answered all nine calls without a single failed request. OpenRouter's model, a reasoning model that spent about 3,000 output tokens per call, returned a plan refinement that was not usable JSON, so the Director kept the rule-based plan; Gemini's and Groq's refinements passed validation and were used.
3. **The analysis does not depend on the LLM.** All three runs pass the same 24 of 25 checks as the offline run, because every number comes from the deterministic tools.
4. **Cost and time.** The free tiers were enough for a full study per provider (9 requests each). LLM time ranged from 74 s (Groq) to 252 s (OpenRouter); whole runs took 4.1 to 7.6 minutes, measured while the seed study (section 7) was using the CPU.

Free model line-ups change often: the OpenRouter models first configured for this run had been withdrawn from the free tier, and one more was rate-limited when tested. `.env.example` and [USER_GUIDE.md §8](USER_GUIDE.md#8-switching-on-an-llm-optional) explain how to choose models and fallbacks. The results are in [docs/results/llm_runs.json](results/llm_runs.json).

## 10. Efficiency

| Stage | Agents | Time (reference run) |
|---|---|---|
| Plan | Research Director | 0.5 s |
| Collect | Data Collection (including live World Bank calls) | 18.8 s |
| Clean | Data Quality | 2.2 s |
| Analyse, in parallel on 3 workers | Market 8.2 s, Competition 6.1 s, Consumer 72.9 s, Segmentation 58.0 s, Forecasting 89.1 s | about 89 s of wall-clock time |
| Synthesise, write, check | Strategy 0.01 s, Report Writer 3.8 s, Critic 0.02 s | 3.8 s |
| **Total** | 11 agents, 51 tool calls, 37 findings, 174 trace events | **114.4 s** |

Times vary between runs on a laptop. The same code took 114 to 134 s in today's runs, and the previous version of this report measured 48 s. Timed alone, the steps added in this version cost about 3 s: the price bootstrap takes 2.1 s, and the new elasticity model 1.7 s instead of 0.9 s. Most of the variation comes from the three heavy analysis agents (deep learning, clustering and gradient boosting) competing for the same 8 CPU threads, and from the machine's state. A first run adds model training, about 15 s for the linear model and 80 s for the BiGRU. With an LLM switched on, each run adds nine calls, which took 74 to 252 s on the free tiers (section 9). Responses are cached across runs.

## 11. Reproducing these results

```bash
python scripts/generate_data.py                 # seeded: identical data every time
python run.py --no-llm                          # a new offline run
python scripts/evaluate_agents.py               # scores the latest run and writes evaluation.json
python -m pytest -q                             # unit, end-to-end, QA-loop and schema tests
python scripts/multi_seed.py                    # section 7: five more data seeds, 5-10 minutes each
python scripts/ablations.py                     # section 8
python scripts/llm_runs.py                      # section 9; needs at least one LLM key in .env
python scripts/validate_on_real_data.py         # section 4.6; needs the two real datasets in data/external/
```

The three study scripts write `summary.json` files under `outputs/seeds`, `outputs/ablations` and `outputs/llm_runs`; copies of the results reported here are in [docs/results/](results/). Small differences between runs can come from multi-threaded floating-point work in PyTorch and scikit-learn, and LLM runs differ from one call to the next.

## 12. Threats to validity

- **The data was simulated by the same team that built the agents.** The checks prove that the system recovers effects of the kind that were planted. They do not prove it would find real-world effects of other kinds. The generator was written to be realistic (noise, defects, overlapping segments, slang) and was recalibrated against real benchmarks, and the checks read machine-readable metrics, but a pilot on real data is the decisive test. The first real-data check (section 4.6) confirms the risk for text: models trained on simulated reviews do not transfer to real reviews. Adding real reviews to the training data (`--sentiment-data study+real`) fixes this without losing accuracy on the study's reviews.
- **The thresholds were set by the designers** (for example a macro-F1 of at least 0.75, an ARI of at least 0.80). They are conventional, but they are choices. Some checks sit close to a decision boundary in the planted data (the concept price, section 4.5; the fastest-growing category and the declining topics, section 7), so a single run cannot settle them.
- **Five seeds is a small sample.** Section 7 gives failure rates per check, but with five runs a check that fails one time in ten may simply not have failed yet, and the failure rates themselves are rough (3 of 5 could be anything from about 15% to 95%).
- **The labels are proxies.** Star ratings are a noisy stand-in for the sentiment of the text, and the aspect lexicon covers only 9 aspects.
- **The QA gate checks where numbers come from, not whether the tools computed them right.** A dashboard dry run found that a brief asking for a 6-month forecast reported growth of -43%, because six forecast months were compared with twelve actual months. Every number was grounded in tool output, so QA scored the report 100. The comparison now uses the same months a year earlier, and a test pins it for 3, 6 and 12 months; the ground-truth checks use the default 12 months, so they could not have caught it.
- **LLM quality is measured by the Critic, not by people.** Section 9 counts grounding failures and revisions; the usefulness and clarity of the LLM's narrative have not been rated by human readers. Free LLM tiers change their models and limits often, so those runs are snapshots.
- **Known weaknesses:** two brands' elasticity intervals miss the truth because of bias (section 4.4); shocks such as the packaging crisis cannot be forecast (section 4.3); the concept price sits near a charm-price boundary, where four misassigned respondents decide it (section 4.5); and the concept revenue relies on an explicit 5% conversion assumption.

## 13. Recommended next evaluations

1. More seeds (20 or more) to pin down the failure rate of the borderline checks.
2. Fault injection: make each analysis agent fail in turn, and confirm that the study recovers through the Director's follow-up or completes with honest gaps (covered for the market analyst in `tests/test_agentic.py`, and for an analyst plus the Critic in `tests/test_failure_paths.py`).
3. Human evaluation: have marketing practitioners rate the report's usefulness and clarity, blind to whether an LLM was used.
4. Re-run the real-text validation (section 4.6) on the recalibrated data.
5. Make the price research robust to misassigned respondents (section 4.5), for example by running it on each segment's core members (those much closer to their own cluster centre than to the next) or by reporting how far the OPP moves when the most extreme 1% of answers are dropped, and test the change across seeds.
6. A real-data pilot through the documented schemas, judged on whether the findings match what the client's team already knows. The pipeline is ready (`scripts/import_tokopedia.py`, `run.py --data-dir`, [DATA_SOURCES.md §8](DATA_SOURCES.md#8-studying-real-data)); it needs the Tokopedia 2025 file, which a Kaggle account can download.
