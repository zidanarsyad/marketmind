"""MaklonNusa: the cosmetics contract manufacturer ("maklon") that fills Kirana's moisturizer on two lines."""
from __future__ import annotations

import math
from collections import defaultdict

from ..governance import Governance, Role
from ..models import BreakdownModel
from ..negotiation import Tactic
from ..world import BATCH, WEEKS
from .base import Agent, Enterprise

CAPACITY_BATCHES = 5                 # two lines, five batches of 5,000 a week in all
# other clients' batches by week: private. They peak before 12.12 and before Ramadan, when every brand stocks up
OTHER_CLIENTS = {1: 2, 2: 2, 3: 3, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 2, 10: 2, 11: 2, 12: 3, 13: 3, 14: 3, 15: 3, 16: 2}
LIST_PRICE = 25_000
UNIT_COST = 16_500                   # formula, filling, labour and overhead per unit, packaging excluded
INITIAL_SETS = 20_000
QC_DETECTION = 0.90                  # incoming inspection finds nine in ten defective sets
PRICE_TACTIC = Tactic("unit_price", target=25_000, reservation=23_800, beta=0.6, deadline=8)
CLAIM_FACTOR = 1.5                   # a defective set found at incoming QC is charged back at 1.5x its price (sorting, handling)
DISCOUNT_TACTIC = Tactic("discount", target=0.15, reservation=0.05, beta=1.2, deadline=6)


