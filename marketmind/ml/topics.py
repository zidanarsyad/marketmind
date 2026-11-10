"""Unsupervised topic discovery (TF-IDF + NMF) to surface recurring complaint themes."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from .text import ASPECT_LABELS, ASPECT_LEXICON, STOPWORDS, normalize


def _label(terms: list[str]) -> tuple[str, str]:
    best, best_hits = "other", 0.0
    for aspect, keys in ASPECT_LEXICON.items():
        hits = sum(len(terms) - rank for rank, t in enumerate(terms)
                   if any(w.startswith(k) for w in t.split() for k in keys if " " not in k) or any(" " in k and k in t for k in keys))
        if hits > best_hits:
            best, best_hits = aspect, hits
    return best, ASPECT_LABELS.get(best, "Other")


def discover_topics(texts, n_topics: int = 6, n_terms: int = 8, seed: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    texts = [t for t in texts if isinstance(t, str) and t.strip()]
    if len(texts) < n_topics * 10:
        return pd.DataFrame(columns=["topic", "label", "aspect", "share", "top_terms"]), np.array([])
    vec = TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), min_df=5, max_df=0.4,
                          stop_words=sorted(STOPWORDS), token_pattern=r"(?u)\b[a-z][a-z0-9-]+\b")
    X = vec.fit_transform(texts)
    nmf = NMF(n_components=n_topics, init="nndsvda", random_state=seed, max_iter=500)
    W = nmf.fit_transform(X)
    names = vec.get_feature_names_out()
    dominant = W.argmax(1)
    rows = []
    for k, comp in enumerate(nmf.components_):
        terms = [names[i] for i in comp.argsort()[::-1][:n_terms]]
        aspect, label = _label(terms)
        rows.append(dict(topic=k + 1, label=label, aspect=aspect, share=round(float((dominant == k).mean()), 4),
                         top_terms=", ".join(terms)))
    return pd.DataFrame(rows).sort_values("share", ascending=False).reset_index(drop=True), dominant
