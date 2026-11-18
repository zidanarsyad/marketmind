"""Kirana Beauty: the local skincare brand launching the barrier-repair moisturizer (MarketMind's client)."""
from __future__ import annotations

import math
from collections import defaultdict

from ..governance import Governance, Role
from ..models import DemandForecaster
from ..negotiation import Tactic, rank_options
from ..protocol import Message
from ..world import BATCH, CAMPAIGN_WEEKS, PRICE, PRODUCT, REGION_SHARE, REGIONS, SKU, WEEKS
from .base import Agent, Enterprise

INITIAL_STOCK = {"JKT": 18_000, "SBY": 8_000}
LIST_PRICE = 25_000                 # MaklonNusa's list price, paid when there is no negotiated contract
STANDARD_SHARE = 0.60               # PasarNusa's standard share of a campaign voucher the brand pays
VOUCHER = 0.10
COMMISSION, CAMPAIGN_FEE, DIRECT_CHANNEL_COST = 0.08, 0.02, 0.05
RETURN_COST = 25_000                # a defective pump that reaches a customer: refund, shipping, a complaint
HOLDING = 150
CONTRACT_VOLUME = 200_000           # units over the season, the basis of the production contract
PRICE_TACTIC = Tactic("unit_price", target=22_000, reservation=24_800, beta=1.4, deadline=8)
SHARE_TACTIC = Tactic("brand_share", target=0.30, reservation=0.60, beta=1.2, deadline=6)
REROUTE_WEIGHTS = {"cost_idr_per_unit": 0.3, "delay_days": 0.2, "risk": 0.5}   # in a flood, getting through matters most


