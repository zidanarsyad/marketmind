"""Consumer Insight Agent - the deep-learning agent.

Trains (or reuses, when the data is unchanged) a PyTorch BiGRU-with-attention sentiment model
alongside a TF-IDF/logistic-regression baseline, picks the best on validation data, and applies it to:

* every review (text sentiment by brand and month),
* every aspect-bearing clause inside reviews (aspect-based sentiment: what exactly people love or hate),
* social-media posts, which carry no star rating at all (transfer of the review-trained model).

It then detects anomalous spikes in aspect complaints, mines complaint topics with NMF, and links
survey NPS and skin-type evidence to the findings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.metrics import accuracy_score, f1_score

from ..config import ROOT
from ..core.agent import BaseAgent
from ..core.findings import Finding
from ..ml import real_reviews
from ..ml.sentiment import LABELS, SentimentSuite, aspect_mentions, rating_to_label
from ..ml.text import ASPECT_LABELS
from ..ml.topics import discover_topics
from .common import pct, windows


def _period(ep) -> str:
    s, e = pd.Timestamp(ep["start"]), pd.Timestamp(ep["end"])
    return f"in {s:%b %Y}" if s == e else f"between {s:%b %Y} and {e:%b %Y}"


def _nss(labels: pd.Series) -> float:
    return float((labels == "positive").mean() - (labels == "negative").mean()) if len(labels) else float("nan")


MIN_TRAINING_REVIEWS = 100   # below this the train / validation / test split cannot be stratified meaningfully


class ConsumerInsightAgent(BaseAgent):
    name = "Consumer Insight Agent"
    finding_prefix = "CON"
    requires = ("reviews",)
    role = "NLP / deep-learning specialist. Reads what consumers write in reviews and on social media."
    goal = "Explain what consumers love and dislike - by brand, aspect and over time - and flag emerging problems early."
    ml_capability = ("Deep learning: PyTorch BiGRU + attention sentiment classifier (with TF-IDF/LogReg baseline and "
                     "ensemble), aspect-based sentiment, NMF topic mining, anomaly detection")

    def register_tools(self):
        self.tool("train_sentiment_models", self._train, "train BiGRU-attention and TF-IDF/LogReg models, select by validation macro-F1")
        self.tool("score_reviews", self._score_reviews, "predict sentiment for every review text")
        self.tool("aspect_based_sentiment", self._aspects, "split reviews into clauses, detect aspects, score each clause")
        self.tool("detect_complaint_spikes", self._anomalies, "find months where aspect complaints spike above baseline")
        self.tool("mine_complaint_topics", self._topics, "NMF topic model over the client's negative reviews")
        self.tool("validate_transfer", lambda s: self.suite.evaluate_transfer(s["post_text"].tolist(), s["human_label"].tolist()),
                  "test each model on hand-labelled social posts (out-of-domain) and pick the transfer scorer")
        self.tool("score_social_posts", self._social, "apply the review-trained model to unlabeled social posts")
        self.tool("analyse_skin_type_fit", self._skin_fit, "compare sensitive-skin reviews of fragranced vs fragrance-free products")

    def execute(self) -> str:
        data = self.bb.require("datasets")
        self.client = self.bb.require("plan")["client"]
        reviews = data["reviews"]
        text = reviews[reviews["has_text"]].reset_index(drop=True)
        labels = rating_to_label(text["rating"].values)
        mode = self._training_mode()
        counts = pd.Series(labels).value_counts()
        if mode == "study" and (len(text) < MIN_TRAINING_REVIEWS or len(counts) < 3 or counts.min() < 5):
            raise ValueError(
                f"Too few labelled reviews to train the sentiment models: {len(text):,} with text ("
                + ", ".join(f"{LABELS[k]} {counts.get(k, 0)}" for k in range(3)) + f"); at least {MIN_TRAINING_REVIEWS} "
                "are needed, with every sentiment class represented (a few thousand give a reliable model). Import more "
                "products, or train on the real corpus with --sentiment-data real.")
        mix: dict = {}
        train_x, train_y, sources = real_reviews.training_set(mode, text["review_text"].values, labels, report=mix)
        if mix.get("overlap_removed"):
            self.think(f"Left out {mix['overlap_removed']:,} real reviews that duplicate this study's own reviews.")
        self.suite = SentimentSuite(real_reviews.model_dir(mode))
        h = self.suite.data_hash(train_x, train_y)
        if not self.options.get("force_retrain") and self.suite.try_load(h):
            self.think(f"Found a sentiment model trained on this exact data (hash {h}); reusing it instead of retraining.")
        else:
            n_study, n_real = int((sources == "study").sum()), int((sources == "real").sum())
            what = {"study": f"{n_study:,} labelled reviews",
                    "study+real": f"{n_study:,} of this study's reviews plus {n_real:,} real Shopee/Tokopedia beauty reviews",
                    "real": f"{n_real:,} real Shopee/Tokopedia beauty reviews only (none from this study)"}[mode]
            self.think(f"Training sentiment models on {what} (labels from star ratings).")
            self.use("train_sentiment_models", train_x, train_y, None if mode == "study" else sources)
            self.suite.save(h)
        self.suite.card["training_data"] = dict(
            mode=mode, study_reviews=int((sources == "study").sum()), real_reviews=int((sources == "real").sum()),
            overlap_removed=mix.get("overlap_removed", 0),
            real_source=None if mode == "study" else real_reviews.SOURCE,
            model_dir=real_reviews.model_dir(mode).relative_to(ROOT).as_posix())
        if mode == "study" and (self.bb.get("data.provenance") or {}).get("kind") != "real":
            self.suite.card["real_text_note"] = (
                "These models learned from simulated reviews only; on real marketplace reviews they reach a macro-F1 of "
                "only about 0.45 (docs/EVALUATION.md, section 4.6), so train them with --sentiment-data study+real "
                "before scoring real text.")
        else:
            self.suite.card.pop("real_text_note", None)
        self.suite.social_rules = not self.options.get("no_social_rules")   # ablation option
        labels_df = data.get("social_labels")
        if labels_df is not None and "social" in data and not self.options.get("skip_transfer_check"):
            sample = labels_df.merge(data["social"][["post_id", "post_text"]], on="post_id")
            if len(sample) >= 50:
                tr = self.use("validate_transfer", sample)
                self.think(f"Transfer check on {len(sample)} hand-labelled social posts: "
                           + ", ".join(f"{m} macro-F1 {v['macro_f1']:.3f}" for m, v in tr.items())
                           + f" -> using '{self.suite.transfer}' for social posts and review clauses.")
        # ablation options (scripts/ablations.py): assume the review-selected model transfers, or force one candidate
        if self.options.get("skip_transfer_check"):
            self.suite.transfer = self.suite.selected
        if self.options.get("sentiment_model"):
            self.suite.selected = self.suite.transfer = self.suite.card["selected"] = self.options["sentiment_model"]
            self.suite.card["transfer_model"] = self.options["sentiment_model"]
        card = self.suite.card
        t = {}
        scored = self.use("score_reviews", text)
        if mode == "real":  # the model never saw the study's reviews, so all of them are a fair test
            y, pred = rating_to_label(scored["rating"].values), scored["pred"].map(LABELS.index).values
            card["study_reviews_check"] = dict(n=int(len(scored)), accuracy=round(float(accuracy_score(y, pred)), 4),
                                               macro_f1=round(float(f1_score(y, pred, average="macro")), 4))
        self.put("consumer.model_card", card, "Sentiment model card (metrics, selection, training data, training history)")
        t.update(self._sentiment_tables(reviews, scored))
        asp = self.use("aspect_based_sentiment", text)
        t.update(self._aspect_tables(asp, scored))
        t["anomalies"] = self.use("detect_complaint_spikes", asp, scored)
        t["complaint_topics"] = self.use("mine_complaint_topics", text)
        if "social" in data:
            t.update(self.use("score_social_posts", data["social"]))
        if "survey" in data:
            sv = data["survey"]
            t["nps"] = (sv.groupby("main_brand")["nps_main_brand"]
                        .apply(lambda s: 100 * ((s >= 9).mean() - (s <= 6).mean())).round(1)
                        .rename("nps").reset_index().merge(sv.groupby("main_brand").size().rename("n").reset_index())
                        .rename(columns={"main_brand": "brand"}).sort_values("nps", ascending=False))
        if "catalog" in data:
            t["skin_type_fit"] = self.use("analyse_skin_type_fit", reviews, asp, data["catalog"])
        t["example_reviews"] = self._examples(scored, asp, t["anomalies"])
        self.put("consumer.tables", t, "Consumer sentiment, aspect and anomaly tables")
        self._publish_findings(t, card)
        sel = card["selected"]
        return (f"Sentiment model '{sel}' macro-F1 {self._headline['macro_f1']:.3f} on the study's reviews; "
                f"{len(asp):,} aspect mentions; {len(t['anomalies'])} complaint spikes detected")

    def _training_mode(self) -> str:
        mode = self.options.get("sentiment_data") or "study"
        if mode != "study" and not real_reviews.available():
            self.warn(f"Real reviews not found in {real_reviews.REAL_REVIEWS_DIR}; training on the study's reviews only "
                      "(docs/DATA_SOURCES.md explains how to get them).")
            return "study"
        return mode

    # ------------------------------------------------------------------ tools
    def _train(self, texts, labels, sources=None) -> dict:
        card = self.suite.train(texts, labels, log=lambda m: self.emit("observation", m), sources=sources)
        sel = card["selected"]
        self.think(f"Model selection on validation macro-F1 {card['validation_macro_f1']} -> '{sel}'. "
                   f"Held-out test macro-F1 {card['test_metrics'][sel]['macro_f1']:.3f}, "
                   f"accuracy {card['test_metrics'][sel]['accuracy']:.3f}.")
        return card

    def _score_reviews(self, text: pd.DataFrame) -> pd.DataFrame:
        proba = self.suite.predict_proba(text["review_text"].tolist())
        out = text.copy()
        out["pred"] = [LABELS[i] for i in proba.argmax(1)]
        out["score"] = proba[:, 2] - proba[:, 0]
        out["rating_label"] = [LABELS[i] for i in rating_to_label(out["rating"].values)]
        return out

    def _aspects(self, text: pd.DataFrame) -> pd.DataFrame:
        return aspect_mentions(text, self.suite)

    def _anomalies(self, asp: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
        base = scored.groupby(["brand", "month"]).size()
        neg = asp[asp["polarity"] == "negative"].groupby(["brand", "aspect", "month"])["review_id"].nunique()
        months = sorted(scored["month"].unique())
        episodes = []
        for (brand, aspect), s in neg.groupby(level=[0, 1]):
            counts = s.droplevel([0, 1]).reindex(months, fill_value=0)
            n = base.loc[brand].reindex(months).fillna(0)
            rate = 100 * counts / n.replace(0, np.nan)
            baseline = rate.shift(1).rolling(6, min_periods=4).median()
            expected = (baseline.fillna(rate.median()) / 100 * n).clip(lower=0.5)
            p_value = pd.Series(poisson.sf(counts.to_numpy() - 1, expected.to_numpy()), index=months)
            flag = (counts >= 8) & (rate >= 2 * baseline + 2) & (p_value < 1e-3)
            run = []
            for m in months + [None]:
                if m is not None and flag.get(m, False):
                    run.append(m)
                    continue
                if run:
                    seg = rate.loc[run]
                    b = float(baseline.loc[run[0]])
                    excess = float((counts.loc[run] - expected.loc[run]).sum())
                    episodes.append(dict(
                        brand=brand, aspect=aspect, aspect_label=ASPECT_LABELS.get(aspect, aspect),
                        start=run[0], end=run[-1], months=len(run), peak_rate=round(float(seg.max()), 1),
                        baseline_rate=round(b, 1), complaints=int(counts.loc[run].sum()),
                        excess_complaints=round(excess, 1), min_p_value=float(p_value.loc[run].min()),
                        severity=round(excess, 1)))
                    run = []
        out = pd.DataFrame(episodes)
        return out.sort_values("severity", ascending=False).reset_index(drop=True) if len(out) else out

    def _topics(self, text: pd.DataFrame) -> pd.DataFrame:
        neg = text[(text["brand"] == self.client) & (text["rating"] <= 2)]["review_text"].tolist()
        topics, _ = discover_topics(neg, n_topics=5)
        return topics

    def _social(self, social: pd.DataFrame) -> dict:
        s = social.copy()
        s["pred"], s["score"] = self.suite.score_social(s["post_text"].tolist())
        branded = s[s["brand_mentioned"] != ""]
        last, l12, _ = windows(s["month"])
        cur = branded[branded["month"] >= l12]
        by_brand = cur.groupby("brand_mentioned").apply(lambda g: pd.Series(dict(
            posts=len(g), nss=_nss(g["pred"]), engagement_weighted_score=np.average(g["score"], weights=g["engagement"] + 1),
            negative_share=(g["pred"] == "negative").mean())), include_groups=False).reset_index().rename(columns={"brand_mentioned": "brand"})
        monthly = branded.groupby(["month", "brand_mentioned"])["pred"].apply(_nss).rename("nss").reset_index() \
                         .rename(columns={"brand_mentioned": "brand"})
        platform = cur.groupby(["platform"])["pred"].apply(_nss).rename("nss").reset_index()
        self._social_scored = s
        return {"social_sentiment": by_brand.sort_values("nss", ascending=False), "social_monthly": monthly,
                "social_platform": platform,
                "social_scored": s[["post_id", "month", "platform", "brand_mentioned", "pred", "score"]].round(4)}

    def _skin_fit(self, reviews: pd.DataFrame, asp: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
        ff = catalog.set_index("sku_id")["fragrance_free"]
        r = reviews.assign(fragrance_free=reviews["sku_id"].map(ff))
        r["skin"] = np.where(r["reviewer_skin_type"] == "sensitive", "sensitive", "other / unknown")
        reaction = asp[(asp["aspect"] == "reaksi_kulit") & (asp["polarity"] == "negative")]["review_id"].unique()
        r["reaction_complaint"] = r["review_id"].isin(reaction)
        out = r.groupby(["skin", "fragrance_free"]).agg(reviews=("review_id", "count"), avg_rating=("rating", "mean"),
                                                        negative_share=("rating", lambda s: (s <= 2).mean()),
                                                        reaction_complaint_rate=("reaction_complaint", "mean")).reset_index()
        out["product_type"] = np.where(out["fragrance_free"], "fragrance-free", "fragranced")
        return out.round(4)

    # ------------------------------------------------------------------ tables
    def _sentiment_tables(self, reviews: pd.DataFrame, scored: pd.DataFrame) -> dict:
        last, l12, p12 = windows(reviews["month"])
        rv = reviews[reviews["month"] >= l12]
        sc = scored[scored["month"] >= l12]
        by_brand = pd.DataFrame({
            "reviews": rv.groupby("brand").size(), "avg_rating": rv.groupby("brand")["rating"].mean(),
            "text_nss": sc.groupby("brand")["pred"].apply(_nss),
            "rating_nss": sc.groupby("brand")["rating_label"].apply(_nss),
            "positive": sc.groupby("brand")["pred"].apply(lambda s: (s == "positive").mean()),
            "neutral": sc.groupby("brand")["pred"].apply(lambda s: (s == "neutral").mean()),
            "negative": sc.groupby("brand")["pred"].apply(lambda s: (s == "negative").mean()),
        }).reset_index().rename(columns={"index": "brand"}).sort_values("text_nss", ascending=False)
        monthly = scored.groupby(["month", "brand"]).agg(reviews=("review_id", "count"), avg_rating=("rating", "mean"),
                                                         text_nss=("pred", _nss)).reset_index()
        agree = float((scored["pred"] == scored["rating_label"]).mean())
        self._agreement = agree
        return {"sentiment_by_brand": by_brand, "sentiment_monthly": monthly}

    def _aspect_tables(self, asp: pd.DataFrame, scored: pd.DataFrame) -> dict:
        last, l12, p12 = windows(scored["month"])
        n_rev = scored[scored["month"] >= l12].groupby("brand").size()
        cur = asp[asp["month"] >= l12]
        g = cur.groupby(["brand", "aspect"])
        summary = pd.DataFrame({"mentions": g.size(),
                                "positive": g["polarity"].apply(lambda s: (s == "positive").sum()),
                                "negative": g["polarity"].apply(lambda s: (s == "negative").sum())}).reset_index()
        summary["net_sentiment"] = (summary["positive"] - summary["negative"]) / summary["mentions"]
        summary["negative_per_100_reviews"] = 100 * summary["negative"] / summary["brand"].map(n_rev)
        summary["mention_rate"] = summary["mentions"] / summary["brand"].map(n_rev)
        summary["aspect_label"] = summary["aspect"].map(ASPECT_LABELS)
        cl = asp[asp["brand"] == self.client]
        base = scored[scored["brand"] == self.client].groupby("month").size()
        cm = cl.groupby(["month", "aspect"])["polarity"].agg(
            negative=lambda s: (s == "negative").sum(), positive=lambda s: (s == "positive").sum()).reset_index()
        cm["negative_per_100_reviews"] = 100 * cm["negative"] / cm["month"].map(base)
        cm["aspect_label"] = cm["aspect"].map(ASPECT_LABELS)
        prev = asp[(asp["month"] >= p12) & (asp["month"] < l12)]
        trend = []
        for (b, a), grp in cur.groupby(["brand", "aspect"]):
            pg = prev[(prev["brand"] == b) & (prev["aspect"] == a)]
            if len(pg) >= 20 and len(grp) >= 20:
                trend.append(dict(brand=b, aspect=a, aspect_label=ASPECT_LABELS.get(a, a),
                                  net_l12=((grp["polarity"] == "positive").mean() - (grp["polarity"] == "negative").mean()),
                                  net_p12=((pg["polarity"] == "positive").mean() - (pg["polarity"] == "negative").mean())))
        tr = pd.DataFrame(trend)
        if len(tr):
            tr["change"] = tr["net_l12"] - tr["net_p12"]
        return {"aspect_summary": summary.round(4), "client_aspect_monthly": cm.round(3), "aspect_trend": tr.round(4),
                "aspect_mentions_sample": asp.sample(min(len(asp), 3000), random_state=0)}

    def _examples(self, scored: pd.DataFrame, asp: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
        rows = []
        if len(anomalies):
            for ep in anomalies.head(3).itertuples():
                sub = asp[(asp["brand"] == ep.brand) & (asp["aspect"] == ep.aspect) & (asp["polarity"] == "negative")
                          & (asp["month"] >= ep.start) & (asp["month"] <= ep.end)]
                for clause in sub["clause"].drop_duplicates().head(4):
                    rows.append(dict(brand=ep.brand, aspect=ep.aspect_label, type="complaint spike", text=clause))
        best = scored[(scored["brand"] == self.client) & (scored["pred"] == "positive")].nlargest(4, "score")
        rows += [dict(brand=self.client, aspect="overall", type="praise", text=t) for t in best["review_text"]]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ findings
    def _publish_findings(self, t: dict, card: dict) -> None:
        c = self.client
        sel = card["selected"]
        tm = card["test_metrics"]
        name = {"bigru": "BiGRU-attention network", "linear": "TF-IDF + logistic regression",
                "ensemble": "ensemble of a BiGRU-attention network and TF-IDF logistic regression"}[sel]
        transfer = card.get("transfer_metrics", {}).get(card.get("transfer_model", ""), {})
        mode = (card.get("training_data") or {}).get("mode", "study")
        by_source, split = card.get("test_metrics_by_source") or {}, card.get("split_sources") or {}

        def per_model(r: dict) -> str:
            return (f" (BiGRU {r['bigru']['macro_f1']:.3f}, ensemble {r['ensemble']['macro_f1']:.3f}, "
                    f"linear baseline {r['linear']['macro_f1']:.3f})")

        # the headline score is always measured on this study's own reviews
        if mode == "study+real" and {"study", "real"} <= set(by_source):
            ref = by_source["study"]
            headline = ref[sel]
            trained = (f"Of three sentiment models trained on {split['train']['study']:,} of this study's reviews plus "
                       f"{split['train']['real']:,} real Shopee/Tokopedia beauty reviews, validation picked the {name}: "
                       f"macro-F1 {headline['macro_f1']:.3f} and accuracy {headline['accuracy']:.3f} on "
                       f"{split['test']['study']:,} held-out study reviews" + per_model(ref)
                       + f", and macro-F1 {by_source['real'][sel]['macro_f1']:.3f} on {split['test']['real']:,} held-out real reviews.")
        elif mode == "real" and card.get("study_reviews_check"):
            ref, headline = tm, card["study_reviews_check"]
            trained = (f"Of three sentiment models trained only on {card['n_train']:,} real Shopee/Tokopedia beauty reviews, "
                       f"validation picked the {name}: macro-F1 {tm[sel]['macro_f1']:.3f} on {card['n_test']:,} held-out real "
                       f"reviews" + per_model(tm) + f". Against the star ratings of all {headline['n']:,} study reviews, which "
                       f"it never saw, it reaches macro-F1 {headline['macro_f1']:.3f} and accuracy {headline['accuracy']:.3f}.")
        else:
            ref, headline = tm, tm[sel]
            trained = (f"Of three sentiment models trained on {card['n_train']:,} reviews, validation picked the {name}: "
                       f"macro-F1 {headline['macro_f1']:.3f} and accuracy {headline['accuracy']:.3f} on {card['n_test']:,} "
                       f"held-out reviews" + per_model(tm) + ".")
        self._headline = headline
        self.publish(Finding(
            id="CON-01", agent=self.name, area="consumer", title="Deep-learning sentiment model",
            statement=(trained
                       + (f" On {card['transfer_n']} hand-labelled social posts the {card['transfer_model']} scorer reaches "
                          f"macro-F1 {transfer['macro_f1']:.3f}." if transfer else "")),
            metrics=dict(selected=sel, macro_f1=headline["macro_f1"], accuracy=headline["accuracy"], n_test=card["n_test"],
                         bigru_macro_f1=ref["bigru"]["macro_f1"], linear_macro_f1=ref["linear"]["macro_f1"],
                         training_mode=mode, transfer_model=card.get("transfer_model"),
                         transfer_macro_f1=transfer.get("macro_f1"), transfer_n=card.get("transfer_n")),
            evidence=["product_reviews.csv", "consumer.model_card"] + ([real_reviews.SOURCE] if mode != "study" else []),
            impact=2, confidence=0.95, tags=["methodology", "model"]))

        asp = t["aspect_summary"]
        product_aspects = {"efektivitas", "tekstur", "aroma", "kemasan", "harga", "reaksi_kulit"}
        mine = asp[(asp["brand"] == c) & (asp["mentions"] >= 30) & asp["aspect"].isin(product_aspects)] \
            .sort_values("net_sentiment", ascending=False)
        if len(mine) >= 2:
            a, b = mine.iloc[0], mine.iloc[1]
            peer = asp[(asp["aspect"] == a["aspect"]) & (asp["brand"] != c)]["net_sentiment"].mean()
            self.publish(Finding(
                id="CON-02", agent=self.name, area="consumer", title=f"What consumers love about {c}",
                statement=(f"Consumers praise {c} most for {a['aspect_label'].lower()} (net sentiment {a['net_sentiment']:+.2f} "
                           f"vs {peer:+.2f} for competitors) and {b['aspect_label'].lower()} ({b['net_sentiment']:+.2f})."),
                metrics=dict(aspect_1=a["aspect_label"], net_1=round(a["net_sentiment"], 3), peer_net_1=round(peer, 3),
                             aspect_2=b["aspect_label"], net_2=round(b["net_sentiment"], 3)),
                evidence=["product_reviews.csv (aspect-based sentiment)"], impact=3, confidence=0.8, swot="S",
                tags=["aspect", "strength"]))

        an = t["anomalies"]
        mine_an = an[an["brand"] == c] if len(an) else an
        if len(mine_an):
            ep = mine_an.iloc[0]
            self.publish(Finding(
                id="CON-03", agent=self.name, area="consumer", title=f"Complaint spike: {ep['aspect_label']}",
                statement=(f"{ep['aspect_label']} complaints about {c} spiked to {ep['peak_rate']:.1f} per 100 reviews "
                           f"{_period(ep)} (baseline {ep['baseline_rate']:.1f}); {ep['complaints']} negative mentions were "
                           f"detected, about {ep['excess_complaints']:.0f} above normal - the most severe issue in {c}'s reviews."),
                metrics=dict(aspect=ep["aspect_label"], peak_rate=ep["peak_rate"], baseline_rate=ep["baseline_rate"],
                             start=f"{ep['start']:%Y-%m}", end=f"{ep['end']:%Y-%m}", complaints=int(ep["complaints"])),
                evidence=["product_reviews.csv (anomaly detection on aspect complaints)"], impact=5, confidence=0.85,
                swot="W", tags=["pain point", "anomaly"]))
            if len(mine_an) > 1:
                ep2 = mine_an.iloc[1]
                self.publish(Finding(
                    id="CON-04", agent=self.name, area="consumer", title=f"Second complaint spike: {ep2['aspect_label']}",
                    statement=(f"{ep2['aspect_label']} complaints about {c} also rose to {ep2['peak_rate']:.1f} per 100 reviews "
                               f"{_period(ep2)} (baseline {ep2['baseline_rate']:.1f})."),
                    metrics=dict(aspect=ep2["aspect_label"], peak_rate=ep2["peak_rate"], baseline_rate=ep2["baseline_rate"],
                                 start=f"{ep2['start']:%Y-%m}", end=f"{ep2['end']:%Y-%m}"),
                    evidence=["product_reviews.csv (anomaly detection)"], impact=3, confidence=0.75, swot="W",
                    tags=["pain point", "anomaly"]))
        rivals = an[an["brand"] != c] if len(an) else an
        if len(rivals):
            ep = rivals.iloc[0]
            self.publish(Finding(
                id="CON-05", agent=self.name, area="consumer", title=f"Competitor crisis: {ep['brand']}",
                statement=(f"{ep['brand']} suffered a crisis over {ep['aspect_label'].lower()}: complaints peaked at "
                           f"{ep['peak_rate']:.1f} per 100 reviews {_period(ep)} (baseline {ep['baseline_rate']:.1f}) - an "
                           f"opening to win over its customers."),
                metrics=dict(brand=ep["brand"], aspect=ep["aspect_label"], peak_rate=ep["peak_rate"],
                             baseline_rate=ep["baseline_rate"], start=f"{ep['start']:%Y-%m}", end=f"{ep['end']:%Y-%m}"),
                evidence=["product_reviews.csv (anomaly detection)"], impact=3, confidence=0.75, swot="O",
                tags=["competitor", "anomaly"]))

        tr = t.get("aspect_trend")
        if tr is not None and len(tr):
            price = tr[(tr["brand"] == c) & (tr["aspect"] == "harga")]
            if len(price) and price.iloc[0]["change"] < -0.1:
                p = price.iloc[0]
                self.publish(Finding(
                    id="CON-06", agent=self.name, area="consumer", title="Value-for-money perception is slipping",
                    statement=(f"Net sentiment on {c}'s price/value fell from {p['net_p12']:+.2f} to {p['net_l12']:+.2f} "
                               f"over the last 12 months - consumers increasingly mention price increases."),
                    metrics=dict(aspect=ASPECT_LABELS["harga"], net_prior=round(p["net_p12"], 3),
                                 net_recent=round(p["net_l12"], 3), change=round(p["change"], 3)),
                    evidence=["product_reviews.csv (aspect-based sentiment)"], impact=4, confidence=0.8, swot="W",
                    tags=["price", "pain point"]))

        fit = t.get("skin_type_fit")
        if fit is not None and len(fit):
            s = fit[fit["skin"] == "sensitive"].set_index("product_type")
            if {"fragranced", "fragrance-free"} <= set(s.index):
                fr, ff = s.loc["fragranced"], s.loc["fragrance-free"]
                ratio = fr["reaction_complaint_rate"] / max(ff["reaction_complaint_rate"], 1e-6)
                self.publish(Finding(
                    id="CON-07", agent=self.name, area="consumer", title="Sensitive skin needs fragrance-free",
                    statement=(f"Sensitive-skin reviewers rate fragranced products {fr['avg_rating']:.2f} stars versus "
                               f"{ff['avg_rating']:.2f} for fragrance-free ones, and report skin reactions {ratio:.1f}x as often "
                               f"({pct(fr['reaction_complaint_rate'], sign=False)} vs {pct(ff['reaction_complaint_rate'], sign=False)} of reviews)."),
                    metrics=dict(rating_fragranced=round(fr["avg_rating"], 2), rating_fragrance_free=round(ff["avg_rating"], 2),
                                 reaction_rate_fragranced=round(fr["reaction_complaint_rate"], 4),
                                 reaction_rate_fragrance_free=round(ff["reaction_complaint_rate"], 4), ratio=round(ratio, 2)),
                    evidence=["product_reviews.csv", "product_catalog.csv"], impact=4, confidence=0.8, swot="O",
                    tags=["concept", "sensitive skin"]))

        if "nps" in t and "social_sentiment" in t:
            nps = t["nps"][t["nps"]["brand"] != "Other local brand"].set_index("brand")
            soc = t["social_sentiment"].set_index("brand")
            if c in nps.index and c in soc.index:
                rank = int((nps["nps"] > nps.loc[c, "nps"]).sum() + 1)
                leader = nps["nps"].idxmax()
                self.publish(Finding(
                    id="CON-08", agent=self.name, area="consumer", title="Loyalty and social sentiment",
                    statement=(f"{c}'s NPS is {nps.loc[c, 'nps']:+.1f} (#{rank} of {len(nps)}; leader {leader} {nps.loc[leader, 'nps']:+.1f}) "
                               f"and its social net sentiment, scored by the deep-learning model on unlabeled posts, is "
                               f"{soc.loc[c, 'nss']:+.2f} versus {soc['nss'].max():+.2f} for {soc['nss'].idxmax()}."),
                    metrics=dict(nps=float(nps.loc[c, "nps"]), nps_rank=rank, nps_leader=leader,
                                 nps_leader_value=float(nps.loc[leader, "nps"]), social_nss=round(float(soc.loc[c, "nss"]), 3),
                                 social_best=soc["nss"].idxmax(), social_best_nss=round(float(soc["nss"].max()), 3)),
                    evidence=["consumer_survey.csv", "social_mentions.csv"], impact=3, confidence=0.7,
                    swot="S" if rank <= 3 else "W", tags=["loyalty", "social"]))

        tp = t.get("complaint_topics")
        if tp is not None and len(tp):
            top = tp.head(3)
            self.publish(Finding(
                id="CON-09", agent=self.name, area="consumer", title=f"Complaint themes in {c}'s negative reviews",
                statement=(f"Topic modelling of {c}'s 1-2 star reviews surfaces these themes: "
                           + "; ".join(f"{r.label.lower()} ({pct(r.share, 0, sign=False)} of complaints: {', '.join(r.top_terms.split(', ')[:4])})"
                                       for r in top.itertuples()) + "."),
                metrics={**{f"topic_{i + 1}": r.label for i, r in enumerate(top.itertuples())},
                         **{f"topic_{i + 1}_share": r.share for i, r in enumerate(top.itertuples())}},
                evidence=["product_reviews.csv (NMF topic model)"], impact=3, confidence=0.7, swot="W", tags=["pain point"]))
