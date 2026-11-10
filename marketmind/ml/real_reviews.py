"""Real Indonesian beauty reviews for training the sentiment models (see docs/DATA_SOURCES.md).

The Consumer Insight agent normally learns sentiment from the study's own reviews. The
``sentiment_data`` option lets it add, or use only, a corpus of real Shopee and Tokopedia beauty
reviews (Hugging Face ``sekarmulyani/ulasan-beauty-products``, Apache-2.0) downloaded into
``data/external/ulasan-beauty-products/``:

* ``study``       the study's own reviews (default; the bundled data is simulated)
* ``study+real``  the study's reviews plus the real reviews
* ``real``        the real reviews only

Only the corpus's train and validation splits are used for training; its test split stays untouched
for ``scripts/validate_on_real_data.py``. Each mode keeps its own model cache.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import DATA_EXTERNAL, MODELS_DIR
from .sentiment import rating_to_label

REAL_REVIEWS_DIR = DATA_EXTERNAL / "ulasan-beauty-products"
TRAINING_MODES = ("study", "study+real", "real")
TRAINING_SPLITS = ("train", "validation")
SOURCE = "Shopee/Tokopedia beauty reviews (Hugging Face sekarmulyani/ulasan-beauty-products, Apache-2.0)"

# The corpus writes emojis as names (":thumbs_up:"). Map the ones MarketMind's normaliser knows back to the
# characters it turns into emopos / emoneg; keep any other emoji as one token so a model can still use it.
EMOJI_NAMES = {
    "smiling_face_with_heart-eyes": "😍", "smiling_face_with_hearts": "🥰", "thumbs_up": "👍", "sparkles": "✨",
    "hundred_points": "💯", "folded_hands": "🙏", "red_heart": "❤", "smiling_face_with_smiling_eyes": "😊",
    "star-struck": "🤩", "ok_hand": "👌", "loudly_crying_face": "😭", "enraged_face": "😡", "pouting_face": "😡",
    "face_with_steam_from_nose": "😤", "thumbs_down": "👎", "disappointed_face": "😞",
    "slightly_frowning_face": "🙁", "crying_face": "😢", "angry_face": "😠", "broken_heart": "💔",
}
EMOJI_NAME = re.compile(r":([a-z0-9_\-]+):", re.I)


def unname_emojis(text: str) -> str:
    def swap(m: re.Match) -> str:
        name = m.group(1).lower()
        return f" {EMOJI_NAMES[name]} " if name in EMOJI_NAMES else f" emo{re.sub(r'[^a-z0-9]', '', name)} "
    return EMOJI_NAME.sub(swap, text)


def available(splits: tuple[str, ...] = TRAINING_SPLITS) -> bool:
    return all((REAL_REVIEWS_DIR / f"{s}_data.parquet").exists() for s in splits)


def load(split: str) -> pd.DataFrame:
    """One split of the corpus as columns text, stars and label (0 negative, 1 neutral, 2 positive)."""
    df = pd.read_parquet(REAL_REVIEWS_DIR / f"{split}_data.parquet")
    stars = df[[f"Bintang {i}" for i in range(1, 6)]].to_numpy().argmax(1) + 1
    return pd.DataFrame(dict(text=[unname_emojis(t) for t in df["Review"].astype(str)], stars=stars,
                             label=rating_to_label(stars)))


def model_dir(mode: str) -> Path:
    """Model cache per training mode; ``study`` keeps the original location."""
    return MODELS_DIR / {"study": "sentiment", "study+real": "sentiment_study_real", "real": "sentiment_real"}[mode]


def training_set(mode: str, study_texts, study_labels) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Texts, labels and a source tag ("study" or "real") per row for one training mode."""
    if mode not in TRAINING_MODES:
        raise ValueError(f"sentiment training mode must be one of {TRAINING_MODES}, not {mode!r}")
    parts = []
    if mode != "real":
        parts.append((np.asarray(study_texts, dtype=object), np.asarray(study_labels), "study"))
    if mode != "study":
        real = pd.concat([load(s) for s in TRAINING_SPLITS], ignore_index=True)
        parts.append((real["text"].to_numpy(dtype=object), real["label"].to_numpy(), "real"))
    texts = np.concatenate([p[0] for p in parts])
    labels = np.concatenate([p[1] for p in parts])
    sources = np.concatenate([np.full(len(p[0]), p[2], dtype=object) for p in parts])
    return texts, labels, sources
