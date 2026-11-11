"""The sentiment_data option: training the sentiment models on the study's reviews, real reviews, or both.

These tests use a tiny stand-in for the real corpus, so they run without the downloaded files.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from marketmind.ml import real_reviews
from marketmind.ml.sentiment import SentimentSuite


@pytest.fixture
def fake_corpus(tmp_path, monkeypatch):
    """A small corpus in the layout of the Hugging Face dataset (Review + one-hot star columns)."""
    for split, n in (("train", 6), ("validation", 3)):
        stars = np.arange(n) % 5 + 1
        df = pd.DataFrame({"Review": [f"ulasan {split} {i} :thumbs_up:" for i in range(n)]})
        for s in range(1, 6):
            df[f"Bintang {s}"] = stars == s
        df.to_parquet(tmp_path / f"{split}_data.parquet")
    monkeypatch.setattr(real_reviews, "REAL_REVIEWS_DIR", tmp_path)
    return tmp_path


def test_emoji_names_become_tokens_the_normaliser_knows():
    text = real_reviews.unname_emojis("mantap :thumbs_up: tapi :face_with_rolling_eyes:")
    assert "👍" in text and "emofacewithrollingeyes" in text and ":" not in text


def test_training_modes_combine_the_right_reviews(fake_corpus):
    study_x, study_y = np.array(["bagus", "jelek"], dtype=object), np.array([2, 0])
    sizes = {}
    for mode in real_reviews.TRAINING_MODES:
        x, y, src = real_reviews.training_set(mode, study_x, study_y)
        assert len(x) == len(y) == len(src)
        sizes[mode] = {s: int((src == s).sum()) for s in ("study", "real")}
    assert sizes == {"study": {"study": 2, "real": 0}, "study+real": {"study": 2, "real": 9}, "real": {"study": 0, "real": 9}}
    assert real_reviews.available()


def test_study_mode_keeps_the_existing_cache_key():
    texts, labels = pd.Series(["bagus banget", "biasa", "rusak"]), np.array([2, 1, 0])
    x, y, _ = real_reviews.training_set("study", texts.values, labels)
    assert SentimentSuite.data_hash(x, y) == SentimentSuite.data_hash(texts, labels)
    assert real_reviews.model_dir("study").name == "sentiment"


def test_the_model_card_finds_its_cache_inside_and_outside_the_project():
    """MARKETMIND_OUTPUTS may point outside the project; the Consumer Insight agent used to crash on that."""
    from marketmind.config import ROOT, project_path
    inside, outside = ROOT / "outputs" / "models" / "sentiment", ROOT.parent / "marketmind-runs" / "models" / "sentiment"
    assert project_path(inside) == "outputs/models/sentiment"           # portable in the saved run
    assert project_path(outside) == outside.resolve().as_posix()        # outside the project: absolute
    for folder in (inside, outside):                                     # how the dashboard and the web API load it
        assert (ROOT / project_path(folder)).resolve() == folder.resolve()


def test_missing_corpus_and_unknown_modes(tmp_path, monkeypatch):
    monkeypatch.setattr(real_reviews, "REAL_REVIEWS_DIR", tmp_path)
    assert not real_reviews.available()
    with pytest.raises(ValueError):
        real_reviews.training_set("everything", [], [])
    from marketmind.system import MarketResearchSystem
    with pytest.raises(ValueError):
        MarketResearchSystem(sentiment_data="everything")


def test_training_with_sources_reports_metrics_per_source():
    words = {0: ["jelek", "rusak", "kecewa", "lengket"], 1: ["biasa", "lumayan", "standar", "cukup"],
             2: ["bagus", "suka", "mantap", "lembut"]}
    rng = np.random.default_rng(0)
    texts, labels, sources = [], [], []
    for source in ("study", "real"):
        for label, vocab in words.items():
            for _ in range(40):
                texts.append(" ".join(rng.choice(vocab, size=4)))
                labels.append(label)
                sources.append(source)
    card = SentimentSuite("unused").train(texts, labels, sources=sources)
    assert set(card["test_metrics_by_source"]) == {"study", "real"}
    assert set(card["split_sources"]["test"]) == {"study", "real"}
    assert sum(card["split_sources"]["test"].values()) == card["n_test"]
    for metrics in card["test_metrics_by_source"].values():
        assert set(metrics) == {"linear", "bigru", "ensemble"}
