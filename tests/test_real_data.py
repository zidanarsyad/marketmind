"""Real-data readiness: the Tokopedia importer, planning from the data that exists, and a study on a real-data folder.

The importer is tested on a small archive written in the exact layout of the Kaggle dataset (one row per product,
review fields as position-aligned lists stored as text). The end-to-end study runs on a folder that holds only reviews
and a product catalogue, with a manifest that marks it as real data, which is what an imported folder looks like.
"""
from __future__ import annotations

import json
import shutil
import zipfile

import pandas as pd
import pytest

from marketmind.config import DATA_RAW, DATASETS
from marketmind.core.agent import RunContext
from marketmind.core.blackboard import Blackboard
from marketmind.core.events import Tracer
from marketmind.core.llm import LLMClient

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())


def product(pid, category, name, shop, reviews, price="Rp45.000", location="Kota Tangerang", sold=120.0):
    cols = dict(review_id=[], message=[], review_rating=[], review_time=[], review_timestamp=[], review_like=[],
                variant_name=[], bad_rating_reason=[])
    for k, (rating, text, ts) in enumerate(reviews):
        cols["review_id"].append(f"{pid}-{k}")
        cols["message"].append(text)
        cols["review_rating"].append(rating)
        cols["review_time"].append(0)
        cols["review_timestamp"].append(ts)
        cols["review_like"].append(k)
        cols["variant_name"].append("")
        cols["bad_rating_reason"].append("")
    return dict(product_id=pid, category=category, name=name, count_sold=sold, discounted_price="", preorder=False,
                price=price, stock=10, gold_merchant=True, is_official=True, is_topads=False, rating_average=4.8,
                shop_id=shop, shop_location=location, warehouse_id=1.0, product_url="https://example.invalid/p",
                **{c: str(v) for c, v in cols.items()})   # lists written as text, as in the Kaggle CSV


@pytest.fixture
def archive(tmp_path):
    face = "Kecantikan|Perawatan Wajah"
    r = [(5, "bagus banget, cepat meresap", "2024-05-12 10:22:01"), (2, "pump-nya rusak", "2024-06-01 08:00:00"),
         (None, "rating hilang", "2024-06-02 08:00:00"), (4, "", "2024-07-03 09:00:00")]
    rows = [
        product(1, face, "Wardah Lightening Facial Wash 100ml", 11, r),
        product(2, face, "Wardah UV Shield Sunscreen Gel SPF 30 40ml", 11, r[:2], price="Rp52.500"),
        product(3, "Kecantikan|Makeup Bibir", "Wardah Lipstick Matte", 11, r[:1]),
        product(4, face, "WARDAH Crystal Secret Serum 17ml", 11, r[:2]),
        product(5, face, "SKINTIFIC 5X Ceramide Barrier Moisturize Gel 30g", 22, r[:2], price="139000", location="Jakarta Barat"),
        product(6, face, "SKINTIFIC Niacinamide Brightening Toner 80ml", 22, r[:1], location="Jakarta Barat"),
        product(7, face, "SKINTIFIC Mugwort Acne Clay Mask 55g", 22, r[:1], location="Jakarta Barat"),
        product(8, face, "[PROMO] Somethinc Niacinamide Serum 20ml", 33, r[:2], location="Medan"),
        product(9, face, "Emina Bright Stuff Face Wash 50ml", 33, [], location="Medan"),
        product(10, "Perawatan Tubuh|Body Lotion", "Vaseline Body Lotion 200ml", 44, r[:1]),
        product(11, "Elektronik|Audio", "Speaker Bluetooth", 55, r[:1]),
    ]
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tokopedia_products_with_review.csv", pd.DataFrame(rows).to_csv(index=False))
    return path


def test_the_importer_turns_tokopedia_products_into_marketmind_contracts(archive, tmp_path):
    import sys
    sys.path.insert(0, str(DATA_RAW.parents[1] / "scripts"))
    from import_tokopedia import contract_errors

    from marketmind.adapters import tokopedia
    products = tokopedia.read_beauty_products(archive)
    assert set(products["product_id"].astype(int)) == set(range(1, 10))          # beauty only
    reviews, catalog, cross, stats = tokopedia.convert(products)
    cat = catalog.set_index("product_name")
    assert dict(zip(cat.index, cat["category"], strict=True)) == {
        "Wardah Lightening Facial Wash 100ml": "Facial Wash", "Wardah UV Shield Sunscreen Gel SPF 30 40ml": "Sunscreen",
        "WARDAH Crystal Secret Serum 17ml": "Serum", "SKINTIFIC 5X Ceramide Barrier Moisturize Gel 30g": "Moisturizer",
        "SKINTIFIC Niacinamide Brightening Toner 80ml": "Toner", "[PROMO] Somethinc Niacinamide Serum 20ml": "Serum"}
    assert set(cat["brand"]) == {"Wardah", "Skintific", "Somethinc"}                 # one spelling per brand
    sunscreen = cat.loc["Wardah UV Shield Sunscreen Gel SPF 30 40ml"]
    assert (sunscreen["price_idr"], sunscreen["spf"], sunscreen["size_ml"]) == (52500, 30, 40.0)
    assert cat.loc["SKINTIFIC 5X Ceramide Barrier Moisturize Gel 30g", "key_ingredient"] == "Ceramide"
    assert pd.isna(cat.loc["Wardah Lightening Facial Wash 100ml", "halal_certified"])  # unknown, not False
    # reviews: one row per rated, dated review; empty text kept as rating-only; the seller's region
    assert len(reviews) == 3 + 2 + 2 + 2 + 1 + 2 and stats["reviews"] == len(reviews)
    assert reviews["review_text"].isna().sum() == 1 and set(reviews["channel"]) == {"Tokopedia"}
    assert set(reviews["region"]) == {"DKI Jakarta & Banten", "Sumatera"}
    assert len(cross) == len(reviews) and cross["source_review_id"].str.startswith("1-").any()
    assert contract_errors(reviews, "review_row") == [] and contract_errors(catalog, "product_row") == []
    manifest = tokopedia.write(tmp_path / "real", reviews, catalog, cross, stats, archive)
    assert manifest["kind"] == "real" and "CC BY-NC" in manifest["licence"] and manifest["caveats"]
    assert (tmp_path / "real" / "raw" / "product_reviews.csv").exists()
    fixed = tokopedia.convert(products, brand_map={"somethinc": "SOMETHINC Official"})[1]
    assert "SOMETHINC Official" in set(fixed["brand"])


