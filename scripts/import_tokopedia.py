#!/usr/bin/env python
"""Import the Tokopedia Product and Review Dataset (2025) as a MarketMind real-data folder.

    python scripts/import_tokopedia.py path/to/archive.zip                  # writes data/real/tokopedia-2025
    python scripts/import_tokopedia.py archive.zip --out data/real/toko --brand-map brands.csv --min-reviews 20

Download archive.zip yourself from https://www.kaggle.com/datasets/musabiam/tokopedia-product-and-review-dataset
(a Kaggle account is needed; CC BY-NC 4.0, research and education only, so keep the output out of git and do not
share it). The importer keeps the facial-skincare products, writes raw/product_reviews.csv and raw/product_catalog.csv
in MarketMind's row contracts, checks every row against them, and records the source, the licence and every derived
or unknown field in manifest.json. Then study the data:

    python run.py --data-dir data/real/tokopedia-2025 --client "<a brand in the data>"

A brand map (CSV with columns pattern,brand; the pattern is a regular expression matched against the product name)
corrects brands the automatic rule gets wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from marketmind.adapters import tokopedia  # noqa: E402


def contract_errors(df: pd.DataFrame, schema: str, limit: int = 10) -> list[str]:
    """Rows that break a dataset row contract (docs/schemas/datasets), up to `limit` messages."""
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(json.loads((ROOT / "docs" / "schemas" / "datasets" / f"{schema}.schema.json")
                                                .read_text(encoding="utf-8")))
    errors = []
    for i, row in enumerate(json.loads(df.to_json(orient="records"))):   # native types; NaN and NA become null
        errors += [f"{schema} row {i + 1}: {e.message}" for e in validator.iter_errors(row)]
        if len(errors) >= limit:
            break
    return errors[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, help="archive.zip from Kaggle, or the CSV or JSON inside it")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "real" / "tokopedia-2025", help="data folder to write")
    ap.add_argument("--brand-map", type=Path, help="CSV with columns pattern,brand to correct derived brands")
    ap.add_argument("--min-reviews", type=int, default=1, help="leave out products with fewer reviews (default 1)")
    ap.add_argument("--max-products", type=int, default=999, help="keep the most-reviewed products, up to 999")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not args.input.exists():
        print(f"{args.input} not found. Download archive.zip from Kaggle first (see the top of this script).")
        return 2
    brand_map = None
    if args.brand_map:
        bm = pd.read_csv(args.brand_map)
        brand_map = dict(zip(bm["pattern"], bm["brand"], strict=True))

    print(f"Reading beauty products from {args.input} ...", flush=True)
    products = tokopedia.read_beauty_products(args.input)
    reviews, catalog, cross, stats = tokopedia.convert(products, brand_map, args.min_reviews, min(args.max_products, 999))
    errors = contract_errors(reviews, "review_row") + contract_errors(catalog, "product_row")
    manifest = tokopedia.write(args.out, reviews, catalog, cross, stats, args.input)

    print(f"\n{stats['beauty_products']:,} beauty products -> {stats['products']:,} facial-skincare products with "
          f"{stats['reviews']:,} reviews ({stats['reviews_with_text']:,} with text), {stats['brands']} brands, "
          f"{stats['date_range'][0]} to {stats['date_range'][1]}.")
    print("Brands with the most reviews: " + ", ".join(f"{b} ({n:,})" for b, n in list(manifest["brands"].items())[:10]))
    print(f"Region unknown for {stats['unknown_region_share']:.0%} of reviews (the seller's location is used).")
    print("Contract check: " + ("every row meets the row contracts." if not errors else
                                f"{len(errors)} problem(s), first ones:\n  " + "\n  ".join(errors)))
    print(f"\nWrote {args.out / 'raw'} and {args.out / 'manifest.json'}. Next:\n"
          f"  python run.py --data-dir {args.out} --client \"{next(iter(manifest['brands']))}\"")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
