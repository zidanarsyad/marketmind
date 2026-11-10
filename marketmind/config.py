"""Central configuration: paths, dataset registry, environment settings and the default brief."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_EXTERNAL = ROOT / "data" / "external"
GROUND_TRUTH = ROOT / "data" / "ground_truth.json"
OUTPUTS = ROOT / "outputs"
RUNS_DIR = OUTPUTS / "runs"
MODELS_DIR = OUTPUTS / "models"
CACHE_DIR = OUTPUTS / "cache"

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

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


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def ensure_dirs() -> None:
    for d in (RUNS_DIR, MODELS_DIR, CACHE_DIR, DATA_EXTERNAL):
        d.mkdir(parents=True, exist_ok=True)
