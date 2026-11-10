"""Plotly chart library shared by the HTML report and the Streamlit dashboard.

Design rules (validated palette, light + dark): brand colours follow the entity (client = slot 1),
"highlight one, grey the rest" when the story is the client, one series -> one colour, diverging
blue/red with a grey midpoint for polarity, one y-axis per chart, thin marks and hairline grids.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
TOKENS = {
    "light": dict(surface="#fcfcfb", text="#0b0b0b", text2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  neutral="#c3c2b7", mid="#f0efec", band="rgba(42,120,214,0.14)",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
                  blue=["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"], red="#e34948",
                  good="#0ca30c", critical="#d03b3b"),
    "dark": dict(surface="#1a1a19", text="#f0efec", text2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
                 neutral="#5c5b57", mid="#383835", band="rgba(57,135,229,0.22)",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
                 blue=["#104281", "#184f95", "#1c5cab", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"], red="#e66767",
                 good="#0ca30c", critical="#d03b3b"),
}


def tk(mode: str) -> dict:
    return TOKENS["dark" if mode == "dark" else "light"]


def base_layout(fig: go.Figure, mode: str = "light", title: str | None = None, height: int = 380,
                legend: bool = True, yfmt: str | None = None, xfmt: str | None = None) -> go.Figure:
    t = tk(mode)
    top = 44 if title else 14  # legends sit below the plot, where Plotly grows the margin to fit any wrapping
    fig.update_layout(
        template="none", height=height, margin=dict(l=12, r=16, t=top, b=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12.5, color=t["text2"]),
        title=dict(text=title, x=0, xanchor="left", y=1, yref="container", yanchor="top", pad=dict(t=10, l=4),
                   font=dict(size=15, color=t["text"])) if title else None,
        showlegend=legend, legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0,
                                       font=dict(color=t["text2"]), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font=dict(family=FONT, size=12), bgcolor=t["surface"], bordercolor=t["axis"],
                        font_color=t["text"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=t["axis"], tickcolor=t["axis"], ticks="outside", ticklen=4,
                     zeroline=False, tickfont=dict(color=t["muted"]), title_font=dict(color=t["text2"]),
                     automargin=True)
    fig.update_yaxes(gridcolor=t["grid"], gridwidth=1, linecolor=t["axis"], zeroline=False,
                     tickfont=dict(color=t["muted"]), title_font=dict(color=t["text2"]), automargin=True)
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    if xfmt:
        fig.update_xaxes(tickformat=xfmt)
    return fig


def brand_colors(brands, client: str | None, mode: str = "light") -> dict:
    """Client = slot 1; competitors take slots 2.. in alphabetical order (stable across charts)."""
    s = tk(mode)["series"]
    others = sorted(b for b in set(brands) if b != client)
    out = {client: s[0]} if client else {}
    out.update({b: s[(i + 1) % len(s)] for i, b in enumerate(others)})
    return out


def _empty(msg: str, mode: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=tk(mode)["muted"]))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return base_layout(fig, mode, height=200, legend=False)


def _bn(x):
    return f"Rp {x / 1e9:,.0f} bn"


def _dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s)


# ======================================================================== market
def market_size(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    cats = [c for c in ["Facial Wash", "Toner", "Serum", "Moisturizer", "Sunscreen"] if c in df]
    fig = go.Figure()
    for i, c in enumerate(cats):
        fig.add_bar(x=df["year"].astype(str) + np.where(df["status"] == "estimate", "E", ""), y=df[c] / 1000, name=c,
                    marker=dict(color=t["series"][i], line=dict(color=t["surface"], width=1.5)),
                    hovertemplate=f"{c}: Rp %{{y:.1f}} tn<extra></extra>")
    totals = df["total_idr_bn"] / 1000
    fig.add_scatter(x=df["year"].astype(str) + np.where(df["status"] == "estimate", "E", ""), y=totals, mode="text",
                    text=[f"{v:.1f}" for v in totals], textposition="top center", showlegend=False,
                    textfont=dict(color=t["text2"], size=11), hoverinfo="skip")
    fig.update_layout(barmode="stack", bargap=0.35)
    fig = base_layout(fig, mode, "Facial-skincare market size (Rp trillion, E = estimate)", height=400)
    fig.update_yaxes(title=None, range=[0, totals.max() * 1.15])
    fig.update_xaxes(type="category")
    return fig


def growth_bars(df: pd.DataFrame, label: str, title: str, mode="light", highlight: str | None = None) -> go.Figure:
    t = tk(mode)
    d = df.sort_values("growth")
    colors = [t["series"][0] if (highlight is None or v == highlight) else t["neutral"] for v in d[label]]
    fig = go.Figure(go.Bar(x=d["growth"], y=d[label], orientation="h", marker=dict(color=colors, cornerradius=4),
                           text=[f"{v * 100:+.1f}%" for v in d["growth"]], textposition="outside",
                           textfont=dict(color=t["text2"]), cliponaxis=False,
                           hovertemplate="%{y}: %{x:+.1%}<extra></extra>"))
    fig = base_layout(fig, mode, title, height=max(260, 46 * len(d) + 90), legend=False, xfmt="+.0%")
    fig.update_xaxes(range=[min(0, d["growth"].min() * 1.3), d["growth"].max() * 1.3])
    return fig


def channel_mix(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    chans = [c for c in ["Shopee", "TikTok Shop", "Offline Retail", "Tokopedia", "Lazada"] if c in df] + \
            [c for c in df.columns if c not in ("year", "Shopee", "TikTok Shop", "Offline Retail", "Tokopedia", "Lazada")]
    fig = go.Figure()
    for i, c in enumerate(chans):
        fig.add_bar(x=df["year"].astype(str), y=df[c], name=c, marker=dict(color=t["series"][i], line=dict(color=t["surface"], width=1.5)),
                    hovertemplate=f"{c}: %{{y:.1%}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35)
    fig = base_layout(fig, mode, "Channel mix of tracked sales (share of revenue)", height=380, yfmt=".0%")
    fig.update_xaxes(type="category")
    return fig


def topic_trends(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.dropna(subset=["sov_change"]).sort_values("sov_change")
    colors = [t["series"][0] if v >= 0 else t["red"] for v in d["sov_change"]]
    fig = go.Figure(go.Bar(x=d["sov_change"], y=d["topic"], orientation="h", marker=dict(color=colors, cornerradius=4),
                           text=[f"{v * 100:+.0f}%" for v in d["sov_change"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]),
                           customdata=np.c_[d["sov_p12"], d["sov_l12"], d["status"]],
                           hovertemplate="%{y}: %{x:+.0%} share of voice<br>prior %{customdata[0]:.1%} -> recent %{customdata[1]:.1%}<br>%{customdata[2]}<extra></extra>"))
    fig = base_layout(fig, mode, "Social conversation momentum (change in topic share of voice, last 12m)",
                      height=max(320, 30 * len(d) + 90), legend=False, xfmt="+.0%")
    fig.update_xaxes(range=[d["sov_change"].min() * 1.35, d["sov_change"].max() * 1.25])
    return fig


def seasonality(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    d = df.sort_values("month_of_year")
    fig = go.Figure(go.Bar(x=[months[m - 1] for m in d["month_of_year"]], y=d["seasonal_index"],
                           marker=dict(color=t["series"][0], cornerradius=4),
                           hovertemplate="%{x}: %{y:.2f}x trend<extra></extra>"))
    fig.add_hline(y=1, line=dict(color=t["axis"], width=1))
    fig = base_layout(fig, mode, "Seasonal index (monthly revenue / 12-month trend)", height=330, legend=False)
    fig.update_yaxes(range=[min(0.8, d["seasonal_index"].min() - 0.03), d["seasonal_index"].max() + 0.05])
    return fig


def monthly_market(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.assign(month=_dt(df["month"]))
    fig = go.Figure(go.Scatter(x=d["month"], y=d["revenue_idr"] / 1e9, mode="lines", line=dict(color=t["series"][0], width=2),
                               hovertemplate="%{x|%b %Y}: Rp %{y:,.0f} bn<extra></extra>"))
    fig = base_layout(fig, mode, "Tracked-panel revenue per month (Rp bn)", height=330, legend=False)
    fig.update_layout(hovermode="x unified")
    return fig


# ======================================================================== competition
def brand_share(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("share_l12")
    colors = [t["series"][0] if b == client else t["neutral"] for b in d["brand"]]
    fig = go.Figure(go.Bar(x=d["share_l12"], y=d["brand"], orientation="h", marker=dict(color=colors, cornerradius=4),
                           text=[f"{s * 100:.1f}%  ({c * 100:+.1f} pp)" for s, c in zip(d["share_l12"], d["share_change_pp"], strict=True)],
                           textposition="outside", cliponaxis=False, textfont=dict(color=t["text2"]),
                           customdata=np.c_[d["revenue_l12"] / 1e9, d["growth"]],
                           hovertemplate="%{y}<br>share %{x:.1%}<br>revenue Rp %{customdata[0]:,.0f} bn<br>growth %{customdata[1]:+.1%}<extra></extra>"))
    fig = base_layout(fig, mode, "Value share of tracked panel, last 12 months (change vs prior year)", height=340,
                      legend=False, xfmt=".0%")
    fig.update_xaxes(range=[0, d["share_l12"].max() * 1.45])
    return fig


def share_trend(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    d = df.assign(month=_dt(df["month"]))
    colors = brand_colors(d["brand"].unique(), client, mode)
    fig = go.Figure()
    order = [client] + sorted(b for b in d["brand"].unique() if b != client)
    for b in order:
        g = d[d["brand"] == b].sort_values("month")
        fig.add_scatter(x=g["month"], y=g["share"].rolling(3, min_periods=1).mean(), mode="lines", name=b,
                        line=dict(color=colors[b], width=3 if b == client else 1.8),
                        hovertemplate=f"{b}: %{{y:.1%}}<extra></extra>")
    fig = base_layout(fig, mode, "Monthly value share by brand (3-month rolling)", height=380, yfmt=".0%")
    fig.update_layout(hovermode="x unified")
    return fig


def channel_index(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("index")
    colors = [t["series"][0] if v >= 1 else t["red"] for v in d["index"]]
    label = d.columns[0]
    fig = go.Figure(go.Bar(x=d["index"], y=d[label], orientation="h", base=0, marker=dict(color=colors, cornerradius=4),
                           text=[f"{v:.2f}x" for v in d["index"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]),
                           customdata=np.c_[d["client_mix"], d["market_mix"], d["market_growth"]],
                           hovertemplate="%{y}<br>index %{x:.2f}<br>" + client + " mix %{customdata[0]:.1%} vs market %{customdata[1]:.1%}"
                                         "<br>segment growth %{customdata[2]:+.1%}<extra></extra>"))
    fig.add_vline(x=1, line=dict(color=t["axis"], width=1))
    fig = base_layout(fig, mode, f"{client} over/under-index by {label} (1.0 = market mix)",
                      height=max(260, 44 * len(d) + 90), legend=False)
    fig.update_xaxes(range=[0, max(1.6, d["index"].max() * 1.25)])
    return fig


def positioning(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    if "avg_rating" not in df:
        return _empty("No rating data", mode)
    d = df.copy()
    size = 18 + 42 * np.sqrt(d["revenue_l12"] / d["revenue_l12"].max())
    fig = go.Figure()
    for is_client in (False, True):
        g = d[(d["brand"] == client) == is_client]
        fig.add_scatter(x=g["price_index"], y=g["avg_rating"], mode="markers+text", text=g["brand"],
                        textposition="top center", textfont=dict(color=t["text"] if is_client else t["text2"]),
                        marker=dict(size=size[g.index], color=t["series"][0] if is_client else t["neutral"],
                                    opacity=0.9 if is_client else 0.75, line=dict(color=t["surface"], width=2)),
                        customdata=np.c_[g["revenue_l12"] / 1e9, g.get("net_rating_sentiment", g["avg_rating"] * 0)],
                        hovertemplate="%{text}<br>price index %{x:.2f}x<br>rating %{y:.2f}<br>revenue Rp %{customdata[0]:,.0f} bn<extra></extra>",
                        showlegend=False)
    fig.add_vline(x=1, line=dict(color=t["axis"], width=1))
    fig = base_layout(fig, mode, "Price-value map (bubble = last-12-month revenue)", height=420, legend=False)
    fig.update_xaxes(title="Price index vs category average", range=[d["price_index"].min() - 0.25, d["price_index"].max() + 0.3])
    fig.update_yaxes(title="Average star rating", range=[d["avg_rating"].min() - 0.15, d["avg_rating"].max() + 0.15])
    return fig


def threats(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("threat_index")
    colors_map = brand_colors(list(d["brand"]) + [client], client, mode)
    top = d["brand"].iloc[-1]
    colors = [colors_map[b] if b == top else t["neutral"] for b in d["brand"]]
    fig = go.Figure(go.Bar(x=d["threat_index"], y=d["brand"], orientation="h", marker=dict(color=colors, cornerradius=4),
                           text=[f"{v:.2f}" for v in d["threat_index"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]),
                           customdata=np.c_[d["growth"], d["share_l12"], d["category_overlap"], d["social_sov"]],
                           hovertemplate="%{y}<br>threat index %{x:.2f}<br>growth %{customdata[0]:+.1%}, share %{customdata[1]:.1%}"
                                         "<br>category overlap %{customdata[2]:.2f}, social SoV %{customdata[3]:.1%}<extra></extra>"))
    fig = base_layout(fig, mode, f"Competitive threat index to {client} (0-1)", height=320, legend=False)
    fig.update_xaxes(range=[0, 1.15])
    return fig


def white_space(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("opportunity_score")
    top = d["space"].iloc[-1]
    fig = go.Figure(go.Bar(x=d["opportunity_score"], y=d["space"], orientation="h",
                           marker=dict(color=[t["series"][0] if s == top else t["neutral"] for s in d["space"]], cornerradius=4),
                           text=[f"{v:.0f}" for v in d["opportunity_score"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]),
                           customdata=np.c_[d["supply_skus"], d["consumer_need_share"], d["trend_momentum"]],
                           hovertemplate="%{y}<br>score %{x:.0f}/100<br>SKUs on market: %{customdata[0]}<br>"
                                         "consumer need %{customdata[1]:.0%}, trend %{customdata[2]:+.0%}<extra></extra>"))
    fig = base_layout(fig, mode, "White-space opportunity score (need x momentum / supply)", height=330, legend=False)
    fig.update_xaxes(range=[0, 118])
    return fig


# ======================================================================== consumer
def sentiment_by_brand(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("text_nss")
    fig = go.Figure()
    for col, color, name in (("negative", t["red"], "Negative"), ("neutral", t["neutral"], "Neutral"),
                             ("positive", t["series"][0], "Positive")):
        fig.add_bar(x=d[col], y=d["brand"], orientation="h", name=name,
                    marker=dict(color=color, line=dict(color=t["surface"], width=1.5)),
                    hovertemplate=f"%{{y}} {name.lower()}: %{{x:.1%}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.35)
    fig = base_layout(fig, mode, "Review text sentiment by brand (deep-learning model, last 12 months)", height=360, xfmt=".0%")
    for _, r in d.iterrows():
        fig.add_annotation(x=1.0, y=r["brand"], text=f"NSS {r['text_nss']:+.2f}", showarrow=False, xanchor="left",
                           xshift=6, font=dict(color=t["text2"], size=11))
    fig.update_layout(margin=dict(r=80))
    return fig


def aspect_heatmap(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    piv = df.pivot_table(index="brand", columns="aspect_label", values="net_sentiment")
    order = [client] + sorted(b for b in piv.index if b != client)
    piv = piv.reindex([b for b in order if b in piv.index])
    cols = piv.mean().sort_values().index
    piv = piv[cols]
    scale = [[0, t["red"]], [0.5, t["mid"]], [1, t["series"][0]]]
    fig = go.Figure(go.Heatmap(z=piv.values, x=list(piv.columns), y=list(piv.index), zmin=-1, zmax=1, colorscale=scale,
                               text=np.vectorize(lambda v: "" if np.isnan(v) else f"{v:+.2f}")(piv.values),
                               texttemplate="%{text}", textfont=dict(size=11, color=t["text"]),
                               xgap=2, ygap=2, colorbar=dict(title="net", thickness=10, outlinewidth=0,
                                                             tickfont=dict(color=t["muted"])),
                               hovertemplate="%{y} - %{x}: net sentiment %{z:+.2f}<extra></extra>"))
    fig = base_layout(fig, mode, "Aspect-based net sentiment (positive - negative mentions, last 12 months)",
                      height=360, legend=False)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    return fig


def client_aspect_trend(df: pd.DataFrame, anomalies: pd.DataFrame | None, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.assign(month=_dt(df["month"]))
    top = d.groupby("aspect_label")["negative"].sum().sort_values(ascending=False).head(4).index
    fig = go.Figure()
    for i, a in enumerate(top):
        g = d[d["aspect_label"] == a].sort_values("month")
        fig.add_scatter(x=g["month"], y=g["negative_per_100_reviews"], mode="lines", name=a,
                        line=dict(color=t["series"][i], width=2), hovertemplate=f"{a}: %{{y:.1f}} per 100 reviews<extra></extra>")
    if anomalies is not None and len(anomalies):
        for ep in anomalies[anomalies["brand"] == client].head(3).itertuples():
            fig.add_vrect(x0=pd.Timestamp(ep.start) - pd.Timedelta(days=14), x1=pd.Timestamp(ep.end) + pd.Timedelta(days=14),
                          fillcolor=t["band"], line_width=0, layer="below",
                          annotation_text=f"{ep.aspect_label} spike", annotation_position="top left",
                          annotation_font=dict(color=t["text2"], size=11))
    fig = base_layout(fig, mode, f"{client}: negative aspect mentions per 100 reviews", height=380)
    fig.update_layout(hovermode="x unified")
    return fig


def social_sentiment(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("nss")
    fig = go.Figure(go.Bar(x=d["nss"], y=d["brand"], orientation="h",
                           marker=dict(color=[t["series"][0] if b == client else t["neutral"] for b in d["brand"]], cornerradius=4),
                           text=[f"{v:+.2f}" for v in d["nss"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]), customdata=d["posts"],
                           hovertemplate="%{y}: net sentiment %{x:+.2f} (%{customdata:,} posts)<extra></extra>"))
    fig = base_layout(fig, mode, "Social net sentiment, last 12 months (DL model on unlabeled posts)", height=320, legend=False)
    fig.update_xaxes(range=[min(0, d["nss"].min() * 1.3), d["nss"].max() * 1.3])
    return fig


def model_comparison(card: dict, mode="light") -> go.Figure:
    t = tk(mode)
    names = {"linear": "TF-IDF + LogReg", "bigru": "BiGRU + attention", "ensemble": "Ensemble"}
    tm = card["test_metrics"]
    keys = ["linear", "bigru", "ensemble"]
    fig = go.Figure()
    for i, metric in enumerate(["macro_f1", "accuracy"]):
        fig.add_bar(x=[names[k] for k in keys], y=[tm[k][metric] for k in keys], name=metric.replace("_", "-"),
                    marker=dict(color=t["series"][i], cornerradius=4), text=[f"{tm[k][metric]:.3f}" for k in keys],
                    textposition="outside", textfont=dict(color=t["text2"]), cliponaxis=False,
                    hovertemplate="%{x} " + metric + ": %{y:.3f}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    fig = base_layout(fig, mode, f"Model comparison, held-out test set (n={card['n_test']:,})", height=340)
    fig.update_yaxes(range=[0.5, 1.0])
    return fig


def confusion(card: dict, mode="light") -> go.Figure:
    t = tk(mode)
    cm = np.array(card["confusion_matrix"], dtype=float)
    norm = cm / cm.sum(axis=1, keepdims=True)
    labels = card["labels"]
    light = t["blue"][:5] if mode != "dark" else t["blue"][2:]
    fig = go.Figure(go.Heatmap(z=norm, x=labels, y=labels, zmin=0, zmax=1,
                               colorscale=[[i / (len(light) - 1), c] for i, c in enumerate(light)], xgap=2, ygap=2,
                               text=[[f"{norm[i, j]:.0%}<br>({int(cm[i, j]):,})" for j in range(3)] for i in range(3)],
                               texttemplate="%{text}", textfont=dict(size=12),
                               colorbar=dict(thickness=10, outlinewidth=0, tickformat=".0%", tickfont=dict(color=t["muted"])),
                               hovertemplate="true %{y} -> predicted %{x}: %{z:.1%}<extra></extra>"))
    fig = base_layout(fig, mode, "Confusion matrix (row-normalised, test set)", height=340, legend=False)
    fig.update_xaxes(title="Predicted")
    fig.update_yaxes(title="True (from star rating)", autorange="reversed", gridcolor="rgba(0,0,0,0)")
    return fig


def training_curve(card: dict, mode="light") -> go.Figure:
    t = tk(mode)
    h = pd.DataFrame(card.get("bigru_history", []))
    if h.empty:
        return _empty("No training history", mode)
    fig = go.Figure()
    fig.add_scatter(x=h["epoch"], y=h["val_macro_f1"], mode="lines+markers", name="validation macro-F1",
                    line=dict(color=t["series"][0], width=2), marker=dict(size=8, line=dict(color=t["surface"], width=2)))
    fig.add_scatter(x=h["epoch"], y=h["val_accuracy"], mode="lines+markers", name="validation accuracy",
                    line=dict(color=t["series"][1], width=2), marker=dict(size=8, line=dict(color=t["surface"], width=2)))
    fig = base_layout(fig, mode, "BiGRU training: validation scores by epoch", height=320)
    fig.update_xaxes(dtick=1, title="Epoch")
    fig.update_layout(legend=dict(y=-0.24))
    fig.update_layout(hovermode="x unified")
    return fig


# ======================================================================== segmentation
def segment_map(df: pd.DataFrame, profiles: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    segs = profiles.sort_values("segment")
    n = len(segs)
    fig = make_subplots(rows=1, cols=n, shared_yaxes=True, horizontal_spacing=0.02,
                        subplot_titles=[f"{r.name}<br>{r.share:.0%}" for r in segs.itertuples()])
    for i, r in enumerate(segs.itertuples(), 1):
        rest = df[df["segment"] != r.segment]
        me = df[df["segment"] == r.segment]
        fig.add_scatter(x=rest["pc1"], y=rest["pc2"], mode="markers", marker=dict(size=4, color=t["neutral"], opacity=0.35),
                        hoverinfo="skip", showlegend=False, row=1, col=i)
        fig.add_scatter(x=me["pc1"], y=me["pc2"], mode="markers", marker=dict(size=5, color=t["series"][0], opacity=0.75),
                        name=r.name, showlegend=False, row=1, col=i,
                        hovertemplate=f"{r.name}<br>PC1 %{{x:.2f}}, PC2 %{{y:.2f}}<extra></extra>")
    fig = base_layout(fig, mode, "Segments in PCA space (each panel highlights one segment)", height=360, legend=False)
    fig.update_layout(margin=dict(t=92))
    fig.update_annotations(font=dict(size=11, color=t["text2"]))
    fig.update_xaxes(showticklabels=False, ticks="")
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return fig


def segment_importance(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    piv = df.pivot_table(index="name", columns="attribute", values="importance")
    light = t["blue"][:5] if mode != "dark" else t["blue"][2:]
    fig = go.Figure(go.Heatmap(z=piv.values, x=list(piv.columns), y=list(piv.index), zmin=1, zmax=5,
                               colorscale=[[i / (len(light) - 1), c] for i, c in enumerate(light)], xgap=2, ygap=2,
                               text=np.round(piv.values, 1), texttemplate="%{text}", textfont=dict(size=11),
                               colorbar=dict(title="1-5", thickness=10, outlinewidth=0, tickfont=dict(color=t["muted"])),
                               hovertemplate="%{y}<br>%{x}: %{z:.2f} / 5<extra></extra>"))
    fig = base_layout(fig, mode, "What matters to each segment (mean importance, 1-5)", height=360, legend=False)
    fig.update_xaxes(tickangle=-30)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    return fig


def concept(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("concept_t2b")
    top = df.iloc[0]["name"]
    fig = go.Figure(go.Bar(x=d["concept_t2b"], y=d["name"], orientation="h",
                           marker=dict(color=[t["series"][0] if n == top else t["neutral"] for n in d["name"]], cornerradius=4),
                           text=[f"{v:.0%}" for v in d["concept_t2b"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]), customdata=np.c_[d["share"], d["attractiveness"]],
                           hovertemplate="%{y}<br>top-2-box intent %{x:.0%}<br>segment size %{customdata[0]:.0%}<br>"
                                         "attractiveness %{customdata[1]:.2f}<extra></extra>"))
    fig = base_layout(fig, mode, "Concept purchase intent by segment (top-2-box; highlighted = primary target)",
                      height=320, legend=False, xfmt=".0%")
    fig.update_xaxes(range=[0, 1.12])
    return fig


def van_westendorp(curves: pd.DataFrame, points: pd.DataFrame | None, mode="light") -> go.Figure:
    t = tk(mode)
    fig = go.Figure()
    for i, (col, name) in enumerate([("too_cheap", "Too cheap"), ("cheap", "Cheap / bargain"),
                                     ("expensive", "Expensive"), ("too_expensive", "Too expensive")]):
        fig.add_scatter(x=curves["price_idr"], y=curves[col], mode="lines", name=name, line=dict(color=t["series"][i], width=2),
                        hovertemplate=f"{name}: %{{y:.0%}} at Rp %{{x:,.0f}}<extra></extra>")
    if points is not None and len(points):
        p = points[points["group"] == "Target segments"]
        p = p.iloc[0] if len(p) else points.iloc[0]
        for key, label in (("pmc", "PMC"), ("opp", "OPP"), ("ipp", "IPP"), ("pme", "PME")):
            if pd.notna(p.get(key)):
                fig.add_vline(x=p[key], line=dict(color=t["axis"], width=1))
                fig.add_annotation(x=p[key], y=1.04, yref="paper", text=f"{label}<br>{p[key] / 1000:.0f}k", showarrow=False,
                                   font=dict(color=t["text2"], size=10))
    fig = base_layout(fig, mode, "Van Westendorp price sensitivity (target segments)", height=400, yfmt=".0%")
    fig.update_xaxes(title="Price (Rp)", range=[curves["price_idr"].quantile(0.02), curves["price_idr"].quantile(0.9)])
    fig.update_layout(legend=dict(y=-0.24))
    fig.update_layout(hovermode="x unified", margin=dict(t=84))
    return fig


# ======================================================================== pricing / forecast
def elasticities(df: pd.DataFrame, client: str, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("elasticity")
    fig = go.Figure(go.Bar(x=d["elasticity"], y=d["brand"], orientation="h",
                           marker=dict(color=[t["series"][0] if b == client else t["neutral"] for b in d["brand"]], cornerradius=4),
                           error_x=dict(type="data", symmetric=False, array=d["ci_high"] - d["elasticity"],
                                        arrayminus=d["elasticity"] - d["ci_low"], color=t["text2"], thickness=1.2, width=4),
                           text=[f"{v:.2f}" for v in d["elasticity"]], textposition="inside", insidetextanchor="start",
                           textfont=dict(color=["#ffffff" if b == client else t["text"] for b in d["brand"]]),
                           hovertemplate="%{y}: elasticity %{x:.2f}<extra></extra>"))
    fig.add_vline(x=-1, line=dict(color=t["axis"], width=1), annotation_text="unit elastic", annotation_position="top",
                  annotation_font=dict(color=t["muted"], size=10))
    fig = base_layout(fig, mode, "Own-price elasticity of demand by brand (95% CI)", height=340, legend=False)
    fig.update_xaxes(range=[min(d["ci_low"].min(), -1.2) * 1.25, 0])
    return fig


def price_scenarios(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    fig = go.Figure()
    for i, (col, name) in enumerate([("volume_change_pct", "Volume"), ("revenue_change_pct", "Revenue"),
                                     ("gross_profit_change_pct", "Gross profit (60% margin)")]):
        fig.add_scatter(x=df["price_change_pct"], y=df[col], mode="lines+markers", name=name,
                        line=dict(color=t["series"][i], width=2), marker=dict(size=8, line=dict(color=t["surface"], width=2)),
                        hovertemplate=f"{name}: %{{y:+.1f}}% at %{{x:+.0f}}% price<extra></extra>")
    fig.add_hline(y=0, line=dict(color=t["axis"], width=1))
    fig = base_layout(fig, mode, "What-if: change vs baseline for a list-price move (%)", height=360)
    fig.update_xaxes(title="Price change (%)", ticksuffix="%")
    fig.update_layout(legend=dict(y=-0.24))
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(hovermode="x unified")
    return fig


def outlook(df: pd.DataFrame, title: str, mode="light", value: str = "revenue") -> go.Figure:
    t = tk(mode)
    d = df.assign(month=_dt(df["month"]))
    a, f = d[d["type"] == "actual"].sort_values("month"), d[d["type"] == "forecast"].sort_values("month")
    scale = 1e9 if value == "revenue" else 1e6
    unit = "Rp bn" if value == "revenue" else "mn units"
    fig = go.Figure()
    if f"{value}_hi" in f:
        fig.add_scatter(x=pd.concat([f["month"], f["month"][::-1]]), y=pd.concat([f[f"{value}_hi"], f[f"{value}_lo"][::-1]]) / scale,
                        fill="toself", fillcolor=t["band"], line=dict(width=0), name="80% interval", hoverinfo="skip")
    fig.add_scatter(x=a["month"], y=a[value] / scale, mode="lines", name="Actual", line=dict(color=t["text2"], width=2),
                    hovertemplate=f"actual %{{y:,.1f}} {unit}<extra></extra>")
    joined = pd.concat([a.tail(1), f])
    fig.add_scatter(x=joined["month"], y=joined[value] / scale, mode="lines", name="Forecast",
                    line=dict(color=t["series"][0], width=2.5, dash="dot"),
                    hovertemplate=f"forecast %{{y:,.1f}} {unit}<extra></extra>")
    fig = base_layout(fig, mode, title, height=380)
    fig.update_yaxes(title=unit)
    fig.update_layout(hovermode="x unified")
    return fig


def backtest(df: pd.DataFrame, best: str | None, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.assign(month=_dt(df["month"]))
    names = {"gradient_boosting": "Gradient boosting", "seasonal_naive": "Seasonal naive",
             "seasonal_naive_drift": "Seasonal naive + drift", "ensemble": "GBM + drift ensemble"}
    act = d[d["model"] == d["model"].iloc[0]].sort_values("month")
    fig = go.Figure(go.Scatter(x=act["month"], y=act["market_actual"] / 1e6, mode="lines+markers", name="Actual",
                               line=dict(color=t["text2"], width=2), marker=dict(size=8)))
    for i, m in enumerate(["ensemble", "gradient_boosting", "seasonal_naive"]):
        g = d[d["model"] == m].sort_values("month")
        if len(g):
            fig.add_scatter(x=g["month"], y=g["market_forecast"] / 1e6, mode="lines", name=names[m] + (" (selected)" if m == best else ""),
                            line=dict(color=t["series"][i], width=3 if m == best else 1.6))
    fig = base_layout(fig, mode, "Backtest, last fold: market units (mn) - actual vs model forecasts", height=360)
    fig.update_layout(hovermode="x unified")
    return fig


def feature_importance(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df[df["importance"] > 0].sort_values("importance").tail(10)
    fig = go.Figure(go.Bar(x=d["importance"], y=d["label"], orientation="h", marker=dict(color=t["series"][0], cornerradius=4),
                           hovertemplate="%{y}: %{x:.4f}<extra></extra>"))
    return base_layout(fig, mode, "Forecast drivers (permutation importance)", height=360, legend=False)


def opportunities(df: pd.DataFrame, mode="light") -> go.Figure:
    t = tk(mode)
    d = df.sort_values("value_idr")
    fig = go.Figure(go.Bar(x=d["value_idr"] / 1e9, y=d["opportunity"], orientation="h", marker=dict(color=t["series"][0], cornerradius=4),
                           text=[_bn(v) for v in d["value_idr"]], textposition="outside", cliponaxis=False,
                           textfont=dict(color=t["text2"]), customdata=d["basis"],
                           hovertemplate="%{y}<br>Rp %{x:,.1f} bn<br>%{customdata}<extra></extra>"))
    fig = base_layout(fig, mode, "Indicative value at stake per opportunity (Rp bn, 12 months)", height=330, legend=False)
    fig.update_xaxes(range=[0, d["value_idr"].max() / 1e9 * 1.35])
    return fig


# ======================================================================== registry
class TableSource:
    """Uniform access to tables/JSON for a live blackboard or a saved run."""

    def __init__(self, table: Callable[[str, str], pd.DataFrame | None], obj: Callable[[str], object],
                 frame: Callable[[str], pd.DataFrame | None], client: str):
        self._table, self._obj, self._frame, self.client = table, obj, frame, client

    def t(self, group: str, name: str) -> pd.DataFrame | None:
        return self._table(group, name)

    def j(self, key: str):
        return self._obj(key)

    def df(self, key: str) -> pd.DataFrame | None:
        return self._frame(key)

    @classmethod
    def from_blackboard(cls, bb) -> "TableSource":
        def table(group, name):
            return (bb.get(f"{group}.tables") or {}).get(name)
        return cls(table, bb.get, bb.get, (bb.get("plan") or {}).get("client", ""))

    @classmethod
    def from_run(cls, run) -> "TableSource":
        return cls(lambda g, n: run.table(f"{g}.tables.{n}"), lambda k: run.json(k), run.table, run.meta.get("client", ""))


def _safe(fn):
    def wrapped(src: TableSource, mode: str = "light"):
        try:
            return fn(src, mode)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            return None
    return wrapped


CHARTS: dict[str, Callable] = {
    "market_size": _safe(lambda s, m: market_size(s.t("market", "market_size_by_year"), m)),
    "category_growth": _safe(lambda s, m: growth_bars(s.t("market", "category_growth"), "category", "Revenue growth by category, last 12 months", m)),
    "channel_mix": _safe(lambda s, m: channel_mix(s.t("market", "channel_mix"), m)),
    "region_growth": _safe(lambda s, m: growth_bars(s.t("market", "region_growth"), "region", "Revenue growth by region, last 12 months", m)),
    "topic_trends": _safe(lambda s, m: topic_trends(s.t("market", "topic_trends"), m)),
    "seasonality": _safe(lambda s, m: seasonality(s.t("market", "seasonal_index"), m)),
    "monthly_market": _safe(lambda s, m: monthly_market(s.t("market", "monthly_market"), m)),
    "brand_share": _safe(lambda s, m: brand_share(s.t("competition", "brand_share"), s.client, m)),
    "share_trend": _safe(lambda s, m: share_trend(s.t("competition", "share_trend"), s.client, m)),
    "channel_index": _safe(lambda s, m: channel_index(s.t("competition", "channel_index"), s.client, m)),
    "region_index": _safe(lambda s, m: channel_index(s.t("competition", "region_index"), s.client, m)),
    "positioning": _safe(lambda s, m: positioning(s.t("competition", "price_positioning"), s.client, m)),
    "threats": _safe(lambda s, m: threats(s.t("competition", "threats"), s.client, m)),
    "white_space": _safe(lambda s, m: white_space(s.t("competition", "white_space"), m)),
    "sentiment_by_brand": _safe(lambda s, m: sentiment_by_brand(s.t("consumer", "sentiment_by_brand"), m)),
    "aspect_heatmap": _safe(lambda s, m: aspect_heatmap(s.t("consumer", "aspect_summary"), s.client, m)),
    "client_aspect_trend": _safe(lambda s, m: client_aspect_trend(s.t("consumer", "client_aspect_monthly"), s.t("consumer", "anomalies"), s.client, m)),
    "social_sentiment": _safe(lambda s, m: social_sentiment(s.t("consumer", "social_sentiment"), s.client, m)),
    "model_quality": _safe(lambda s, m: model_comparison(s.j("consumer.model_card"), m)),
    "confusion": _safe(lambda s, m: confusion(s.j("consumer.model_card"), m)),
    "training_curve": _safe(lambda s, m: training_curve(s.j("consumer.model_card"), m)),
    "segment_map": _safe(lambda s, m: segment_map(s.t("segmentation", "assignments"), s.t("segmentation", "profiles"), m)),
    "segment_importance": _safe(lambda s, m: segment_importance(s.t("segmentation", "importance"), m)),
    "concept": _safe(lambda s, m: concept(s.t("segmentation", "concept"), m)),
    "van_westendorp": _safe(lambda s, m: van_westendorp(s.t("segmentation", "vw_curves"), s.t("segmentation", "vw_points"), m)),
    "elasticities": _safe(lambda s, m: elasticities(s.t("forecast", "elasticities"), s.client, m)),
    "price_scenarios": _safe(lambda s, m: price_scenarios(s.t("forecast", "price_scenarios"), m)),
    "market_forecast": _safe(lambda s, m: outlook(s.t("forecast", "market_outlook"), "Tracked-panel revenue: actual and 12-month forecast (Rp bn)", m)),
    "client_forecast": _safe(lambda s, m: outlook(s.t("forecast", "client_outlook"), f"{s.client}: actual and 12-month revenue forecast (Rp bn)", m)),
    "backtest": _safe(lambda s, m: backtest(s.t("forecast", "backtest_detail"), (s.j("forecast.model_card") or {}).get("model_key"), m)),
    "feature_importance": _safe(lambda s, m: feature_importance(s.t("forecast", "feature_importance"), m)),
    "opportunities": _safe(lambda s, m: opportunities(s.df("strategy.opportunities"), m)),
}
