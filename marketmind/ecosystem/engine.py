"""The ecosystem run: the Global Agentic Control Center's agents, the message bus, and the weekly simulation.

The Control Center has three agents. The **Environment** is the world: it announces disruptions and sends customer
orders. The **Coordinator** is the ecosystem's global intelligence (ecosystem mode only): it asks every enterprise
for its shared view, translates each dialect into one vocabulary (``adapt``), solves the joint plan, proposes each
enterprise its slice, re-solves with the constraints an enterprise sends back when it rejects one, and confirms the
plan everyone accepted; a risk or disruption an enterprise reports triggers a new plan. The **Monitor** keeps the
log: every message on the bus, every plan revision and how it differs from the last, the KPIs week by week.

Enterprises are reached through a ``Transport``: in process (tests, the command line) or over HTTP, each enterprise
on its own server with its own database. The Control Center never opens an enterprise's database: it sees what the
enterprise's API hands it.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Protocol

from .enterprises import ENTERPRISES, ORDER, Enterprise
from .planner import DEFAULT_WEIGHTS, PlanInput, solve
from .protocol import Message, MessageFactory
from .world import CAMPAIGN_WEEKS, REGIONS, SCENARIOS, WEEKS, World, iso_week, week_label

NEGOTIATIONS = ("production_contract", "campaign_terms", "quality_compensation", "reroute_options")
REPLAN_EVERY = 2            # the coordinator re-plans every two weeks (rolling horizon), and at once when a risk is reported
REPLAN_TRIGGERS = ("defect_risk", "flood_risk", "capacity_risk", "capacity_change", "forecast_revision", "demand_signal")
PLAN_AGENTS = {"kirana": "supply_planner", "maklonnusa": "capacity_planner", "kemasprima": "production",
               "kirimcepat": "route_planner", "pasarnusa": "campaign_planner"}
OPS_AGENT = {"kirana": "fulfilment", "maklonnusa": "capacity_planner", "kemasprima": "production",
             "kirimcepat": "route_planner", "pasarnusa": "seller_performance", "research": "insight_service"}

# how each enterprise's shared view maps onto the coordinator's vocabulary (the schema mapping, shown in the docs and UI)
SCHEMA_MAPPING = [
    {"enterprise": "kirana", "local": "demand_forecast[region][week]", "unit": "pieces", "shared": "demand[region][week]",
     "conversion": "as is"},
    {"enterprise": "maklonnusa", "local": "freeCapacity.batchesByWeek[week]", "unit": "batches",
     "shared": "maklon_capacity[week]", "conversion": "x batchUnits (5,000)"},
    {"enterprise": "kemasprima", "local": "kapasitas_set_per_minggu", "unit": "set kemasan / minggu",
     "shared": "packaging_capacity[week]", "conversion": "sets = units, same every week"},
    {"enterprise": "kemasprima", "local": "prediksi_tingkat_cacat[minggu]", "unit": "share",
     "shared": "defect_rate[week]", "conversion": "as is; good sets = capacity x (1 - rate)"},
    {"enterprise": "kirimcepat", "local": "lane_capacity.lanes[lane][ISO week]", "unit": "pallets",
     "shared": "lane_capacity[region][week]", "conversion": "x units_per_pallet (1,200); ISO week -> week number"},
    {"enterprise": "kirimcepat", "local": "express.capacity_units, price_idr_per_unit", "unit": "pieces, rupiah",
     "shared": "express_capacity, express_price", "conversion": "as is"},
    {"enterprise": "pasarnusa", "local": "stock_commitments[week]", "unit": "pieces",
     "shared": "commitments[campaign week]", "conversion": "as is"},
]


class Transport(Protocol):
    def send(self, m: Message) -> list[Message]: ...
    def tick(self, key: str, week: int, signals: dict) -> list[Message]: ...
    def end_week(self, key: str, week: int) -> list[Message]: ...
    def shared(self, key: str, audience: str) -> dict: ...
    def kpis(self, key: str) -> dict: ...
    def status(self, key: str) -> dict: ...
    def reset(self, key: str, mode: str, scenario: str, seed: int) -> None: ...


class InProcessTransport:
    """Every enterprise in this process (each still with its own database file)."""

    def __init__(self, enterprises: dict[str, Enterprise]):
        self.enterprises = enterprises

    def send(self, m):
        return self.enterprises[m.receiver_enterprise].receive(m)

    def tick(self, key, week, signals):
        return self.enterprises[key].tick(week, signals)

    def end_week(self, key, week):
        return self.enterprises[key].end_week(week)

    def shared(self, key, audience):
        return self.enterprises[key].shared(audience)

    def kpis(self, key):
        return self.enterprises[key].kpis()

    def status(self, key):
        return self.enterprises[key].status()

    def reset(self, key, mode, scenario, seed):
        self.enterprises[key].reset(mode, scenario, seed)


class HttpTransport:
    """Every enterprise behind its own server (``python -m marketmind.ecosystem up``)."""

    def __init__(self, urls: dict[str, str], timeout: float = 60.0):
        import httpx
        self.urls = {k: u.rstrip("/") for k, u in urls.items()}
        self.client = httpx.Client(timeout=timeout)

    def _post(self, key: str, path: str, body: dict) -> dict:
        r = self.client.post(f"{self.urls[key]}{path}", json=body)
        r.raise_for_status()
        return r.json()

    def _get(self, key: str, path: str, **params) -> dict:
        r = self.client.get(f"{self.urls[key]}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def send(self, m):
        return [Message(**x) for x in self._post(m.receiver_enterprise, "/api/a2a/messages", m.model_dump())["replies"]]

    def tick(self, key, week, signals):
        return [Message(**x) for x in self._post(key, "/api/a2a/tick", {"week": week, "signals": signals})["messages"]]

    def end_week(self, key, week):
        return [Message(**x) for x in self._post(key, "/api/a2a/end-week", {"week": week})["messages"]]

    def shared(self, key, audience):
        return self._get(key, "/api/a2a/shared", audience=audience)["view"]

    def kpis(self, key):
        return self._get(key, "/api/kpis")

    def status(self, key):
        return self._get(key, "/api/status")

    def reset(self, key, mode, scenario, seed):
        self._post(key, "/api/a2a/reset", {"mode": mode, "scenario": scenario, "seed": seed})


def _weeks(d: dict | None) -> dict[int, float]:
    return {int(k): v for k, v in (d or {}).items()}


def adapt(key: str, view: dict) -> dict:
    """Translate one enterprise's shared view into the coordinator's vocabulary (see ``SCHEMA_MAPPING``)."""
    if key == "kirana":
        return {"demand": {r: _weeks(view.get("demand_forecast", {}).get(r)) for r in REGIONS},
                "inventory": view.get("inventory", {}), "in_transit": {int(k): v for k, v in view.get("in_transit", {}).items()},
                "factory_stock": view.get("factory_stock", 0), "locked": _weeks(view.get("locked_production")),
                "unit_price": view.get("unit_price"), "margin": view.get("margin_per_unit"),
                "commitments": _weeks(view.get("commitments")), "reroute": view.get("reroute")}
    if key == "maklonnusa":
        cap = view.get("freeCapacity", {})
        unit = cap.get("batchUnits", 5_000)
        return {"capacity": {int(w): n * unit for w, n in cap.get("batchesByWeek", {}).items()},
                "sets_on_hand": view.get("packagingSetsOnHand", 0)}
    if key == "kemasprima":
        return {"capacity_per_week": view.get("kapasitas_set_per_minggu", 0),
                "defect_rate": _weeks(view.get("prediksi_tingkat_cacat"))}
    if key == "kirimcepat":
        lanes = view.get("lane_capacity", {})
        per = lanes.get("units_per_pallet", 1_200)
        iso_to_week = {iso_week(w): w for w in range(1, WEEKS + 2)}
        return {"lane_capacity": {r: {iso_to_week[iso]: p * per for iso, p in lanes.get("lanes", {}).get(r, {}).items()
                                      if iso in iso_to_week} for r in REGIONS},
                "express": view.get("express", {}), "risk_notices": view.get("risk_notices", [])}
    if key == "pasarnusa":
        return {"commitments": _weeks(view.get("stock_commitments")),
                "participation": view.get("campaign_participation", {})}
    return view


class Control:
    """The Global Agentic Control Center's agents: Environment, Coordinator and Monitor."""

    def __init__(self, transport: Transport, world: World, mode: str, weights: dict | None = None):
        self.transport, self.world, self.mode = transport, world, mode
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.msg = MessageFactory("control")
        self.bus: Bus | None = None
        self.views: dict[str, dict] = {}
        self.responses: dict[str, Message] = {}
        self.triggers: list[dict] = []
        self.plans: list[dict] = []
        self.events: list[dict] = []
        self.decisions: list[dict] = []
        self.week = 0

    # ------------------------------------------------------------------ incoming
    def receive(self, m: Message) -> list[Message]:
        if m.task == "shared_view" and m.message_type == "INFORM":
            self.views[m.sender_enterprise] = m.payload.get("view", {})
        elif m.task == "plan" and m.message_type in ("ACCEPT_PROPOSAL", "REJECT_PROPOSAL"):
            self.responses[m.sender_enterprise] = m
        elif m.message_type == "INFORM" and m.task in REPLAN_TRIGGERS and self.mode == "ecosystem":
            self.triggers.append({"week": m.week, "from": m.sender, "task": m.task, "payload": m.payload,
                                  "message_id": m.message_id})
        return []

    def note(self, agent: str, decision: str, reasoning: str, **extra) -> None:
        self.decisions.append({"week": self.week, "agent": agent, "decision": decision, "reasoning": reasoning, **extra})

    # ------------------------------------------------------------------ environment
    def disruptions(self, week: int) -> list[Message]:
        out = []
        for e in self.world.starting(week):
            self.events.append({"week": week, "kind": "disruption", "key": e.key, "title": e.title, "detail": e.detail,
                                "target": e.target, "start": e.start, "end": e.end})
            self.note("environment", f"{e.title} begins", e.detail, target=e.target)
            out.append(self.msg.new("control.environment", f"{e.target}.{OPS_AGENT[e.target]}", "INFORM",
                                    "environment_change", {"title": e.title, "detail": e.detail, "weeks": [e.start, e.end],
                                                           **e.params}, week=week))
        for e in self.world.events:
            if e.end + 1 == week:
                self.events.append({"week": week, "kind": "recovery", "key": e.key, "title": f"{e.title} over",
                                    "detail": "Operations are back to normal.", "target": e.target})
        if week in CAMPAIGN_WEEKS and (week == 1 or CAMPAIGN_WEEKS.get(week - 1) != CAMPAIGN_WEEKS[week]):
            self.events.append({"week": week, "kind": "campaign", "key": CAMPAIGN_WEEKS[week],
                                "title": f"{CAMPAIGN_WEEKS[week]} opens", "detail": "PasarNusa campaign week.", "target": "pasarnusa"})
        return out

    def customer_orders(self, week: int) -> tuple[list[Message], dict]:
        public = self.transport.shared("pasarnusa", "control")
        self.world.visibility.update({int(k): float(v) for k, v in public.get("listing_visibility", {}).items()})
        campaign = CAMPAIGN_WEEKS.get(week)
        joined = bool(campaign and public.get("campaign_participation", {}).get(campaign))
        demand = self.world.demand(week, joined)
        msgs = [self.msg.new("control.environment", "pasarnusa.seller_performance", "INFORM", "customer_orders",
                             {"orders": demand["marketplace"], "campaign": campaign}, week=week),
                self.msg.new("control.environment", "kirana.fulfilment", "INFORM", "customer_orders",
                             {"orders": demand["direct"], "channel": "direct"}, week=week)]
        return msgs, demand

    # ------------------------------------------------------------------ coordinator
    def plan(self, week: int, reason: str) -> dict | None:
        self.week = week
        partners = list(PLAN_AGENTS)
        self.views = {}
        self.bus.deliver([self.msg.new("control.coordinator", f"{k}.{PLAN_AGENTS[k]}", "REQUEST", "shared_view",
                                       {"purpose": "ecosystem plan", "from_week": week}, week=week, reply_required=True)
                          for k in partners])
        v = {k: adapt(k, self.views.get(k, {})) for k in partners}
        kir, mak, kem, log, mkt = v["kirana"], v["maklonnusa"], v["kemasprima"], v["kirimcepat"], v["pasarnusa"]
        express = log.get("express", {})
        reroute = kir.get("reroute") or {}
        max_batches: dict[int, int] = {}
        rounds, result = 0, None
        for rounds in range(1, 4):
            inp = PlanInput(
                week=week, horizon=WEEKS, demand=kir["demand"],
                maklon_capacity=mak["capacity"],
                packaging_good_capacity={w: kem["capacity_per_week"] * (1 - kem["defect_rate"].get(w, 0.015))
                                         for w in range(week, WEEKS + 1)},
                defect_rate={w: kem["defect_rate"].get(w, 0.015) for w in range(week, WEEKS + 1)},
                lane_capacity=log["lane_capacity"],
                lane_price={"JKT": 380, "SBY": 1_150},
                inventory=kir["inventory"],
                arriving=kir["in_transit"].get(week, {}) if week > 0 else {},
                factory_stock=kir["factory_stock"], locked_production=kir["locked"].get(week, 0),
                unit_price=kir["unit_price"], margin_per_unit=kir["margin"],
                commitments=mkt["commitments"] or kir["commitments"],
                express_capacity=reroute.get("capacity_units", express.get("capacity_units", 6_000)),
                express_price=reroute.get("cost_idr_per_unit", express.get("price_idr_per_unit", 1_800)),
                max_batches=dict(max_batches), weights=self.weights)
            result = solve(inp)
            if result["status"] == "infeasible":
                self.note("coordinator", "No feasible plan", result.get("message", ""))
                return None
            self.responses = {}
            self.bus.deliver([self._proposal(k, week, result) for k in partners])
            rejected = {k: r for k, r in self.responses.items() if r.message_type == "REJECT_PROPOSAL"}
            if not rejected:
                break
            for k, r in rejected.items():
                limits = {int(w): int(n) for w, n in r.payload.get("max_batches", {}).items()}
                max_batches.update(limits)
                said = ", ".join(f"at most {n} batches in W{w}" for w, n in sorted(limits.items())) or "no limit given"
                self.note("coordinator", f"{ENTERPRISES[k].name} rejected the plan; solving again",
                          f"{r.payload.get('reason', 'no reason given').capitalize()}: {said}.", round=rounds)
        revision = len(self.plans) + 1
        prev = self.plans[-1]["result"] if self.plans else None
        diff = plan_diff(prev, result)
        self.plans.append({"revision": revision, "week": week, "label": week_label(week), "reason": reason,
                           "rounds": rounds, "result": result, "diff": diff})
        self.note("coordinator", f"Plan rev. {revision} confirmed ({result['planned_fill_rate']:.1%} planned fill rate)",
                  reason + (f"; changes {len(diff)} weekly figures from rev. {revision - 1}" if prev else ""), rounds=rounds)
        self.bus.deliver([self.msg.new("control.coordinator", f"{k}.{PLAN_AGENTS[k]}", "CONFIRM", "plan",
                                       {"revision": revision, "reason": reason, "weeks": result["weeks"],
                                        "planned_fill_rate": result["planned_fill_rate"]}, week=week) for k in partners])
        return result

    def _proposal(self, key: str, week: int, result: dict) -> Message:
        weeks = result["weeks"]
        if key == "maklonnusa":
            body = [{"week": r["week"], "batches": r["batches"], "production": r["production"]} for r in weeks]
        elif key == "kemasprima":
            body = [{"week": r["week"], "sets": r["production"]} for r in weeks if r["week"] > week]
        elif key == "kirimcepat":
            body = [{"week": r["week"], **{f"ship_{x}": r[f"ship_{x}"] for x in REGIONS}, "express": r["express"]}
                    for r in weeks]
        elif key == "pasarnusa":
            body = [{"week": r["week"], "stock": r["stock_JKT"] + r["stock_SBY"]} for r in weeks]
        else:
            body = weeks
        return self.msg.new("control.coordinator", f"{key}.{PLAN_AGENTS[key]}", "PROPOSE", "plan",
                            {"weeks": body, "planned_fill_rate": result["planned_fill_rate"],
                             "objective": result["objective"], "terms": result["terms"]}, week=week, reply_required=True)


