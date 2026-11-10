"""Customer segmentation: standardised attitudinal + behavioural features, K-Means with the number
of segments chosen by silhouette score, PCA for visualisation and data-driven persona naming."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

IMPORTANCE = ["imp_price", "imp_halal", "imp_ingredients", "imp_brand_reputation", "imp_packaging",
              "imp_reviews_influencers", "imp_local_brand", "imp_sustainability", "imp_fragrance_free", "imp_fast_results"]
BEHAVIOUR = ["age", "routine_steps", "social_media_hours_per_day", "influencer_trust", "purchase_freq_per_month", "log_spend"]
FEATURES = IMPORTANCE + BEHAVIOUR
LABELS = {
    "imp_price": "Price", "imp_halal": "Halal certification", "imp_ingredients": "Ingredients / efficacy",
    "imp_brand_reputation": "Brand reputation", "imp_packaging": "Packaging", "imp_reviews_influencers": "Reviews & influencers",
    "imp_local_brand": "Local brand pride", "imp_sustainability": "Sustainability", "imp_fragrance_free": "Fragrance-free",
    "imp_fast_results": "Fast results", "age": "Age", "routine_steps": "Routine steps",
    "social_media_hours_per_day": "Social media hours", "influencer_trust": "Influencer trust",
    "purchase_freq_per_month": "Purchase frequency", "log_spend": "Skincare spend (log)",
}
ADJECTIVE = {
    "imp_price": "Price-Driven", "imp_halal": "Halal-First", "imp_ingredients": "Ingredient-Savvy",
    "imp_brand_reputation": "Prestige-Seeking", "imp_packaging": "Premium-Minded", "imp_reviews_influencers": "Influencer-Led",
    "imp_local_brand": "Local-Proud", "imp_sustainability": "Eco-Conscious", "imp_fragrance_free": "Sensitive-Skin",
    "imp_fast_results": "Results-Hungry",
}


def feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    X = df[FEATURES[:-1]].astype(float).copy()
    X["log_spend"] = np.log(df["monthly_skincare_spend_idr"].clip(lower=10000))
    scaler = StandardScaler().fit(X)
    return scaler.transform(X), scaler


def select_k(X: np.ndarray, k_range=range(3, 9), seed: int = 42) -> tuple[int, pd.DataFrame]:
    rows = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
        rows.append(dict(k=k, silhouette=round(silhouette_score(X, km.labels_), 4),
                         calinski_harabasz=round(calinski_harabasz_score(X, km.labels_), 1),
                         davies_bouldin=round(davies_bouldin_score(X, km.labels_), 4), inertia=round(km.inertia_, 1)))
    table = pd.DataFrame(rows)
    return int(table.loc[table["silhouette"].idxmax(), "k"]), table


def fit_segments(X: np.ndarray, k: int, seed: int = 42) -> tuple[np.ndarray, KMeans]:
    km = KMeans(n_clusters=k, n_init=20, random_state=seed).fit(X)
    order = np.argsort(-np.bincount(km.labels_))  # segment 1 = largest
    remap = {old: new for new, old in enumerate(order)}
    return np.array([remap[l] + 1 for l in km.labels_]), km


def pca_coords(X: np.ndarray, seed: int = 42) -> tuple[np.ndarray, list[float]]:
    pca = PCA(n_components=2, random_state=seed).fit(X)
    return pca.transform(X), [round(v, 4) for v in pca.explained_variance_ratio_]


def _top(series: pd.Series) -> tuple[str, float]:
    vc = series.dropna().value_counts(normalize=True)
    return (str(vc.index[0]), round(float(vc.iloc[0]), 3)) if len(vc) else ("n/a", 0.0)


def nps(scores: pd.Series) -> float:
    s = scores.dropna()
    return round(100 * ((s >= 9).mean() - (s <= 6).mean()), 1) if len(s) else float("nan")


def profile_segments(df: pd.DataFrame, labels: np.ndarray, client: str) -> pd.DataFrame:
    d = df.assign(segment=labels)
    rows = []
    for seg, g in d.groupby("segment"):
        occ, occ_p = _top(g["occupation"])
        skin, skin_p = _top(g["skin_type"])
        concern, concern_p = _top(g["primary_concern"])
        channel, channel_p = _top(g["preferred_channel"])
        platform, platform_p = _top(g["primary_platform"])
        brand, brand_p = _top(g["main_brand"])
        row = dict(
            segment=int(seg), size=len(g), share=round(len(g) / len(d), 4), age_mean=round(g["age"].mean(), 1),
            female_pct=round((g["gender"] == "Female").mean(), 3), top_occupation=occ, top_occupation_pct=occ_p,
            housewife_pct=round((g["occupation"] == "Housewife").mean(), 3),
            student_pct=round((g["occupation"] == "Student").mean(), 3),
            income_median_idr=float(g["monthly_income_idr"].median()),
            spend_mean_idr=round(g["monthly_skincare_spend_idr"].mean(), -3),
            routine_steps=round(g["routine_steps"].mean(), 1), social_hours=round(g["social_media_hours_per_day"].mean(), 1),
            influencer_trust=round(g["influencer_trust"].mean(), 2),
            top_skin_type=skin, top_skin_type_pct=skin_p, top_concern=concern, top_concern_pct=concern_p,
            top_channel=channel, top_channel_pct=channel_p, top_platform=platform, top_platform_pct=platform_p,
            top_brand=brand, top_brand_pct=brand_p, client_user_pct=round((g["main_brand"] == client).mean(), 3),
            client_aware_pct=round(g["aware_client"].mean(), 3) if "aware_client" in g else np.nan,
            nps_main_brand=nps(g["nps_main_brand"]),
            concept_t2b=round((g["concept_purchase_intent"] >= 4).mean(), 3),
            concept_mean=round(g["concept_purchase_intent"].mean(), 2),
            vw_cheap_median=float(g["vw_cheap_idr"].median()), vw_expensive_median=float(g["vw_expensive_idr"].median()),
        )
        row.update({c: round(g[c].mean(), 2) for c in IMPORTANCE})
        rows.append(row)
    return pd.DataFrame(rows)


def name_segments(profiles: pd.DataFrame, df: pd.DataFrame) -> dict[int, str]:
    mu, sd = df[IMPORTANCE].mean(), df[IMPORTANCE].std().replace(0, 1)
    names: dict[int, str] = {}
    for _, p in profiles.iterrows():
        z = ((p[IMPORTANCE] - mu) / sd).astype(float).sort_values(ascending=False)
        age = p["age_mean"]
        if age < 23.5:
            noun = "Gen Z Students" if p["student_pct"] > 0.4 else "Gen Z Shoppers"
        elif age < 32:
            noun = "Young Professionals"
        elif age < 39:
            noun = "Family Shoppers" if p["housewife_pct"] > 0.2 else "Established Adults"
        else:
            noun = "Mature Professionals"
        for feat in z.index:
            name = f"{ADJECTIVE[feat]} {noun}"
            if name not in names.values():
                names[int(p["segment"])] = name
                break
    return names


def describe(p: pd.Series) -> str:
    return (f"Avg age {p['age_mean']:.0f}, {p['female_pct']:.0%} female, mostly {p['top_occupation'].lower()}s; "
            f"spends ~Rp{p['spend_mean_idr'] / 1000:,.0f}k/month on skincare; main concern: {p['top_concern'].lower()} "
            f"({p['top_concern_pct']:.0%}); shops on {p['top_channel']} ({p['top_channel_pct']:.0%}); "
            f"top brand {p['top_brand']} ({p['top_brand_pct']:.0%}).")


def distinctive_drivers(profiles: pd.DataFrame, df: pd.DataFrame, n: int = 3) -> dict[int, list[str]]:
    mu, sd = df[IMPORTANCE].mean(), df[IMPORTANCE].std().replace(0, 1)
    out = {}
    for _, p in profiles.iterrows():
        z = ((p[IMPORTANCE] - mu) / sd).astype(float).sort_values(ascending=False)
        out[int(p["segment"])] = [LABELS[f] for f in z.index[:n]]
    return out
