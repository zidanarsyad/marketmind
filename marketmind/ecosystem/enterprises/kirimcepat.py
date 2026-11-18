"""KirimCepat: the logistics company that trucks Kirana's goods from Cikarang to its Jakarta and Surabaya warehouses.

It thinks in pallets (1,200 units) and ISO weeks; its shared view uses them, and the Control Center converts.
"""
from __future__ import annotations

import math
from collections import defaultdict

from ..governance import Governance, Role
from ..models import FloodRiskModel
from ..world import PALLET, REGIONS, WEEKS, iso_week
from .base import Agent, Enterprise

LANES = {"JKT": {"capacity": 16_000, "price": 380, "cost": 260, "name": "Cikarang to Jakarta warehouse"},
         "SBY": {"capacity": 9_000, "price": 1_150, "cost": 870, "name": "Cikarang to Surabaya warehouse"}}
SURGE_AT, SURGE_FACTOR = 0.85, 1.2
EXPRESS = {"id": "express_sby", "capacity_units": 6_000, "cost_idr_per_unit": 1_800, "own_cost": 1_200}
FLOOD_FACTOR = 0.25
REROUTE_OPTIONS = [
    {"id": "express_sby", "title": "Express trucks from the Surabaya warehouse to Jakarta customers",
     "cost_idr_per_unit": 1_600, "delay_days": 1, "risk": 0.08, "capacity_units": 6_000},
    {"id": "air_sby", "title": "Air freight Surabaya to Jakarta", "cost_idr_per_unit": 4_800, "delay_days": 0,
     "risk": 0.05, "capacity_units": 2_000},
    {"id": "rail_sby", "title": "Rail from Surabaya to Jakarta", "cost_idr_per_unit": 1_300, "delay_days": 2,
     "risk": 0.20, "capacity_units": 4_000},
]


