"""Central configuration: paths, dataset registry, environment settings and the default brief."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

# MARKETMIND_DATA_DIR and MARKETMIND_OUTPUTS point a run at another dataset and output folder
# (scripts/multi_seed.py uses them to study data generated with other seeds, in isolation)
DATA_DIR = Path(os.getenv("MARKETMIND_DATA_DIR") or ROOT / "data")
DATA_RAW = DATA_DIR / "raw"
DATA_EXTERNAL = ROOT / "data" / "external"     # downloaded corpora and API caches are shared
GROUND_TRUTH = DATA_DIR / "ground_truth.json"
OUTPUTS = Path(os.getenv("MARKETMIND_OUTPUTS") or ROOT / "outputs")
RUNS_DIR = OUTPUTS / "runs"
MODELS_DIR = OUTPUTS / "models"
CACHE_DIR = OUTPUTS / "cache"

DATASETS = {
    "sales": dict(file="market_sales_panel.csv", description="Monthly sell-out panel by brand, category, channel and region",
                  date_col="month", source="Retail & e-commerce panel (simulated)"),
    "catalog": dict(file="product_catalog.csv", description="SKU catalogue with price, size, ingredients, claims and ratings",
                    date_col="launch_month", source="Marketplace scraping (simulated)"),
    "reviews": dict(file="product_reviews.csv", description="E-commerce product reviews (Indonesian) with star ratings",
                    date_col="review_date", source="Shopee / Tokopedia / TikTok Shop / Lazada reviews (simulated)"),
    "social": dict(file="social_mentions.csv", description="Social-listening posts with engagement metrics",
                   date_col="post_date", source="TikTok / Instagram / X / YouTube listening (simulated)"),
    "survey": dict(file="consumer_survey.csv", description="Usage & attitude survey with concept test and Van Westendorp",
                   date_col="survey_date", source="Online consumer panel, n=2,400 (simulated)"),
    "market_size": dict(file="market_size.csv", description="Industry market size by category, 2019-2026E",
                        date_col="year", source="Industry estimate (simulated)"),
    "social_labels": dict(file="social_validation_labels.csv", description="Hand-labelled validation sample of social posts",
                          date_col=None, source="Analyst annotation, n=400 (simulated)"),
}

DEFAULT_CLIENT = "Kirana Beauty"
DEFAULT_BRIEF = (
    "Kirana Beauty wants to accelerate growth in Indonesia's local facial-skincare market over the next 12 months. "
    "Assess market size and trends, our competitive position versus the main local brands, consumer sentiment and "
    "pain points, and which consumer segments to target with a fragrance-free barrier-repair moisturizer concept. "
    "Recommend a price point, forecast demand, and tell us where to play and how to win."
)


# used when the data folder holds real data (a manifest.json says so) and no brief is given
DEFAULT_REAL_BRIEF = (
    "Find out what consumers say about our facial skincare products in real marketplace reviews compared with "
    "competing brands: what they love, which pain points are emerging, and what we should fix first."
)
SIMULATED = dict(kind="simulated", source="MarketMind simulator (scripts/generate_data.py, seeded)",
                 licence="generated for this project", datasets={})


def data_manifest(raw_dir: Path | None = None) -> dict:
    """What the data folder holds: real or simulated data, its source, licence and what was filled in.

    A real-data folder written by an adapter (scripts/import_tokopedia.py) carries a manifest.json next to raw/;
    the bundled simulated data has none.
    """
    path = Path(raw_dir or DATA_RAW).parent / "manifest.json"
    if path.exists():
        import json
        return {**SIMULATED, "datasets": {}, **json.loads(path.read_text(encoding="utf-8"))}
    return dict(SIMULATED)


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def ensure_dirs() -> None:
    for d in (RUNS_DIR, MODELS_DIR, CACHE_DIR, DATA_EXTERNAL):
        d.mkdir(parents=True, exist_ok=True)
