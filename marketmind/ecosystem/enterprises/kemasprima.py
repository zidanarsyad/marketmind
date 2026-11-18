"""KemasPrima: the packaging maker that supplies airless pump bottles ("set kemasan") to MaklonNusa.

Its own systems speak Indonesian: tables, columns and the keys of its shared view (``kapasitas_set_per_minggu``,
``prediksi_tingkat_cacat``); the Control Center's adapters map them to the shared vocabulary.
"""
from __future__ import annotations

from collections import defaultdict

from ..governance import Governance, Role
from ..models import DefectRiskModel
from ..negotiation import Tactic
from .base import Agent, Enterprise

CAPACITY_SETS = 30_000
PRICE_SET, COST_SET, INSPECTION_COST = 3_600, 2_700, 150
SLIP_AFTER_INSPECTION = 0.002
DISCOUNT_TACTIC = Tactic("discount", target=0.03, reservation=0.12, beta=0.8, deadline=6)


class KemasPrima(Enterprise):
    key = "kemasprima"
    name = "KemasPrima"
    industry = "Packaging manufacturer"
    city = "Tangerang"
    accent, accent_dark = "#c2410c", "#dd6a2c"
    description = "Moulds airless pump bottles and assembles them into packaging sets for cosmetics fillers."
    roles = (
        Role("Kepala Produksi", "Plans moulding and assembly", datasets=("lot_produksi", "pesanan", "prediksi_cacat",
                                                                           "decisions", "messages"),
             hidden_fields=("harga_per_set",)),             # plans the orders without their prices
        Role("Analis QC", "Runs quality control and the defect model", datasets=("riwayat_qc", "prediksi_cacat",
                                                                                  "lot_produksi")),
        Role("Penjualan", "Takes orders and negotiates terms", datasets=("pesanan", "ledger", "messages", "decisions"),
             can_approve=True),
    )
    modules = (("Produksi", "Moulding and assembly capacity"), ("Kendali mutu", "Defect prediction from lot readings"),
               ("Penjualan", "Orders, prices and quality agreements"))
    platform = {"database": "SQLite (relational), Indonesian table and column names", "api": "REST + JSON, Indonesian keys",
                "units": "packaging sets (set kemasan)", "time": "minggu (simulation week)", "stack": "FastAPI on its own port"}
    governance = Governance(
        public=("daftar_harga",),
        partner=("kapasitas_set_per_minggu", "prediksi_tingkat_cacat"),
        control=("kapasitas_set_per_minggu", "prediksi_tingkat_cacat"),
        private=("riwayat_qc", "ledger"),
        policies={"max_discount": DISCOUNT_TACTIC.reservation, "inspection_cost_per_set": INSPECTION_COST},
        approval_threshold_idr=None)
    private_datasets = ("riwayat_qc", "ledger")

    def make_agents(self):
        return [Agent("qc_predictor", "QC Prediction Agent", "predictive",
                      "Predicts next week's defect rate from lot readings", DefectRiskModel.name),
                Agent("production", "Production Agent", "operations", "Moulds, assembles and ships packaging sets"),
                Agent("sales", "Sales Agent", "negotiation", "Takes orders; negotiates quality compensation")]

    def service_agent(self):
        return "sales"

    def setup(self):
        self.model = DefectRiskModel(seed=self.seed + 11)
        self.store.insert_many("riwayat_qc", self.model.history)
        self.orders: dict[int, int] = defaultdict(int)
        self.predicted: dict[int, float] = {}
        self.discount, self.inspection = 0.0, False
        self.delivered = self.defects_shipped = self.defects_caught = 0

    def on_request_packaging_order(self, m):
        w, units = int(m.payload["week"]), int(m.payload["units"])
        accepted = max(0, min(units, CAPACITY_SETS - self.orders[w]))
        self.orders[w] += accepted
        self.store.insert("pesanan", {"minggu": w, "pelanggan": "maklonnusa", "jumlah_set": accepted,
                                      "harga_per_set": PRICE_SET})
        return [self.reply(m, "sales", "AGREE", {"accepted_units": accepted, "requested_units": units, "week": w})]

    def on_request_proposal_quality_compensation(self, m):
        self.decide("sales", "Offer a 3% discount and 100% inspection",
                    "Our own forecast agrees the lots are at risk; inspecting every set costs Rp 150 a set but keeps "
                    "the customer and its brand safe.", refs=[m.message_id])
        return self.open_offer(m, DISCOUNT_TACTIC, "discount", "sales", decimals=4, extra={"inspection": True})

    def _agree(self, value, basis):
        self.discount, self.inspection = float(value), True
        self.decide("sales", f"Quality agreement at {self.discount:.0%} with 100% inspection", basis)

    def on_counter_proposal_quality_compensation(self, m):
        return self.negotiate(m, DISCOUNT_TACTIC, float(m.payload["discount"]), "discount", "sales",
                              lambda v: self._agree(v, "accepted MaklonNusa's counter-offer"),
                              lambda: None, counter_type="PROPOSE", decimals=4, extra={"inspection": True})

    def on_accept_proposal_quality_compensation(self, m):
        self._agree(m.payload["discount"], "MaklonNusa accepted the offer")
        return []

    def on_inform_defect_claim(self, m):
        self.book("maklonnusa", "defect claims", -m.payload["amount_idr"], m.payload["sets"])
        self.decide("sales", f"Pay a Rp {m.payload['amount_idr']:,} defect claim",
                    f"MaklonNusa's incoming QC rejected {m.payload['sets']:,} sets.", refs=[m.message_id])
        return []

    def on_tick(self, week, leading, actual):
        out = []
        if week == 0:
            return out
        if leading:
            pred = self.model.predict(leading)
            w = int(leading["week"])
            self.predicted[w] = pred["expected_defect_rate"]
            self.store.insert("prediksi_cacat", {"minggu": w, "pemasok_pegas": leading["sub_supplier"],
                                                 "deviasi_tegangan_pegas": leading["spring_tension_dev"],
                                                 "peluang_lot_cacat_tinggi": pred["p_high_defect"],
                                                 "tingkat_cacat_prediksi": pred["expected_defect_rate"]})
            if pred["expected_defect_rate"] > 0.03:
                self.decide("qc_predictor", f"W{w} lots at risk: {pred['expected_defect_rate']:.1%} defects expected",
                            f"Spring tension deviation {leading['spring_tension_dev']} from sub-supplier "
                            f"{leading['sub_supplier']}; the lot model gives p(high defect) = {pred['p_high_defect']:.0%}.",
                            inputs=leading, outputs=pred)
                if self.mode == "ecosystem":
                    for to in ("maklonnusa.procurement", "control.coordinator"):
                        out.append(self.send("qc_predictor", to, "INFORM", "defect_risk",
                                             {"week": w, "expected_defect_rate": pred["expected_defect_rate"]}))
        units = self.orders.get(week, 0)
        if units:
            rate = float(actual.get("defect_rate", 0.015))
            defective = round(units * rate)
            cost = units * COST_SET
            if self.inspection and rate > 0.03:
                caught = defective - round(units * SLIP_AFTER_INSPECTION)
                cost += units * INSPECTION_COST + caught * COST_SET     # inspect every set, replace the bad ones
                self.defects_caught += caught
                defective -= caught
            price = PRICE_SET * (1 - (self.discount if rate > 0.03 else 0.0))
            invoice = round(units * price)
            self.delivered += units
            self.defects_shipped += defective
            self.book("maklonnusa", "sales", invoice, units)
            self.book("own plant", "production cost", -cost, units)
            self.store.insert("lot_produksi", {"minggu": week, "jumlah_set": units, "tingkat_cacat_aktual": rate,
                                               "cacat_terkirim": defective, "diperiksa_100": bool(self.inspection and rate > 0.03)})
            out.append(self.send("production", "maklonnusa.procurement", "INFORM", "packaging_delivery",
                                 {"week": week, "units": units, "invoice_idr": invoice,
                                  "inspected": bool(self.inspection and rate > 0.03),
                                  "physical": {"defective_sets": defective}}))
        return out

    def view(self):
        return {"daftar_harga": {"harga_per_set": PRICE_SET},
                "kapasitas_set_per_minggu": CAPACITY_SETS,
                "prediksi_tingkat_cacat": {str(w): r for w, r in self.predicted.items() if w >= self.week}}

    def kpis(self):
        revenue = self.ledger_total("sales")
        cost = self.ledger_total("production cost") + self.ledger_total("defect claims")
        return {"sets_delivered": self.delivered, "defects_shipped": self.defects_shipped,
                "defect_ppm_shipped": round(1e6 * self.defects_shipped / self.delivered) if self.delivered else 0,
                "defects_caught_by_inspection": self.defects_caught, "discount": self.discount,
                "revenue_idr": round(revenue), "costs_idr": round(-cost), "profit_idr": round(revenue + cost)}
