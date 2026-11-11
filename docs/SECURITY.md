# Trust and security

MarketMind produces findings and recommendations that people act on, holds API keys for paid and free LLM services, and can process real marketplace reviews. This document lists what keeps its results trustworthy and the system safe, where each mechanism lives in the code, and the limits that remain. It describes a single-user research tool that runs on your own computer; it is not hardened for hosting on the internet.

## 1. Trustworthy results

| Practice | What it does | Where |
|---|---|---|
| Numbers come from tools, not from the LLM | Every number is computed by a deterministic tool. In the pipeline the LLM only sees those results, as JSON facts, under the shared ground rules: use only the facts, never invent a number, cite finding IDs. The pipeline never puts raw review text into a prompt (review quotes reach the report without passing through the model), which keeps instructions hidden in third-party text away from it. | `core/agent.py` (`ask_llm`, `GROUNDING_RULES`) |
| Answers checked before they are shown | The two on-demand agents verify their own answers with the Critic's number check: the agentic-RAG Analyst Chat against the passages it retrieved (every citation must name one of them), the ReAct Data Agent against its tools' observations. A failing draft goes back once or twice with the reasons; after that the agent shows its evidence instead of an unchecked answer. | `core/grounding.py`, `agents/analyst_chat.py`, `agents/data_agent.py` |
| A QA gate before release | The Critic is fully deterministic. It checks every number in the prose against the tools' outputs, plus citations, coverage of every research question, evidence behind every recommendation and the required disclosures. A failing report goes back for revision (twice at most); if the Critic itself crashes, the run is marked `unverified` and the report says "NOT VERIFIED". | `agents/critic.py`, `agents/director.py` |
| Human approval gates | A person can approve, trim or reject the research plan and the recommendations. Once a person has been asked, a gate never approves on their behalf: a gate nobody answers within 30 minutes, or a review screen that fails, stops the study. Without a reviewer the gates approve automatically, and the report says no reviewer was asked. | `core/approval.py` |
| An audit trail | Every thought, tool call, finding, LLM call, warning and approval is traced and saved with the run (`trace.jsonl`, `run_meta.json`). The report's Appendix D lists the approval decisions and the Director's follow-up requests. | `core/events.py`, `core/store.py` |
| Honest disclosure | The report states whether the data is simulated or real (and its source), which LLM wrote any text or that none did, when the sentiment model learned from simulated reviews only, and "not identified" for an elasticity the data cannot support, instead of an invented slope. | `agents/reporter.py`, `ml/pricing.py` |
| Bounded autonomy | Each run has an LLM budget (40 calls, 300,000 tokens), each agent a time limit (900 s) and one retry, and every step has a deterministic fallback, so the system also works offline. | `system.py`, `core/agent.py`, `core/orchestrator.py` |
| Honest evaluation | 25 checks against answers planted in the simulated data, five more data seeds, ablations and real-LLM runs; misses and threats to validity are documented, not tuned away. | [EVALUATION.md](EVALUATION.md) |

## 2. Security

### Credentials

API keys live in `.env`, which git ignores, and are only sent in request headers, never in URLs, prompts or files. As a last line of defence, `core/redact.py` replaces the value of every environment variable that names a credential (`..._KEY`, `..._TOKEN`, `..._SECRET`, `..._PASSWORD`) with `[redacted]` wherever text leaves the process:

- the agent trace, in the live console and in `trace.jsonl`;
- every file a run saves (reports, tables, JSON artefacts, `findings.json`, `run_meta.json`);
- LLM error messages, so a provider that echoes a key back passes it no further;
- the dashboard's error boxes;
- the web API's responses, event streams and reports.

### Who can reach the servers

Both servers answer on this computer only by default: `.streamlit/config.toml` binds the dashboard to `localhost`, and `python -m api` listens on 127.0.0.1. The web API also refuses requests that name another host (which stops DNS rebinding), and accepts changes only as JSON from its own page (which stops cross-site request forgery).