def test_the_director_plans_around_missing_data(tmp_path, monkeypatch):
    from marketmind import config
    from marketmind.agents.director import ResearchDirectorAgent
    raw = tmp_path / "raw"
    raw.mkdir()
    pd.DataFrame(dict(review_date=["2024-01-05", "2024-03-09", "2024-03-10"], brand=["Wardah", "Skintific", "Skintific"],
                      category=["Serum"] * 3, channel=["Tokopedia"] * 3)).to_csv(raw / "product_reviews.csv", index=False)
    (tmp_path / "manifest.json").write_text(json.dumps(dict(kind="real", source="test source")), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_RAW", raw)
    ctx = RunContext("t", Blackboard(), Tracer("t"), LLMClient(provider="none"), tmp_path, dict(brief="Help us grow"))
    director = ResearchDirectorAgent(ctx)
    catalog = director._scan_catalog()
    assert catalog["source"] == "reviews" and catalog["first_month"] == "2024-01-01" and catalog["data"]["kind"] == "real"
    plan = director._rule_plan("Help us grow", catalog)          # no module named: every module, then the data decides
    assert plan["client"] == "Skintific"                                    # the brand with the most records
    assert [a for a, on in plan["modules"].items() if on] == ["consumer"]
    assert set(plan["unavailable"]) == {"market", "competition", "segmentation", "pricing", "forecast"}
    assert "the sales panel" in plan["unavailable"]["market"] and plan["data"]["kind"] == "real"
    assert [q["area"] for q in plan["questions"]] == ["consumer", "strategy"]
    asked = director._rule_plan("How do we beat the rival brands on share?", catalog)   # asks for competition only
    assert [a for a, on in asked["modules"].items() if on] == ["consumer"] and "competition" in asked["unavailable"]
    (raw / "product_reviews.csv").unlink()
    with pytest.raises(ValueError, match="nothing to study"):
        director._scan_catalog()


@pytest.mark.slow
@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_a_study_on_a_real_data_folder_runs_the_modules_its_data_supports(tmp_path, monkeypatch):
    from marketmind import config
    from marketmind import system as system_module
    from marketmind.core.store import RunData
    from marketmind.evaluation import evaluate
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for key in ("reviews", "catalog"):        # what an imported real-data folder holds
        shutil.copy(DATA_RAW / DATASETS[key]["file"], raw / DATASETS[key]["file"])
    (raw.parent / "manifest.json").write_text(json.dumps(dict(
        kind="real", source="a test copy of marketplace reviews", licence="test only",
        caveats=["Brands are derived from product names."])), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_RAW", raw)
    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path / "runs")
    system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"), sentiment_data="study",
                                                brief="Find out what consumers say about Kirana Beauty's skincare.")
    res = system.run()
    plan = system.blackboard.get("plan")
    assert res.status == "completed" and res.qa["passed"], res.qa
    assert [a for a, on in plan["modules"].items() if on] == ["consumer"] and plan["data"]["kind"] == "real"
    assert set(res.results) >= {"collect", "quality", "consumer", "strategy", "report", "qa"}
    assert not {"market", "competition", "segmentation", "forecast"} & set(res.results)
    ids = {f.id[:3] for f in system.blackboard.findings()}
    assert ids <= {"DAT", "MAC", "CON"} and "CON" in ids
    assert len(system.blackboard.get("strategy.recommendations")) >= 1
    report = (res.run_dir / "report.md").read_text(encoding="utf-8")
    assert "Not studied for lack of data" in report and "real marketplace data" in report
    assert "simulated reviews only" not in report        # the models learned from the folder's own reviews
    assert "all data in this report is simulated" not in report                     # the title note says real data
    assert "All data is simulated" not in (res.run_dir / "report.html").read_text(encoding="utf-8")   # and the footer
    meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["options"]["data_dir"] == str(raw.parent)
    assert evaluate(RunData(run_id=res.run_id, path=res.run_dir, meta=meta))["available"] is False