class Kirana(Enterprise):
    key = "kirana"
    name = "Kirana Beauty"
    industry = "Local skincare brand"
    city = "Bandung"
    accent, accent_dark = "#b4235f", "#d6578f"
    description = ("An Indonesian local skincare brand launching a fragrance-free barrier-repair moisturizer at "
                   "Rp 79,900, sold on PasarNusa and through its own channels.")
    roles = (
        Role("Supply Planner", "Plans production orders, shipments and stock", datasets=(
            "forecasts", "inventory", "fulfilment", "contracts", "product", "decisions", "messages"),
            hidden_fields=("value",)),                     # sees the contracts, not the negotiated price
        Role("Brand Manager", "Owns the launch, the campaigns and the forecast", datasets=(
            "forecasts", "fulfilment", "campaigns", "product", "ledger", "decisions", "messages"),
            hidden_fields=("amount_idr",)),                # sees what was settled, not the amounts
        Role("Finance", "Approves contracts above Rp 2 bn; owns the ledger", can_approve=True),
    )
    modules = (("Demand planning", "Weekly forecast by region"), ("Supply planning", "Production orders and shipments"),
               ("Procurement", "Contract with the contract manufacturer"), ("Channel", "Campaign terms with PasarNusa"),
               ("Fulfilment", "Customer orders from each warehouse"), ("Finance", "Ledger and approvals"))
    platform = {"database": "SQLite (relational)", "api": "REST + JSON, snake_case", "units": "pieces (pcs)",
                "time": "simulation week number", "stack": "FastAPI on its own port"}
    governance = Governance(
        public=("product", "campaign_participation"),
        partner=("demand_forecast", "commitments"),
        control=("demand_forecast", "inventory", "in_transit", "factory_stock", "locked_production", "unit_price",
                 "margin_per_unit", "commitments", "campaign_participation", "fill_rate_to_date", "reroute"),
        private=("ledger", "contracts"),
        policies={"service_level_target": 0.95, "max_unit_price_idr": PRICE_TACTIC.reservation,
                  "max_brand_voucher_share": SHARE_TACTIC.reservation},
        approval_threshold_idr=2_000_000_000)
    private_datasets = ("ledger", "contracts")

    def make_agents(self):
        return [Agent("demand_planner", "Demand Planning Agent", "predictive", "Forecasts weekly demand by region",
                      DemandForecaster.name),
                Agent("supply_planner", "Supply Planning Agent", "planning",
                      "Order-up-to policy (local) or follows the confirmed ecosystem plan"),
                Agent("procurement", "Procurement Agent", "negotiation",
                      "Negotiates the unit price with MaklonNusa (alternating offers)"),
                Agent("channel_manager", "Channel Agent", "negotiation",
                      "Negotiates campaign voucher co-funding with PasarNusa"),
                Agent("fulfilment", "Fulfilment Agent", "operations", "Serves customer orders from each warehouse"),
                Agent("finance", "Finance Agent", "monitoring", "Books settlements; signs off contracts above the threshold")]

    # ------------------------------------------------------------------ state
    def setup(self):
        self.inventory = dict(INITIAL_STOCK)
        self.in_transit: dict[int, dict[str, int]] = defaultdict(lambda: {r: 0 for r in REGIONS})
        self.ready = 0
        self.pending: dict[int, int] = defaultdict(int)
        self.escaped = 0
        self.unit_price: float | None = None
        self.share: dict[str, float] = {}
        self.joined: dict[str, bool] = {}
        self.campaigns: dict[str, list[int]] = {}
        self.commitments: dict[int, int] = {}
        self.intel: dict | None = None
        self.lift: dict[str, float] = {}
        self.plan: dict[int, dict] = {}
        self.plan_revision = 0
        self.express_booked: dict[int, int] = defaultdict(int)
        self.express_left = 0
        self.forecaster = DemandForecaster()
        self.forecast: dict[int, float] = {}
        self.orders_seen: dict[int, int] = defaultdict(int)
        self.served: dict[int, int] = defaultdict(int)
        self.lost: dict[int, int] = defaultdict(int)
        self.reroute: dict | None = None
        self.store.insert("product", {"sku": SKU, "name": PRODUCT, "price_idr": PRICE, "launch": "W1",
                                      "positioning": "fragrance-free barrier repair, Gentle Glow Seekers"})
        self._snapshot()

    def _snapshot(self):
        self.store.insert("inventory", {"week": self.week, "JKT": self.inventory["JKT"], "SBY": self.inventory["SBY"],
                                        "at_factory": self.ready,
                                        "in_transit": sum(sum(v.values()) for k, v in self.in_transit.items() if k > self.week)})

    def _campaign_of(self, week: int) -> str | None:
        name = CAMPAIGN_WEEKS.get(week)
        return name if name and self.joined.get(name) else None

    # ------------------------------------------------------------------ forecasting and planning
    def forecast_total(self, week: int) -> float:
        if self.mode == "ecosystem" and self.intel:
            return self.forecaster.ecosystem(week, self.intel, self.lift)
        return self.forecaster.local(week, CAMPAIGN_WEEKS)

    def demand_forecast(self) -> dict:
        start = max(self.week, 1)
        return {r: {str(w): round(self.forecast_total(w) * REGION_SHARE[r]) for w in range(start, WEEKS + 1)}
                for r in REGIONS}

    def margin_per_unit(self) -> float:
        price = self.unit_price or LIST_PRICE
        return round(PRICE * (1 - COMMISSION - 0.6 * VOUCHER * 0.25) - price - 600)

    def local_order(self, week: int) -> int:
        """Order-up-to on its own forecast: cover the three weeks the order will sell into (the public campaign
        calendar raises its own guess for campaign weeks)."""
        cover = sum(self.forecaster.local(w, CAMPAIGN_WEEKS) for w in range(week, week + 3))
        position = (sum(self.inventory.values()) + sum(sum(v.values()) for k, v in self.in_transit.items() if k >= self.week)
                    + self.ready + sum(u for w, u in self.pending.items() if w >= self.week))
        need = max(0.0, cover - position)
        units = math.ceil(need / BATCH) * BATCH
        self.decide("supply_planner", f"Order {units:,} units for W{week}",
                    f"Order-up-to: my own forecast for W{week}-W{week + 2} is {cover:,.0f} units (moving average of "
                    f"my orders, +{DemandForecaster.RULE_OF_THUMB_LIFT:.0%} rule of thumb in campaign weeks); "
                    f"{position:,.0f} are on hand, in transit or on order.",
                    inputs={"cover": round(cover), "position": round(position)}, outputs={"units": units})
        return units

    def plan_order(self, week: int) -> int:
        row = self.plan.get(week)
        if row is None:
            return self.local_order(week)
        units = int(row["production"])
        self.decide("supply_planner", f"Order {units:,} units for W{week} (plan rev. {self.plan_revision})",
                    "Follows the ecosystem plan every partner accepted.", outputs={"units": units})
        return units

    # ------------------------------------------------------------------ the week
    def on_tick(self, week, leading, actual):
        out: list[Message] = []
        if week == 0:
            if self.mode == "ecosystem":
                out.append(self.send("demand_planner", "research.insight_service", "REQUEST", "market_intelligence",
                                     {"sku": SKU, "price_idr": PRICE, "horizon_weeks": WEEKS}, reply_required=True))
                out.append(self.send("procurement", "maklonnusa.quotation", "REQUEST_PROPOSAL", "production_contract",
                                     {"sku": SKU, "volume_units": CONTRACT_VOLUME, "weeks": WEEKS}, reply_required=True))
            else:
                out.append(self.send("procurement", "maklonnusa.quotation", "REQUEST", "price_list", {"sku": SKU},
                                     reply_required=True))
                out.append(self._production_order(1, self.local_order(1)))
            return out
        f = self.forecast_total(week)
        self.forecast[week] = f
        self.store.insert("forecasts", {"week": week, "units": round(f), "method": "ecosystem" if (
            self.mode == "ecosystem" and self.intel) else "local moving average", "scale": round(self.forecaster.scale, 3)})
        if week < WEEKS:
            units = self.plan_order(week + 1) if self.mode == "ecosystem" else self.local_order(week + 1)
            if units > 0:
                out.append(self._production_order(week + 1, units))
        if self.ready > 0:
            out.append(self._book_shipment(week))
        self.express_left = 0
        if self.mode == "ecosystem":
            want = int(self.plan.get(week, {}).get("express", 0))
            if want > 0:
                out.append(self.send("supply_planner", "kirimcepat.booking", "REQUEST", "express",
                                     {"week": week, "units": want}, reply_required=True))
        return out

    def _production_order(self, week: int, units: int) -> Message:
        return self.send("supply_planner", "maklonnusa.capacity_planner", "REQUEST", "production_order",
                         {"week": week, "units": units, "sku": SKU}, reply_required=True)

    def _book_shipment(self, week: int) -> Message:
        total = self.ready
        if self.mode == "ecosystem" and week in self.plan:
            row = self.plan[week]
            planned = {r: int(row.get(f"ship_{r}", 0)) for r in REGIONS}
            want = sum(planned.values())
            if want > total and want > 0:
                planned = {r: int(total * planned[r] / want) for r in REGIONS}
            elif total > want:
                planned["JKT"] += total - want
            split = planned
            why = f"Ships what plan rev. {self.plan_revision} sends to each warehouse."
        else:
            jkt = int(round(total * REGION_SHARE["JKT"]))
            split = {"JKT": jkt, "SBY": total - jkt}
            why = "Ships everything ready, split by each region's share of demand."
        self.decide("supply_planner", f"Book {sum(split.values()):,} units with KirimCepat", why, outputs=split)
        return self.send("supply_planner", "kirimcepat.booking", "REQUEST", "shipment_booking",
                         {"week": week, "units": split}, reply_required=True)

    def on_end_week(self, week):
        out = []
        if week >= 1:
            observed = self.orders_seen[week]
            f = self.forecast.get(week)
            change = self.forecaster.observe(week, observed, f if self.mode == "ecosystem" and self.intel else None)
            if self.mode == "ecosystem" and f and abs(observed - f) / f > 0.12:
                self.decide("demand_planner", f"Revise the forecast (scale {self.forecaster.scale:.2f})",
                            f"W{week} orders were {observed:,} against a forecast of {f:,.0f}.",
                            inputs={"observed": observed, "forecast": round(f)}, outputs={"scale_change": round(change, 3)})
                out.append(self.send("demand_planner", "control.coordinator", "INFORM", "forecast_revision",
                                     {"week": week, "observed": observed, "forecast": round(f),
                                      "scale": round(self.forecaster.scale, 3)}))
            stock = sum(self.inventory.values())
            if stock:
                self.book("warehouse", "holding", -stock * HOLDING, stock)
            self._snapshot()
        return out

    # ------------------------------------------------------------------ fulfilment
    def _fulfil(self, week: int, orders: dict, channel: str) -> tuple[dict, dict]:
        served, lost = {}, {}
        for r in REGIONS:
            want = int(orders.get(r, 0))
            s = min(want, self.inventory[r])
            self.inventory[r] -= s
            if r == "JKT" and want > s and self.express_left > 0:
                e = min(want - s, self.express_left, self.inventory["SBY"])
                if e > 0:
                    self.inventory["SBY"] -= e
                    self.express_left -= e
                    s += e
                    self.book("kirimcepat", "express", -e * (self.reroute or {}).get("cost_idr_per_unit", 1_800), e)
                    self._express_used = getattr(self, "_express_used", 0) + e
            served[r], lost[r] = s, want - s
        total_served = sum(served.values())
        self.orders_seen[week] += sum(int(orders.get(r, 0)) for r in REGIONS)
        self.served[week] += total_served
        self.lost[week] += sum(lost.values())
        stock_before = sum(self.inventory.values()) + total_served
        if self.escaped and stock_before:
            returned = min(self.escaped, round(total_served * self.escaped / stock_before))
            if returned:
                self.escaped -= returned
                self.book("customers", "returns", -returned * RETURN_COST, returned, "defective pump returned")
        self.store.insert("fulfilment", {"week": week, "channel": channel, **{f"orders_{r}": int(orders.get(r, 0)) for r in REGIONS},
                                         **{f"served_{r}": served[r] for r in REGIONS}, **{f"lost_{r}": lost[r] for r in REGIONS}})
        return served, lost

    def on_request_fulfil_orders(self, m):
        served, lost = self._fulfil(m.week, m.payload["orders"], "marketplace")
        self.decide("fulfilment", f"Serve {sum(served.values()):,} PasarNusa orders, {sum(lost.values()):,} lost",
                    "Each region from its own warehouse; Jakarta also by express from Surabaya when booked.",
                    inputs={"orders": m.payload["orders"]}, outputs={"served": served, "lost": lost}, refs=[m.message_id])
        msgs = [self.reply(m, "fulfilment", "INFORM", {"week": m.week, "served": served, "lost": lost}, task="fulfilment")]
        used = getattr(self, "_express_used", 0)
        if used:
            msgs.append(self.send("fulfilment", "kirimcepat.booking", "INFORM", "express_used", {"week": m.week, "units": used}))
            self._express_used = 0
        return msgs

    def on_inform_customer_orders(self, m):
        served, lost = self._fulfil(m.week, m.payload["orders"], "direct")
        revenue = sum(served.values()) * PRICE * (1 - DIRECT_CHANNEL_COST)
        self.book("customers", "direct sales", revenue, sum(served.values()))
        used = getattr(self, "_express_used", 0)
        if used:
            self._express_used = 0
            return [self.send("fulfilment", "kirimcepat.booking", "INFORM", "express_used", {"week": m.week, "units": used})]
        return []

    # ------------------------------------------------------------------ partners' messages
    def on_inform_market_intelligence(self, m):
        self.intel = m.payload
        fee = m.payload.get("fee_idr", 0)
        if fee:
            self.book("research", "market intelligence", -fee)
        self.decide("demand_planner", "Adopt MarketMind's demand baseline",
                    f"{m.payload['base_weekly_units']:,} units/week at maturity, from {m.payload.get('source', 'research')}.",
                    inputs={k: m.payload[k] for k in ("base_weekly_units", "source") if k in m.payload}, refs=[m.message_id])
        return []

    def on_inform_demand_signal(self, m):
        """PasarNusa's live traffic: raise this campaign week's lift before its orders arrive."""
        w, extra = int(m.payload["week"]), float(m.payload["extra_uplift"])
        if not (self.intel and self._campaign_of(w)):
            return []
        before = self.forecast_total(w)
        self.lift[str(w)] = round(self.lift.get(str(w), 0.0) + extra, 4)
        after = self.forecast_total(w)
        self.decide("demand_planner", f"Raise the W{w} forecast by {after - before:,.0f} units",
                    f"PasarNusa reports live {m.payload.get('campaign', 'campaign')} traffic {extra:.0%} above its lift "
                    "forecast; the Control Center gets the new figure in my shared forecast.",
                    inputs=m.payload, outputs={"before": round(before), "after": round(after)}, refs=[m.message_id])
        return []

    def on_inform_price_list(self, m):
        self.unit_price = float(m.payload["unit_price"])
        self.store.insert("contracts", {"week": self.week, "counterparty": "maklonnusa", "term": "unit_price",
                                        "value": self.unit_price, "basis": "list price (no negotiation)"})
        self.decide("procurement", f"Buy at the list price Rp {self.unit_price:,.0f}",
                    "Local mode: no negotiation, the supplier's list price applies.", refs=[m.message_id])
        return []

    def _negotiate(self, m: Message, tactic: Tactic, value: float, issue: str, agent: str, done, fallback):
        return self.negotiate(m, tactic, value, issue, agent, done, fallback, counter_type="COUNTER_PROPOSAL",
                              decimals=4 if issue == "brand_share" else 0)

    def _set_price(self, value: float, basis: str):
        self.unit_price = float(value)
        total = self.unit_price * CONTRACT_VOLUME
        self.store.insert("contracts", {"week": self.week, "counterparty": "maklonnusa", "term": "unit_price",
                                        "value": self.unit_price, "basis": basis})
        approval = (f" Contract value Rp {total / 1e9:,.1f} bn is above the Rp 2 bn threshold: signed off by the Finance "
                    "role under policy (simulated).") if total > (self.governance.approval_threshold_idr or 0) else ""
        self.decide("procurement", f"Contract at Rp {self.unit_price:,.0f} per unit", basis + "." + approval,
                    outputs={"unit_price": self.unit_price})

    def on_propose_production_contract(self, m):
        return self._negotiate(m, PRICE_TACTIC, float(m.payload["unit_price"]), "unit_price", "procurement",
                               lambda v: self._set_price(v, "accepted MaklonNusa's offer"),
                               lambda: self._set_price(LIST_PRICE, "no agreement: list price"))

    def on_accept_proposal_production_contract(self, m):
        self._set_price(m.payload["unit_price"], "MaklonNusa accepted the counter-offer")
        return []

    def on_reject_proposal_production_contract(self, m):
        self._set_price(LIST_PRICE, "no agreement: list price")
        return []

    def on_inform_campaign_announcement(self, m):
        self.campaigns = {c["name"]: c["weeks"] for c in m.payload["campaigns"]}
        self.commitments = {int(k): v for k, v in m.payload.get("stock_commitments", {}).items()}
        if self.mode == "ecosystem":
            self.lift = {str(k): v for k, v in m.payload.get("uplift_forecast", {}).items()}
            return [self.send("channel_manager", "pasarnusa.campaign_planner", "REQUEST_PROPOSAL", "campaign_terms",
                              {"campaigns": list(self.campaigns), "voucher_depth": VOUCHER}, reply_required=True)]
        return [self.send("channel_manager", "pasarnusa.campaign_planner", "REQUEST", "join_campaign",
                          {"campaigns": list(self.campaigns), "terms": "standard"}, reply_required=True)]

    def _join(self, share: float, basis: str):
        for c in self.campaigns:
            self.joined[c], self.share[c] = True, float(share)
        self.store.insert("campaigns", {"week": self.week, "campaigns": list(self.campaigns), "brand_share": share,
                                        "commitments": {str(k): v for k, v in self.commitments.items()}, "basis": basis})
        self.decide("channel_manager", f"Join {', '.join(self.campaigns)} paying {share:.0%} of the voucher", basis + ".",
                    outputs={"brand_share": share})

    def on_propose_campaign_terms(self, m):
        return self._negotiate(m, SHARE_TACTIC, float(m.payload["brand_share"]), "brand_share", "channel_manager",
                               lambda v: self._join(v, "accepted PasarNusa's offer"),
                               lambda: self._join(STANDARD_SHARE, "no agreement: standard terms"))

    def on_accept_proposal_campaign_terms(self, m):
        self._join(m.payload["brand_share"], "PasarNusa accepted the counter-offer")
        return []

    def on_reject_proposal_campaign_terms(self, m):
        self._join(STANDARD_SHARE, "no agreement: standard terms")
        return []

    def on_agree_join_campaign(self, m):
        self._join(m.payload.get("brand_share", STANDARD_SHARE), "standard terms (local mode, no negotiation)")
        return []

    def on_agree_production_order(self, m):
        for w, u in m.payload["schedule"].items():
            self.pending[int(w)] += int(u)
        if m.payload["accepted_units"] < m.payload["requested_units"]:
            self.decide("supply_planner", "Order only partly scheduled on time",
                        f"MaklonNusa scheduled {m.payload['schedule']} for {m.payload['requested_units']:,} requested.",
                        inputs=m.payload, refs=[m.message_id])
        return []

    def on_inform_goods_ready(self, m):
        w, units = int(m.payload["week"]), int(m.payload["units"])
        self.ready += units
        self.pending[w] = max(0, self.pending[w] - units - int(m.payload.get("shortfall", 0)))
        for wk, u in m.payload.get("rescheduled", {}).items():
            self.pending[int(wk)] += int(u)
        self.escaped += int(m.payload.get("escaped_defects", 0))
        if units:
            self.book("maklonnusa", "production", -units * (self.unit_price or LIST_PRICE), units)
        return []

    def on_agree_shipment_booking(self, m):
        acc = m.payload["accepted"]
        self.ready -= sum(acc.values())
        for r, u in acc.items():
            self.in_transit[m.week + 1][r] += int(u)
        self.book("kirimcepat", "transport", -m.payload["charge_idr"], sum(acc.values()))
        return []

    def on_inform_arrival(self, m):
        w = int(m.payload["week"])
        for r in REGIONS:
            d = int(m.payload["delivered"].get(r, 0))
            late = int(m.payload.get("delayed", {}).get(r, 0))
            self.inventory[r] += d
            self.in_transit[w][r] = 0
            if late:
                self.in_transit[w + 1][r] += late
        return []

    def on_agree_express(self, m):
        self.express_booked[m.week] = int(m.payload["units"])
        self.express_left = int(m.payload["units"])
        return []

    def on_propose_plan(self, m):
        fill = m.payload.get("planned_fill_rate", 1.0)
        note = ("meets the service target" if fill >= self.governance.policies["service_level_target"]
                else "below the service target, but the partners' capacity allows no more")
        self.decide("supply_planner", f"Accept plan proposal (planned fill rate {fill:.1%})", note, refs=[m.message_id])
        return [self.reply(m, "supply_planner", "ACCEPT_PROPOSAL", {"planned_fill_rate": fill})]

    def on_confirm_plan(self, m):
        self.plan = {int(r["week"]): r for r in m.payload["weeks"]}
        self.plan_revision = int(m.payload["revision"])
        self.decide("supply_planner", f"Adopt ecosystem plan rev. {self.plan_revision}",
                    m.payload.get("reason", "confirmed by every partner"), refs=[m.message_id])
        if self.week == 0 and 1 in self.plan and self.plan[1]["production"] > 0:
            return [self._production_order(1, int(self.plan[1]["production"]))]
        return []

    def on_inform_flood_risk(self, m):
        self.decide("supply_planner", f"Flood risk for W{m.payload['week']} noted",
                    f"KirimCepat puts the chance at {m.payload['probability']:.0%}.", inputs=m.payload, refs=[m.message_id])
        if self.reroute is None:
            self.reroute = {"pending": True}
            return [self.send("supply_planner", "kirimcepat.booking", "REQUEST_PROPOSAL", "reroute_options",
                              {"weeks": m.payload.get("weeks", [m.payload["week"]])}, reply_required=True)]
        return []

    def on_propose_reroute_options(self, m):
        ranked = rank_options(m.payload["options"], REROUTE_WEIGHTS)
        best = ranked[0]
        self.reroute = best
        self.decide("supply_planner", f"Choose '{best['id']}' to reach Jakarta during the flood",
                    "Contract Net: proposals ranked on risk (50%), cost (30%) and delay (20%).",
                    inputs={"options": ranked}, outputs={"chosen": best["id"]}, refs=[m.message_id])
        return [self.reply(m, "supply_planner", "ACCEPT_PROPOSAL", {"option": best["id"]})]

    def on_inform_settlement(self, m):
        p = m.payload
        self.book("pasarnusa", "marketplace payout", p["gmv_idr"], p["units"])
        self.book("pasarnusa", "commission", -p["commission_idr"])
        if p.get("voucher_brand_idr"):
            self.book("pasarnusa", "voucher co-funding", -p["voucher_brand_idr"])
        return []

    def on_inform_sla_report(self, m):
        self.decide("channel_manager", f"PasarNusa fill rate {m.payload['fill_rate']:.1%} in W{m.payload['week']}",
                    m.payload.get("consequence", ""), inputs=m.payload, refs=[m.message_id])
        return []

    def on_inform_capacity_change(self, m):
        self.decide("supply_planner", "MaklonNusa capacity change noted", m.payload.get("reason", ""), inputs=m.payload,
                    refs=[m.message_id])
        return []

    # ------------------------------------------------------------------ views
    def view(self):
        demand = sum(self.orders_seen.values())
        served = sum(self.served.values())
        return {"product": {"sku": SKU, "name": PRODUCT, "price_idr": PRICE},
                "campaign_participation": {c: self.joined.get(c, False) for c in self.campaigns},
                "demand_forecast": self.demand_forecast(), "commitments": {str(k): v for k, v in self.commitments.items()},
                "inventory": dict(self.inventory),
                "in_transit": {str(k): dict(v) for k, v in self.in_transit.items() if k >= max(self.week, 1)},
                "factory_stock": self.ready, "locked_production": {str(k): v for k, v in self.pending.items() if v},
                "unit_price": self.unit_price or LIST_PRICE, "margin_per_unit": self.margin_per_unit(),
                "fill_rate_to_date": round(served / demand, 4) if demand else None,
                "reroute": ({k: self.reroute[k] for k in ("id", "cost_idr_per_unit", "capacity_units", "delay_days")}
                            if self.reroute and "id" in self.reroute else None)}

    def kpis(self):
        demand = sum(self.orders_seen.values())
        served = sum(self.served.values())
        lost = sum(self.lost.values())
        money = {item: self.ledger_total(item) for item in (
            "marketplace payout", "direct sales", "commission", "voucher co-funding", "production", "transport",
            "express", "holding", "returns", "market intelligence")}
        stock = sum(self.inventory.values()) + self.ready + sum(sum(v.values()) for k, v in self.in_transit.items() if k > self.week)
        stock_value = stock * (self.unit_price or LIST_PRICE)
        revenue = money["marketplace payout"] + money["direct sales"]
        profit = sum(money.values()) + stock_value
        return {"demand_units": demand, "served_units": served, "lost_units": lost,
                "fill_rate": round(served / demand, 4) if demand else None,
                "stockout_weeks": sum(1 for w, n in self.lost.items() if n > 0),
                "revenue_idr": round(revenue), "cogs_idr": round(-money["production"]),
                "logistics_idr": round(-(money["transport"] + money["express"])),
                "marketplace_fees_idr": round(-(money["commission"] + money["voucher co-funding"])),
                "returns_idr": round(-money["returns"]), "holding_idr": round(-money["holding"]),
                "research_fee_idr": round(-money["market intelligence"]),
                "unit_price_idr": self.unit_price, "ending_stock_units": stock, "profit_idr": round(profit)}
