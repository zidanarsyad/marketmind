"""Sentiment models for Indonesian e-commerce text (the system's deep-learning component).

Three candidates are trained on labels derived from star ratings (1-2 negative, 3 neutral,
4-5 positive) - weak supervision that every marketplace provides for free:

1. ``linear``   TF-IDF (word 1-2 grams + char 3-5 grams) + logistic regression
2. ``bigru``    bidirectional GRU with additive attention, trained from scratch in PyTorch
3. ``ensemble`` soft vote of both

Model selection uses a validation split; the reported metrics come from a held-out test split
that no model saw during training or selection. The chosen model then labels data that has no
ratings at all (clauses inside reviews for aspect-level sentiment, and social-media posts).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from .text import normalize

LABELS = ["negative", "neutral", "positive"]
SOCIAL_NOISE = re.compile(r"#\w+|@\w+|https?://\S+")
SOCIAL_QUESTION = re.compile(r"\?|\b(ada yang|ada yg|rekomendasi|gimana|bagusan mana|mau tau|apa sih|tips|thread|"
                             r"kalian tim|haul|lagi cari|lagi bandingin|worth it ga)\b")


def rating_to_label(ratings) -> np.ndarray:
    r = np.asarray(ratings)
    return np.select([r <= 2, r == 3], [0, 1], 2)


# ------------------------------------------------------------------------- linear baseline

class LinearSentiment:
    name = "TF-IDF + Logistic Regression"

    def __init__(self, C: float = 2.0):
        self.pipe = Pipeline([
            ("features", FeatureUnion([
                ("word", TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                ("char", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                                         sublinear_tf=True, max_features=60000)),
            ])),
            ("clf", LogisticRegression(C=C, max_iter=3000, class_weight="balanced")),
        ])

    def fit(self, texts, y):
        self.pipe.fit(list(texts), y)
        return self

    def predict_proba(self, texts) -> np.ndarray:
        return self.pipe.predict_proba(list(texts))

    def top_terms(self, n: int = 12) -> dict[str, list[str]]:
        word_vec = self.pipe.named_steps["features"].transformer_list[0][1]
        n_word = len(word_vec.vocabulary_)
        names = word_vec.get_feature_names_out()
        coef = self.pipe.named_steps["clf"].coef_[:, :n_word]
        return {LABELS[k]: [names[i] for i in np.argsort(coef[k])[::-1][:n]] for k in range(coef.shape[0])}


# ------------------------------------------------------------------------- neural model

class Vocab:
    def __init__(self, itos: list[str] | None = None):
        self.itos = itos or ["<pad>", "<unk>"]
        self.stoi = {t: i for i, t in enumerate(self.itos)}

    @classmethod
    def build(cls, token_lists, min_freq: int = 2, max_size: int = 20000) -> "Vocab":
        counts = Counter(t for toks in token_lists for t in toks)
        words = [w for w, c in counts.most_common(max_size) if c >= min_freq]
        return cls(["<pad>", "<unk>"] + words)

    def encode(self, token_lists, max_len: int) -> tuple[np.ndarray, np.ndarray]:
        X = np.zeros((len(token_lists), max_len), dtype=np.int64)
        lens = np.ones(len(token_lists), dtype=np.int64)
        for i, toks in enumerate(token_lists):
            ids = [self.stoi.get(t, 1) for t in toks[:max_len]] or [1]
            X[i, :len(ids)] = ids
            lens[i] = len(ids)
        return X, lens

    def __len__(self) -> int:
        return len(self.itos)


class BiGRUAttention(nn.Module):
    def __init__(self, vocab_size: int, emb_dim: int = 96, hidden: int = 64, n_classes: int = 3, dropout: float = 0.3):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=0)
        self.gru = nn.GRU(emb_dim, hidden, batch_first=True, bidirectional=True)
        self.att = nn.Linear(2 * hidden, 1)
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(2 * hidden, n_classes)

    def forward(self, x: torch.Tensor):
        mask = x != 0
        h, _ = self.gru(self.drop(self.emb(x)))
        scores = self.att(torch.tanh(h)).squeeze(-1).masked_fill(~mask, -1e9)
        alpha = torch.softmax(scores, dim=1)
        context = (alpha.unsqueeze(-1) * h).sum(dim=1)
        return self.out(self.drop(context)), alpha


class NeuralSentiment:
    name = "BiGRU + Attention (PyTorch)"

    def __init__(self, emb_dim: int = 96, hidden: int = 64, max_len: int = 64, epochs: int = 10, batch_size: int = 128,
                 lr: float = 2e-3, patience: int = 3, word_dropout: float = 0.1, seed: int = 42):
        self.cfg = dict(emb_dim=emb_dim, hidden=hidden, max_len=max_len, epochs=epochs, batch_size=batch_size,
                        lr=lr, patience=patience, word_dropout=word_dropout, seed=seed)
        self.vocab: Vocab | None = None
        self.model: BiGRUAttention | None = None
        self.history: list[dict] = []

    @staticmethod
    def _tokens(texts) -> list[list[str]]:
        return [normalize(t).split() for t in texts]

    def fit(self, texts_tr, y_tr, texts_va, y_va, log=None) -> "NeuralSentiment":
        c = self.cfg
        torch.manual_seed(c["seed"])
        rng = np.random.default_rng(c["seed"])
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 2)))
        tok_tr = self._tokens(texts_tr)
        self.vocab = Vocab.build(tok_tr)
        X, lens = self.vocab.encode(tok_tr, c["max_len"])
        y = np.asarray(y_tr, dtype=np.int64)
        freq = np.bincount(y, minlength=3).astype(float)
        weights = (freq.sum() / (3 * np.maximum(freq, 1))) ** 0.5
        self.model = BiGRUAttention(len(self.vocab), c["emb_dim"], c["hidden"])
        opt = torch.optim.AdamW(self.model.parameters(), lr=c["lr"], weight_decay=1e-4)
        loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(weights / weights.mean(), dtype=torch.float32))
        best_f1, best_state, bad = -1.0, None, 0
        for epoch in range(1, c["epochs"] + 1):
            t0 = time.time()
            self.model.train()
            # length-bucketed batches (jittered each epoch) keep padding - and CPU time - low
            order = np.argsort(lens + rng.random(len(y)) * 4, kind="stable")
            batches = [order[i:i + c["batch_size"]] for i in range(0, len(y), c["batch_size"])]
            total = 0.0
            for b in rng.permutation(len(batches)):
                idx = batches[b]
                xb = torch.from_numpy(X[idx, :lens[idx].max()])
                if c["word_dropout"]:  # replace random tokens with <unk>: robustness to unseen words / new domains
                    drop = (torch.rand(xb.shape) < c["word_dropout"]) & (xb > 1)
                    xb = xb.masked_fill(drop, 1)
                yb = torch.from_numpy(y[idx])
                opt.zero_grad()
                logits, _ = self.model(xb)
                loss = loss_fn(logits, yb)
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
                total += loss.item() * len(idx)
            pred = self.predict_proba(texts_va).argmax(1)
            f1 = f1_score(y_va, pred, average="macro")
            rec = dict(epoch=epoch, train_loss=round(total / len(y), 4), val_macro_f1=round(f1, 4),
                       val_accuracy=round(accuracy_score(y_va, pred), 4), seconds=round(time.time() - t0, 1))
            self.history.append(rec)
            if log:
                log(f"epoch {epoch}: loss {rec['train_loss']:.3f}, val macro-F1 {f1:.3f} ({rec['seconds']}s)")
            if f1 > best_f1 + 1e-4:
                best_f1, best_state, bad = f1, copy.deepcopy(self.model.state_dict()), 0
            else:
                bad += 1
                if bad >= c["patience"]:
                    if log:
                        log(f"early stopping after epoch {epoch} (best val macro-F1 {best_f1:.3f})")
                    break
        self.model.load_state_dict(best_state)
        return self

    def predict_proba(self, texts, batch_size: int = 512) -> np.ndarray:
        X, lens = self.vocab.encode(self._tokens(texts), self.cfg["max_len"])
        self.model.eval()
        order = np.argsort(lens, kind="stable")
        proba = np.zeros((len(X), 3), dtype=np.float32)
        with torch.no_grad():
            for i in range(0, len(X), batch_size):
                idx = order[i:i + batch_size]
                logits, _ = self.model(torch.from_numpy(X[idx, :max(1, lens[idx].max())]))
                proba[idx] = torch.softmax(logits, dim=1).numpy()
        return proba

    def explain(self, text: str) -> list[tuple[str, float]]:
        toks = self._tokens([text])[0][: self.cfg["max_len"]]
        if not toks:
            return []
        X, _ = self.vocab.encode([toks], self.cfg["max_len"])
        self.model.eval()
        with torch.no_grad():
            _, alpha = self.model(torch.from_numpy(X[:, :len(toks)]))
        return list(zip(toks, [round(float(a), 4) for a in alpha[0].numpy()], strict=True))

    def save(self, path: Path) -> None:
        torch.save({"state_dict": self.model.state_dict(), "itos": self.vocab.itos, "cfg": self.cfg,
                    "history": self.history}, path)

    @classmethod
    def load(cls, path: Path) -> "NeuralSentiment":
        blob = torch.load(path, map_location="cpu", weights_only=True)
        obj = cls(**{k: v for k, v in blob["cfg"].items() if k in cls.__init__.__code__.co_varnames})
        obj.vocab = Vocab(blob["itos"])
        obj.model = BiGRUAttention(len(obj.vocab), obj.cfg["emb_dim"], obj.cfg["hidden"])
        obj.model.load_state_dict(blob["state_dict"])
        obj.model.eval()
        obj.history = blob.get("history", [])
        return obj


# ------------------------------------------------------------------------- model suite

def _metrics(y_true, proba) -> dict:
    pred = proba.argmax(1)
    rep = classification_report(y_true, pred, labels=[0, 1, 2], target_names=LABELS, output_dict=True, zero_division=0)
    return dict(accuracy=round(accuracy_score(y_true, pred), 4), macro_f1=round(f1_score(y_true, pred, average="macro"), 4),
                per_class={k: {m: round(v, 4) for m, v in rep[k].items()} for k in LABELS})


class SentimentSuite:
    """Trains, compares, persists and serves the sentiment candidates."""

    def __init__(self, model_dir: Path):
        self.dir = Path(model_dir)
        self.linear: LinearSentiment | None = None
        self.neural: NeuralSentiment | None = None
        self.selected = "ensemble"
        self.ensemble_weight = 0.5
        self.transfer = "ensemble"   # scorer for out-of-domain text (social posts, review clauses)
        self.card: dict = {}

    @staticmethod
    def data_hash(texts, labels) -> str:
        h = hashlib.sha1()
        for t, y in zip(texts, labels, strict=True):
            h.update(f"{t}\x1f{y}\x1e".encode("utf-8"))
        return h.hexdigest()[:16]

    def try_load(self, data_hash: str) -> bool:
        card_path = self.dir / "model_card.json"
        if not card_path.exists():
            return False
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if card.get("data_hash") != data_hash:
            return False
        try:
            self.linear = joblib.load(self.dir / "linear.joblib")
            self.neural = NeuralSentiment.load(self.dir / "bigru.pt")
        except Exception:
            return False
        self.card, self.selected = card, card["selected"]
        self.ensemble_weight = card.get("ensemble_weight", 0.5)
        self.transfer = card.get("transfer_model", "ensemble")
        return True

    def train(self, texts, labels, log=None, seed: int = 42, sources=None) -> dict:
        """``sources`` (optional) tags each row with where it came from, e.g. "study" or "real": the splits are
        then stratified by source and label, and the card reports test metrics per source."""
        texts, labels = np.asarray(texts, dtype=object), np.asarray(labels)
        sources = None if sources is None else np.asarray(sources, dtype=object)
        strata = labels if sources is None else np.array([f"{s}:{y}" for s, y in zip(sources, labels, strict=True)])
        idx = np.arange(len(texts))
        tr, tmp = train_test_split(idx, test_size=0.30, random_state=seed, stratify=strata)
        va, te = train_test_split(tmp, test_size=0.50, random_state=seed, stratify=strata[tmp])
        say = log or (lambda m: None)

        t0 = time.time()
        say(f"training {LinearSentiment.name} on {len(tr):,} reviews")
        self.linear = LinearSentiment().fit(texts[tr], labels[tr])
        t_lin = time.time() - t0

        t0 = time.time()
        say(f"training {NeuralSentiment.name} on {len(tr):,} reviews")
        self.neural = NeuralSentiment().fit(texts[tr], labels[tr], texts[va], labels[va], log=say)
        t_nn = time.time() - t0

        p_lin_va, p_nn_va = self.linear.predict_proba(texts[va]), self.neural.predict_proba(texts[va])
        best_w, best_f1 = 0.5, -1
        for w in (0.3, 0.4, 0.5, 0.6, 0.7):
            f1 = f1_score(labels[va], (w * p_lin_va + (1 - w) * p_nn_va).argmax(1), average="macro")
            if f1 > best_f1:
                best_w, best_f1 = w, f1
        self.ensemble_weight = best_w
        val = {"linear": f1_score(labels[va], p_lin_va.argmax(1), average="macro"),
               "bigru": f1_score(labels[va], p_nn_va.argmax(1), average="macro"),
               "ensemble": best_f1}
        self.selected = max(val, key=val.get)

        p_lin_te, p_nn_te = self.linear.predict_proba(texts[te]), self.neural.predict_proba(texts[te])
        p_ens_te = best_w * p_lin_te + (1 - best_w) * p_nn_te
        test = {"linear": _metrics(labels[te], p_lin_te), "bigru": _metrics(labels[te], p_nn_te),
                "ensemble": _metrics(labels[te], p_ens_te)}
        chosen = {"linear": p_lin_te, "bigru": p_nn_te, "ensemble": p_ens_te}[self.selected]
        cm = confusion_matrix(labels[te], chosen.argmax(1), labels=[0, 1, 2])

        self.card = dict(
            task="3-class sentiment (negative / neutral / positive) from Indonesian review text",
            labels=LABELS, label_source="star rating: 1-2 negative, 3 neutral, 4-5 positive",
            n_train=int(len(tr)), n_val=int(len(va)), n_test=int(len(te)),
            class_distribution={LABELS[k]: int(v) for k, v in enumerate(np.bincount(labels, minlength=3))},
            validation_macro_f1={k: round(v, 4) for k, v in val.items()},
            test_metrics=test, selected=self.selected, ensemble_weight=best_w,
            confusion_matrix=cm.tolist(), training_seconds=dict(linear=round(t_lin, 1), bigru=round(t_nn, 1)),
            bigru_history=self.neural.history, bigru_config=self.neural.cfg, vocab_size=len(self.neural.vocab),
            trained_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        if sources is not None:
            probs = {"linear": p_lin_te, "bigru": p_nn_te, "ensemble": p_ens_te}
            self.card["split_sources"] = {name: {str(s): int(n) for s, n in zip(*np.unique(sources[part], return_counts=True), strict=True)}
                                          for name, part in (("train", tr), ("val", va), ("test", te))}
            self.card["test_metrics_by_source"] = {
                str(s): {m: _metrics(labels[te][sources[te] == s], p[sources[te] == s]) for m, p in probs.items()}
                for s in np.unique(sources[te])}
        return self.card

    def save(self, data_hash: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.linear, self.dir / "linear.joblib")
        self.neural.save(self.dir / "bigru.pt")
        self.card["data_hash"] = data_hash
        (self.dir / "model_card.json").write_text(json.dumps(self.card, indent=2), encoding="utf-8")

    def predict_proba(self, texts) -> np.ndarray:
        texts = ["" if not isinstance(t, str) else t for t in texts]
        if self.selected == "linear":
            return self.linear.predict_proba(texts)
        if self.selected == "bigru":
            return self.neural.predict_proba(texts)
        w = self.ensemble_weight
        return w * self.linear.predict_proba(texts) + (1 - w) * self.neural.predict_proba(texts)

    def predict(self, texts) -> list[str]:
        return [LABELS[i] for i in self.predict_proba(texts).argmax(1)]

    # -- out-of-domain scoring (social posts, review clauses) ------------------------------------
    def _proba(self, texts, model: str) -> np.ndarray:
        if model == "linear":
            return self.linear.predict_proba(texts)
        if model == "bigru":
            return self.neural.predict_proba(texts)
        return 0.5 * self.linear.predict_proba(texts) + 0.5 * self.neural.predict_proba(texts)

    social_rules = True   # the domain rules below; scripts/ablations.py switches them off to measure what they buy

    def score_social(self, texts, model: str | None = None) -> tuple[list[str], np.ndarray]:
        """Domain-adapted social scoring: strip hashtags/mentions/URLs (topic tags, not sentiment), treat
        questions and informational posts as neutral unless strongly polar, and use a neutral band."""
        texts = [t if isinstance(t, str) else "" for t in texts]
        if not self.social_rules:                       # the review model as it is: plain argmax
            p = self._proba(texts, model or self.transfer)
            return [LABELS[i] for i in p.argmax(1)], p[:, 2] - p[:, 0]
        clean = [SOCIAL_NOISE.sub(" ", t).strip() for t in texts]
        p = self._proba(clean, model or self.transfer)
        score = p[:, 2] - p[:, 0]
        labels = []
        for text, s in zip(clean, score, strict=True):
            if (SOCIAL_QUESTION.search(text.lower()) and abs(s) < 0.8) or abs(s) < 0.2:
                labels.append("neutral")
            else:
                labels.append("positive" if s > 0 else "negative")
        return labels, score

    def evaluate_transfer(self, texts, labels) -> dict:
        """Compare candidates on a hand-labelled out-of-domain sample and keep the best as transfer model."""
        out = {}
        for model in ("linear", "bigru", "ensemble"):
            pred, _ = self.score_social(texts, model)
            out[model] = dict(accuracy=round(accuracy_score(labels, pred), 4),
                              macro_f1=round(f1_score(labels, pred, average="macro"), 4))
        self.transfer = max(out, key=lambda m: out[m]["macro_f1"])
        self.card["transfer_metrics"] = out
        self.card["transfer_model"] = self.transfer
        self.card["transfer_n"] = len(labels)
        return out

    def score_clauses(self, texts) -> np.ndarray:
        p = self._proba(["" if not isinstance(t, str) else t for t in texts], self.transfer)
        return p[:, 2] - p[:, 0]

    def score(self, texts) -> np.ndarray:
        """Polarity score in [-1, 1] = P(positive) - P(negative)."""
        p = self.predict_proba(texts)
        return p[:, 2] - p[:, 0]


def polarity(score: float, threshold: float = 0.2) -> str:
    return "positive" if score > threshold else "negative" if score < -threshold else "neutral"


def aspect_mentions(reviews: pd.DataFrame, suite: SentimentSuite) -> pd.DataFrame:
    """Aspect-based sentiment: split reviews into clauses, detect aspects with the lexicon and
    score each aspect-bearing clause with the trained sentiment model."""
    from .text import detect_aspects, split_clauses

    rows = []
    for r in reviews[["review_id", "brand", "category", "channel", "month", "review_text", "reviewer_skin_type"]].itertuples(index=False):
        for clause in split_clauses(r.review_text):
            for aspect in detect_aspects(clause):
                rows.append((r.review_id, r.brand, r.category, r.channel, r.month, r.reviewer_skin_type, aspect, clause))
    df = pd.DataFrame(rows, columns=["review_id", "brand", "category", "channel", "month", "skin_type", "aspect", "clause"])
    if df.empty:
        return df.assign(score=[], polarity=[])
    uniq = df["clause"].unique()
    scores = dict(zip(uniq, suite.score_clauses(uniq), strict=True))
    df["score"] = df["clause"].map(scores).round(4)
    df["polarity"] = df["score"].map(polarity)
    return df