def plan_diff(prev: dict | None, new: dict) -> list[dict]:
    """The weekly figures a new plan changes: what measurably moved when the environment changed."""
    if not prev:
        return []
    old = {r["week"]: r for r in prev["weeks"]}
    out = []
    for r in new["weeks"]:
        o = old.get(r["week"])
        if not o:
            continue
        for field in ("production", "ship_JKT", "ship_SBY", "express"):
            if abs(r[field] - o[field]) >= 100:
                out.append({"week": r["week"], "field": field, "before": o[field], "after": r[field]})
    return out


class Bus:
    """Delivers messages one at a time, in order, until no one has anything left to say; logs every message."""

    def __init__(self, transport: Transport, control: Control, on_message: Callable[[Message], None] | None = None):
        self.transport, self.control = transport, control
        self.log: list[Message] = []
        self.on_message = on_message

    def deliver(self, messages: list[Message], limit: int = 5_000) -> None:
        queue = deque(messages)
        n = 0
        while queue:
            m = queue.popleft()
            n += 1
            if n > limit:
                raise RuntimeError("message storm: more than 5,000 messages in one exchange")
            self.log.append(m)
            if self.on_message:
                self.on_message(m)
            replies = self.control.receive(m) if m.receiver_enterprise == "control" else self.transport.send(m)
            queue.extend(replies)


