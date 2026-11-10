"""Load the research datasets and saved runs into a relational database (docs/schemas/database.sql).

The datasets are cleaned by the Data Quality agent itself before loading, so the database holds the
same analysis-ready data the agents work on, and its constraints double as a check on that cleaning.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from .config import DATA_RAW, DATASETS, ROOT
from .core.store import RunData

SCHEMA_SQL = ROOT / "docs" / "schemas" / "database.sql"
ONLINE_CHANNELS = {"Shopee", "Tokopedia", "TikTok Shop", "Lazada"}


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))


def clean_datasets() -> dict[str, pd.DataFrame]:
    """Run the Data Quality agent on the raw files and return its cleaned tables."""
    from .agents.data_quality import DataQualityAgent
    from .core.agent import RunContext
    from .core.blackboard import Blackboard
    from .core.events import Tracer
    from .core.llm import LLMClient

    raw = {k: pd.read_csv(DATA_RAW / v["file"]) for k, v in DATASETS.items() if (DATA_RAW / v["file"]).exists()}
    bb = Blackboard()
    bb.put("datasets.raw", raw)
    ctx = RunContext("sql-export", bb, Tracer("sql-export"), LLMClient(provider="none"), ROOT, {})
    result = DataQualityAgent(ctx).run()
    if result.status != "completed":
        raise RuntimeError(f"Data Quality agent failed: {result.error}")
    return bb.get("datasets")


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _insert(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    cols = [c for c in _columns(conn, table) if c in df.columns]
    frame = df[cols].copy()
    for c in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[c]):
            frame[c] = frame[c].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_bool_dtype(frame[c]):
            frame[c] = frame[c].astype(int)
    rows = frame.astype(object).where(frame.notna(), None).values.tolist()
    conn.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
    return len(rows)


def load_datasets(conn: sqlite3.Connection, data: dict[str, pd.DataFrame], client: str | None = None) -> dict[str, int]:
    sales, catalog = data["sales"], data["catalog"]
    brands = set(sales["brand"]) | set(catalog["brand"])
    if "survey" in data:
        brands |= set(data["survey"]["main_brand"])
    counts = {
        "dim_brand": _insert(conn, "dim_brand", pd.DataFrame({"brand": sorted(brands),
                                                               "is_client": [int(b == client) for b in sorted(brands)]})),
        "dim_category": _insert(conn, "dim_category", pd.DataFrame({"category": sorted(sales["category"].unique())})),
        "dim_channel": _insert(conn, "dim_channel", pd.DataFrame({"channel": sorted(sales["channel"].unique()),
                                                                   "is_online": [int(c in ONLINE_CHANNELS) for c in sorted(sales["channel"].unique())]})),
        "dim_region": _insert(conn, "dim_region", pd.DataFrame({"region": sorted(sales["region"].unique())})),
        "dim_product": _insert(conn, "dim_product", catalog),
        "fact_sales_monthly": _insert(conn, "fact_sales_monthly", sales),
    }
    if "reviews" in data:
        reviews = data["reviews"].copy()
        reviews["review_text"] = reviews["review_text"].where(reviews["has_text"], None)
        counts["fact_review"] = _insert(conn, "fact_review", reviews)
    if "social" in data:
        social = data["social"].copy()
        social["brand_mentioned"] = social["brand_mentioned"].replace("", None)
        counts["fact_social_post"] = _insert(conn, "fact_social_post", social)
        if "social_labels" in data:
            labels = data["social_labels"][data["social_labels"]["post_id"].isin(social["post_id"])]
            counts["social_label"] = _insert(conn, "social_label", labels)
    if "survey" in data:
        counts["fact_survey_response"] = _insert(conn, "fact_survey_response", data["survey"])
    if "market_size" in data:
        counts["fact_market_size"] = _insert(conn, "fact_market_size", data["market_size"])
    conn.commit()
    return counts


def load_run(conn: sqlite3.Connection, run: RunData) -> dict[str, int]:
    meta = run.meta
    llm, qa = meta.get("llm", {}), meta.get("qa", {})
    conn.execute(
        "INSERT INTO run (run_id, started, status, seconds, brief, client, llm_provider, llm_model, qa_score, qa_passed, qa_revisions) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run.run_id, meta.get("started"), meta.get("status"), meta.get("seconds"), meta.get("brief"), meta.get("client"),
         llm.get("provider"), llm.get("model"), qa.get("score"),
         None if qa.get("passed") is None else int(qa["passed"]), qa.get("revisions")))
    agents = pd.DataFrame([dict(run_id=run.run_id, task_id=tid, **res) for tid, res in meta.get("agents", {}).items()])
    findings = pd.DataFrame([dict(run_id=run.run_id, finding_id=f.id, agent=f.agent, area=f.area, title=f.title,
                                  statement=f.statement, metrics_json=json.dumps(f.metrics, ensure_ascii=False),
                                  evidence_json=json.dumps(f.evidence, ensure_ascii=False), impact=f.impact,
                                  confidence=f.confidence, swot=f.swot, tags_json=json.dumps(f.tags), priority=f.priority)
                             for f in run.findings])
    recs = run.json("strategy.recommendations", []) or []
    rec_df = pd.DataFrame([dict(run_id=run.run_id, rec_id=r["id"], **{k: r.get(k) for k in (
        "title", "action", "rationale", "kpi", "timeline", "horizon", "owner", "effort", "value_idr", "impact", "confidence",
        "priority")}) for r in recs])
    known = set(findings["finding_id"]) if len(findings) else set()
    evidence = pd.DataFrame([dict(run_id=run.run_id, rec_id=r["id"], finding_id=e) for r in recs for e in r["evidence"] if e in known])
    qa_result = run.json("qa.result", {}) or {}
    checks = pd.DataFrame([dict(run_id=run.run_id, revision=qa_result.get("revision", 0), check_name=k, score=v.get("score"))
                           for k, v in qa_result.get("checks", {}).items()])
    trace = pd.DataFrame([dict(run_id=run.run_id, seq=i, ts=e["ts"], agent=e["agent"], kind=e["kind"], message=e["message"],
                               data_json=json.dumps(e.get("data", {}), ensure_ascii=False)) for i, e in enumerate(run.trace)])
    counts = {}
    for table, df in (("agent_result", agents), ("finding", findings), ("recommendation", rec_df),
                      ("recommendation_evidence", evidence), ("qa_check", checks), ("trace_event", trace)):
        counts[table] = _insert(conn, table, df) if len(df) else 0
    conn.commit()
    return counts
