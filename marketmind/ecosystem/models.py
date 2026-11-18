"""The predictive models of the enterprises' agents, each trained on that enterprise's own (synthetic) history.

* KemasPrima, QC Prediction Agent: logistic regression on lot readings (sub-supplier, spring tension, mould
  temperature, resin moisture) for the chance a lot is a high-defect lot; the expected defect rate follows from it.
* KirimCepat, Flood Risk Agent: logistic regression on the rainfall and tide forecast for the chance the
  Cikarang-Jakarta lane is cut.
* MaklonNusa, Line Reliability Agent: logistic regression on vibration and hours since service for the chance a
  filling line breaks down next week.
* PasarNusa, Traffic Forecast Agent: ridge regression of a campaign's demand lift on voucher depth, seller rating and
  participation, fitted on past campaigns.
* Kirana Beauty, Demand Planning Agent: a moving average of its own orders (local), or MarketMind's research
  baseline times the season and PasarNusa's campaign lift, recalibrated on what it observes (ecosystem).

The histories are generated with a fixed seed, stored in the enterprise's own database (its data explorer shows them)
and never shared: only the predictions leave, and only in the ecosystem mode.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge

NORMAL_DEFECT, SPIKE_DEFECT = 0.015, 0.10


class DefectRiskModel:
    features = ("sub_supplier_b", "spring_tension_dev", "mold_temp_dev", "resin_moisture")
    name = "LogisticRegression (lot defect risk)"

    def __init__(self, seed: int = 11, n: int = 480):
        rng = np.random.default_rng(seed)
        b = rng.random(n) < 0.25
        tension = np.where(b, rng.normal(2.2, 0.8, n), rng.normal(0.4, 0.5, n))
        mold = rng.normal(0.8, 0.5, n)
        moist = rng.normal(0.11, 0.02, n)
        logit = -4.2 + 1.9 * tension + 0.6 * b + 0.5 * mold + 8 * (moist - 0.11)
        high = rng.random(n) < 1 / (1 + np.exp(-logit))
        rate = np.where(high, rng.normal(SPIKE_DEFECT, 0.015, n), rng.normal(NORMAL_DEFECT, 0.004, n)).clip(0.002, 0.3)
        self.X = np.column_stack([b.astype(float), tension, mold, moist])
        self.y = high
        self.history = [{"lot": f"LOT-{i + 1:04d}", "sub_supplier": "B" if b[i] else "A",
                         "spring_tension_dev": round(float(tension[i]), 3), "mold_temp_dev": round(float(mold[i]), 3),
                         "resin_moisture": round(float(moist[i]), 4), "defect_rate": round(float(rate[i]), 4),
                         "high_defect_lot": bool(high[i])} for i in range(n)]
        self.clf = LogisticRegression(max_iter=1000).fit(self.X, self.y)
        self.accuracy = float(self.clf.score(self.X, self.y))

    def predict(self, reading: dict) -> dict:
        x = np.array([[1.0 if reading["sub_supplier"] == "B" else 0.0, reading["spring_tension_dev"],
                       reading["mold_temp_dev"], reading["resin_moisture"]]])
        p = float(self.clf.predict_proba(x)[0, 1])
        return {"p_high_defect": round(p, 3), "expected_defect_rate": round(NORMAL_DEFECT + p * (SPIKE_DEFECT - NORMAL_DEFECT), 4)}


class FloodRiskModel:
    name = "LogisticRegression (lane flood risk)"

    def __init__(self, seed: int = 12, n: int = 300):
        rng = np.random.default_rng(seed)
        rain = rng.gamma(2.0, 14.0, n)
        tide = rng.normal(100, 18, n)
        logit = -9.0 + 0.085 * rain + 0.03 * (tide - 100)
        cut = rng.random(n) < 1 / (1 + np.exp(-logit))
        self.history = [{"iso_week": f"H{i + 1:03d}", "rain_mm": round(float(rain[i]), 1), "tide_cm": round(float(tide[i]), 1),
                         "lane_cut": bool(cut[i])} for i in range(n)]
        self.clf = LogisticRegression(max_iter=1000).fit(np.column_stack([rain, tide]), cut)
        self.accuracy = float(self.clf.score(np.column_stack([rain, tide]), cut))

    def predict(self, forecast: dict) -> float:
        return round(float(self.clf.predict_proba(np.array([[forecast["rain_mm"], forecast["tide_cm"]]]))[0, 1]), 3)


class BreakdownModel:
    name = "LogisticRegression (line breakdown risk)"

    def __init__(self, seed: int = 13, n: int = 360):
        rng = np.random.default_rng(seed)
        vib = rng.gamma(3.0, 1.0, n)
        hours = rng.uniform(50, 800, n)
        logit = -7.5 + 0.75 * vib + 0.004 * hours
        down = rng.random(n) < 1 / (1 + np.exp(-logit))
        self.history = [{"recordId": i + 1, "lineNo": int(1 + i % 2), "vibrationMmS": round(float(vib[i]), 2),
                         "hoursSinceService": int(hours[i]), "brokeDownNextWeek": bool(down[i])} for i in range(n)]
        self.clf = LogisticRegression(max_iter=1000).fit(np.column_stack([vib, hours]), down)
        self.accuracy = float(self.clf.score(np.column_stack([vib, hours]), down))

    def predict(self, line: dict) -> float:
        x = np.array([[line["vibration_mm_s"], line["hours_since_service"]]])
        return round(float(self.clf.predict_proba(x)[0, 1]), 3)


class UpliftModel:
    name = "Ridge regression (campaign demand lift)"

    def __init__(self, seed: int = 14, n: int = 220):
        rng = np.random.default_rng(seed)
        voucher = rng.choice([0.0, 0.05, 0.10, 0.15], n)
        rating = rng.uniform(4.2, 4.9, n)
        mega = rng.random(n) < 0.4
        lift = 0.02 + 2.0 * voucher + 0.45 * mega + 0.20 * (rating - 4.5) + rng.normal(0, 0.05, n)
        self.history = [{"campaign_id": f"CMP-{i + 1:03d}", "voucher_depth": float(voucher[i]),
                         "seller_rating": round(float(rating[i]), 2), "mega_sale": bool(mega[i]),
                         "demand_lift": round(float(lift[i]), 3)} for i in range(n)]
        X = np.column_stack([voucher, rating, mega.astype(float)])
        self.reg = Ridge(alpha=0.5).fit(X, lift)
        self.r2 = float(self.reg.score(X, lift))

    def predict(self, voucher: float, rating: float, mega: bool) -> float:
        return round(float(self.reg.predict(np.array([[voucher, rating, 1.0 if mega else 0.0]]))[0]), 3)


class DemandForecaster:
    """Kirana's Demand Planning Agent. Local: the mean of the last three weeks of orders it saw (a launch guess before
    that). Ecosystem: research baseline x launch ramp x season x campaign lift, scaled by a factor it re-estimates from
    the orders it observes (exponential smoothing of observed / forecast)."""

    LAUNCH_GUESS = 9_000
    name = "Moving average (local) or research baseline x season x campaign lift, recalibrated (ecosystem)"

    def __init__(self):
        self.observed: dict[int, int] = {}
        self.scale = 1.0

    RULE_OF_THUMB_LIFT = 0.30           # the brand's own guess for a campaign week, without PasarNusa's model

    def local(self, week: int, campaign_weeks=(), marketplace_share: float = 0.75) -> float:
        past = [self.observed[w] for w in sorted(self.observed) if w < week][-3:]
        base = float(np.mean(past)) if past else float(self.LAUNCH_GUESS)
        return base * (1 + marketplace_share * self.RULE_OF_THUMB_LIFT) if week in campaign_weeks else base

    def ecosystem(self, week: int, intel: dict, lift: dict) -> float:
        ramp = intel.get("launch_ramp", {}).get(str(week), 1.0)
        season = intel.get("season", {}).get(str(week), 1.0)
        growth = 1 + intel.get("weekly_growth", 0.0) * max(0, week - 4)
        market_share = intel.get("marketplace_share", 0.75)
        base = intel["base_weekly_units"] * ramp * season * growth
        return self.scale * base * (1 - market_share + market_share * (1 + lift.get(str(week), lift.get(week, 0.0))))

    def observe(self, week: int, units: int, forecast: float | None) -> float:
        """Record a week's orders; returns the change in the scale factor (ecosystem recalibration)."""
        self.observed[week] = units
        if not forecast:
            return 0.0
        old = self.scale
        self.scale = 0.7 * self.scale + 0.3 * self.scale * (units / forecast)
        return self.scale - old