class Ecosystem:
    """One simulated season: 16 weeks of the scenario, in one mode."""

    def __init__(self, transport: Transport, scenario: str = "normal", mode: str = "ecosystem", seed: int = 7,
                 weights: dict | None = None, progress: Callable[[int, str], None] | None = None):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}")
        if mode not in ("local", "ecosystem"):
            raise ValueError("mode is local or ecosystem")
        self.transport, self.scenario, self.mode, self.seed = transport, scenario, mode, seed
        self.weights = weights
        self.progress = progress or (lambda week, note: None)

    def run(self) -> dict:
        world = World(self.scenario, self.seed)
        for k in ORDER:
            self.transport.reset(k, self.mode, self.scenario, self.seed)
        control = Control(self.transport, world, self.mode, self.weights)
        bus = Bus(self.transport, control)
        control.bus = bus
        weekly, truth = [], {"demand": 0}
        signals = world.signals(0)
        for k in ORDER:
            bus.deliver(self.transport.tick(k, 0, signals[k]))
        if self.mode == "ecosystem":
            control.plan(0, "initial plan before the launch")
        self.progress(0, "setup done")
        for w in range(1, WEEKS + 1):
            control.week = w
            # the week opens with what changed in the world; the coordinator then plans with every risk reported so
            # far (including one a disruption raised this morning), before the enterprises run the week
            bus.deliver(control.disruptions(w))
            if self.mode == "ecosystem" and (control.triggers or w % REPLAN_EVERY == 0):
                reasons = "; ".join(sorted({f"{t['task'].replace('_', ' ')} from {t['from'].split('.')[0]}"
                                            for t in control.triggers})) or "fortnightly rolling plan"
                control.triggers = []
                control.plan(w, reasons)
            signals = world.signals(w)
            for k in ORDER:
                bus.deliver(self.transport.tick(k, w, signals[k]))
            orders, demand = control.customer_orders(w)
            bus.deliver(orders)
            truth["demand"] += sum(sum(ch.values()) for ch in demand.values())
            for k in ORDER:
                bus.deliver(self.transport.end_week(k, w))
            kir = self.transport.kpis("kirana")
            weekly.append({"week": w, "label": week_label(w), "demand": kir["demand_units"], "served": kir["served_units"],
                           "lost": kir["lost_units"], "fill_rate": kir["fill_rate"], "messages": len(bus.log)})
            self.progress(w, f"week {w} done")
        kpis = {k: self.transport.kpis(k) for k in ORDER}
        return summarise(self.scenario, self.mode, self.seed, bus.log, control, weekly, kpis, truth)


