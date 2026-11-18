"""The simulated world the enterprises share: the calendar, the true demand, the disruptions, and the readings each
enterprise's own sensors pick up.

Only the Global Control Center's environment simulator sees this module's state. An enterprise meets the world as
customer orders, deliveries, its own operations (``actual``: what happens to it this week) and its own sensors
(``leading``: readings its predictive agent can use to see a problem coming). The same random draws drive both modes,
so a ``local`` and an ``ecosystem`` run of a scenario face exactly the same customers and the same disruptions.

The case: Kirana Beauty launches its fragrance-free barrier-repair moisturizer (the concept MarketMind recommended, at
Rp 79,900) through the 12.12 mega-sale and Ramadan 2027, a 16-week horizon from Monday 23 November 2026.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

START = date(2026, 11, 23)
WEEKS = 16
SKU = "KB-BRM-50"
PRODUCT = "Kirana Barrier Repair Moisturizer 50 ml"
PRICE = 79_900
BATCH = 5_000                       # units in one production batch at the contract manufacturer
PALLET = 1_200                      # units on one pallet at the logistics company
REGIONS = ("JKT", "SBY")
REGION_NAME = {"JKT": "Jakarta", "SBY": "Surabaya"}
REGION_SHARE = {"JKT": 0.65, "SBY": 0.35}
MARKETPLACE_SHARE = 0.75            # of demand that comes through PasarNusa; the rest is Kirana's own channels
CAMPAIGNS = {"12.12 Mega Sale": (3,), "Ramadan Ekstra": (12, 13, 14, 15)}
CAMPAIGN_WEEKS = {w: name for name, weeks in CAMPAIGNS.items() for w in weeks}

# the truth, which no enterprise knows: mature weekly demand, the launch ramp, the Ramadan season (Ramadan 2027 runs
# 8 February to 9 March, Eid on 10 March), and the lift a campaign gives a brand that joins it
TRUE_BASE = 14_000
RAMP = {1: 0.55, 2: 0.75, 3: 0.90, 4: 0.95}
SEASON = {12: 1.10, 13: 1.10, 14: 1.25, 15: 1.25, 16: 1.15}
TRUE_UPLIFT = {3: 0.70, 12: 0.20, 13: 0.20, 14: 0.20, 15: 0.20}
NONPARTICIPANT_UPLIFT = 0.10


def week_start(w: int) -> date:
    return START + timedelta(weeks=w - 1)


def week_label(w: int) -> str:
    return "setup" if w <= 0 else f"W{w} ({week_start(w):%d %b})"


def iso_week(w: int) -> str:
    y, wk, _ = week_start(max(w, 1)).isocalendar()
    return f"{y}-W{wk:02d}"


@dataclass(frozen=True)
class Event:
    key: str
    start: int
    end: int
    target: str
    kind: str
    params: dict
    title: str
    detail: str

    def active(self, w: int) -> bool:
        return self.start <= w <= self.end


EVENTS = {
    "packaging_defect": Event("packaging_defect", 5, 8, "kemasprima", "defect_spike", {"defect_rate": 0.10},
                              "Packaging defect spike",
                              "Pump springs from a new sub-supplier fail: 10% of KemasPrima's sets are defective for "
                              "four weeks, against 1.5% normally."),
    "warehouse_flood": Event("warehouse_flood", 8, 9, "kirimcepat", "flood", {"jakarta_lane_factor": 0.25},
                             "Jakarta flood",
                             "Flooded roads cut the Cikarang-Jakarta lane to a quarter of its capacity for two weeks."),
    "demand_surge": Event("demand_surge", 3, 3, "pasarnusa", "traffic_surge", {"extra_uplift": 0.35},
                          "12.12 traffic surge",
                          "12.12 traffic on PasarNusa runs 35 points above any forecast."),
    "line_breakdown": Event("line_breakdown", 6, 6, "maklonnusa", "line_down", {"batches_lost": 2},
                            "Filling line breakdown",
                            "Filling line 2 at MaklonNusa breaks down for a week: two batches of capacity are lost."),
}

SCENARIOS = {
    "normal": ("Normal operations", "No disruption: the launch, 12.12 and Ramadan as planned.", ()),
    "packaging_defect": ("Packaging defect spike", EVENTS["packaging_defect"].detail, ("packaging_defect",)),
    "warehouse_flood": ("Jakarta flood", EVENTS["warehouse_flood"].detail, ("warehouse_flood",)),
    "demand_surge": ("12.12 traffic surge", EVENTS["demand_surge"].detail, ("demand_surge",)),
    "line_breakdown": ("Filling line breakdown", EVENTS["line_breakdown"].detail, ("line_breakdown",)),
    "stress": ("Every disruption", "All four disruptions in one run.",
               ("packaging_defect", "warehouse_flood", "demand_surge", "line_breakdown")),
}
MODES = ("local", "ecosystem")


def scenario_info() -> list[dict]:
    return [{"key": k, "title": t, "description": d,
             "events": [dict(key=e, title=EVENTS[e].title, start=EVENTS[e].start, end=EVENTS[e].end,
                             target=EVENTS[e].target, detail=EVENTS[e].detail) for e in keys]}
            for k, (t, d, keys) in SCENARIOS.items()]


@dataclass
class World:
    scenario: str = "normal"
    seed: int = 7
    visibility: dict[int, float] = field(default_factory=dict)   # PasarNusa's listing visibility for Kirana, by week

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {self.scenario!r}; choose one of {', '.join(SCENARIOS)}")
        self.events = [EVENTS[k] for k in SCENARIOS[self.scenario][2]]
        rng = np.random.default_rng(self.seed)
        # demand noise and sensor noise, drawn once per run and independent of the mode
        self.noise = {w: {r: float(rng.normal(1.0, 0.05)) for r in REGIONS} for w in range(1, WEEKS + 1)}
        self.sensor = {w: rng.normal(0.0, 1.0, size=8) for w in range(0, WEEKS + 3)}

    # ------------------------------------------------------------------ events
    def event(self, kind: str, w: int) -> Event | None:
        return next((e for e in self.events if e.kind == kind and e.active(w)), None)

    def starting(self, w: int) -> list[Event]:
        return [e for e in self.events if e.start == w]

    # ------------------------------------------------------------------ demand
    def true_base(self, w: int) -> float:
        growth = 1 + 0.01 * max(0, w - 4)
        return TRUE_BASE * RAMP.get(w, 1.0) * growth * SEASON.get(w, 1.0)

    def demand(self, w: int, joined: bool) -> dict[str, dict[str, int]]:
        """Customer orders for Kirana in week ``w``, by channel and region. ``joined``: Kirana is in this week's
        campaign on PasarNusa (only matters in campaign weeks)."""
        base = self.true_base(w)
        lift = (TRUE_UPLIFT.get(w, 0.0) if joined else NONPARTICIPANT_UPLIFT) if w in CAMPAIGN_WEEKS else 0.0
        surge = self.event("traffic_surge", w)
        lift += surge.params["extra_uplift"] if surge and joined else 0.0
        market = base * MARKETPLACE_SHARE * (1 + lift) * self.visibility.get(w, 1.0)
        direct = base * (1 - MARKETPLACE_SHARE)
        return {ch: {r: int(round(total * REGION_SHARE[r] * self.noise[w][r])) for r in REGIONS}
                for ch, total in (("marketplace", market), ("direct", direct))}

    # ------------------------------------------------------------------ sensors and operations
    def signals(self, w: int) -> dict[str, dict]:
        """What each enterprise's sensors read in week ``w`` (``leading``) and what happens to its operations this
        week (``actual``). Leading readings show a coming problem one or two weeks early, with noise."""
        z = self.sensor[w]
        defect_next = self.event("defect_spike", w + 1)
        flood = [self.event("flood", w + k) for k in (1, 2, 3)]     # a three-week rainfall outlook
        down = {k: self.event("line_down", w + k) for k in (1, 2)}     # vibration builds up two weeks before a failure
        spike_now, flood_now, down_now = self.event("defect_spike", w), self.event("flood", w), self.event("line_down", w)
        return {
            "kemasprima": {
                "leading": {"week": w + 1, "sub_supplier": "B" if defect_next else "A",
                            "spring_tension_dev": round((2.6 if defect_next else 0.3) + 0.4 * z[0], 3),
                            "mold_temp_dev": round(0.8 + 0.5 * z[1], 3), "resin_moisture": round(0.11 + 0.02 * z[2], 4)},
                "actual": {"defect_rate": spike_now.params["defect_rate"] if spike_now else 0.015},
            },
            "kirimcepat": {
                "leading": {"forecasts": [{"week": w + k, "rain_mm": round((88.0 if f else 18.0) + 6 * z[1 + k], 1),
                                           "tide_cm": round((140.0 if f else 95.0) + 8 * z[4 + k], 1)}
                                          for k, f in zip((1, 2, 3), flood, strict=True)]},
                "actual": {"jakarta_lane_factor": flood_now.params["jakarta_lane_factor"] if flood_now else 1.0},
            },
            "maklonnusa": {
                "leading": {"weeks": [{"week": w + k, "lines": [
                    {"line": 1, "vibration_mm_s": round(2.1 + 0.3 * z[6], 2), "hours_since_service": 180 + 10 * w},
                    {"line": 2, "vibration_mm_s": round((7.4 if down[k] else 2.4) + 0.4 * z[7], 2),
                     "hours_since_service": (620 if down[k] else 240) + 10 * w}]} for k in (1, 2)]},
                "actual": {"batches_lost": down_now.params["batches_lost"] if down_now else 0},
            },
            "pasarnusa": {"leading": {}, "actual": {}},
            "kirana": {"leading": {}, "actual": {}},
            "research": {"leading": {}, "actual": {}},
        }