class MaklonNusa(Enterprise):
    key = "maklonnusa"
    name = "MaklonNusa"
    industry = "Cosmetics contract manufacturer"
    city = "Cikarang"
    accent, accent_dark = "#4338ca", "#7d76e8"
    description = ("A BPOM-certified contract manufacturer that formulates and fills skincare for several local "
                   "brands on two filling lines, in batches of 5,000 units.")
    roles = (
        Role("Production Manager", "Schedules batches on the filling lines", datasets=(
            "LineCalendar", "BatchRecord", "LineRisk", "PackagingReceipt", "Quote", "decisions", "messages"),
            hidden_fields=("unitPrice",)),                 # knows the contract, not its price
        Role("Maintenance Engineer", "Keeps the lines running", datasets=("MaintenanceLog", "LineRisk", "LineCalendar")),
        Role("Sales", "Quotes prices and signs contracts", datasets=("Quote", "ledger", "messages", "decisions"),
             can_approve=True),
    )
    modules = (("Capacity planning", "Batch schedule on two lines"), ("Line reliability", "Breakdown prediction"),
               ("Quotation", "Prices and contracts"), ("Procurement", "Packaging sets from KemasPrima"),
               ("Incoming QC", "Inspects packaging deliveries"))
    platform = {"database": "SQLite (relational), PascalCase tables and camelCase columns", "api": "REST + JSON",
                "units": "batches of 5,000 units", "time": "simulation week number", "stack": "FastAPI on its own port"}
    governance = Governance(
        public=("priceList", "leadTimeWeeks"),
        partner=("freeCapacity",),
        control=("freeCapacity", "packagingSetsOnHand"),
        private=("MaintenanceLog", "LineCalendar", "ledger"),
        policies={"min_margin": 0.12, "batch_units": BATCH, "max_batches_per_week": CAPACITY_BATCHES},
        approval_threshold_idr=None)
    private_datasets = ("MaintenanceLog", "LineCalendar", "ledger")

    def make_agents(self):
        return [Agent("capacity_planner", "Capacity Planning Agent", "planning",
                      "Schedules Kirana's batches in free line capacity (FIFO backlog)"),
                Agent("line_reliability", "Line Reliability Agent", "predictive", "Predicts filling-line breakdowns",
                      BreakdownModel.name),
                Agent("quotation", "Quotation Agent", "negotiation", "Quotes and negotiates the unit price (Boulware)"),
                Agent("procurement", "Procurement Agent", "operations",
                      "Orders packaging sets; negotiates quality compensation with KemasPrima")]

    def setup(self):
        self.model = BreakdownModel(seed=self.seed + 13)
        self.store.insert_many("MaintenanceLog", self.model.history)
        self.scheduled: dict[int, int] = defaultdict(int)       # week -> Kirana units scheduled
        self.sets = INITIAL_SETS
        self.sets_ordered: dict[int, int] = {}                   # delivery week -> sets ordered from KemasPrima
        self.produced_week = 0
        self.escaped_pool = 0
        self.predicted_defect: dict[int, float] = {}
        self.risk: dict[int, float] = {}
        self.unit_price: float | None = None
        self.discount = 0.0
        self.inspection = False
        self.compensation_open = False
        self.produced = 0
        self.shortfall = 0
        self.scrapped = 0
        self.passed_on = 0
        self.plan: dict[int, dict] = {}

    def free_batches(self, week: int, lost: int = 0) -> int:
        """Free batches for Kirana in ``week``; a line its own reliability model expects to fail counts as lost."""
        used = math.ceil(self.scheduled.get(week, 0) / BATCH)
        at_risk = 2 if self.risk.get(week, 0.0) > 0.5 else 0
        return max(0, CAPACITY_BATCHES - OTHER_CLIENTS.get(week, 2) - max(lost, at_risk) - used)

    def available_for_kirana(self, week: int) -> int:
        return max(0, CAPACITY_BATCHES - OTHER_CLIENTS.get(week, 2)) * BATCH

    def _packaging_requests(self) -> list:
        """Order the packaging sets each scheduled week still lacks, for delivery at the start of that week.

        Sets on hand roll forward week by week; each week needs its scheduled units plus a defect buffer: the
        historical 1.5% (local), or KemasPrima's shared forecast for that week (ecosystem)."""
        out, stock = [], self.sets
        if self.produced_week < self.week:              # this week's batches have not used their sets yet
            stock = max(0, stock - self.scheduled.get(self.week, 0))
        for wk in range(self.week + 1, WEEKS + 1):
            need = self.scheduled.get(wk, 0)
            rate = self.predicted_defect.get(wk, 0.015) if self.mode == "ecosystem" else 0.015
            target = need / (1 - rate) * (1.02 if self.mode == "ecosystem" else 1.0)
            available = stock + self.sets_ordered.get(wk, 0)
            if need and target > available:
                order = math.ceil((target - available) / 1000) * 1000
                self.sets_ordered[wk] = self.sets_ordered.get(wk, 0) + order
                available += order
                why = (f"Covers W{wk}'s {need:,} units with a {rate:.1%} defect buffer"
                       + (" from KemasPrima's forecast." if rate > 0.015 else " (the usual rate)."))
                self.decide("procurement", f"Order {order:,} packaging sets for W{wk}", why, outputs={"sets": order})
                out.append(self.send("procurement", "kemasprima.sales", "REQUEST", "packaging_order",
                                     {"week": wk, "units": order}, reply_required=True))
            stock = max(0.0, available - target)
        return out

    def _schedule(self, start: int, units: int) -> dict[int, int]:
        """Put ``units`` into free capacity from ``start`` on, first come first served."""
        plan, left, w = {}, units, start
        while left > 0 and w <= WEEKS:
            take = min(left, self.free_batches(w) * BATCH)
            if take > 0:
                self.scheduled[w] += take
                plan[w] = plan.get(w, 0) + take
                left -= take
            w += 1
        return plan

    # ------------------------------------------------------------------ negotiation
    def on_request_price_list(self, m):
        return [self.reply(m, "quotation", "INFORM", {"unit_price": LIST_PRICE, "lead_time_weeks": 1, "batch_units": BATCH},
                           task="price_list")]

    def on_request_proposal_production_contract(self, m):
        self.decide("quotation", "Open the price negotiation at Rp 25,000",
                    "Boulware tactic: hold close to the list price, concede only near the deadline; the reservation "
                    "price (private) keeps the minimum margin.", refs=[m.message_id])
        return self.open_offer(m, PRICE_TACTIC, "unit_price", "quotation")

    def _set_price(self, value, basis):
        self.unit_price = float(value)
        self.store.insert("Quote", {"week": self.week, "client": "kirana", "unitPrice": self.unit_price, "basis": basis})
        self.decide("quotation", f"Contract with Kirana at Rp {self.unit_price:,.0f}", basis)

    def on_counter_proposal_production_contract(self, m):
        return self.negotiate(m, PRICE_TACTIC, float(m.payload["unit_price"]), "unit_price", "quotation",
                              lambda v: self._set_price(v, "accepted Kirana's counter-offer"),
                              lambda: self._set_price(LIST_PRICE, "no agreement: list price"), counter_type="PROPOSE")

    def on_accept_proposal_production_contract(self, m):
        self._set_price(m.payload["unit_price"], "Kirana accepted the offer")
        return []

    def on_reject_proposal_production_contract(self, m):
        self._set_price(LIST_PRICE, "no agreement: list price")
        return []

    # ------------------------------------------------------------------ orders and plans
    def on_request_production_order(self, m):
        week, units = int(m.payload["week"]), int(m.payload["units"])
        schedule = self._schedule(week, units)
        on_time = schedule.get(week, 0)
        why = ("All of it fits the free capacity of the week." if on_time >= units else
               f"Only {on_time:,} fit W{week} (other clients' batches come first); the rest goes to the next free weeks.")
        self.decide("capacity_planner", f"Schedule {units:,} units for Kirana", why,
                    inputs={"requested": units, "week": week}, outputs={str(k): v for k, v in schedule.items()},
                    refs=[m.message_id])
        return [self.reply(m, "capacity_planner", "AGREE", {"schedule": {str(k): v for k, v in schedule.items()},
                                                             "accepted_units": on_time, "requested_units": units}),
                *self._packaging_requests()]

    def on_propose_plan(self, m):
        rows = {int(r["week"]): r for r in m.payload["weeks"]}
        limits = {}
        for w, r in rows.items():
            b = r.get("batches")
            if b is None:
                continue
            cap = CAPACITY_BATCHES - OTHER_CLIENTS.get(w, 2)
            if self.risk.get(w, 0.0) > 0.5:
                cap = max(0, cap - 2)
            if b > cap:
                limits[str(w)] = cap
        if limits:
            self.decide("capacity_planner", f"Reject the plan: too many batches in {', '.join('W' + k for k in limits)}",
                        "My line reliability forecast (private) says filling line 2 is likely to fail; I can commit "
                        "only to the batches named, without sharing the maintenance data behind it.",
                        outputs={"max_batches": limits}, refs=[m.message_id])
            return [self.reply(m, "capacity_planner", "REJECT_PROPOSAL",
                               {"max_batches": limits, "reason": "line reliability forecast"})]
        self.decide("capacity_planner", "Accept the plan", "Every week fits my free capacity.", refs=[m.message_id])
        return [self.reply(m, "capacity_planner", "ACCEPT_PROPOSAL", {})]

    def on_confirm_plan(self, m):
        self.plan = {int(r["week"]): r for r in m.payload["weeks"]}
        return []

    # ------------------------------------------------------------------ packaging
    def on_inform_packaging_delivery(self, m):
        units = int(m.payload["units"])
        self.sets_ordered.pop(int(m.payload["week"]), None)
        defective = int(m.payload.get("physical", {}).get("defective_sets", 0))
        detected = round(defective * QC_DETECTION)
        self.sets += units - detected
        self.escaped_pool += defective - detected
        self.scrapped += detected
        self.book("kemasprima", "packaging", -m.payload["invoice_idr"], units)
        self.store.insert("PackagingReceipt", {"week": self.week, "setsReceived": units, "defectsDetected": detected,
                                               "setsScrapped": detected, "inspectedBySupplier": bool(m.payload.get("inspected"))})
        if detected:
            claim = round(detected * m.payload["invoice_idr"] / max(units, 1) * CLAIM_FACTOR)
            self.book("kemasprima", "defect claims", claim, detected)
            self.decide("procurement", f"Scrap {detected:,} defective sets and claim Rp {claim:,}",
                        f"Incoming inspection found {detected:,} of {units:,} sets defective (charged back at "
                        f"{CLAIM_FACTOR}x their price under the supply contract); about one in ten defects goes "
                        "unnoticed and ends up in filled units.", inputs={"received": units}, refs=[m.message_id])
            return [self.send("procurement", "kemasprima.sales", "INFORM", "defect_claim",
                              {"week": self.week, "sets": detected, "amount_idr": claim})]
        return []

    def on_agree_packaging_order(self, m):
        w = int(m.payload["week"])
        asked = int(m.payload.get("requested_units", m.payload["accepted_units"]))
        short = asked - int(m.payload["accepted_units"])
        if short > 0:
            self.sets_ordered[w] = max(0, self.sets_ordered.get(w, 0) - short)
        return []

    def on_inform_defect_risk(self, m):
        w, rate = int(m.payload["week"]), float(m.payload["expected_defect_rate"])
        self.predicted_defect[w] = rate
        self.decide("procurement", f"Expect {rate:.1%} defective sets in W{w}",
                    "KemasPrima shared its QC forecast: order a defect buffer and ask for compensation.", refs=[m.message_id])
        out = self._packaging_requests()
        if rate > 0.03 and not self.compensation_open:
            self.compensation_open = True
            out.append(self.send("procurement", "kemasprima.sales", "REQUEST_PROPOSAL", "quality_compensation",
                                 {"expected_defect_rate": rate, "week": w}, reply_required=True))
        return out

    def _set_compensation(self, discount, inspection, basis):
        self.discount, self.inspection = float(discount), bool(inspection)
        self.decide("procurement", f"Quality agreement: {self.discount:.0%} discount"
                    + (", 100% inspection at KemasPrima" if self.inspection else ""), basis)

    def on_propose_quality_compensation(self, m):
        return self.negotiate(m, DISCOUNT_TACTIC, float(m.payload["discount"]), "discount", "procurement",
                              lambda v: self._set_compensation(v, m.payload.get("inspection", True), "accepted KemasPrima's offer"),
                              lambda: self._set_compensation(0.0, False, "no agreement"),
                              counter_type="COUNTER_PROPOSAL", decimals=4)

    def on_accept_proposal_quality_compensation(self, m):
        self._set_compensation(m.payload["discount"], m.payload.get("inspection", True), "KemasPrima accepted the counter-offer")
        return []

    def on_reject_proposal_quality_compensation(self, m):
        self._set_compensation(0.0, False, "no agreement")
        return []

    # ------------------------------------------------------------------ the week
    def on_tick(self, week, leading, actual):
        out = []
        if week == 0:
            return out
        for reading in leading.get("weeks", []):
            w, line2 = int(reading["week"]), reading["lines"][1]
            risk = self.model.predict(line2)
            known = self.risk.get(w, 0.0) > 0.5
            self.risk[w] = risk
            self.store.insert("LineRisk", {"week": w, "lineNo": 2, "vibrationMmS": line2["vibration_mm_s"],
                                           "hoursSinceService": line2["hours_since_service"], "pBreakdown": risk})
            if risk > 0.5 and not known:
                self.decide("line_reliability", f"Line 2 likely to fail in W{w} (p = {risk:.0%})",
                            "Vibration and hours since service are far above normal.", inputs=line2)
                if self.mode == "ecosystem":
                    out.append(self.send("line_reliability", "control.coordinator", "INFORM", "capacity_risk",
                                         {"week": w, "probability": risk}))
        lost = int(actual.get("batches_lost", 0))
        cap_units = max(0, CAPACITY_BATCHES - OTHER_CLIENTS.get(week, 2) - lost) * BATCH
        want = self.scheduled.get(week, 0)
        produced = min(want, cap_units, self.sets)
        short = want - produced
        rescheduled = {}
        if short:
            self.scheduled[week] = produced
            rescheduled = self._schedule(week + 1, short)
            reason = (f"filling line 2 broke down ({lost} batches lost)" if lost and cap_units < want
                      else "not enough good packaging sets")
            self.decide("capacity_planner", f"Short {short:,} units in W{week}: {reason}",
                        f"Rescheduled to {', '.join(f'W{k}' for k in rescheduled) or 'no week (beyond the horizon)'}.",
                        outputs={"rescheduled": {str(k): v for k, v in rescheduled.items()}})
            notify = ["kirana.supply_planner"] + (["control.coordinator"] if self.mode == "ecosystem" else [])
            for to in notify:
                out.append(self.send("capacity_planner", to, "INFORM", "capacity_change",
                                     {"week": week, "shortfall": short, "reason": reason}))
        escaped = round(produced * self.escaped_pool / self.sets) if self.sets else 0
        self.escaped_pool -= escaped
        self.sets -= produced
        self.produced_week = week
        self.produced += produced
        self.shortfall += short
        self.passed_on += escaped
        price = self.unit_price or LIST_PRICE
        if produced:
            self.book("kirana", "sales", produced * price, produced)
            self.book("own plant", "production cost", -produced * UNIT_COST, produced)
        self.store.insert("LineCalendar", {"week": week, "totalBatches": CAPACITY_BATCHES,
                                           "otherClientBatches": OTHER_CLIENTS.get(week, 2), "lostBatches": lost,
                                           "kiranaUnits": produced})
        self.store.insert("BatchRecord", {"week": week, "unitsProduced": produced, "setsUsed": produced,
                                          "escapedDefects": escaped})
        out.append(self.send("capacity_planner", "kirana.supply_planner", "INFORM", "goods_ready",
                             {"week": week, "units": produced, "shortfall": short,
                              "rescheduled": {str(k): v for k, v in rescheduled.items()}, "escaped_defects": escaped,
                              "invoice_idr": produced * price}))
        if rescheduled:
            out.extend(self._packaging_requests())
        return out

    # ------------------------------------------------------------------ views
    def view(self):
        """camelCase, capacity in batches: MaklonNusa's own API style (the Control Center's adapter converts it)."""
        start = max(self.week + 1, 1)
        return {"priceList": {"unitPrice": LIST_PRICE, "batchUnits": BATCH}, "leadTimeWeeks": 1,
                "freeCapacity": {"batchUnits": BATCH, "batchesByWeek": {
                    str(w): self.available_for_kirana(w) // BATCH for w in range(start, WEEKS + 1)}},
                "packagingSetsOnHand": self.sets}

    def kpis(self):
        weeks = max(1, min(self.week, WEEKS))
        kirana_batches = self.produced / BATCH
        others = sum(OTHER_CLIENTS.get(w, 2) for w in range(1, weeks + 1))
        revenue = self.ledger_total("sales") + self.ledger_total("defect claims")
        costs = self.ledger_total("production cost") + self.ledger_total("packaging")
        return {"units_produced": self.produced, "shortfall_units": self.shortfall,
                "utilization": round((kirana_batches + others) / (CAPACITY_BATCHES * weeks), 4),
                "unit_price_idr": self.unit_price, "revenue_idr": round(revenue), "costs_idr": round(-costs),
                "sets_scrapped": self.scrapped, "defects_passed_on": self.passed_on,
                "profit_idr": round(revenue + costs)}
