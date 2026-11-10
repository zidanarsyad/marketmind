#!/usr/bin/env python
"""Generate realistic synthetic datasets for the MarketMind multi-agent market research system.

Scenario
--------
Indonesian local facial-skincare market, January 2023 - October 2026.
Client: **Kirana Beauty** (fictional). Competitors (fictional): Lumiere Lab, DewiSkin,
GlowNesia, Aurelia Derma, Purabotanica.

Files written to ``data/raw``:

* ``market_sales_panel.csv``  monthly sell-out panel (brand x category x channel x region)
* ``product_catalog.csv``     SKU catalogue (price, size, key ingredient, claims, rating)
* ``product_reviews.csv``     e-commerce reviews in Indonesian (slang, emojis, typos) + stars
* ``social_mentions.csv``     social-listening posts (TikTok / Instagram / X / YouTube), unlabeled
* ``consumer_survey.csv``     usage & attitude survey + concept test + Van Westendorp pricing
* ``market_size.csv``         industry market size by category, 2019 - 2026E
* ``social_validation_labels.csv``  400 hand-labelled social posts for validating model transfer

``data/ground_truth.json`` records every effect planted in the data (elasticities, events,
segments, trends, data-quality defects) so the agents' findings can be scored objectively
with ``scripts/evaluate_agents.py``.

All brands, products and respondents are fictional. Everything is seeded and reproducible.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

SEED = 2026
P = pd.Period
MONTHS = pd.period_range("2023-01", "2026-10", freq="M")

CATEGORIES = ["Facial Wash", "Toner", "Serum", "Moisturizer", "Sunscreen"]
CHANNELS = ["Shopee", "Tokopedia", "TikTok Shop", "Lazada", "Offline Retail"]
ONLINE = CHANNELS[:4]
REGIONS = [
    "DKI Jakarta & Banten", "Jawa Barat", "Jawa Tengah & DIY", "Jawa Timur",
    "Sumatera", "Kalimantan & Sulawesi", "Bali & Indonesia Timur",
]
REGION_BASE = np.array([0.26, 0.18, 0.13, 0.16, 0.14, 0.09, 0.04])
REGION_GROWTH = np.array([-0.04, 0.00, 0.01, 0.00, 0.045, 0.075, 0.03])  # extra yearly growth vs national

CAT_PRICE = {"Facial Wash": 45000, "Toner": 65000, "Serum": 89000, "Moisturizer": 75000, "Sunscreen": 69000}
CAT_TILT = {"Facial Wash": -0.03, "Toner": -0.06, "Serum": 0.02, "Moisturizer": 0.01, "Sunscreen": 0.12}

CLIENT = "Kirana Beauty"
BRANDS: dict[str, dict] = {
    "Kirana Beauty": dict(
        price_index=1.00, base_rev=40e9, elasticity=-1.3, promo=1.0, review_rate=2.4,  # client scrapes all own reviews
        growth={2023: 0.16, 2024: 0.17, 2025: 0.13, 2026: 0.11},
        cat_mix={"Facial Wash": 0.18, "Toner": 0.10, "Serum": 0.14, "Moisturizer": 0.30, "Sunscreen": 0.28},
        ch_start=[0.40, 0.18, 0.07, 0.08, 0.27], ch_end=[0.38, 0.11, 0.12, 0.07, 0.32],
        region_tilt=[1.15, 1.40, 1.00, 0.85, 0.65, 0.55, 0.80],
        quality=dict(efektivitas=0.80, tekstur=0.88, aroma=0.74, kemasan=0.82, harga=0.66,
                     pengiriman=0.84, reaksi_kulit=0.82, keaslian=0.96, stok=0.86),
    ),
    "Lumière Lab": dict(
        price_index=1.35, base_rev=96e9, elasticity=-0.9, promo=0.8, review_rate=1.0,
        growth={2023: 0.10, 2024: 0.10, 2025: 0.10, 2026: 0.11},
        cat_mix={"Facial Wash": 0.12, "Toner": 0.16, "Serum": 0.40, "Moisturizer": 0.18, "Sunscreen": 0.14},
        ch_start=[0.38, 0.24, 0.10, 0.10, 0.18], ch_end=[0.34, 0.16, 0.24, 0.08, 0.18],
        region_tilt=[1.25, 1.10, 0.95, 1.00, 0.90, 0.80, 1.00],
        quality=dict(efektivitas=0.89, tekstur=0.85, aroma=0.82, kemasan=0.86, harga=0.42,
                     pengiriman=0.86, reaksi_kulit=0.87, keaslian=0.96, stok=0.90),
    ),
    "DewiSkin": dict(
        price_index=0.75, base_rev=87.5e9, elasticity=-1.5, promo=1.0, review_rate=0.85,
        growth={2023: 0.02, 2024: 0.02, 2025: 0.01, 2026: 0.03},
        cat_mix={"Facial Wash": 0.32, "Toner": 0.14, "Serum": 0.12, "Moisturizer": 0.24, "Sunscreen": 0.18},
        ch_start=[0.22, 0.10, 0.05, 0.06, 0.57], ch_end=[0.22, 0.07, 0.14, 0.05, 0.52],
        region_tilt=[0.85, 0.95, 1.30, 1.30, 1.00, 0.90, 0.80],
        quality=dict(efektivitas=0.70, tekstur=0.75, aroma=0.72, kemasan=0.72, harga=0.88,
                     pengiriman=0.80, reaksi_kulit=0.80, keaslian=0.95, stok=0.92),
    ),
    "GlowNesia": dict(
        price_index=0.65, base_rev=35e9, elasticity=-1.8, promo=1.4, review_rate=1.3,
        growth={2023: 0.42, 2024: 0.38, 2025: 0.30, 2026: 0.22},
        cat_mix={"Facial Wash": 0.18, "Toner": 0.10, "Serum": 0.30, "Moisturizer": 0.16, "Sunscreen": 0.26},
        ch_start=[0.30, 0.10, 0.45, 0.05, 0.10], ch_end=[0.22, 0.05, 0.62, 0.03, 0.08],
        region_tilt=[0.90, 0.95, 0.95, 1.00, 1.20, 1.30, 1.00],
        quality=dict(efektivitas=0.73, tekstur=0.77, aroma=0.70, kemasan=0.68, harga=0.91,
                     pengiriman=0.74, reaksi_kulit=0.66, keaslian=0.82, stok=0.80),
    ),
    "Aurelia Derma": dict(
        price_index=2.10, base_rev=46.7e9, elasticity=-0.6, promo=0.7, review_rate=0.8,
        growth={2023: -0.01, 2024: -0.03, 2025: -0.05, 2026: -0.05},
        cat_mix={"Facial Wash": 0.10, "Toner": 0.12, "Serum": 0.34, "Moisturizer": 0.32, "Sunscreen": 0.12},
        ch_start=[0.25, 0.20, 0.03, 0.07, 0.45], ch_end=[0.28, 0.14, 0.08, 0.06, 0.44],
        region_tilt=[1.50, 1.00, 0.80, 0.95, 0.75, 0.70, 1.10],
        quality=dict(efektivitas=0.87, tekstur=0.83, aroma=0.84, kemasan=0.91, harga=0.33,
                     pengiriman=0.86, reaksi_kulit=0.88, keaslian=0.97, stok=0.92),
    ),
    "Purabotanica": dict(
        price_index=1.15, base_rev=25e9, elasticity=-1.1, promo=0.8, review_rate=1.0,
        growth={2023: 0.08, 2024: 0.10, 2025: 0.12, 2026: 0.14},
        cat_mix={"Facial Wash": 0.24, "Toner": 0.26, "Serum": 0.18, "Moisturizer": 0.20, "Sunscreen": 0.12},
        ch_start=[0.42, 0.25, 0.08, 0.10, 0.15], ch_end=[0.40, 0.16, 0.20, 0.08, 0.16],
        region_tilt=[1.20, 1.10, 1.00, 0.90, 0.85, 0.80, 1.40],
        quality=dict(efektivitas=0.77, tekstur=0.81, aroma=0.52, kemasan=0.83, harga=0.58,
                     pengiriman=0.80, reaksi_kulit=0.73, keaslian=0.95, stok=0.88),
    ),
}
BRAND_NAMES = list(BRANDS)

# Indonesian festive calendar (government dates). Eid al-Fitr is the day after Ramadan ends.
RAMADAN = {
    2023: ("2023-03-23", "2023-04-21"), 2024: ("2024-03-12", "2024-04-09"),
    2025: ("2025-03-01", "2025-03-30"), 2026: ("2026-02-18", "2026-03-19"),
}

# ----------------------------------------------------------------------------- helpers

def months_since(m: pd.Period, ref: str) -> int:
    return (m - P(ref, freq="M")).n


def festive_factor(m: pd.Period) -> tuple[float, float]:
    """Return (demand multiplier, share of days inside Ramadan) for a month.

    Ramadan lifts demand (THR holiday bonus, Eid gifting); the two weeks before Eid peak,
    and the week after Eid dips while shops close and people travel (mudik).
    """
    days = pd.date_range(m.start_time, m.end_time.normalize(), freq="D")
    mult, in_ramadan = [], 0
    for d in days:
        f = 1.0
        for start, end in RAMADAN.values():
            s, e = pd.Timestamp(start), pd.Timestamp(end)
            eid = e + pd.Timedelta(days=1)
            if s <= d <= e:
                f = 1.40 if (eid - d).days <= 14 else 1.12
                in_ramadan += 1
            elif eid <= d <= eid + pd.Timedelta(days=6):
                f = 0.80
        mult.append(f)
    return float(np.mean(mult)), in_ramadan / len(days)


FESTIVE = {m: festive_factor(m) for m in MONTHS}
ECOM_EVENT = {6: 1.03, 7: 1.03, 8: 1.03, 9: 1.06, 10: 1.06, 11: 1.22, 12: 1.18}
OFFLINE_EVENT = {12: 1.08, 1: 0.95}
GENERAL = {1: 0.94, 2: 0.98}
CAT_SEASON = {
    "Sunscreen": {6: 1.10, 7: 1.12, 8: 1.08, 12: 0.94, 1: 0.93, 2: 0.95},
    "Moisturizer": {7: 1.04, 8: 1.05, 9: 1.03},
}
CH_BASE_DISC = {"Shopee": 0.08, "Tokopedia": 0.07, "TikTok Shop": 0.12, "Lazada": 0.09, "Offline Retail": 0.03}
LINE_PREMIUM = {
    ("Lumière Lab", "Serum"): 1.08, ("Aurelia Derma", "Moisturizer"): 1.12,
    ("GlowNesia", "Sunscreen"): 0.95, ("DewiSkin", "Facial Wash"): 0.96,
}


def season(m: pd.Period, ch: str, cat: str) -> float:
    f = FESTIVE[m][0] * GENERAL.get(m.month, 1.0)
    f *= ECOM_EVENT.get(m.month, 1.0) if ch in ONLINE else OFFLINE_EVENT.get(m.month, 1.0)
    f *= CAT_SEASON.get(cat, {}).get(m.month, 1.0)
    return f * m.days_in_month / 30.44


def demand_event(brand: str, m: pd.Period, cat: str, ch: str) -> float:
    """Brand-specific market events planted in the data (see ground_truth.json)."""
    f = 1.0
    if brand == "GlowNesia":
        if m >= P("2024-08", freq="M"):  # viral TikTok campaign
            k = months_since(m, "2024-08")
            f *= (1.30 + 0.40 * math.exp(-k / 3)) if ch == "TikTok Shop" else 1.05
        f *= {"2026-05": 0.80, "2026-06": 0.75, "2026-07": 0.85, "2026-08": 0.93, "2026-09": 0.97}.get(str(m), 1.0)
    if brand == CLIENT:
        if cat == "Sunscreen" and m >= P("2024-03", freq="M"):  # UV Shield Aqua Gel launch
            f *= 1 + 0.45 * (1 - math.exp(-months_since(m, "2024-03") / 4))
        if cat == "Moisturizer":  # pump-defect complaints, returns
            f *= {"2026-02": 0.93, "2026-03": 0.88, "2026-04": 0.90, "2026-05": 0.96}.get(str(m), 1.0)
    if brand == "Lumière Lab" and cat == "Serum" and m >= P("2025-10", freq="M"):  # ceramide serum launch
        f *= 1 + 0.28 * (1 - math.exp(-months_since(m, "2025-10") / 2.5))
    if brand == "DewiSkin" and ch in ONLINE and m >= P("2026-01", freq="M"):  # rebrand
        f *= 1 + 0.18 * (1 - math.exp(-months_since(m, "2026-01") / 3))
    if brand == "Purabotanica" and m >= P("2025-06", freq="M"):  # refill campaign
        f *= 1.12
    return f


def list_price(brand: str, cat: str, m: pd.Period) -> float:
    b = BRANDS[brand]
    price = CAT_PRICE[cat] * b["price_index"] * LINE_PREMIUM.get((brand, cat), 1.0)
    price *= 1.03 ** (m.year - 2023)  # yearly list-price indexation
    if brand == CLIENT and m >= P("2025-07", freq="M"):
        price *= 1.12  # Kirana list-price increase, July 2025
    return round(price / 500) * 500


def ref_price(brand: str, cat: str) -> float:
    return CAT_PRICE[cat] * BRANDS[brand]["price_index"] * LINE_PREMIUM.get((brand, cat), 1.0) * 0.91


# ----------------------------------------------------------------------------- sales panel

def build_sales(rng: np.random.Generator) -> pd.DataFrame:
    t_years = np.arange(len(MONTHS)) / 12.0

    trend = {}
    for brand, b in BRANDS.items():
        levels, lvl = [], 1.0
        for m in MONTHS:
            levels.append(lvl)
            lvl *= (1 + b["growth"][m.year]) ** (1 / 12)
        trend[brand] = np.array(levels)

    shocks = {}
    for brand in BRANDS:
        s, out = 0.0, []
        for _ in MONTHS:
            s = 0.5 * s + rng.normal(0, 0.03)
            out.append(s)
        shocks[brand] = np.exp(out)

    stockouts = {}
    for brand in BRANDS:
        for ch in CHANNELS:
            for m in MONTHS:
                stockouts[(brand, ch, m)] = int(rng.random() < 0.04) * int(rng.integers(1, 4))
    stockouts[(CLIENT, "TikTok Shop", P("2026-02", freq="M"))] = 9
    stockouts[(CLIENT, "TikTok Shop", P("2026-03", freq="M"))] = 12

    disc_noise = {(b, ch, m): rng.normal(0, 0.05) for b in BRANDS for ch in CHANNELS for m in MONTHS}

    rows = []
    for ti, m in enumerate(MONTHS):
        ramadan_share = FESTIVE[m][1]
        for brand, b in BRANDS.items():
            w = ti / (len(MONTHS) - 1)
            ch_mix = (1 - w) * np.array(b["ch_start"]) + w * np.array(b["ch_end"])
            ch_mix /= ch_mix.sum()
            cat_w = np.array([b["cat_mix"][c] * math.exp(CAT_TILT[c] * t_years[ti]) for c in CATEGORIES])
            cat_w /= cat_w.sum()
            reg_w = REGION_BASE * np.exp(REGION_GROWTH * t_years[ti]) * np.array(b["region_tilt"])
            reg_w /= reg_w.sum()
            base = b["base_rev"] * trend[brand][ti] * shocks[brand][ti]
            for ci, cat in enumerate(CATEGORIES):
                lp = list_price(brand, cat, m)
                rp = ref_price(brand, cat)
                for hi, ch in enumerate(CHANNELS):
                    d = CH_BASE_DISC[ch]
                    if ch in ONLINE:
                        d += {11: 0.12, 12: 0.10, 9: 0.04, 10: 0.04}.get(m.month, 0.0)
                    if ramadan_share > 0.3:
                        d += 0.06 if ch in ONLINE else 0.03
                    d *= b["promo"]
                    if brand == "Aurelia Derma" and str(m) == "2025-12" and ch in ONLINE:
                        d = 0.35  # one-off 12.12 clearance
                    d = float(np.clip(d + disc_noise[(brand, ch, m)] + rng.normal(0, 0.02), 0.0, 0.5))
                    eff = lp * (1 - d)
                    oos = stockouts[(brand, ch, m)]
                    demand_rev = base * season(m, ch, cat) * demand_event(brand, m, cat, ch) * cat_w[ci] * ch_mix[hi]
                    for ri, region in enumerate(REGIONS):
                        units = demand_rev * reg_w[ri] / rp
                        units *= (eff / rp) ** b["elasticity"]
                        units *= 1 - oos / m.days_in_month
                        units *= rng.lognormal(0, 0.08)
                        units = max(int(round(units)), 0)
                        rows.append((m.start_time.date().isoformat(), brand, cat, ch, region, units,
                                     round(units * eff), lp, round(eff), round(d, 3), d >= 0.15, oos))
    df = pd.DataFrame(rows, columns=[
        "month", "brand", "category", "channel", "region", "units", "revenue_idr",
        "list_price_idr", "avg_selling_price_idr", "discount_pct", "promo_flag", "stockout_days",
    ])
    return df


def inject_sales_defects(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    n = len(df)
    miss_idx = rng.choice(n, size=int(0.01 * n), replace=False)
    df.loc[miss_idx, "discount_pct"] = np.nan
    neg_idx = rng.choice(n, size=12, replace=False)
    df.loc[neg_idx, ["units", "revenue_idr"]] *= -1
    out_idx = rng.choice(np.setdiff1d(np.arange(n), neg_idx), size=8, replace=False)
    df.loc[out_idx, ["units", "revenue_idr"]] *= 12
    variants = {"TikTok Shop": "Tiktok Shop", "Tokopedia": "tokopedia", "Shopee": "SHOPEE", "Offline Retail": "Offline"}
    var_idx = rng.choice(n, size=int(0.005 * n), replace=False)
    df.loc[var_idx, "channel"] = df.loc[var_idx, "channel"].map(lambda c: variants.get(c, c))
    dup = df.sample(frac=0.003, random_state=SEED)
    df = pd.concat([df, dup], ignore_index=True)
    return df, dict(missing_discount=len(miss_idx), negative_units=len(neg_idx), outliers_x12=len(out_idx),
                    channel_label_variants=len(var_idx), duplicate_rows=len(dup))


# ----------------------------------------------------------------------------- catalogue

CATALOG_SPEC = [
    # brand, product, category, key ingredient, size_ml, price, launch, fragrance_free, spf
    (CLIENT, "Kirana Bright Rice Gentle Facial Wash", "Facial Wash", "Rice extract + amino acid", 100, 42900, "2021-03", False, None),
    (CLIENT, "Kirana Acne Calm Salicylic Facial Wash", "Facial Wash", "Salicylic acid 1%", 100, 45900, "2022-02", True, None),
    (CLIENT, "Kirana Bright Rice Essence Toner", "Toner", "Rice water + niacinamide", 100, 64900, "2021-06", False, None),
    (CLIENT, "Kirana 5% Niacinamide Bright Serum", "Serum", "Niacinamide", 20, 79900, "2021-09", True, None),
    (CLIENT, "Kirana Acne Calm 2% BHA Serum", "Serum", "Salicylic acid", 20, 84900, "2022-07", True, None),
    (CLIENT, "Kirana Hydra Barrier Moisturizer (Pump)", "Moisturizer", "Hyaluronic acid + ceramide", 40, 79900, "2021-01", False, None),
    (CLIENT, "Kirana Hydra Barrier Gel Cream", "Moisturizer", "Hyaluronic acid", 30, 69900, "2022-05", False, None),
    (CLIENT, "Kirana UV Shield Tone-Up SPF 40 PA+++", "Sunscreen", "Tone-up chemical filters", 40, 62900, "2022-01", False, 40),
    (CLIENT, "Kirana UV Shield Aqua Gel SPF 50 PA++++", "Sunscreen", "Chemical filters + hyaluronic acid", 50, 69900, "2024-03", True, 50),
    (CLIENT, "Kirana UV Shield Aqua Gel SPF 50 Travel Size", "Sunscreen", "Chemical filters + hyaluronic acid", 15, 29900, "2024-09", True, 50),
    ("Lumière Lab", "Lumière Lab Low pH Amino Cleanser", "Facial Wash", "Amino acid", 100, 59900, "2020-05", True, None),
    ("Lumière Lab", "Lumière Lab AHA/BHA Clarifying Toner", "Toner", "AHA/BHA", 100, 89900, "2020-08", True, None),
    ("Lumière Lab", "Lumière Lab Hyaluronic Water Toner", "Toner", "Hyaluronic acid", 150, 95000, "2023-05", True, None),
    ("Lumière Lab", "Lumière Lab 10% Niacinamide Bright Serum", "Serum", "Niacinamide", 20, 119000, "2020-02", True, None),
    ("Lumière Lab", "Lumière Lab 15% Vitamin C Radiance Serum", "Serum", "Vitamin C", 20, 129000, "2021-04", True, None),
    ("Lumière Lab", "Lumière Lab 0.3% Retinol Renewal Serum", "Serum", "Retinol", 20, 139000, "2022-09", True, None),
    ("Lumière Lab", "Lumière Lab Barrier Ceramide Serum", "Serum", "Ceramide + peptide", 20, 135000, "2025-10", True, None),
    ("Lumière Lab", "Lumière Lab Ceramide Barrier Cream", "Moisturizer", "Ceramide", 30, 149000, "2021-11", True, None),
    ("Lumière Lab", "Lumière Lab Daily Fluid Sunscreen SPF 50 PA++++", "Sunscreen", "Hybrid filters", 50, 99000, "2022-03", True, 50),
    ("DewiSkin", "DewiSkin Fresh Halal Facial Foam", "Facial Wash", "Green tea", 100, 32500, "2015-01", False, None),
    ("DewiSkin", "DewiSkin Bright Glow Facial Wash", "Facial Wash", "Vitamin C", 100, 34500, "2018-06", False, None),
    ("DewiSkin", "DewiSkin Fresh Halal Toner", "Toner", "Witch hazel", 150, 39900, "2016-03", False, None),
    ("DewiSkin", "DewiSkin Bright Glow Serum", "Serum", "Niacinamide + licorice", 20, 59900, "2020-10", False, None),
    ("DewiSkin", "DewiSkin Daily Moisturizer Gel", "Moisturizer", "Aloe vera", 40, 45900, "2017-04", False, None),
    ("DewiSkin", "DewiSkin Bright Glow Day Cream SPF 30", "Moisturizer", "Niacinamide", 30, 52900, "2019-02", False, 30),
    ("DewiSkin", "DewiSkin Daily Barrier Cream", "Moisturizer", "Ceramide", 40, 54900, "2026-01", False, None),
    ("DewiSkin", "DewiSkin Sun Protect Lotion SPF 50 PA+++", "Sunscreen", "Chemical filters", 50, 49900, "2020-01", False, 50),
    ("GlowNesia", "GlowNesia 2% Salicylic Acne Facial Wash", "Facial Wash", "Salicylic acid", 100, 29900, "2022-01", False, None),
    ("GlowNesia", "GlowNesia Mugwort Calming Toner", "Toner", "Mugwort", 100, 39900, "2022-06", False, None),
    ("GlowNesia", "GlowNesia 2% Salicylic Acne Serum", "Serum", "Salicylic acid", 20, 49900, "2021-11", False, None),
    ("GlowNesia", "GlowNesia 10% Niacinamide Glow Serum", "Serum", "Niacinamide", 20, 49900, "2022-03", False, None),
    ("GlowNesia", "GlowNesia Peptide Firming Serum", "Serum", "Peptide", 20, 59900, "2025-08", False, None),
    ("GlowNesia", "GlowNesia Ceramide Gel Moisturizer", "Moisturizer", "Ceramide", 30, 45900, "2022-08", False, None),
    ("GlowNesia", "GlowNesia Glass Skin Sunscreen SPF 50 PA++++", "Sunscreen", "Chemical filters", 50, 44900, "2022-05", False, 50),
    ("GlowNesia", "GlowNesia Glass Skin Sunscreen Spray SPF 50", "Sunscreen", "Chemical filters", 100, 54900, "2024-11", False, 50),
    ("Aurelia Derma", "Aurelia Derma Silk Cleansing Milk", "Facial Wash", "Squalane", 120, 115000, "2018-03", True, None),
    ("Aurelia Derma", "Aurelia Derma Peptide Essence Toner", "Toner", "Peptide", 120, 189000, "2019-05", True, None),
    ("Aurelia Derma", "Aurelia Derma Age Reverse Retinol Serum", "Serum", "Retinol", 30, 289000, "2019-09", True, None),
    ("Aurelia Derma", "Aurelia Derma Peptide Lift Serum", "Serum", "Peptide", 30, 319000, "2021-06", True, None),
    ("Aurelia Derma", "Aurelia Derma Peptide Repair Cream", "Moisturizer", "Peptide + ceramide", 50, 245000, "2020-02", True, None),
    ("Aurelia Derma", "Aurelia Derma Retinol Night Cream", "Moisturizer", "Retinol", 50, 265000, "2018-10", False, None),
    ("Aurelia Derma", "Aurelia Derma Mineral Sunscreen SPF 50", "Sunscreen", "Mineral (zinc oxide)", 40, 179000, "2021-03", True, 50),
    ("Purabotanica", "Purabotanica Rice & Tea Gentle Cleanser", "Facial Wash", "Rice + green tea", 120, 54900, "2020-07", False, None),
    ("Purabotanica", "Purabotanica Centella Calming Toner", "Toner", "Centella asiatica", 150, 74900, "2020-03", False, None),
    ("Purabotanica", "Purabotanica Centella Calming Toner Refill Pouch", "Toner", "Centella asiatica", 300, 99900, "2025-06", False, None),
    ("Purabotanica", "Purabotanica Rosehip Glow Serum", "Serum", "Rosehip oil", 20, 99900, "2021-08", False, None),
    ("Purabotanica", "Purabotanica Rosemary Barrier Cream", "Moisturizer", "Ceramide + rosemary oil", 40, 95000, "2022-04", False, None),
    ("Purabotanica", "Purabotanica Aloe Soothing Gel", "Moisturizer", "Aloe vera", 100, 59900, "2021-05", False, None),
    ("Purabotanica", "Purabotanica Zinc Botanical Sunscreen SPF 35", "Sunscreen", "Mineral (zinc oxide)", 50, 89900, "2022-09", False, 35),
]


def build_catalog_base() -> pd.DataFrame:
    df = pd.DataFrame(CATALOG_SPEC, columns=[
        "brand", "product_name", "category", "key_ingredient", "size_ml", "price_idr",
        "launch_month", "fragrance_free", "spf",
    ])
    df.insert(0, "sku_id", [f"SKU-{i:03d}" for i in range(1, len(df) + 1)])
    df["price_per_ml_idr"] = (df["price_idr"] / df["size_ml"]).round(0)
    df["halal_certified"] = df["brand"].ne("Aurelia Derma") | df["product_name"].str.contains("Sunscreen")
    df["bpom_registered"] = True
    return df


# ----------------------------------------------------------------------------- review text engine

ASPECTS = ["efektivitas", "tekstur", "aroma", "kemasan", "harga", "pengiriman", "reaksi_kulit", "keaslian", "stok"]
ASPECT_WEIGHT = dict(efektivitas=1.5, tekstur=1.0, aroma=0.8, kemasan=0.8, harga=0.9, pengiriman=0.6,
                     reaksi_kulit=1.5, keaslian=1.4, stok=0.6)
MENTION = dict(efektivitas=0.55, tekstur=0.40, aroma=0.22, kemasan=0.22, harga=0.28, pengiriman=0.33,
               reaksi_kulit=0.28, keaslian=0.05, stok=0.04)

PHRASES = {
    "efektivitas": {
        "pos": ["kulit jadi lebih cerah dan glowing", "bekas jerawat mulai pudar setelah {w} minggu",
                "kusamnya berkurang banget", "hasilnya keliatan dalam {w} minggu", "beneran ngefek di kulitku",
                "pori-pori keliatan lebih kecil", "dark spot pelan-pelan memudar", "kulit lebih halus dan kenyal",
                "skin barrier aku membaik", "jerawat cepet kempes", "efeknya kerasa dari pemakaian pertama",
                "kulitku sehat banget sekarang"],
        "neg": ["belum keliatan hasilnya padahal udah {w} minggu", "ga ngefek sama sekali",
                "hasilnya biasa aja, ga sesuai klaim", "jerawat tetep muncul terus", "kusamnya ga berkurang",
                "klaimnya lebay", "efeknya ga kerasa", "buang-buang duit, ga ada perubahan"],
    },
    "tekstur": {
        "pos": ["teksturnya ringan", "cepet meresap", "ga lengket sama sekali", "teksturnya adem di kulit",
                "enak dipake di bawah makeup", "watery dan nyaman dipake", "ga bikin muka berminyak"],
        "neg": ["teksturnya lengket", "berat banget di kulit", "lama nyerapnya", "bikin muka greasy",
                "pilling kalo ditumpuk", "terlalu kental"],
    },
    "aroma": {
        "pos": ["wanginya enak dan ga nyengat", "ga ada bau sama sekali, aman buat yang sensitif",
                "aromanya fresh", "wanginya calming"],
        "neg": ["baunya nyengat banget", "wanginya terlalu kuat", "bau alkoholnya kecium",
                "aromanya bikin pusing", "wangi parfumnya bikin perih"],
    },
    "kemasan": {
        "pos": ["kemasannya cantik dan kokoh", "pump-nya gampang dipake", "botolnya travel friendly",
                "packagingnya premium", "segelnya rapi"],
        "neg": ["tutupnya gampang patah", "botolnya bocor pas sampe", "kemasannya penyok",
                "isinya tumpah karena kemasan ga rapet", "kemasannya ringkih"],
    },
    "harga": {
        "pos": ["harganya terjangkau", "worth it banget sama harganya", "murah tapi kualitasnya bagus",
                "harganya bersahabat buat pelajar", "lagi promo jadi makin murah"],
        "neg": ["harganya kemahalan", "pricey buat ukuran segini", "isinya dikit buat harga segitu",
                "mending cari dupe yang lebih murah", "harganya ga masuk akal"],
    },
    "pengiriman": {
        "pos": ["pengiriman cepet", "packing aman pake bubble wrap", "seller responsif",
                "sampe dalam 2 hari", "kurirnya ramah"],
        "neg": ["pengirimannya lama banget", "packingnya asal-asalan", "barangnya telat seminggu",
                "seller slow respon", "salah kirim varian"],
    },
    "reaksi_kulit": {
        "pos": ["ga bikin breakout", "cocok di kulit sensitif aku", "ga perih sama sekali",
                "aman buat kulit berjerawat", "ga bikin bruntusan"],
        "neg": ["bikin breakout parah", "muncul bruntusan di jidat", "perih pas dipake",
                "kulit jadi merah-merah", "jerawat malah tambah banyak", "gatel-gatel setelah pemakaian"],
    },
    "keaslian": {
        "pos": ["original, nomor BPOM-nya ada", "barang ori dari official store", "barcode-nya asli"],
        "neg": ["curiga barangnya palsu", "beda sama yang biasa aku beli, teksturnya lain",
                "kemasannya beda, takut fake", "nomor BPOM-nya ga ke-detect", "kayaknya dapet barang KW"],
    },
    "stok": {
        "pos": ["akhirnya restock juga", "stoknya selalu ada"],
        "neg": ["stoknya sering kosong", "susah banget dapetinnya, selalu sold out",
                "nunggu restock lama banget", "kehabisan pas flash sale"],
    },
}
CAT_PHRASES = {
    ("efektivitas", "Sunscreen"): {"pos": ["muka ga gosong walau sering di luar", "ga belang lagi"],
                                    "neg": ["tetep gosong padahal udah reapply", "muka tetep merah kena matahari"]},
    ("efektivitas", "Facial Wash"): {"pos": ["bersihin sisa makeup sampe tuntas", "muka bersih tapi ga ketarik"],
                                      "neg": ["ga bersih ngangkat sunscreen", "muka masih berminyak abis cuci muka"]},
    ("efektivitas", "Moisturizer"): {"pos": ["kulit kering jadi lembab seharian", "bangun tidur kulit masih kenyal"],
                                      "neg": ["kurang lembab buat kulit kering", "siang dikit kulit udah kering lagi"]},
    ("efektivitas", "Toner"): {"pos": ["kulit jadi kalem dan seger", "makeup jadi nempel lebih bagus"],
                                "neg": ["kayak air biasa, ga ada efeknya"]},
    ("efektivitas", "Serum"): {"pos": ["jerawat kering dalam 2 hari", "bekas jerawat memudar"],
                                "neg": ["bekas jerawat ga ilang-ilang"]},
    ("tekstur", "Sunscreen"): {"pos": ["ga ninggalin white cast", "ringan kayak ga pake apa-apa"],
                                "neg": ["ninggalin white cast parah", "bikin muka abu-abu"]},
    ("tekstur", "Facial Wash"): {"pos": ["busanya lembut", "busanya melimpah"],
                                  "neg": ["busanya dikit banget", "bikin kulit ketarik"]},
}
PUMP_NEG = ["pump-nya macet", "pump-nya rusak baru seminggu dipake", "pump-nya ga mau keluar, harus dibuka tutupnya",
            "pump-nya patah, isinya ga bisa keluar", "pump-nya rusak, kecewa sama kemasannya"]
PRICE_UP_NEG = ["harganya naik terus", "sekarang harganya naik, jadi mikir-mikir buat repurchase",
                "harga naik tapi isinya sama aja"]
COUNTERFEIT_NEG = ["dapet barang palsu, teksturnya beda jauh", "banyak yang jual versi palsunya, hati-hati",
                   "curiga fake, kemasannya beda dari yang biasa"]
GENERIC_SHORT = ["Mantap", "Bagus", "Oke", "Sesuai pesanan", "Barang sampai dengan selamat", "Mantul", "Good",
                 "Suka", "Sesuai deskripsi", "Ok seller", "Top", "Recommended seller", "Bagus banget", "Mantap jiwa"]
NEUTRAL = ["biasa aja sih", "B aja, ga ada yang spesial", "lumayan lah", "masih nyobain dulu", "standar",
           "not bad", "belum bisa bilang cocok atau engga", "masih adaptasi sama produknya"]
OPENERS = ["Udah repurchase ke-{n} kali.", "Baru pertama kali coba.", "Review jujur ya.", "Pemakaian {w} minggu.",
           "Beli karena viral di TikTok.", "Dapet rekomendasi dari temen.", "Kulitku {skin}.", "Awalnya ragu,",
           "Ini produk ke-{n} dari {brand} yang aku coba.", "Udah pake hampir sebulan."]
CLOSERS = {
    "pos": ["Recommended!", "Bakal repurchase.", "Love it!", "Holy grail aku sih.", "Pokoknya mantap.",
            "Makasih seller.", "Sukses terus {brand}!", "10/10.", "Puas banget."],
    "neg": ["Kecewa.", "Kapok beli lagi.", "Ga akan repurchase.", "Not worth it.", "Nyesel beli.",
            "Semoga diperbaiki ya.", "Ga recommended."],
    "mix": ["Overall oke lah.", "Lumayan.", "B aja sih.", "Semoga kedepannya lebih baik.", "Masih mikir buat repurchase."],
}
EMO = {"pos": ["😍", "🥰", "👍", "✨", "💯", "🙏", "❤️"], "neg": ["😭", "😡", "😤", "👎", "😞", "🙁"], "mix": ["🙂", "😅"]}
ENGLISH = {
    "pos": ["Love the texture, absorbs quickly.", "My skin looks brighter after two weeks.", "Gentle and doesn't break me out.",
            "Great value for money.", "Fast delivery, well packed."],
    "neg": ["Broke me out badly.", "Didn't see any results.", "Way too expensive for the size.",
            "The pump broke after a week.", "Smells too strong for my sensitive skin."],
}
SLANG = [
    (r"\bbanget\b", ["bgt", "bngt", "banget", "bangett"]), (r"\byang\b", ["yg"]), (r"\bga\b", ["gak", "nggak", "ngga", "g"]),
    (r"\budah\b", ["udh", "dah", "sudah"]), (r"\bkarena\b", ["krn", "karna"]), (r"\bjuga\b", ["jg"]),
    (r"\bsama\b", ["sm"]), (r"\bbuat\b", ["bwt", "untuk"]), (r"\bkalo\b", ["klo", "kalau"]), (r"\baku\b", ["aq", "ak", "saya"]),
    (r"\bpake\b", ["pakai", "pk"]), (r"\bcepet\b", ["cepat", "cpt"]), (r"\bdengan\b", ["dgn"]), (r"\bterus\b", ["trs"]),
]
SKIN_WORDS = {"oily": "berminyak", "dry": "kering", "combination": "kombinasi", "sensitive": "sensitif", "normal": "normal"}


class TextEngine:
    def __init__(self, pyr: random.Random):
        self.r = pyr

    def pick(self, items):
        return self.r.choice(items)

    def phrase(self, aspect: str, pol: str, cat: str, ctx: dict) -> str:
        pool = list(PHRASES[aspect][pol])
        pool += CAT_PHRASES.get((aspect, cat), {}).get(pol, [])
        if aspect == "kemasan" and pol == "neg" and ctx.get("pump_defect"):
            pool = PUMP_NEG * 3 + pool
        if aspect == "harga" and pol == "neg" and ctx.get("price_up"):
            pool = PRICE_UP_NEG * 2 + pool
        if aspect == "keaslian" and pol == "neg" and ctx.get("counterfeit"):
            pool = COUNTERFEIT_NEG * 2 + pool
        return self.pick(pool).format(w=self.r.randint(1, 6))

    def slangify(self, text: str, p: float) -> str:
        for pattern, alts in SLANG:
            if self.r.random() < p:
                text = re.sub(pattern, lambda _m: self.r.choice(alts), text)
        return text

    def compose(self, parts: list[tuple[str, str]], tone: str, ctx: dict) -> str:
        r = self.r
        if r.random() < 0.05:  # occasional English review
            pols = [p for _, p in parts] or ["pos"]
            sents = [self.pick(ENGLISH[p if p in ENGLISH else "pos"]) for p in pols[:2]]
            closer = {"pos": " Will repurchase!", "neg": " Not recommended.", "mix": " It's okay."}[tone]
            return " ".join(sents) + closer
        chunks = []
        prev = None
        for aspect, pol in parts:
            text = self.phrase(aspect, pol, ctx["category"], ctx)
            if prev is None:
                chunks.append(text)
            elif prev != pol:
                chunks.append(self.pick([", tapi ", ". Tapi ", ", cuma ", ". Sayangnya ", ", namun ", ", sayang "]) + text)
            else:
                chunks.append(self.pick([", ", " dan ", ". ", ", terus ", ", juga "]) + text)
            prev = pol
        body = "".join(chunks)
        if tone == "mix" and r.random() < 0.5:
            body = self.pick(NEUTRAL).capitalize() + ", " + body
        body = body[0].upper() + body[1:] + "."
        if r.random() < 0.40:
            opener = self.pick(OPENERS).format(n=r.randint(2, 6), w=r.randint(1, 6),
                                                skin=SKIN_WORDS.get(ctx.get("skin") or "normal"), brand=ctx["brand"])
            body = opener + " " + body
        if r.random() < 0.65:
            body += " " + self.pick(CLOSERS[tone]).format(brand=ctx["brand"])
        body = self.slangify(body, 0.35)
        if r.random() < 0.35:
            body += " " + "".join(self.pick(EMO[tone]) for _ in range(r.randint(1, 3)))
        if r.random() < 0.08:
            body = re.sub(r"[.,!]", "", body.lower())
        if tone == "neg" and r.random() < 0.04:
            body = body.upper()
        if r.random() < 0.06:
            body = re.sub(r"(\w)\b", lambda mm: mm.group(1) * self.r.randint(1, 3), body, count=1)
        return body


def aspect_profile(brand: str, m: pd.Period, channel: str, skin: str | None, fragrance_free: bool,
                   category: str) -> tuple[dict, dict, dict]:
    """Probability that a mention of each aspect is positive, mention propensities, and text context."""
    q = dict(BRANDS[brand]["quality"])
    mention = dict(MENTION)
    ctx = {}
    ms = str(m)
    if brand == CLIENT:
        if category == "Moisturizer" and "2026-02" <= ms <= "2026-04":
            q["kemasan"], mention["kemasan"], ctx["pump_defect"] = 0.12, 0.70, True
        if m >= P("2025-07", freq="M"):
            q["harga"], mention["harga"], ctx["price_up"] = 0.42, 0.40, True
        if channel == "TikTok Shop" and ms in ("2026-02", "2026-03"):
            q["stok"], mention["stok"] = 0.15, 0.45
    if brand == "GlowNesia" and "2026-05" <= ms <= "2026-07":
        q["keaslian"], mention["keaslian"], ctx["counterfeit"] = 0.20, 0.42, True
    if brand == "Lumière Lab" and category == "Serum" and m >= P("2025-10", freq="M"):
        q["efektivitas"] = 0.92
    if skin == "sensitive" and not fragrance_free:
        q["reaksi_kulit"] -= 0.25
        q["aroma"] -= 0.22
        mention["reaksi_kulit"] += 0.20
        mention["aroma"] += 0.15
    if skin == "sensitive" and fragrance_free:
        q["reaksi_kulit"] = min(0.97, q["reaksi_kulit"] + 0.06)
    if category == "Sunscreen":
        mention["tekstur"] += 0.15
    if category == "Facial Wash":
        mention["reaksi_kulit"] += 0.05
    q = {k: float(np.clip(v, 0.03, 0.98)) for k, v in q.items()}
    return q, mention, ctx


def rating_from_latent(x: float) -> int:
    if x > 0.50:
        return 5
    if x > 0.15:
        return 4
    if x > -0.20:
        return 3
    if x > -0.55:
        return 2
    return 1


def j_shaped_rating(r: random.Random) -> int:
    return r.choices([5, 4, 3, 2, 1], weights=[0.62, 0.17, 0.08, 0.04, 0.09])[0]


def build_reviews(sales: pd.DataFrame, catalog: pd.DataFrame, rng: np.random.Generator, pyr: random.Random,
                  n_target: int = 20000) -> tuple[pd.DataFrame, dict]:
    eng = TextEngine(pyr)
    online = sales[sales["channel"].isin(ONLINE)]
    bm = online.groupby(["brand", "month"])["units"].sum().reset_index()
    bm["w"] = bm["units"] * bm["brand"].map(lambda b: BRANDS[b]["review_rate"])
    bm["lam"] = n_target * bm["w"] / bm["w"].sum()
    ch_split = online.groupby(["brand", "month", "channel"])["units"].sum()
    cat_split = online.groupby(["brand", "month", "category"])["units"].sum()
    reg_split = online.groupby(["brand", "month", "region"])["units"].sum()

    skin_pref = {
        CLIENT: [0.30, 0.20, 0.25, 0.15, 0.10], "Lumière Lab": [0.25, 0.20, 0.30, 0.12, 0.13],
        "DewiSkin": [0.25, 0.25, 0.25, 0.08, 0.17], "GlowNesia": [0.50, 0.10, 0.25, 0.08, 0.07],
        "Aurelia Derma": [0.10, 0.45, 0.20, 0.10, 0.15], "Purabotanica": [0.15, 0.20, 0.20, 0.38, 0.07],
    }
    skin_types = ["oily", "dry", "combination", "sensitive", "normal"]
    catalog = catalog.assign(launch_period=pd.PeriodIndex(catalog["launch_month"], freq="M"))
    cat_by_key = {k: g for k, g in catalog.groupby(["brand", "category"])}

    rows = []
    rid = 0
    for _, row in bm.iterrows():
        brand, month = row["brand"], row["month"]
        m = P(month, freq="M")
        n = rng.poisson(row["lam"])
        # unhappy buyers of the defective pump batch write extra reviews (complaint-driven review volume)
        extra = int(rng.poisson(28)) if brand == CLIENT and "2026-02" <= month[:7] <= "2026-04" else 0
        n += extra
        if n == 0:
            continue
        chs = ch_split.loc[(brand, month)]
        cats = cat_split.loc[(brand, month)]
        regs = reg_split.loc[(brand, month)]
        ch_draw = rng.choice(chs.index.to_numpy(), size=n, p=(chs / chs.sum()).values)
        cat_draw = rng.choice(cats.index.to_numpy(), size=n, p=(cats / cats.sum()).values)
        if extra:
            cat_draw[-extra:] = "Moisturizer"
        reg_draw = rng.choice(regs.index.to_numpy(), size=n, p=(regs / regs.sum()).values)
        days = rng.integers(1, m.days_in_month + 1, size=n)
        for i in range(n):
            rid += 1
            ch, cat, region = ch_draw[i], cat_draw[i], reg_draw[i]
            date = pd.Timestamp(year=m.year, month=m.month, day=int(days[i]))
            skus = cat_by_key[(brand, cat)]
            skus = skus[skus["launch_period"] <= m]
            sku = skus.sample(1, random_state=int(rng.integers(1_000_000_000))).iloc[0]
            skin = pyr.choices(skin_types, weights=skin_pref[brand])[0]
            q, mention, ctx = aspect_profile(brand, m, ch, skin, bool(sku["fragrance_free"]), cat)
            ctx.update(category=cat, brand=brand.split()[0], skin=skin)

            u = pyr.random()
            if u < 0.03:  # rating-only review
                text, rating, polar = "", j_shaped_rating(pyr), []
            elif u < 0.15:  # short generic praise
                text = pyr.choice(GENERIC_SHORT)
                if pyr.random() < 0.3:
                    text += " " + pyr.choice(EMO["pos"])
                rating = pyr.choices([5, 4, 3], weights=[0.80, 0.17, 0.03])[0]
                polar = []
            else:
                k = pyr.choices([1, 2, 3, 4], weights=[0.30, 0.37, 0.22, 0.11])[0]
                probs = np.array([mention[a] for a in ASPECTS])
                chosen = list(rng.choice(ASPECTS, size=k, replace=False, p=probs / probs.sum()))
                if ctx.get("pump_defect") and "kemasan" not in chosen and pyr.random() < 0.65:
                    chosen[-1] = "kemasan"  # most buyers of the defective batch complain about the pump
                parts = [(a, "pos" if pyr.random() < q[a] else "neg") for a in chosen]
                score = sum(ASPECT_WEIGHT[a] * (1 if p == "pos" else -1) for a, p in parts)
                score /= sum(ASPECT_WEIGHT[a] for a, _ in parts)
                latent = score + rng.normal(0, 0.28)
                rating = rating_from_latent(latent)
                if pyr.random() < 0.04:  # label noise: star rating disagrees with text
                    rating = j_shaped_rating(pyr)
                tone = "pos" if latent > 0.35 else ("neg" if latent < -0.30 else "mix")
                parts.sort(key=lambda ap: (ap[1] != ("neg" if tone == "neg" else "pos")))
                text = eng.compose(parts, tone, ctx)
                polar = parts
            helpful = int(rng.poisson(0.4 + (1.6 if rating <= 2 else 0.0) + len(text) / 250))
            rows.append(dict(
                review_id=f"R{rid:06d}", review_date=date.date().isoformat(), brand=brand,
                sku_id=sku["sku_id"], product_name=sku["product_name"], category=cat, channel=ch, region=region,
                rating=rating, review_text=text, helpful_votes=helpful, verified_purchase=pyr.random() < 0.92,
                reviewer_id=f"U{int(rng.integers(100000, 999999))}",
                reviewer_skin_type=skin if pyr.random() > 0.25 else None,
                _aspects=";".join(f"{a}:{p}" for a, p in polar),
            ))
    df = pd.DataFrame(rows)
    dup = df.sample(frac=0.01, random_state=SEED)
    df = pd.concat([df, dup], ignore_index=True).sort_values("review_date").reset_index(drop=True)
    return df, dict(duplicate_reviews=len(dup), rating_only_share=0.03)


# ----------------------------------------------------------------------------- social listening

TOPICS = {
    # topic: (start weight, end weight, kind)
    "niacinamide": (1.00, 0.70, "declining"), "ceramide": (0.22, 1.20, "rising"),
    "skin barrier": (0.18, 1.25, "rising"), "peptide": (0.08, 0.60, "emerging"),
    "retinol": (0.40, 0.55, "rising"), "salicylic acid": (0.80, 0.80, "stable"),
    "sunscreen": (0.55, 1.15, "rising"), "centella": (0.60, 0.62, "stable"),
    "mugwort": (0.30, 0.20, "fad"), "vitamin c": (0.50, 0.45, "stable"),
    "dupe": (0.18, 0.50, "rising"), "halal": (0.40, 0.40, "stable"),
    "refill": (0.06, 0.30, "rising"), "glass skin": (0.50, 0.38, "declining"),
}
TOPIC_TAG = {t: "#" + t.replace(" ", "") for t in TOPICS}
TOPIC_BENEFIT = {
    "niacinamide": "mencerahkan", "ceramide": "memperbaiki skin barrier", "skin barrier": "kulit sehat",
    "peptide": "anti-aging", "retinol": "garis halus", "salicylic acid": "jerawat", "sunscreen": "proteksi UV",
    "centella": "menenangkan kulit", "mugwort": "kulit kemerahan", "vitamin c": "kulit kusam",
    "dupe": "hemat budget", "halal": "rasa aman", "refill": "kurangi sampah plastik", "glass skin": "kulit glowing",
}
BRAND_BUZZ = {CLIENT: 0.12, "Lumière Lab": 0.20, "DewiSkin": 0.10, "GlowNesia": 0.36, "Aurelia Derma": 0.08,
              "Purabotanica": 0.14}


def topic_weight(topic: str, ti: int, m: pd.Period) -> float:
    s, e, kind = TOPICS[topic]
    x = ti / (len(MONTHS) - 1)
    if kind == "emerging":
        w = s + (e - s) * (1 / (1 + math.exp(-12 * (x - 0.72))))
    elif kind == "fad":
        w = s + 0.55 * math.exp(-((x - 0.42) ** 2) / 0.012)
    else:
        w = s + (e - s) * x
    if topic == "sunscreen":
        w *= {6: 1.18, 7: 1.22, 8: 1.15, 12: 0.90, 1: 0.88}.get(m.month, 1.0)
    if topic == "refill" and m >= P("2025-06", freq="M"):
        w *= 1.4
    return w


def build_social(catalog: pd.DataFrame, rng: np.random.Generator, pyr: random.Random,
                 n_target: int = 11000) -> tuple[pd.DataFrame, pd.DataFrame]:
    eng = TextEngine(pyr)
    launch = pd.PeriodIndex(catalog["launch_month"], freq="M")
    growth = np.linspace(0.65, 1.35, len(MONTHS))
    per_month = n_target * growth / growth.sum()
    platforms = ["TikTok", "Instagram", "X", "YouTube"]
    tiers = ["nano", "micro", "macro", "mega"]
    tier_followers = {"nano": (1e3, 1e4), "micro": (1e4, 1e5), "macro": (1e5, 1e6), "mega": (1e6, 8e6)}
    rows, truth = [], []
    pid = 0
    for ti, m in enumerate(MONTHS):
        n = rng.poisson(per_month[ti])
        tw = np.array([topic_weight(t, ti, m) for t in TOPICS])
        tw /= tw.sum()
        tiktok_share = 0.42 + 0.16 * ti / (len(MONTHS) - 1)
        pw = np.array([tiktok_share, 0.30, 0.16, 0.12])
        pw /= pw.sum()
        for _ in range(n):
            pid += 1
            platform = rng.choice(platforms, p=pw)
            topics = list(rng.choice(list(TOPICS), size=pyr.choice([1, 1, 2]), replace=False, p=tw))
            topic = topics[0]
            buzz = dict(BRAND_BUZZ)
            if platform == "TikTok":
                buzz["GlowNesia"] *= 1.8
                buzz[CLIENT] *= 0.6
            brand = None
            if pyr.random() < 0.58:
                names, ws = zip(*buzz.items())
                ws = np.array(ws) / sum(ws)
                brand = str(rng.choice(names, p=ws))
            day = int(rng.integers(1, m.days_in_month + 1))
            date = pd.Timestamp(year=m.year, month=m.month, day=day)
            tag = TOPIC_TAG[topic]
            extra_tags = " ".join(TOPIC_TAG[t] for t in topics[1:])
            if brand:
                prods = catalog[(catalog["brand"] == brand) & (launch <= m)]
                prod = prods.sample(1, random_state=int(rng.integers(1_000_000_000))).iloc[0]
                q, _, ctx = aspect_profile(brand, m, "TikTok Shop" if platform == "TikTok" else "Shopee",
                                           None, bool(prod["fragrance_free"]), prod["category"])
                ctx.update(category=prod["category"], brand=brand.split()[0], skin=None)
                pos_p = float(np.mean([q["efektivitas"], q["tekstur"], q["reaksi_kulit"], q["harga"]]))
                counterfeit = ctx.get("counterfeit") and pyr.random() < 0.45
                u = pyr.random()
                if counterfeit:
                    sent = "negative"
                    text = pyr.choice([
                        f"PSA: banyak {brand} palsu beredar di marketplace, cek nomor BPOM dulu ya!",
                        f"Hati-hati beli {prod['product_name']} di toko non-official, aku dapet yang KW 😭",
                        f"Kok {brand} sekarang banyak versi fake-nya sih? Kecewa banget.",
                    ])
                elif u < 0.22:
                    sent = "neutral"
                    text = pyr.choice([
                        f"Ada yang udah coba {prod['product_name']}? Mau tau review jujurnya dong",
                        f"Haul skincare bulan ini: {prod['product_name']}. Nanti aku review ya!",
                        f"{brand} lagi diskon di {pyr.choice(['Shopee', 'TikTok Shop', 'Tokopedia'])}, worth it ga ya?",
                        f"Lagi bandingin {prod['product_name']} sama produk lain yang ada {topic}-nya, bagusan mana?",
                    ])
                elif pyr.random() < pos_p:
                    sent = "positive"
                    a1 = eng.phrase(pyr.choice(["efektivitas", "tekstur", "reaksi_kulit"]), "pos", prod["category"], ctx)
                    text = pyr.choice([
                        f"Udah {pyr.randint(2, 8)} minggu pake {prod['product_name']} dan {a1}! {pyr.choice(EMO['pos'])}",
                        f"Racun banget: {prod['product_name']}. {a1.capitalize()}, recommended!",
                        f"Fix holy grail! {prod['product_name']} {a1}.",
                        f"Review jujur {prod['product_name']}: {a1}. Worth it!",
                    ])
                else:
                    sent = "negative"
                    a1 = eng.phrase(pyr.choice(["efektivitas", "reaksi_kulit", "harga", "kemasan", "tekstur"]),
                                    "neg", prod["category"], ctx)
                    text = pyr.choice([
                        f"Jujur kecewa sama {prod['product_name']}, {a1}. {pyr.choice(EMO['neg'])}",
                        f"Kenapa ya {prod['product_name']} {a1}? Ada yang ngalamin juga?",
                        f"Not recommended: {prod['product_name']}, {a1}.",
                    ])
            else:
                u = pyr.random()
                benefit = TOPIC_BENEFIT[topic]
                if u < 0.55:
                    sent = "neutral"
                    text = pyr.choice([
                        f"Thread: kandungan {topic} itu fungsinya apa sih? 🧵",
                        f"Lagi hype banget {topic} buat {benefit}. Kalian tim mana?",
                        f"Tips: kenali dulu kebutuhan kulit sebelum pakai {topic} ya.",
                        f"Rekomendasi produk lokal yang ada {topic}-nya dong!",
                    ])
                elif u < 0.88:
                    sent = "positive"
                    text = pyr.choice([
                        f"Sejak rutin pakai {topic}, kulitku jauh lebih sehat ✨",
                        f"{topic.capitalize()} beneran game changer buat {benefit}!",
                        f"Suka banget sama tren {topic}, skincare lokal makin keren 😍",
                    ])
                else:
                    sent = "negative"
                    text = pyr.choice([
                        f"Kapok coba-coba {topic}, malah bikin breakout 😭",
                        f"Overclaim banget produk {topic} sekarang, hasilnya ga ada.",
                        f"Capek liat iklan {topic} di mana-mana, padahal ga semua cocok.",
                    ])
            text = eng.slangify(text, 0.30) + f" {tag} {extra_tags} #skincarelokal".replace("  ", " ")
            tier = rng.choice(tiers, p=[0.62, 0.28, 0.08, 0.02])
            lo, hi = tier_followers[tier]
            followers = int(math.exp(rng.uniform(math.log(lo), math.log(hi))))
            reach = followers * rng.lognormal(0.0 if platform != "TikTok" else 0.9, 0.8)
            views = int(reach)
            likes = int(views * rng.beta(2, 30))
            comments = int(likes * rng.beta(2, 25))
            shares = int(likes * rng.beta(1.5, 30) * (2.0 if platform == "TikTok" else 1.0))
            rows.append(dict(post_id=f"P{pid:06d}", post_date=date.date().isoformat(), platform=platform,
                             brand_mentioned=brand or "", topics=";".join(topics), post_text=text,
                             author_followers=followers, influencer_tier=tier, views=views, likes=likes,
                             comments=comments, shares=shares))
            truth.append(dict(post_id=f"P{pid:06d}", true_sentiment=sent))
    df = pd.DataFrame(rows)
    dup = df.sample(frac=0.008, random_state=SEED)  # reposts
    df = pd.concat([df, dup], ignore_index=True).sort_values("post_date").reset_index(drop=True)
    return df, pd.DataFrame(truth)


# ----------------------------------------------------------------------------- consumer survey

SEGMENTS = [
    dict(name="Budget Acne Fighters", share=0.26, age=(20, 2.2, 16, 27), female=0.66,
         occupation={"Student": 0.70, "Employee": 0.15, "Freelancer": 0.10, "Entrepreneur": 0.05},
         income=[0.55, 0.30, 0.12, 0.03, 0.00], spend=95000, steps=(2, 4), freq=1.3,
         skin={"oily": 0.50, "combination": 0.30, "normal": 0.10, "sensitive": 0.07, "dry": 0.03},
         concern={"Acne & breakouts": 0.65, "Oil control": 0.20, "Dullness": 0.15},
         channel={"TikTok Shop": 0.55, "Shopee": 0.35, "Offline Retail": 0.05, "Tokopedia": 0.05},
         brand={"GlowNesia": 0.45, CLIENT: 0.18, "DewiSkin": 0.15, "Lumière Lab": 0.10, "Purabotanica": 0.05,
                "Other local brand": 0.07},
         social=5.2, platform={"TikTok": 0.70, "Instagram": 0.25, "YouTube": 0.05}, trust=4.1,
         imp=dict(price=4.7, halal=3.4, ingredients=3.2, brand_reputation=2.7, packaging=3.2, reviews_influencers=4.5,
                  local_brand=3.6, sustainability=2.3, fragrance_free=2.5, fast_results=4.6),
         intent=3.0, vw=(30000, 50000, 80000, 105000)),
    dict(name="Ingredient-Savvy Professionals", share=0.24, age=(27.5, 3.0, 22, 36), female=0.80,
         occupation={"Employee": 0.70, "Entrepreneur": 0.10, "Freelancer": 0.15, "Student": 0.05},
         income=[0.03, 0.17, 0.45, 0.28, 0.07], spend=260000, steps=(4, 5), freq=1.8,
         skin={"combination": 0.35, "normal": 0.25, "oily": 0.20, "dry": 0.10, "sensitive": 0.10},
         concern={"Dullness": 0.35, "Dark spots": 0.35, "Acne & breakouts": 0.15, "Fine lines & aging": 0.10,
                  "Dryness & barrier": 0.05},
         channel={"Shopee": 0.45, "Tokopedia": 0.25, "TikTok Shop": 0.20, "Offline Retail": 0.10},
         brand={"Lumière Lab": 0.45, CLIENT: 0.22, "GlowNesia": 0.10, "Purabotanica": 0.10, "Aurelia Derma": 0.05,
                "DewiSkin": 0.05, "Other local brand": 0.03},
         social=4.2, platform={"Instagram": 0.45, "TikTok": 0.40, "YouTube": 0.15}, trust=3.4,
         imp=dict(price=3.5, halal=3.0, ingredients=4.8, brand_reputation=3.2, packaging=3.0, reviews_influencers=4.3,
                  local_brand=3.6, sustainability=2.8, fragrance_free=2.9, fast_results=4.2),
         intent=3.6, vw=(45000, 70000, 115000, 150000)),
    dict(name="Halal Value Seekers", share=0.22, age=(35, 6.0, 24, 52), female=0.90,
         occupation={"Housewife": 0.35, "Employee": 0.40, "Entrepreneur": 0.15, "Civil servant": 0.10},
         income=[0.20, 0.38, 0.32, 0.08, 0.02], spend=120000, steps=(2, 3), freq=1.0,
         skin={"normal": 0.35, "combination": 0.25, "dry": 0.20, "oily": 0.15, "sensitive": 0.05},
         concern={"Dullness": 0.40, "Dryness & barrier": 0.20, "Dark spots": 0.20, "Fine lines & aging": 0.15,
                  "Acne & breakouts": 0.05},
         channel={"Offline Retail": 0.55, "Shopee": 0.30, "TikTok Shop": 0.10, "Tokopedia": 0.05},
         brand={"DewiSkin": 0.50, CLIENT: 0.25, "GlowNesia": 0.07, "Lumière Lab": 0.08, "Purabotanica": 0.05,
                "Aurelia Derma": 0.02, "Other local brand": 0.03},
         social=2.6, platform={"Instagram": 0.40, "YouTube": 0.30, "TikTok": 0.25, "Facebook": 0.05}, trust=2.9,
         imp=dict(price=4.2, halal=4.9, ingredients=3.0, brand_reputation=3.9, packaging=3.0, reviews_influencers=3.0,
                  local_brand=4.2, sustainability=2.7, fragrance_free=2.7, fast_results=3.0),
         intent=3.0, vw=(35000, 55000, 90000, 120000)),
    dict(name="Premium Age-Defiers", share=0.13, age=(41, 5.5, 32, 58), female=0.88,
         occupation={"Employee": 0.45, "Entrepreneur": 0.35, "Civil servant": 0.10, "Housewife": 0.10},
         income=[0.00, 0.03, 0.17, 0.45, 0.35], spend=560000, steps=(5, 7), freq=1.6,
         skin={"dry": 0.40, "normal": 0.30, "combination": 0.20, "sensitive": 0.10},
         concern={"Fine lines & aging": 0.70, "Dark spots": 0.20, "Dryness & barrier": 0.10},
         channel={"Offline Retail": 0.45, "Shopee": 0.30, "Tokopedia": 0.20, "TikTok Shop": 0.05},
         brand={"Aurelia Derma": 0.45, "Lumière Lab": 0.30, CLIENT: 0.10, "Purabotanica": 0.08, "DewiSkin": 0.05,
                "Other local brand": 0.02},
         social=2.0, platform={"Instagram": 0.55, "YouTube": 0.30, "TikTok": 0.15}, trust=2.3,
         imp=dict(price=2.0, halal=3.3, ingredients=4.2, brand_reputation=4.9, packaging=4.5, reviews_influencers=2.6,
                  local_brand=2.3, sustainability=3.3, fragrance_free=3.2, fast_results=3.2),
         intent=2.9, vw=(70000, 100000, 160000, 220000)),
    dict(name="Sensitive-Skin Minimalists", share=0.15, age=(27, 4.0, 19, 38), female=0.78,
         occupation={"Employee": 0.55, "Student": 0.20, "Freelancer": 0.20, "Entrepreneur": 0.05},
         income=[0.08, 0.25, 0.40, 0.22, 0.05], spend=210000, steps=(2, 3), freq=1.2,
         skin={"sensitive": 0.65, "dry": 0.20, "combination": 0.10, "normal": 0.05},
         concern={"Sensitivity & redness": 0.60, "Dryness & barrier": 0.25, "Acne & breakouts": 0.15},
         channel={"Shopee": 0.40, "TikTok Shop": 0.25, "Tokopedia": 0.20, "Offline Retail": 0.15},
         brand={"Purabotanica": 0.30, CLIENT: 0.30, "Lumière Lab": 0.20, "DewiSkin": 0.08, "GlowNesia": 0.07,
                "Aurelia Derma": 0.03, "Other local brand": 0.02},
         social=3.3, platform={"Instagram": 0.40, "TikTok": 0.40, "YouTube": 0.15, "X": 0.05}, trust=2.8,
         imp=dict(price=3.4, halal=3.2, ingredients=4.4, brand_reputation=3.3, packaging=3.0, reviews_influencers=3.6,
                  local_brand=3.6, sustainability=4.4, fragrance_free=4.9, fast_results=2.6),
         intent=4.4, vw=(45000, 70000, 110000, 145000)),
]
INCOME_BRACKETS = ["< Rp3 jt", "Rp3-5 jt", "Rp5-10 jt", "Rp10-20 jt", "> Rp20 jt"]
INCOME_MID = [2.2e6, 4.0e6, 7.5e6, 14.0e6, 27.0e6]
SURVEY_REGIONS = dict(zip(REGIONS, [0.27, 0.19, 0.13, 0.16, 0.13, 0.08, 0.04]))
AWARENESS = {CLIENT: 0.58, "Lumière Lab": 0.74, "DewiSkin": 0.81, "GlowNesia": 0.69, "Aurelia Derma": 0.41,
             "Purabotanica": 0.46}
NPS_MEAN = {CLIENT: 7.9, "Lumière Lab": 8.4, "DewiSkin": 7.7, "GlowNesia": 7.3, "Aurelia Derma": 8.6,
            "Purabotanica": 8.2, "Other local brand": 7.2}


def draw(pyr: random.Random, d: dict):
    keys, ws = zip(*d.items())
    return pyr.choices(keys, weights=ws)[0]


def round_price(x: float) -> int:
    return int(max(5000, round(x / 5000) * 5000))


def build_survey(rng: np.random.Generator, pyr: random.Random, n: int = 2400) -> tuple[pd.DataFrame, dict]:
    seg_idx = rng.choice(len(SEGMENTS), size=n, p=[s["share"] for s in SEGMENTS])
    rows = []
    for i, si in enumerate(seg_idx):
        s = SEGMENTS[si]
        mu, sd, lo, hi = s["age"]
        age = int(np.clip(round(rng.normal(mu, sd)), lo, hi))
        gender = "Female" if pyr.random() < s["female"] else "Male"
        inc_i = pyr.choices(range(5), weights=s["income"])[0]
        imp = {k: int(np.clip(round(rng.normal(v, 0.65)), 1, 5)) for k, v in s["imp"].items()}
        main_brand = draw(pyr, s["brand"])
        aware = {}
        for b, base in AWARENESS.items():
            p = base
            if b == main_brand:
                p = 1.0
            elif b == "GlowNesia" and si == 0:
                p = 0.92
            elif b == "Aurelia Derma" and si == 3:
                p = 0.85
            elif b == "DewiSkin" and si == 2:
                p = 0.95
            aware[b] = int(pyr.random() < p)
        nps = int(np.clip(round(rng.normal(NPS_MEAN[main_brand] + (0.4 if si == 4 and main_brand == CLIENT else 0), 1.7)), 0, 10))
        tc, ch, ex, te = s["vw"]
        scale = rng.lognormal(0, 0.14) * (INCOME_MID[inc_i] / 7.5e6) ** 0.12
        vw = sorted([tc * scale * rng.lognormal(0, 0.10), ch * scale * rng.lognormal(0, 0.08),
                     ex * scale * rng.lognormal(0, 0.08), te * scale * rng.lognormal(0, 0.10)])
        vw = [round_price(v) for v in vw]
        for j in range(1, 4):
            if vw[j] <= vw[j - 1]:
                vw[j] = vw[j - 1] + 5000
        rows.append(dict(
            respondent_id=f"S{i + 1:05d}", survey_date=(pd.Timestamp("2026-08-03") + pd.Timedelta(days=int(rng.integers(0, 42)))).date().isoformat(),
            age=age, gender=gender, region=draw(pyr, SURVEY_REGIONS),
            city_tier=pyr.choices(["Tier 1", "Tier 2", "Tier 3"], weights=[0.45, 0.35, 0.20])[0],
            occupation=draw(pyr, s["occupation"]), income_bracket=INCOME_BRACKETS[inc_i],
            monthly_income_idr=INCOME_MID[inc_i],
            monthly_skincare_spend_idr=round_price(rng.lognormal(math.log(s["spend"]), 0.35)),
            routine_steps=int(rng.integers(s["steps"][0], s["steps"][1] + 1)),
            purchase_freq_per_month=round(float(np.clip(rng.normal(s["freq"], 0.35), 0.3, 4)), 1),
            skin_type=draw(pyr, s["skin"]), primary_concern=draw(pyr, s["concern"]),
            preferred_channel=draw(pyr, s["channel"]), main_brand=main_brand,
            **{f"aware_{b.split()[0].lower().replace('è', 'e')}": v for b, v in aware.items()},
            nps_main_brand=nps,
            satisfaction_main_brand=int(np.clip(round(nps / 2 + rng.normal(0, 0.6)), 1, 5)),
            social_media_hours_per_day=round(float(np.clip(rng.normal(s["social"], 1.1), 0.5, 12)), 1),
            primary_platform=draw(pyr, s["platform"]),
            follows_skincare_influencers=pyr.random() < (s["trust"] - 1) / 4,
            influencer_trust=int(np.clip(round(rng.normal(s["trust"], 0.8)), 1, 5)),
            **{f"imp_{k}": v for k, v in imp.items()},
            attention_check=4,
            concept_purchase_intent=int(np.clip(round(rng.normal(s["intent"], 0.85)), 1, 5)),
            vw_too_cheap_idr=vw[0], vw_cheap_idr=vw[1], vw_expensive_idr=vw[2], vw_too_expensive_idr=vw[3],
            completion_time_sec=int(rng.lognormal(math.log(560), 0.30)),
            _segment=s["name"],
        ))
    df = pd.DataFrame(rows)

    n_speed = int(0.03 * n)
    speed_idx = rng.choice(n, n_speed, replace=False)
    df.loc[speed_idx, "completion_time_sec"] = rng.integers(85, 170, n_speed)
    rest = np.setdiff1d(np.arange(n), speed_idx)
    n_straight = int(0.02 * n)
    straight_idx = rng.choice(rest, n_straight, replace=False)
    imp_cols = [c for c in df.columns if c.startswith("imp_")]
    for idx in straight_idx:
        df.loc[idx, imp_cols] = int(rng.integers(3, 6))
    rest = np.setdiff1d(rest, straight_idx)
    n_att = int(0.025 * n)
    att_idx = rng.choice(rest, n_att, replace=False)
    df.loc[att_idx, "attention_check"] = rng.choice([1, 2, 3, 5], n_att)
    miss_inc = rng.choice(n, int(0.04 * n), replace=False)
    df.loc[miss_inc, ["income_bracket", "monthly_income_idr"]] = [None, np.nan]
    bad_age = rng.choice(n, 6, replace=False)
    df.loc[bad_age, "age"] = rng.choice([9, 11, 99, 102], 6)
    return df, dict(speeders=n_speed, straight_liners=n_straight, attention_fails=n_att,
                    missing_income=len(miss_inc), invalid_age=6)


# ----------------------------------------------------------------------------- market size

def build_market_size() -> pd.DataFrame:
    totals = {2019: 23400, 2020: 22700, 2021: 25300, 2022: 28600, 2023: 31900, 2024: 35100, 2025: 38300, 2026: 41600}
    local = {2019: 31, 2020: 35, 2021: 40, 2022: 45, 2023: 48, 2024: 51, 2025: 53, 2026: 55}
    online = {2019: 17, 2020: 27, 2021: 34, 2022: 39, 2023: 43, 2024: 46, 2025: 49, 2026: 52}
    base_share = {"Facial Wash": 0.30, "Toner": 0.15, "Serum": 0.18, "Moisturizer": 0.24, "Sunscreen": 0.13}
    tilt = {"Facial Wash": -0.035, "Toner": -0.045, "Serum": 0.035, "Moisturizer": 0.0, "Sunscreen": 0.06}
    rows = []
    for year, total in totals.items():
        w = {c: base_share[c] * math.exp(tilt[c] * (year - 2019)) for c in CATEGORIES}
        z = sum(w.values())
        for c in CATEGORIES:
            rows.append(dict(year=year, category=c, market_value_idr_bn=round(total * w[c] / z, 1),
                             local_brand_share_pct=local[year], online_share_pct=online[year],
                             status="estimate" if year == 2026 else "actual",
                             source="Simulated industry estimate (MarketMind demo data)"))
    df = pd.DataFrame(rows)
    df["yoy_growth_pct"] = (df.groupby("category")["market_value_idr_bn"].pct_change() * 100).round(1)
    return df


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=RAW)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    pyr = random.Random(SEED)

    print("Simulating sales panel ...")
    sales_clean = build_sales(rng)
    sales, sales_defects = inject_sales_defects(sales_clean, rng)
    sales.to_csv(args.out / "market_sales_panel.csv", index=False)

    print("Building catalogue and reviews ...")
    catalog = build_catalog_base()
    reviews, review_defects = build_reviews(sales_clean, catalog, rng, pyr)
    stats = reviews.drop_duplicates("review_id").groupby("sku_id")["rating"].agg(["mean", "count"])
    catalog["rating_avg"] = catalog["sku_id"].map(lambda s: round(min(4.95, 2.9 + 0.47 * stats["mean"].get(s, 4.2)), 2))
    catalog["review_count"] = catalog["sku_id"].map(lambda s: int(stats["count"].get(s, 3) * rng.uniform(28, 46)))
    catalog["units_sold_estimate"] = (catalog["review_count"] * rng.uniform(3.0, 5.0, len(catalog))).astype(int)
    catalog.loc[catalog["launch_month"] >= "2025-08", "rating_avg"] = np.nan  # too new for a stable rating
    catalog.to_csv(args.out / "product_catalog.csv", index=False)
    reviews.drop(columns="_aspects").to_csv(args.out / "product_reviews.csv", index=False)

    print("Generating social listening posts ...")
    social, social_truth = build_social(catalog, rng, pyr)
    social.to_csv(args.out / "social_mentions.csv", index=False)
    social_truth.sample(400, random_state=SEED).rename(columns={"true_sentiment": "human_label"}).to_csv(
        args.out / "social_validation_labels.csv", index=False)  # analyst-annotated validation sample

    print("Fielding consumer survey ...")
    survey, survey_defects = build_survey(rng, pyr)
    survey.drop(columns="_segment").to_csv(args.out / "consumer_survey.csv", index=False)

    build_market_size().to_csv(args.out / "market_size.csv", index=False)

    gt_dir = args.out.parent / "ground_truth"
    gt_dir.mkdir(exist_ok=True)
    reviews[["review_id", "_aspects"]].drop_duplicates("review_id").rename(columns={"_aspects": "true_aspects"}).to_csv(
        gt_dir / "review_aspects.csv", index=False)
    social_truth.to_csv(gt_dir / "social_sentiment.csv", index=False)
    survey[["respondent_id", "_segment"]].rename(columns={"_segment": "true_segment"}).to_csv(
        gt_dir / "survey_segments.csv", index=False)

    truth = {
        "client_brand": CLIENT,
        "price_elasticity": {b: v["elasticity"] for b, v in BRANDS.items()},
        "events": [
            dict(brand="GlowNesia", start="2024-08", end=None, type="viral_campaign", channel="TikTok Shop",
                 description="Viral TikTok campaign: +70% TikTok demand decaying to a sustained +30%."),
            dict(brand=CLIENT, start="2024-03", end=None, type="product_launch", category="Sunscreen",
                 description="UV Shield Aqua Gel SPF 50 launch lifts Kirana sunscreen demand up to +45%."),
            dict(brand=CLIENT, start="2025-07", end=None, type="price_increase",
                 description="Kirana list price +12% across all categories (elasticity -1.3 => about -14% volume)."),
            dict(brand="Lumière Lab", start="2025-10", end=None, type="product_launch", category="Serum",
                 description="Barrier Ceramide Serum launch: serum demand up to +28%."),
            dict(brand="Purabotanica", start="2025-06", end=None, type="campaign",
                 description="Refill-pouch sustainability campaign: +12% demand."),
            dict(brand="DewiSkin", start="2026-01", end=None, type="rebrand",
                 description="Rebrand lifts online demand up to +18%."),
            dict(brand=CLIENT, start="2026-02", end="2026-04", type="quality_issue", category="Moisturizer",
                 description="Hydra Barrier Moisturizer pump defect: packaging complaints spike, moisturizer sales -7 to -12%."),
            dict(brand=CLIENT, start="2026-02", end="2026-03", type="stockout", channel="TikTok Shop",
                 description="Ramadan stock-outs on TikTok Shop (9 and 12 days)."),
            dict(brand="GlowNesia", start="2026-05", end="2026-07", type="counterfeit_crisis",
                 description="Counterfeit products flood marketplaces: authenticity complaints spike, demand -15 to -25%."),
        ],
        "expected_insights": {
            "client_underindexed_channel": "TikTok Shop",
            "fastest_growing_channel": "TikTok Shop",
            "fastest_growing_category": "Sunscreen",
            "fastest_growing_regions": ["Kalimantan & Sulawesi", "Sumatera", "Bali & Indonesia Timur"],
            "client_top_negative_aspect_2026": "kemasan",
            "client_negative_spike_months": ["2026-02", "2026-03", "2026-04"],
            "glownesia_negative_spike_months": ["2026-05", "2026-06", "2026-07"],
            "rising_topics": ["peptide", "refill", "skin barrier", "ceramide"],
            "declining_topics": ["niacinamide", "glass skin", "mugwort"],
            "top_competitive_threats": ["GlowNesia", "Lumière Lab"],
            "white_space": "Fragrance-free ceramide moisturizer in the Rp60-120k masstige band",
            "target_segment_for_concept": "Sensitive-Skin Minimalists",
            "concept_optimal_price_band_idr": [80000, 100000],
            "n_segments": len(SEGMENTS),
        },
        "segments": [{"name": s["name"], "share": s["share"]} for s in SEGMENTS],
        "topics": {t: v[2] for t, v in TOPICS.items()},
        "data_quality_defects": {"sales": sales_defects, "reviews": review_defects, "survey": survey_defects,
                                 "social_reposts": int(0.008 * len(social_truth))},
    }
    (args.out.parent / "ground_truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nDatasets written to", args.out)
    for f in sorted(args.out.glob("*.csv")):
        n = sum(1 for _ in open(f, encoding="utf-8")) - 1
        print(f"  {f.name:<26} {n:>7,} rows")


if __name__ == "__main__":
    main()