To share either one on a network, an access token is required (`core/access.py`):

- `python -m api --host 0.0.0.0` makes up a token (or uses `MARKETMIND_ACCESS_TOKEN`) and prints a link that carries it. Opening the link stores the token in an HttpOnly, SameSite=Strict cookie and removes it from the address bar; scripts send `Authorization: Bearer <token>`. Any other request gets 401 and no data (`api/security.py`).
- `streamlit run app/dashboard.py --server.address 0.0.0.0` asks visitors from other computers for `MARKETMIND_ACCESS_TOKEN`, once per browser session. If no token is set, it refuses them.

Tokens are compared in constant time. Setting `MARKETMIND_ACCESS_TOKEN` also protects both servers on this computer, for example from other accounts on a shared machine.

### Input handling

| Input | Check |
|---|---|
| Client name | Matched against the brands in the data; an unknown name stops the run at planning |
| Run IDs and file paths in the API | Run IDs must match a strict pattern, so a request cannot reach other folders; static files must lie inside the built front end |
| Request bodies | Size limits on briefs (4,000 characters), chat and data questions (1,000; 40 turns of history), comments and test sentences; JSON is strict (no NaN) |
| The ReAct Data Agent's tool calls | Eight fixed, read-only tools over in-memory copies of the datasets; every table, column, filter and period is checked, and a wrong one comes back as an error message, never an exception. No code is executed: `calculate` parses arithmetic only (numbers, + - * / ** %, round, abs, min, max). At most six steps per question |

### Data and privacy

- Licensed real data in `data/real/` is git-ignored and never committed or redistributed (the Tokopedia dataset is CC BY-NC 4.0).
- The Tokopedia importer reads no reviewer names or account IDs, and masks e-mail addresses, phone numbers and @handles inside review text as it imports (`core/privacy.py`), so they never reach `data/real/`. The review quotes picked for a report are masked again, whatever the data source.
- The bundled datasets are simulated and contain no real people.

### Dependencies

`requirements.txt` sets version ranges and `requirements-lock.txt` pins the versions the evaluation ran under. The `audit` workflow (`.github/workflows/audit.yml`) runs on every push, on pull requests and every Monday:

- `pip-audit` on the newest versions `requirements.txt` allows, which is what CI and a fresh install get (it fails the workflow on any known vulnerability);
- `pip-audit` on the pinned versions in the lock file (it reports only; see the limits below);
- `npm audit` on the front end's locked packages (it fails on high or critical advisories).

## 3. Known limits

- **No HTTPS.** Shared on a network, the token and the data travel unencrypted. Share only on a network you trust, or put a TLS reverse proxy in front.
- **One shared token, no accounts or roles.** Anyone with the token can read every run and start studies, which spend the LLM budget.
- **The lock file pins versions with known vulnerabilities.** On 11 November 2026, 13 pinned packages had advisories with fixes in newer releases (among them tornado, urllib3, pillow, gitpython and torch). `pip install -r requirements.txt` installs patched versions. Refreshing the lock means re-running the test suite and the evaluation under the new versions, since the documented results were produced with the old ones.
- **The QA gate checks where numbers come from, not whether a tool computed them right** (see the threats to validity in [EVALUATION.md](EVALUATION.md)).
- **Prompt injection is limited by design, not filtered.** The pipeline never sends raw review text to the model, but product and brand names from real data appear in the findings it reads. The two on-demand agents do send review text (masked, and labelled as customer data, not instructions), so a review written to manipulate could sway the wording of an answer. It cannot add a number or a citation that fails verification, and the data agent's tools cannot change anything. The checks catch invented numbers and citations, not slanted wording.
- **Masking catches patterns, not meaning.** It finds e-mail addresses, Indonesian mobile numbers and @handles, not names or addresses written out in words.
- **Saved runs are plain files.** Anyone who can open `outputs/` on the computer can read them.
- **A gate waits 30 minutes.** A reviewer who needs longer has to start the study again.