def negotiations(log: list[Message]) -> list[dict]:
    threads: dict[str, dict] = {}
    for m in log:
        if m.task not in NEGOTIATIONS:
            continue
        t = threads.setdefault(m.conversation_id, {"conversation_id": m.conversation_id, "task": m.task, "week": m.week,
                                                   "parties": [m.sender_enterprise, m.receiver_enterprise], "offers": [],
                                                   "outcome": "open"})
        issue = next((k for k in ("unit_price", "brand_share", "discount") if k in m.payload), None)
        if m.message_type in ("PROPOSE", "COUNTER_PROPOSAL") and issue:
            t["offers"].append({"by": m.sender_enterprise, "type": m.message_type, "value": m.payload[issue], "issue": issue})
        if m.message_type == "PROPOSE" and "options" in m.payload:
            t["options"] = m.payload["options"]
        if m.message_type == "ACCEPT_PROPOSAL":
            t["outcome"] = "agreed"
            t["agreed"] = m.payload.get(issue) if issue else m.payload.get("option")
            t["accepted_by"] = m.sender_enterprise
        elif m.message_type == "REJECT_PROPOSAL":
            t["outcome"] = "no agreement"
    return list(threads.values())


def summarise(scenario, mode, seed, log, control, weekly, kpis, truth) -> dict:
    kir = kpis["kirana"]
    profit = {k: v.get("profit_idr", 0) for k, v in kpis.items()}
    by_type: dict[str, int] = {}
    for m in log:
        by_type[m.message_type] = by_type.get(m.message_type, 0) + 1
    threads = negotiations(log)
    eco = {"demand_units": truth["demand"], "served_units": kir["served_units"], "lost_units": kir["lost_units"],
           "fill_rate": round(kir["served_units"] / truth["demand"], 4) if truth["demand"] else None,
           "total_profit_idr": int(sum(profit.values())), "profit_by_enterprise": profit,
           "messages": len(log), "messages_by_type": by_type,
           "negotiations": len(threads), "agreements": sum(1 for t in threads if t["outcome"] == "agreed"),
           "plan_revisions": len(control.plans), "replans": max(0, len(control.plans) - 1),
           "stockout_weeks": kir["stockout_weeks"], "defective_returns_idr": kir["returns_idr"]}
    return {"scenario": scenario, "title": SCENARIOS[scenario][0], "description": SCENARIOS[scenario][1], "mode": mode,
            "seed": seed, "weeks": WEEKS, "ecosystem": eco, "kpis": kpis, "weekly": weekly, "events": control.events,
            "plans": control.plans, "decisions": control.decisions, "negotiations": threads,
            "messages": [m.model_dump() for m in log]}


def compare(local: dict, eco: dict) -> dict:
    """Local versus ecosystem intelligence on the same scenario and the same customers."""
    rows = []
    for key, label, better in (("fill_rate", "Fill rate", "higher"), ("lost_units", "Orders lost", "lower"),
                               ("stockout_weeks", "Stock-out weeks", "lower"),
                               ("defective_returns_idr", "Defective returns (Rp)", "lower"),
                               ("total_profit_idr", "Ecosystem profit (Rp)", "higher"),
                               ("messages", "Messages exchanged", "info"), ("negotiations", "Negotiations", "info"),
                               ("replans", "Replans", "info")):
        a, b = local["ecosystem"][key], eco["ecosystem"][key]
        rows.append({"kpi": key, "label": label, "local": a, "ecosystem": b, "better": better,
                     "delta": (b - a) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None})
    enterprises = [{"enterprise": k, "local_profit_idr": local["kpis"][k].get("profit_idr", 0),
                    "ecosystem_profit_idr": eco["kpis"][k].get("profit_idr", 0)} for k in ORDER]
    return {"scenario": local["scenario"], "title": local["title"], "rows": rows, "enterprises": enterprises}