class KirimCepat(Enterprise):
    key = "kirimcepat"
    name = "KirimCepat Logistics"
    industry = "Logistics and warehousing"
    city = "Bekasi"
    accent, accent_dark = "#0369a1", "#2b8fc4"
    description = "Trucks finished goods from factories to regional warehouses and runs express delivery between cities."
    roles = (
        Role("Fleet Manager", "Plans trucks and lanes", datasets=("shipment", "lane_capacity", "weather_forecast", "ledger",
                                                                   "decisions", "messages"), hidden_fields=("amount_idr",)),
        Role("Risk Analyst", "Watches weather and flood risk", datasets=("weather_forecast", "flood_history", "lane_capacity")),
        Role("Account Manager", "Bookings, prices and contracts", datasets=("shipment", "ledger", "messages", "decisions"),
             can_approve=True),
    )
    modules = (("Booking", "Takes and prices lane bookings"), ("Route planning", "Lanes, express and rerouting"),
               ("Risk", "Flood forecast from rainfall and tide"), ("Tracking", "Deliveries and delays"))
    platform = {"database": "SQLite (relational)", "api": "REST + JSON", "units": f"pallets ({PALLET:,} units)",
                "time": "ISO week (e.g. 2026-W48)", "stack": "FastAPI on its own port"}
    governance = Governance(
        public=("rate_card",),
        partner=("lane_capacity", "risk_notices", "express"),
        control=("lane_capacity", "risk_notices", "express"),
        private=("flood_history", "ledger"),
        policies={"surge_above_utilisation": SURGE_AT, "surge_factor": SURGE_FACTOR},
        approval_threshold_idr=None)
    private_datasets = ("flood_history", "ledger")

    def make_agents(self):
        return [Agent("flood_risk", "Flood Risk Agent", "predictive", "Forecasts lane flooding from rainfall and tide",
                      FloodRiskModel.name),
                Agent("route_planner", "Route Planning Agent", "planning",
                      "Delivers bookings within lane capacity; carries delayed loads over"),
                Agent("booking", "Booking Agent", "negotiation",
                      "Prices bookings (surge above 85%); answers calls for rerouting proposals")]

    def service_agent(self):
        return "booking"

    def setup(self):
        self.model = FloodRiskModel(seed=self.seed + 12)
        self.store.insert_many("flood_history", self.model.history)
        self.booked: dict[int, dict[str, int]] = defaultdict(lambda: {r: 0 for r in REGIONS})
        self.carry = {r: 0 for r in REGIONS}
        self.expected_factor: dict[int, float] = {}
        self.notices: dict[int, float] = {}
        self.informed: set[int] = set()
        self.express = dict(EXPRESS)
        self.moved = self.delayed_units = self.express_units = 0
        self.util: list[float] = []

    def capacity(self, region: str, week: int, actual_factor: float | None = None) -> int:
        f = 1.0
        if region == "JKT":
            f = actual_factor if actual_factor is not None else self.expected_factor.get(week, 1.0)
        return int(LANES[region]["capacity"] * f)

    # ------------------------------------------------------------------ bookings
    def on_request_shipment_booking(self, m):
        tw = int(m.payload["week"]) + 1
        accepted, charge, surge = {}, 0.0, 0
        for r in REGIONS:
            want = int(m.payload["units"].get(r, 0))
            cap = self.capacity(r, tw)
            take = max(0, min(want, cap - self.booked[tw][r]))
            before = self.booked[tw][r]
            std_room = max(0, int(SURGE_AT * cap) - before)
            s = max(0, take - std_room)
            charge += LANES[r]["price"] * (take - s) + LANES[r]["price"] * SURGE_FACTOR * s
            surge += s
            self.booked[tw][r] += take
            accepted[r] = take
        if sum(accepted.values()):
            self.book("kirana", "transport", charge, sum(accepted.values()))
            self.book("own fleet", "transport cost", -sum(LANES[r]["cost"] * accepted[r] for r in REGIONS))
        refused = {r: int(m.payload["units"].get(r, 0)) - accepted[r] for r in REGIONS}
        why = "Within lane capacity." if not any(refused.values()) else (
            f"Lane capacity reached for {iso_week(tw)}; {sum(refused.values()):,} units refused"
            + (" (flood forecast cuts the Jakarta lane)" if self.expected_factor.get(tw, 1.0) < 1 else "") + ".")
        self.decide("booking", f"Book {sum(accepted.values()):,} units for {iso_week(tw)}"
                    + (f", {surge:,} at the surge rate" if surge else ""), why,
                    inputs={"requested": m.payload["units"]}, outputs={"accepted": accepted, "charge_idr": round(charge)},
                    refs=[m.message_id])
        return [self.reply(m, "booking", "AGREE", {"accepted": accepted, "refused": refused, "charge_idr": round(charge),
                                                   "surge_units": surge})]

    def on_request_express(self, m):
        units = min(int(m.payload["units"]), int(self.express["capacity_units"]))
        return [self.reply(m, "booking", "AGREE", {"units": units, "route": self.express["id"],
                                                   "price_idr_per_unit": self.express["cost_idr_per_unit"]})]

    def on_inform_express_used(self, m):
        u = int(m.payload["units"])
        self.express_units += u
        self.book("kirana", "express", u * self.express["cost_idr_per_unit"], u)
        self.book("own fleet", "express cost", -u * EXPRESS["own_cost"], u)
        return []

    def on_request_proposal_reroute_options(self, m):
        self.decide("booking", "Propose three ways to reach Jakarta during the flood",
                    "Contract Net: Kirana chooses on its own criteria.", outputs={"options": [o["id"] for o in REROUTE_OPTIONS]},
                    refs=[m.message_id])
        return [self.reply(m, "booking", "PROPOSE", {"options": REROUTE_OPTIONS, "valid_weeks": m.payload.get("weeks")})]

    def on_accept_proposal_reroute_options(self, m):
        chosen = next(o for o in REROUTE_OPTIONS if o["id"] == m.payload["option"])
        self.express = {**EXPRESS, **{k: chosen[k] for k in ("id", "capacity_units", "cost_idr_per_unit")}}
        self.decide("booking", f"Contract: {chosen['title']}",
                    f"Rp {chosen['cost_idr_per_unit']:,} per unit, up to {chosen['capacity_units']:,} units a week.",
                    refs=[m.message_id])
        return []

    # ------------------------------------------------------------------ the week
    def on_tick(self, week, leading, actual):
        out = []
        for f in leading.get("forecasts", []):
            w = int(f["week"])
            p = self.model.predict(f)
            self.store.insert("weather_forecast", {"iso_week": iso_week(w), "rain_mm": f["rain_mm"], "tide_cm": f["tide_cm"],
                                                   "p_flood": p})
            if p > 0.5 and w <= WEEKS:
                self.expected_factor[w] = FLOOD_FACTOR
                self.notices[w] = p
                if w not in self.informed:
                    self.informed.add(w)
                    self.decide("flood_risk", f"Flood likely on the Jakarta lane in {iso_week(w)} (p = {p:.0%})",
                                f"Forecast rainfall {f['rain_mm']} mm a day and tide {f['tide_cm']} cm.", inputs=f)
                    if self.mode == "ecosystem":
                        flood_weeks = sorted(x for x in self.notices if x >= w)
                        for to in ("kirana.supply_planner", "control.coordinator"):
                            out.append(self.send("flood_risk", to, "INFORM", "flood_risk",
                                                 {"week": w, "weeks": flood_weeks, "probability": p,
                                                  "expected_jakarta_lane_factor": FLOOD_FACTOR}))
        if week == 0:
            return out
        factor = float(actual.get("jakarta_lane_factor", 1.0))
        delivered, late = {}, {}
        for r in REGIONS:
            due = self.booked[week][r] + self.carry[r]
            cap = self.capacity(r, week, factor if r == "JKT" else None)
            d = min(due, cap)
            delivered[r], late[r] = d, due - d
            self.carry[r] = due - d
            if r == "JKT":
                self.util.append(min(1.0, due / LANES[r]["capacity"]))
            if due:
                self.store.insert("shipment", {"iso_week": iso_week(week), "lane": LANES[r]["name"],
                                               "pallets": math.ceil(d / PALLET), "units": d, "delayed_units": due - d,
                                               "status": "delivered" if d == due else "partly delayed"})
            self.store.insert("lane_capacity", {"iso_week": iso_week(week), "lane": r,
                                                "capacity_pallets": cap // PALLET, "booked_pallets": math.ceil(due / PALLET)})
        self.moved += sum(delivered.values())
        self.delayed_units += sum(late.values())
        if any(late.values()):
            self.decide("route_planner", f"{sum(late.values()):,} units delayed in {iso_week(week)}",
                        "The Jakarta lane runs at a quarter of its capacity: loads wait for the next week.",
                        outputs={"delivered": delivered, "delayed": late})
        out.append(self.send("route_planner", "kirana.fulfilment", "INFORM", "arrival",
                             {"week": week, "delivered": delivered, "delayed": late}))
        return out

    # ------------------------------------------------------------------ views
    def view(self):
        start = max(self.week + 1, 1)
        return {"rate_card": {r: {"per_pallet_idr": LANES[r]["price"] * PALLET, "lane": LANES[r]["name"]} for r in REGIONS}
                | {"surge": f"x{SURGE_FACTOR} above {SURGE_AT:.0%} of a lane"},
                "lane_capacity": {"unit": "pallet", "units_per_pallet": PALLET,
                                  "lanes": {r: {iso_week(w): self.capacity(r, w) // PALLET for w in range(start, WEEKS + 2)}
                                            for r in REGIONS}},
                "risk_notices": [{"iso_week": iso_week(w), "lane": "JKT", "probability": p,
                                  "expected_capacity_factor": FLOOD_FACTOR} for w, p in sorted(self.notices.items()) if w >= self.week],
                "express": {"route": self.express["id"], "capacity_units": self.express["capacity_units"],
                            "price_idr_per_unit": self.express["cost_idr_per_unit"]}}

    def kpis(self):
        revenue = self.ledger_total("transport") + self.ledger_total("express")
        cost = self.ledger_total("transport cost") + self.ledger_total("express cost")
        due = self.moved + self.delayed_units
        return {"units_moved": self.moved, "units_delayed": self.delayed_units,
                "on_time_rate": round(1 - self.delayed_units / due, 4) if due else None,
                "express_units": self.express_units,
                "jakarta_lane_utilisation": round(sum(self.util) / len(self.util), 4) if self.util else None,
                "revenue_idr": round(revenue), "costs_idr": round(-cost), "profit_idr": round(revenue + cost)}
