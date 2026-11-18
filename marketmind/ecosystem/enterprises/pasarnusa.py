"""PasarNusa: the e-commerce marketplace where three quarters of Kirana's customers buy. Its data lives in JSON
documents (a document store), not in relational tables like the other enterprises'."""
from __future__ import annotations

from ..governance import Governance, Role
from ..models import UpliftModel
from ..negotiation import Tactic
from ..world import CAMPAIGN_WEEKS, CAMPAIGNS, PRICE, REGIONS
from .base import Agent, Enterprise

COMMISSION, CAMPAIGN_FEE, VOUCHER = 0.08, 0.02, 0.10
STANDARD_SHARE = 0.60
STOCK_COMMITMENTS = {3: 18_000, 12: 20_000}     # units a brand must hold when the campaign opens (1.2x its expected demand)
SLA_TARGET, PENALTY, PENALTY_WEEKS = 0.95, 0.85, 2
SELLER_RATING = 4.7
SHARE_TACTIC = Tactic("brand_share", target=0.75, reservation=0.40, beta=0.8, deadline=6)


class PasarNusa(Enterprise):
    key = "pasarnusa"
    name = "PasarNusa"
    industry = "E-commerce marketplace"
    city = "Jakarta"
    accent, accent_dark = "#a16207", "#bf8a14"
    store_kind = "documents"
    description = "An Indonesian marketplace that runs the 12.12 mega-sale and a Ramadan campaign for its sellers."
    roles = (
        Role("Campaign Manager", "Plans campaigns and their terms", datasets=(
            "campaign_calendar", "campaign_history", "order_events", "seller_scores", "ledger", "decisions", "messages"),
            hidden_fields=("amount_idr",)),
        Role("Seller Success", "Watches seller service levels", datasets=("seller_scores", "order_events")),
        Role("Finance", "Commissions, vouchers and payouts", datasets=("ledger", "order_events"), can_approve=True),
    )
    modules = (("Campaigns", "Calendar, terms and co-funded vouchers"), ("Traffic forecast", "Campaign demand lift"),
               ("Orders", "Customer orders routed to sellers"), ("Seller performance", "Fulfilment SLA and visibility"))
    platform = {"database": "JSON documents (document store)", "api": "REST + JSON documents",
                "units": "orders and GMV (rupiah)", "time": "campaign calendar and simulation weeks",
                "stack": "FastAPI on its own port"}
    governance = Governance(
        public=("campaign_calendar", "campaign_participation", "listing_visibility"),
        partner=("uplift_forecast", "stock_commitments"),
        control=("uplift_forecast", "stock_commitments", "sla"),
        private=("campaign_history", "ledger"),
        policies={"sla_target": SLA_TARGET, "visibility_penalty": PENALTY, "commission": COMMISSION,
                  "campaign_fee": CAMPAIGN_FEE, "min_brand_voucher_share": SHARE_TACTIC.reservation},
        approval_threshold_idr=None)
    private_datasets = ("campaign_history", "ledger")

    def make_agents(self):
        return [Agent("traffic_forecaster", "Traffic Forecast Agent", "predictive", "Forecasts a campaign's demand lift",
                      UpliftModel.name),
                Agent("campaign_planner", "Campaign Planning Agent", "negotiation",
                      "Sets campaign terms; negotiates voucher co-funding (Boulware)"),
                Agent("seller_performance", "Seller Performance Agent", "monitoring",
                      "Scores fulfilment; lowers visibility after a missed campaign SLA")]

    def service_agent(self):
        return "campaign_planner"

    def setup(self):
        self.model = UpliftModel(seed=self.seed + 14)
        self.store.insert_many("campaign_history", self.model.history)
        self.store.insert_many("campaign_calendar", [{"campaign": c, "weeks": list(ws), "voucher_depth": VOUCHER,
                                                      "stock_commitment_units": STOCK_COMMITMENTS.get(ws[0])}
                                                     for c, ws in CAMPAIGNS.items()])
        self.joined: dict[str, bool] = {}
        self.share: dict[str, float] = {}
        self.visibility: dict[int, float] = {}
        self.sla: dict[int, float] = {}
        self.gmv = self.units = 0
        self.penalties = 0

    def uplift_forecast(self) -> dict[str, float]:
        return {str(w): self.model.predict(VOUCHER, SELLER_RATING, name == "12.12 Mega Sale")
                for w, name in CAMPAIGN_WEEKS.items()}

    def on_tick(self, week, leading, actual):
        if week != 0:
            return []
        payload = {"campaigns": [{"name": c, "weeks": list(ws)} for c, ws in CAMPAIGNS.items()],
                   "standard_terms": {"brand_share": STANDARD_SHARE, "voucher_depth": VOUCHER,
                                      "commission": COMMISSION, "campaign_fee": CAMPAIGN_FEE},
                   "stock_commitments": {str(k): v for k, v in STOCK_COMMITMENTS.items()}}
        if self.mode == "ecosystem":
            payload["uplift_forecast"] = self.uplift_forecast()
            self.decide("traffic_forecaster", "Share Kirana's campaign lift forecast",
                        "Ridge model on past campaigns: voucher depth, seller rating, mega-sale.",
                        outputs=payload["uplift_forecast"])
        return [self.send("campaign_planner", "kirana.channel_manager", "INFORM", "campaign_announcement", payload)]

    def _join(self, share, basis):
        for c in CAMPAIGNS:
            self.joined[c], self.share[c] = True, float(share)
        self.decide("campaign_planner", f"Kirana joins the campaigns paying {share:.0%} of the voucher", basis)

    def on_request_join_campaign(self, m):
        self._join(STANDARD_SHARE, "standard terms")
        return [self.reply(m, "campaign_planner", "AGREE", {"brand_share": STANDARD_SHARE,
                                                             "stock_commitments": {str(k): v for k, v in STOCK_COMMITMENTS.items()}})]

    def on_request_proposal_campaign_terms(self, m):
        return self.open_offer(m, SHARE_TACTIC, "brand_share", "campaign_planner", decimals=4,
                               extra={"stock_commitments": {str(k): v for k, v in STOCK_COMMITMENTS.items()}})

    def on_counter_proposal_campaign_terms(self, m):
        return self.negotiate(m, SHARE_TACTIC, float(m.payload["brand_share"]), "brand_share", "campaign_planner",
                              lambda v: self._join(v, "accepted Kirana's counter-offer"),
                              lambda: self._join(STANDARD_SHARE, "no agreement: standard terms"),
                              counter_type="PROPOSE", decimals=4)

    def on_accept_proposal_campaign_terms(self, m):
        self._join(m.payload["brand_share"], "Kirana accepted the offer")
        return []

    def on_reject_proposal_campaign_terms(self, m):
        self._join(STANDARD_SHARE, "no agreement: standard terms")
        return []

    def on_inform_environment_change(self, m):
        """Live campaign traffic: the marketplace sees a surge before any order lands. In the ecosystem it tells the
        brand and the Control Center at once; on its own it keeps its traffic data to itself."""
        out = super().on_inform_environment_change(m)
        extra = m.payload.get("extra_uplift")
        campaign = CAMPAIGN_WEEKS.get(m.week)
        if extra is None or not campaign:
            return out
        live = round(self.uplift_forecast().get(str(m.week), 0.0) + float(extra), 4)
        self.store.insert("order_events", {"week": m.week, "kind": "traffic", "campaign": campaign,
                                           "extra_uplift": float(extra), "live_uplift": live})
        if self.mode == "ecosystem" and self.joined.get(campaign):
            self.decide("traffic_forecaster", f"Tell Kirana: W{m.week} traffic runs {float(extra):.0%} above forecast",
                        "Live sessions and add-to-carts on the campaign page are far above the lift model; the brand and "
                        "the Control Center can still move stock before the orders land.", outputs={"live_uplift": live},
                        refs=[m.message_id])
            signal = {"week": m.week, "campaign": campaign, "extra_uplift": float(extra), "live_uplift": live,
                      "source": "live campaign traffic"}
            out += [self.send("traffic_forecaster", "kirana.demand_planner", "INFORM", "demand_signal", signal),
                    self.send("traffic_forecaster", "control.coordinator", "INFORM", "demand_signal", signal)]
        return out

    def on_inform_customer_orders(self, m):
        w = m.week
        self.store.insert("order_events", {"week": w, "kind": "orders", "campaign": CAMPAIGN_WEEKS.get(w),
                                           "orders": m.payload["orders"]})
        return [self.send("seller_performance", "kirana.fulfilment", "REQUEST", "fulfil_orders",
                          {"week": w, "orders": m.payload["orders"], "campaign": CAMPAIGN_WEEKS.get(w)},
                          reply_required=True)]

    def on_inform_fulfilment(self, m):
        w = m.week
        served = sum(int(m.payload["served"].get(r, 0)) for r in REGIONS)
        lost = sum(int(m.payload["lost"].get(r, 0)) for r in REGIONS)
        fill = served / (served + lost) if served + lost else 1.0
        self.sla[w] = round(fill, 4)
        campaign = CAMPAIGN_WEEKS.get(w)
        in_campaign = bool(campaign and self.joined.get(campaign))
        gmv = served * PRICE
        voucher = gmv * VOUCHER if in_campaign else 0.0
        share = self.share.get(campaign, STANDARD_SHARE) if in_campaign else 0.0
        fees = gmv * (COMMISSION + (CAMPAIGN_FEE if in_campaign else 0.0))
        self.gmv += gmv
        self.units += served
        self.book("kirana", "commission", fees, served)
        if voucher:
            self.book("customers", "platform voucher", -voucher * (1 - share), served)
        self.store.insert("order_events", {"week": w, "kind": "fulfilment", "served": served, "lost": lost,
                                           "fill_rate": round(fill, 4), "gmv_idr": round(gmv)})
        out = [self.send("seller_performance", "kirana.finance", "INFORM", "settlement",
                         {"week": w, "units": served, "gmv_idr": round(gmv), "commission_idr": round(fees),
                          "voucher_brand_idr": round(voucher * share)})]
        consequence = ""
        if in_campaign and fill < SLA_TARGET:
            for k in range(1, PENALTY_WEEKS + 1):
                self.visibility[w + k] = PENALTY
            self.penalties += 1
            consequence = (f"Below the {SLA_TARGET:.0%} campaign SLA: Kirana's listings lose {1 - PENALTY:.0%} visibility "
                           f"for {PENALTY_WEEKS} weeks.")
            self.decide("seller_performance", f"Lower Kirana's visibility after W{w}", consequence,
                        inputs={"fill_rate": round(fill, 4)})
        self.store.insert("seller_scores", {"week": w, "seller": "kirana", "fill_rate": round(fill, 4),
                                            "visibility_next": self.visibility.get(w + 1, 1.0)})
        if in_campaign or fill < SLA_TARGET:
            out.append(self.send("seller_performance", "kirana.channel_manager", "INFORM", "sla_report",
                                 {"week": w, "fill_rate": round(fill, 4), "consequence": consequence}))
        return out

    def view(self):
        return {"campaign_calendar": [{"name": c, "weeks": list(ws)} for c, ws in CAMPAIGNS.items()],
                "campaign_participation": {c: self.joined.get(c, False) for c in CAMPAIGNS},
                "listing_visibility": {str(k): v for k, v in self.visibility.items()},
                "uplift_forecast": self.uplift_forecast(),
                "stock_commitments": {str(k): v for k, v in STOCK_COMMITMENTS.items()},
                "sla": {str(k): v for k, v in self.sla.items()}}

    def kpis(self):
        fees = self.ledger_total("commission")
        vouchers = self.ledger_total("platform voucher")
        campaign_sla = [v for w, v in self.sla.items() if w in CAMPAIGN_WEEKS]
        return {"gmv_idr": round(self.gmv), "units_sold": self.units, "fees_idr": round(fees),
                "platform_voucher_idr": round(-vouchers),
                "campaign_fill_rate": round(sum(campaign_sla) / len(campaign_sla), 4) if campaign_sla else None,
                "visibility_penalties": self.penalties, "profit_idr": round(fees + vouchers)}
