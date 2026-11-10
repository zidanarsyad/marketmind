"""Pricing analytics: econometric price elasticity, what-if scenarios and Van Westendorp PSM."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm


def estimate_elasticities(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Log-log demand model with fixed effects.

    log(units) = series FE + (month x channel) FE + brand-specific quadratic trend
                 + gamma * log(1 - stock-out share) + sum_b beta_b * log(price) * 1[brand = b]

    The series fixed effects absorb level differences, the month x channel effects absorb seasonality
    and campaign peaks (Ramadan, 11.11, 12.12), which differ by channel, and the trends absorb each
    brand's growth path, so the beta_b are identified from promotional and list-price variation.
    Standard errors are clustered by series. With month x online/offline effects instead, channel-specific
    peaks leaked into the price coefficients (mean error 0.15 against the planted elasticities; 0.06 now).
    """
    d = panel[(panel["units"] > 0) & (panel["price"] > 0)].copy()
    d["lu"] = np.log(d["units"])
    d["lp"] = np.log(d["price"])
    d["loos"] = np.log((1 - d["oos_frac"]).clip(lower=0.05))
    d["series"] = d["brand"] + "|" + d["category"] + "|" + d["channel"]
    d["time_group"] = d["month"].astype(str) + "_" + d["channel"]
    d["t"] = (d["month"].rank(method="dense") - 1) / 12.0
    X = pd.get_dummies(d[["series", "time_group"]], drop_first=True, dtype=float)
    brands = sorted(d["brand"].unique())
    for b in brands:
        is_b = (d["brand"] == b).astype(float)
        X[f"trend|{b}"] = d["t"] * is_b
        X[f"trend2|{b}"] = d["t"] ** 2 * is_b
        X[f"lp|{b}"] = d["lp"] * is_b
    X["loos"] = d["loos"]
    X = sm.add_constant(X, has_constant="add")
    with warnings.catch_warnings():  # FE dummies are collinear by design; pinv identifies the elasticities
        warnings.simplefilter("ignore")
        res = sm.OLS(d["lu"].values, X.values).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["series"])[0]})
        params, bse = np.asarray(res.params), np.asarray(res.bse)  # bse is lazy: compute inside the filter
    cols = list(X.columns)
    rows = []
    for b in brands:
        i = cols.index(f"lp|{b}")
        beta, se = float(params[i]), float(bse[i])
        rows.append(dict(brand=b, elasticity=round(beta, 3), std_err=round(se, 3), ci_low=round(beta - 1.96 * se, 3),
                         ci_high=round(beta + 1.96 * se, 3), n_obs=int((d["brand"] == b).sum()),
                         interpretation="elastic" if beta < -1 else "inelastic"))
    info = dict(r_squared=round(float(res.rsquared), 4), n_obs=int(res.nobs), n_params=len(cols),
                stockout_coef=round(float(params[cols.index("loos")]), 3), std_errors="clustered by series")
    return pd.DataFrame(rows), info


def price_scenarios(elasticity: float, base_revenue: float, changes=None, gross_margin: float = 0.6) -> pd.DataFrame:
    changes = np.round(np.arange(-0.20, 0.201, 0.05), 2) if changes is None else np.asarray(changes)
    vol = (1 + changes) ** elasticity
    rev = (1 + changes) * vol
    profit = ((1 + changes) - (1 - gross_margin)) / gross_margin * vol
    return pd.DataFrame(dict(price_change_pct=(changes * 100).round(0), volume_change_pct=((vol - 1) * 100).round(1),
                             revenue_change_pct=((rev - 1) * 100).round(1),
                             gross_profit_change_pct=((profit - 1) * 100).round(1),
                             revenue_idr_bn=(base_revenue * rev / 1e9).round(1)))


def _cross(x: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Price where monotone curve a crosses monotone curve b.

    A clean sign change is interpolated linearly. Where the curves coincide over a stretch - common when answers
    are rounded to Rp 5,000 and the tails are sparse, as both curves sit at the same small share - the crossing is
    the middle of that stretch. Taking its left end biased the optimal price point low in simulated surveys.
    """
    diff = a - b
    sign = np.sign(diff)
    nonzero = np.flatnonzero(sign)
    if not len(nonzero):
        return float("nan")
    start = sign[nonzero[0]]
    after = np.flatnonzero(sign == -start)
    if not len(after):
        return float("nan")
    j = after[0]                                   # first grid point past the crossing
    i = np.flatnonzero(sign[:j] == start)[-1]      # last grid point before it
    if j == i + 1:
        t = diff[i] / (diff[i] - diff[j])
        return float(x[i] + t * (x[j] - x[i]))
    return float((x[i + 1] + x[j - 1]) / 2)


def van_westendorp(df: pd.DataFrame, too_cheap: str, cheap: str, expensive: str, too_expensive: str,
                   step: int = 1000) -> tuple[dict, pd.DataFrame]:
    """Van Westendorp Price Sensitivity Meter.

    OPP = too cheap x too expensive; IPP = cheap x expensive;
    PMC = too cheap x not cheap; PME = too expensive x not expensive.
    The acceptable price range is [PMC, PME].
    """
    d = df[[too_cheap, cheap, expensive, too_expensive]].dropna()
    v = d.to_numpy(float)
    lo, hi = v.min(), v.max()
    grid = np.arange(np.floor(lo / step) * step, np.ceil(hi / step) * step + step, step)
    tc, ch = ((v[:, k][None, :] >= grid[:, None]).mean(axis=1) for k in (0, 1))   # share calling p (too) cheap
    ex, te = ((v[:, k][None, :] <= grid[:, None]).mean(axis=1) for k in (2, 3))   # share calling p (too) expensive
    curves = pd.DataFrame(dict(price_idr=grid, too_cheap=tc, cheap=ch, expensive=ex, too_expensive=te,
                               not_cheap=1 - ch, not_expensive=1 - ex))
    points = dict(pmc=_cross(grid, tc, 1 - ch), opp=_cross(grid, tc, te), ipp=_cross(grid, ch, ex),
                  pme=_cross(grid, te, 1 - ex), n=int(len(d)))
    return {k: (round(v, -2) if isinstance(v, float) and not np.isnan(v) else v) for k, v in points.items()}, curves


def van_westendorp_bootstrap(df: pd.DataFrame, too_cheap: str, cheap: str, expensive: str, too_expensive: str,
                             recommend, n_boot: int = 200, seed: int = 0) -> dict:
    """How stable the price points, and the price they lead to, are under resampling of the respondents.

    The optimal price point is where two sparse tails cross, so it moves by several thousand rupiah between
    samples; when the middle of the optimal zone lies near the boundary between two charm prices, the
    recommendation can flip. Returns each price's share of the bootstrap picks and 90% intervals for OPP and IPP.
    """
    d = df[[too_cheap, cheap, expensive, too_expensive]].dropna().reset_index(drop=True)
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_boot):
        p, _ = van_westendorp(d.iloc[rng.integers(0, len(d), len(d))], too_cheap, cheap, expensive, too_expensive)
        rows.append(dict(opp=p["opp"], ipp=p["ipp"], price=recommend(p)))
    b = pd.DataFrame(rows)
    shares = b["price"].value_counts(normalize=True)
    interval = lambda col: [round(float(b[col].quantile(0.05)), -2), round(float(b[col].quantile(0.95)), -2)]  # noqa: E731
    return dict(n_boot=n_boot, price_shares={int(k): round(float(s), 3) for k, s in shares.items()},
                opp_90=interval("opp"), ipp_90=interval("ipp"))
