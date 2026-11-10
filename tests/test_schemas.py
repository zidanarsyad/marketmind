"""Contract tests: the published schemas (docs/schemas) must describe what the system really produces.

- Every JSON Schema is itself valid (Draft 2020-12).
- A fresh run's outputs conform: findings, plan, recommendations, QA verdict, model card, run metadata, trace.
- The Data Quality agent's cleaned datasets conform to the row contracts; the raw sales file does not.
- The SQL model loads the clean data and the run with every constraint and foreign key satisfied.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from marketmind.config import DATA_RAW, DATASETS, ROOT

SCHEMAS = ROOT / "docs" / "schemas"
DATASET_SCHEMAS = {"sales": "sales_panel_row", "reviews": "review_row", "social": "social_post_row",
                   "survey": "survey_response_row", "catalog": "product_row", "market_size": "market_size_row",
                   "social_labels": "social_label_row"}


@pytest.fixture(scope="module")
def registry():
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in SCHEMAS.rglob("*.schema.json")]
    return Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in docs])


def validator(name: str, registry) -> Draft202012Validator:
    path = next(SCHEMAS.rglob(f"{name}.schema.json"))
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), registry=registry)


def errors(v: Draft202012Validator, instance) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(instance)][:5]


def records(df: pd.DataFrame, n: int = 400) -> list[dict]:
    d = df.sample(min(n, len(df)), random_state=0).copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
    return d.astype(object).where(d.notna(), None).to_dict(orient="records")


def test_every_schema_is_valid():
    paths = list(SCHEMAS.rglob("*.schema.json"))
    assert len(paths) >= 14
    for p in paths:
        Draft202012Validator.check_schema(json.loads(p.read_text(encoding="utf-8")))


def test_run_outputs_match_schemas(offline_run, registry):
    _, _, run = offline_run
    checks = [("finding", f) for f in json.loads((run.path / "findings.json").read_text(encoding="utf-8"))]
    checks += [("research_plan", run.json("plan")), ("qa_result", run.json("qa.result")),
               ("sentiment_model_card", run.json("consumer.model_card")), ("run_meta", run.meta)]
    checks += [("recommendation", r) for r in run.json("strategy.recommendations")]
    checks += [("trace_event", e) for e in run.trace]
    for name, instance in checks:
        assert not errors(validator(name, registry), instance), (name, errors(validator(name, registry), instance))


@pytest.fixture(scope="module")
def clean_data():
    from marketmind.sql_export import clean_datasets
    return clean_datasets()


def test_clean_datasets_match_row_contracts(clean_data, registry):
    for key, name in DATASET_SCHEMAS.items():
        v = validator(name, registry)
        bad = [errors(v, row) for row in records(clean_data[key]) if errors(v, row)]
        assert not bad, (key, bad[:3])


def test_raw_sales_violates_the_contract(registry):
    raw = pd.read_csv(DATA_RAW / DATASETS["sales"]["file"])
    v = validator("sales_panel_row", registry)
    rows = raw.astype(object).where(raw.notna(), None).to_dict(orient="records")
    assert any(errors(v, r) for r in rows), "the raw file carries deliberate defects for the Data Quality agent"


def test_sql_model_loads_data_and_run(clean_data, offline_run):
    from marketmind.sql_export import connect, create_schema, load_datasets, load_run

    _, _, run = offline_run
    conn = connect(":memory:")
    create_schema(conn)
    counts = load_datasets(conn, clean_data, run.meta["client"])
    counts.update(load_run(conn, run))
    assert counts["fact_sales_monthly"] == len(clean_data["sales"])
    assert counts["finding"] == len(run.findings) and counts["recommendation"] >= 3
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    share = conn.execute("SELECT SUM(value_share) FROM v_brand_share_monthly WHERE month = (SELECT MAX(month) FROM fact_sales_monthly)").fetchone()[0]
    assert abs(share - 1.0) < 1e-9
