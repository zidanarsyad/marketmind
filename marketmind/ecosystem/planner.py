"""The Global Ecosystem Planner: a mixed-integer program over the remaining weeks, built only from shared facts.

It chooses, week by week, how many batches MaklonNusa fills for Kirana, how many units KirimCepat moves on each lane
(at the standard rate, or at the surge rate above 85% of a lane's capacity), how many Jakarta orders are served by
express from the Surabaya warehouse, and so where stock sits and which orders are lost. The objective is the course
brief's multi-objective function, every term in rupiah:

    J = w_C * cost + w_T * time + w_R * risk + w_Q * (lost service)

    cost  = production at the negotiated price + transport (standard and surge) + express + holding
            - the stock still on hand after the last week, at its cost (it sells after the season; Kirana's books
              value it the same way, so the plan does not empty the warehouses on purpose as the horizon nears)
    time  = express deliveries (a day slower) and units waiting at the factory
    risk  = expected defective units, from the packaging maker's shared defect forecast
    lost  = orders the plan leaves unserved, at the margin each would have earned

subject to every enterprise's own limits, as each shares them: MaklonNusa's free capacity (whole batches of 5,000),
KemasPrima's good-set capacity after its predicted defect rate, KirimCepat's lane capacity (cut when it forecasts a
flood), the warehouses' storage, and PasarNusa's stock commitment before each campaign (a soft constraint: a shortfall
costs a penalty instead of making the plan infeasible). Local acceptability is enforced afterwards by the enterprises
themselves: each checks its slice against its private knowledge and may reject it with a constraint, which the
planner adds before solving again (see ``engine.Control.plan``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .world import BATCH, REGIONS

SURGE_SHARE = 0.15          # the top 15% of a lane's capacity is sold at the surge rate
DEFAULT_WEIGHTS = {"cost": 1.0, "time": 1.0, "risk": 1.0, "quality": 1.0}


@dataclass
class PlanInput:
    week: int                                   # planning at the start of this week
    horizon: int                                # last week
    demand: dict[str, dict[int, float]]         # region -> week -> forecast units
    maklon_capacity: dict[int, float]           # week -> free capacity for Kirana, units
    packaging_good_capacity: dict[int, float]   # week -> good sets available, units
    defect_rate: dict[int, float]               # week -> predicted defect rate (risk term)
    lane_capacity: dict[str, dict[int, float]]  # region -> transit week -> units
    lane_price: dict[str, float]                # region -> rupiah per unit (standard rate)
    inventory: dict[str, float]                 # region -> units in the warehouse at the start of ``week``
    arriving: dict[str, float]                  # region -> units arriving this week (booked last week)
    factory_stock: float                        # finished units waiting at MaklonNusa
    locked_production: float                    # units already ordered for ``week``
    unit_price: float                           # negotiated price per unit
    margin_per_unit: float                      # what a lost order costs
    commitments: dict[int, float] = field(default_factory=dict)   # campaign week -> units to hold at its start
    express_capacity: float = 6_000
    express_price: float = 1_800
    holding: float = 150
    storage: dict[str, float] = field(default_factory=lambda: {"JKT": 45_000, "SBY": 25_000})
    max_batches: dict[int, int] = field(default_factory=dict)      # constraints enterprises added by rejecting a plan
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    defect_cost: float = 4_000                  # rupiah per expected defective unit (scrap, inspection, returns)
    delay_cost: float = 600                     # rupiah per express unit (a slower delivery)
    commitment_penalty: float = 60_000          # rupiah per unit short of a campaign commitment
    terminal_value: float | None = None         # rupiah per unit still in stock at the horizon (default: the unit price)


def solve(p: PlanInput) -> dict:
    t, T = p.week, p.horizon
    weeks = list(range(t, T + 1))
    idx: dict[tuple, int] = {}

    def var(*key) -> int:
        if key not in idx:
            idx[key] = len(idx)
        return idx[key]

    for w in weeks:
        if w > t:
            var("b", w)
        var("g", w)
        if w < T:
            for r in REGIONS:
                var("ys", r, w), var("yu", r, w)
        var("z", w)
        for r in REGIONS:
            var("s", r, w), var("l", r, w), var("I", r, w)
    for c in p.commitments:
        if t < c <= T:
            var("short", c)
    n = len(idx)

    lb, ub, cost = np.zeros(n), np.full(n, np.inf), np.zeros(n)
    integrality = np.zeros(n)
    wc, wt, wr, wq = (p.weights.get(k, 1.0) for k in ("cost", "time", "risk", "quality"))
    terminal = p.unit_price if p.terminal_value is None else p.terminal_value
    for key, i in idx.items():
        kind, w = key[0], key[-1]
        if kind == "b":
            cap = min(p.maklon_capacity.get(w, 0.0), p.packaging_good_capacity.get(w, 0.0))
            ub[i] = min(int(cap // BATCH), p.max_batches.get(w, 10**6))
            integrality[i] = 1
            cost[i] = wc * p.unit_price * BATCH + wr * p.defect_rate.get(w, 0.0) * BATCH * p.defect_cost
        elif kind == "g":
            cost[i] = wc * p.holding + wt * 50      # stock waiting at the factory: holding plus a small time cost
            if w == T:
                cost[i] -= wc * terminal
        elif kind in ("ys", "yu"):
            r = key[1]
            lane = p.lane_capacity[r].get(w + 1, 0.0)
            ub[i] = lane * ((1 - SURGE_SHARE) if kind == "ys" else SURGE_SHARE)
            cost[i] = wc * p.lane_price[r] * (1.0 if kind == "ys" else 1.2)
        elif kind == "z":
            ub[i] = p.express_capacity
            cost[i] = wc * p.express_price + wt * p.delay_cost
        elif kind == "l":
            cost[i] = wq * p.margin_per_unit
        elif kind == "I":
            ub[i] = p.storage[key[1]]
            cost[i] = wc * p.holding - (wc * terminal if w == T else 0.0)
        elif kind == "short":
            cost[i] = p.commitment_penalty
    rows: list[tuple[dict[int, float], float, float]] = []

    def row(coefs: dict[int, float], lo: float, hi: float) -> None:
        rows.append((coefs, lo, hi))

    for w in weeks:
        # factory stock: last week's stock + this week's production - shipments booked this week
        c = {idx[("g", w)]: 1.0}
        if w > t:
            c[idx[("g", w - 1)]] = -1.0
            c[idx[("b", w)]] = -float(BATCH)
            base = 0.0
        else:
            base = p.factory_stock + p.locked_production
        if w < T:
            for r in REGIONS:
                c[idx[("ys", r, w)]] = c.get(idx[("ys", r, w)], 0) + 1.0
                c[idx[("yu", r, w)]] = c.get(idx[("yu", r, w)], 0) + 1.0
        row(c, base, base)
        for r in REGIONS:
            # warehouse stock: last week's + arrivals - sales (- express units sent from Surabaya)
            c = {idx[("I", r, w)]: 1.0, idx[("s", r, w)]: 1.0}
            if r == "SBY":
                c[idx[("z", w)]] = 1.0
            if w > t:
                c[idx[("I", r, w - 1)]] = -1.0
                c[idx[("ys", r, w - 1)]] = -1.0
                c[idx[("yu", r, w - 1)]] = -1.0
                base = 0.0
            else:
                base = p.inventory.get(r, 0.0) + p.arriving.get(r, 0.0)
            row(c, base, base)
            # every forecast order is served from its own warehouse, by express (Jakarta), or lost
            d = p.demand[r].get(w, 0.0)
            c = {idx[("s", r, w)]: 1.0, idx[("l", r, w)]: 1.0}
            if r == "JKT":
                c[idx[("z", w)]] = 1.0
            row(c, d, d)
    for cw, qty in p.commitments.items():
        if not (t < cw <= T):
            continue
        prev = cw - 1
        c = {idx[("short", cw)]: 1.0}
        for r in REGIONS:
            c[idx[("I", r, prev)]] = 1.0
            if prev < T and ("ys", r, prev) in idx:
                c[idx[("ys", r, prev)]] = 1.0
                c[idx[("yu", r, prev)]] = 1.0
        row(c, qty, np.inf)

    A = lil_matrix((len(rows), n))
    lo, hi = np.zeros(len(rows)), np.zeros(len(rows))
    for k, (coefs, a, b) in enumerate(rows):
        for i, v in coefs.items():
            A[k, i] = v
        lo[k], hi[k] = a, b
    res = milp(cost, constraints=LinearConstraint(A.tocsr(), lo, hi), integrality=integrality, bounds=Bounds(lb, ub),
               options={"time_limit": 20})
    if res.x is None:
        return {"status": "infeasible", "message": res.message, "weeks": []}
    x = res.x

    def v(*key) -> float:
        return float(x[idx[key]]) if key in idx else 0.0

    plan, totals = [], {"production": 0.0, "lost": 0.0, "express": 0.0, "surge": 0.0, "shipped": 0.0}
    terms = {"cost": 0.0, "time": 0.0, "risk": 0.0, "quality": 0.0}
    for w in weeks:
        b = round(v("b", w)) if w > t else None
        prod = (b or 0) * BATCH if w > t else p.locked_production
        rowp = {"week": w, "batches": b, "production": int(round(prod)), "factory_stock": int(round(v("g", w))),
                "express": int(round(v("z", w)))}
        for r in REGIONS:
            ship = v("ys", r, w) + v("yu", r, w)
            rowp[f"ship_{r}"] = int(round(ship))
            rowp[f"surge_{r}"] = int(round(v("yu", r, w)))
            rowp[f"sales_{r}"] = int(round(v("s", r, w)))
            rowp[f"lost_{r}"] = int(round(v("l", r, w)))
            rowp[f"stock_{r}"] = int(round(v("I", r, w)))
            totals["lost"] += v("l", r, w)
            totals["surge"] += v("yu", r, w)
            totals["shipped"] += ship
            terms["cost"] += p.lane_price[r] * (v("ys", r, w) + 1.2 * v("yu", r, w)) + p.holding * v("I", r, w)
            terms["quality"] += p.margin_per_unit * v("l", r, w)
        totals["production"] += prod if w > t else 0.0
        totals["express"] += v("z", w)
        terms["cost"] += p.unit_price * (prod if w > t else 0.0) + p.express_price * v("z", w) + p.holding * v("g", w)
        terms["time"] += p.delay_cost * v("z", w) + 50 * v("g", w)
        terms["risk"] += p.defect_rate.get(w, 0.0) * (prod if w > t else 0.0) * p.defect_cost
        plan.append(rowp)
    left_over = v("g", T) + sum(v("I", r, T) for r in REGIONS)
    terms["cost"] -= terminal * left_over
    totals["ending_stock"] = left_over
    demand = sum(sum(p.demand[r].get(w, 0.0) for w in weeks) for r in REGIONS)
    shortfall = {cw: round(v("short", cw)) for cw in p.commitments if ("short", cw) in idx}
    return {"status": "optimal" if res.status == 0 else str(res.message), "objective": round(float(res.fun)),
            "terms": {k: round(val) for k, val in terms.items()}, "weights": p.weights,
            "weeks": plan, "totals": {k: int(round(val)) for k, val in totals.items()},
            "planned_fill_rate": round(1 - totals["lost"] / demand, 4) if demand else 1.0,
            "commitment_shortfall": shortfall,
            "constraints": {"max_batches": {str(k): v for k, v in p.max_batches.items()}}}
