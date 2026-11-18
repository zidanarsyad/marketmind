"""The multi-enterprise ecosystem (marketmind/ecosystem): six enterprises, each with its own database, agents and API,
an A2A-style message contract, negotiations, the Control Center's joint plan, and the disruptions that change it.

A season of 16 simulated weeks takes about a second in process, so all of this runs offline in the fast suite. The
headline claims of docs/ECOSYSTEM.md are tested here: ecosystem intelligence beats local intelligence on the same
customers, no enterprise is worse off for joining, and every disruption measurably changes a decision.
"""
from __future__ import annotations

import time

import httpx
import pytest
from pydantic import ValidationError

from marketmind.ecosystem import ORDER, PORTS, SCENARIOS, Ecosystem, HttpTransport, InProcessTransport, build, compare, run
from marketmind.ecosystem.engine import NEGOTIATIONS, PLAN_AGENTS, SCHEMA_MAPPING, adapt, plan_diff
from marketmind.ecosystem.enterprises import ENTERPRISES
from marketmind.ecosystem.enterprises.kirana import PRICE_TACTIC as KIRANA_PRICE
from marketmind.ecosystem.enterprises.kirana import REROUTE_WEIGHTS
from marketmind.ecosystem.enterprises.kirimcepat import REROUTE_OPTIONS
from marketmind.ecosystem.enterprises.maklonnusa import CAPACITY_BATCHES, OTHER_CLIENTS
from marketmind.ecosystem.enterprises.maklonnusa import PRICE_TACTIC as MAKLON_PRICE
from marketmind.ecosystem.governance import Governance, Role, visible_row
from marketmind.ecosystem.negotiation import Tactic, alternating_offers, rank_options
from marketmind.ecosystem.planner import PlanInput, solve
from marketmind.ecosystem.protocol import PERFORMATIVES, Message, MessageFactory, agent_card
from marketmind.ecosystem.world import BATCH, EVENTS, WEEKS, World, iso_week


@pytest.fixture(scope="module")
def stress():
    """The stress scenario (all four disruptions) in both modes, on the same customers."""
    return run("stress", "local"), run("stress", "ecosystem")


@pytest.fixture(scope="module")
def season(tmp_path_factory):
    """One ecosystem season of the stress scenario with the enterprises kept open, to read their own databases."""
    ents = build(tmp_path_factory.mktemp("eco"))
    result = Ecosystem(InProcessTransport(ents), "stress", "ecosystem").run()
    yield ents, result
    for e in ents.values():
        e.store.close()


# ---------------------------------------------------------------------------------------------- the message contract
def test_the_brief_example_message_is_a_valid_message():
    m = Message(message_id="MSG-001", conversation_id="MSG-001", sender="kirana.procurement",
                receiver="maklonnusa.quotation", message_type="REQUEST_PROPOSAL", task="production_contract",
                payload={"product": "KB-BRM-50", "units": 200_000}, reply_required=True)
    assert m.sender_enterprise == "kirana" and m.receiver_enterprise == "maklonnusa"
    with pytest.raises(ValidationError):
        Message(**{**m.model_dump(), "receiver": "maklonnusa"})          # an address is enterprise.agent
    with pytest.raises(ValidationError):
        Message(**{**m.model_dump(), "message_type": "SHOUT"})          # only the performatives of the contract


def test_messages_are_numbered_and_replies_stay_in_their_conversation():
    f = MessageFactory("kirana")
    first = f.new("kirana.procurement", "maklonnusa.quotation", "REQUEST_PROPOSAL", "production_contract", week=0)
    reply = MessageFactory("maklonnusa").reply(first, "maklonnusa.quotation", "PROPOSE", {"unit_price": 25_000})
    assert first.message_id == "KIR-0001" and first.conversation_id == first.message_id
    assert reply.conversation_id == first.conversation_id and reply.in_reply_to == first.message_id
    assert reply.receiver == first.sender and reply.task == first.task


def test_every_enterprise_publishes_an_agent_card_with_its_enterprise_model(tmp_path):
    ents = build(tmp_path)
    try:
        for key, e in ents.items():
            card = agent_card(e, f"http://localhost:{PORTS[key]}")
            assert card["url"] == f"http://localhost:{PORTS[key]}/api/a2a/messages"
            assert card["skills"] and all(s["id"].startswith(f"{key}.") for s in card["skills"])
            assert set(card["x-enterprise"]) == {"U_users_roles", "M_modules", "D_datasets", "A_agents", "P_protocol",
                                                 "G_governance"}
            # every enterprise has a predictive or planning agent of its own, not only messengers
            assert any(a["kind"] in ("predictive", "planning", "negotiation") for a in card["x-enterprise"]["A_agents"])
    finally:
        for e in ents.values():
            e.store.close()


# ---------------------------------------------------------------------------------------------- heterogeneity
def test_each_enterprise_keeps_its_own_database_in_its_own_dialect(tmp_path):
    ents = build(tmp_path)
    try:
        assert len({str(e.store.path) for e in ents.values()}) == len(ORDER)          # one database each
        assert ents["pasarnusa"].store.kind.startswith("JSON documents")             # a document store
        assert ents["kirana"].store.kind.startswith("SQLite")
        assert "MaintenanceLog" in ents["maklonnusa"].store.tables()                 # PascalCase tables
        assert "riwayat_qc" in ents["kemasprima"].store.tables()                     # Indonesian tables
        platforms = {k: (e.platform.get("database"), e.platform.get("units"), e.platform.get("time"))
                     for k, e in ents.items()}
        assert len({p[0] for p in platforms.values()}) >= 4                          # data models differ
        assert len({p[1] for p in platforms.values()}) >= 3                          # units differ
    finally:
        for e in ents.values():
            e.store.close()


def test_the_coordinator_translates_each_dialect_into_one_vocabulary():
    maklon = adapt("maklonnusa", {"freeCapacity": {"batchUnits": BATCH, "batchesByWeek": {"3": 2}}, "packagingSetsOnHand": 7})
    assert maklon == {"capacity": {3: 2 * BATCH}, "sets_on_hand": 7}
    kemas = adapt("kemasprima", {"kapasitas_set_per_minggu": 30_000, "prediksi_tingkat_cacat": {"5": 0.1}})
    assert kemas == {"capacity_per_week": 30_000, "defect_rate": {5: 0.1}}
    lanes = {"units_per_pallet": 1_200, "lanes": {"JKT": {iso_week(4): 10}, "SBY": {iso_week(4): 5}}}
    log = adapt("kirimcepat", {"lane_capacity": lanes})
    assert log["lane_capacity"] == {"JKT": {4: 12_000}, "SBY": {4: 6_000}}         # pallets -> units, ISO week -> week
    assert {r["enterprise"] for r in SCHEMA_MAPPING} == set(PLAN_AGENTS)


# ---------------------------------------------------------------------------------------------- governance
def test_an_enterprise_shares_more_in_the_ecosystem_and_never_its_private_records(tmp_path):
    ents = build(tmp_path)
    try:
        kirana, maklon = ents["kirana"], ents["maklonnusa"]
        kirana.reset("local")
        assert set(kirana.shared("control")) == {"product", "campaign_participation"}      # public only
        kirana.reset("ecosystem")
        control, partner = kirana.shared("control"), kirana.shared("partner")
        assert {"inventory", "demand_forecast", "margin_per_unit"} <= set(control)
        assert "inventory" not in partner and "demand_forecast" in partner                # partners see less
        maklon.reset("ecosystem")
        assert "freeCapacity" in maklon.shared("partner") and "packagingSetsOnHand" not in maklon.shared("partner")
        for e in ents.values():
            e.reset("ecosystem")
            assert not set(e.shared("control")) & set(e.private_datasets)
        with pytest.raises(ValueError):
            Governance().share({}, "everyone", "ecosystem")
    finally:
        for e in ents.values():
            e.store.close()


def test_roles_open_only_their_datasets_and_hidden_fields_are_masked(tmp_path):
    ents = build(tmp_path)
    try:
        maklon = ents["maklonnusa"]
        assert maklon.dataset("MaintenanceLog", "Maintenance Engineer", limit=3)["rows"]
        with pytest.raises(PermissionError):
            maklon.dataset("MaintenanceLog", "Sales")
        role = Role("Brand Manager", "", hidden_fields=("amount_idr",))
        assert visible_row({"item": "sales", "amount_idr": 5}, role) == {"item": "sales", "amount_idr": "hidden for this role"}
    finally:
        for e in ents.values():
            e.store.close()


def test_every_enterprise_has_a_role_that_reads_a_dataset_with_a_field_masked(season):
    """The data explorer shows all three cases in each enterprise: datasets open, closed and partly masked."""
    ents, _ = season
    for key, e in ents.items():
        masked = [(r.name, t) for r in e.roles for t in e.store.tables()
                  if r.may_open(t) and r.hidden_fields and e.store.count(t)
                  and any(v == "hidden for this role" for v in e.dataset(t, r.name, limit=1)["rows"][0].values())]
        closed = [(r.name, t) for r in e.roles for t in e.store.tables() if not r.may_open(t)]
        assert masked, f"{key}: no role sees a masked field"
        assert closed, f"{key}: every role opens every dataset"


# ---------------------------------------------------------------------------------------------- negotiation
def test_the_price_negotiation_converges_inside_both_private_reservations():
    deal = alternating_offers(MAKLON_PRICE, KIRANA_PRICE)          # MaklonNusa quotes first, Kirana counters
    assert deal["agreed"] and KIRANA_PRICE.target < MAKLON_PRICE.reservation <= deal["value"] <= KIRANA_PRICE.reservation
    seller = [h["value"] for h in deal["history"] if h["by"] == "opener"]
    buyer = [h["value"] for h in deal["history"] if h["by"] == "responder"]
    assert seller == sorted(seller, reverse=True) and buyer == sorted(buyer)      # each side only concedes


def test_boulware_holds_out_conceder_gives_way_and_no_overlap_means_no_deal():
    boulware, conceder = Tactic("p", 100, 50, beta=0.5, deadline=8), Tactic("p", 100, 50, beta=2.0, deadline=8)
    assert boulware.offer(4) > conceder.offer(4) and boulware.offer(8) == conceder.offer(8) == 50
    seller, buyer = Tactic("p", 120, 90, beta=1.0, deadline=6), Tactic("p", 60, 80, beta=1.0, deadline=6)
    assert not alternating_offers(seller, buyer)["agreed"]           # the seller's floor is above the buyer's ceiling


def test_the_contract_net_picks_the_reroute_that_gets_through():
    best = rank_options(REROUTE_OPTIONS, REROUTE_WEIGHTS)[0]
    assert best["id"] == "express_sby"                     # rail is cheaper but riskier, air safer but three times the price
    assert rank_options(REROUTE_OPTIONS, {"cost_idr_per_unit": 1.0})[0]["id"] == "rail_sby"


# ---------------------------------------------------------------------------------------------- the global planner
def plan_input(**over) -> PlanInput:
    weeks = range(1, 6)
    base = dict(week=1, horizon=5, demand={"JKT": {w: 9_000 for w in weeks}, "SBY": {w: 5_000 for w in weeks}},
                maklon_capacity={w: 15_000 for w in weeks}, packaging_good_capacity={w: 30_000 for w in weeks},
                defect_rate={w: 0.015 for w in weeks}, lane_capacity={"JKT": {w: 16_000 for w in range(1, 7)},
                                                                     "SBY": {w: 9_000 for w in range(1, 7)}},
                lane_price={"JKT": 380, "SBY": 1_150}, inventory={"JKT": 12_000, "SBY": 6_000}, arriving={},
                factory_stock=0, locked_production=10_000, unit_price=24_300, margin_per_unit=31_000)
    return PlanInput(**{**base, **over})


def test_the_plan_respects_capacity_whole_batches_and_a_rejection():
    free = solve(plan_input())
    assert free["status"] == "optimal" and free["planned_fill_rate"] > 0.9
    for r in free["weeks"][1:]:
        assert r["production"] == r["batches"] * BATCH and r["batches"] <= 3          # 15,000 units = 3 batches
        assert r["ship_JKT"] <= 16_000 and r["ship_SBY"] <= 9_000
    capped = solve(plan_input(max_batches={2: 1}))
    assert capped["weeks"][1]["batches"] <= 1 and capped["constraints"]["max_batches"] == {"2": 1}
    assert plan_diff(free, capped)                                                     # and the plan moved


def test_stock_left_after_the_season_keeps_its_value():
    """Valued at nothing, the stock still on hand after the last week makes the plan lose orders rather than fill one
    more batch; Kirana's books value that stock at cost, and so does the planner."""
    valued, worthless = solve(plan_input()), solve(plan_input(terminal_value=0))
    assert valued["totals"]["lost"] == 0 and valued["totals"]["ending_stock"] > 0
    assert worthless["totals"]["lost"] > 0 and worthless["totals"]["production"] < valued["totals"]["production"]


def test_the_objective_weights_change_the_decision():
    """Multi-objective: when lost orders hardly count (quality weight near zero), the cheapest plan is to make less."""
    balanced, cost_only = solve(plan_input()), solve(plan_input(weights={"quality": 0.01}))
    assert cost_only["totals"]["production"] < balanced["totals"]["production"]
    assert cost_only["planned_fill_rate"] < balanced["planned_fill_rate"]


# ---------------------------------------------------------------------------------------------- the world
def test_both_modes_face_the_same_customers_and_sensors_see_trouble_coming():
    a, b = World("stress", 7), World("stress", 7)
    assert a.demand(5, True) == b.demand(5, True)
    assert sum(a.demand(3, True)["marketplace"].values()) > sum(a.demand(3, False)["marketplace"].values())
    ahead = World("line_breakdown").signals(4)["maklonnusa"]["leading"]["weeks"]        # two weeks before the breakdown
    assert [r["week"] for r in ahead] == [5, 6] and ahead[1]["lines"][1]["vibration_mm_s"] > 6 > ahead[0]["lines"][1]["vibration_mm_s"]
    assert World("warehouse_flood").signals(6)["kirimcepat"]["leading"]["forecasts"][1]["rain_mm"] > 60
    with pytest.raises(ValueError):
        World("meteor")


# ---------------------------------------------------------------------------------------------- the whole season
def test_ecosystem_intelligence_beats_local_intelligence_and_every_enterprise_gains(stress):
    local, eco = stress
    a, b = local["ecosystem"], eco["ecosystem"]
    assert a["demand_units"] == b["demand_units"] or abs(a["demand_units"] - b["demand_units"]) / a["demand_units"] < 0.1
    assert b["fill_rate"] > a["fill_rate"] + 0.15 and b["lost_units"] < a["lost_units"] / 3
    assert b["total_profit_idr"] > a["total_profit_idr"] and b["defective_returns_idr"] < a["defective_returns_idr"]
    for row in compare(local, eco)["enterprises"]:
        assert row["ecosystem_profit_idr"] >= row["local_profit_idr"], row["enterprise"]


def test_all_four_negotiations_close_with_an_agreement(stress):
    local, eco = stress
    threads = {t["task"]: t for t in eco["negotiations"]}
    assert set(threads) == set(NEGOTIATIONS) and all(t["outcome"] == "agreed" for t in threads.values())
    assert MAKLON_PRICE.reservation <= threads["production_contract"]["agreed"] <= KIRANA_PRICE.reservation
    assert threads["reroute_options"]["agreed"] == "express_sby"
    assert not local["negotiations"]                       # on its own, nobody negotiates: list prices, standard terms


def test_every_message_follows_the_contract(stress):
    local, eco = stress
    for result in (local, eco):
        seen = set()
        for raw in result["messages"]:
            m = Message(**raw)
            assert m.message_type in PERFORMATIVES
            assert m.in_reply_to is None or m.in_reply_to in seen
            seen.add(m.message_id)
    tasks = {m["task"] for m in local["messages"]}
    assert "plan" not in tasks and "shared_view" not in tasks       # local intelligence: no coordinator, no sharing
    assert {"plan", "shared_view", "defect_risk", "flood_risk", "capacity_risk"} <= {m["task"] for m in eco["messages"]}


def test_a_season_is_reproducible():
    one, two = run("demand_surge", "ecosystem"), run("demand_surge", "ecosystem")
    assert one["ecosystem"] == two["ecosystem"]
    assert [m["message_id"] for m in one["messages"]] == [m["message_id"] for m in two["messages"]]


# ---------------------------------------------------------------------------------------------- adaptation
def test_a_defect_forecast_changes_the_packaging_order_and_the_terms(season):
    ents, result = season
    maklon = ents["maklonnusa"].store.rows("decisions")
    assert any("defect buffer from KemasPrima's forecast" in d["reasoning"] for d in maklon)
    assert any(d["decision"].startswith("Quality agreement") and "inspection" in d["decision"] for d in maklon)
    assert any("defect risk" in p["reason"] and p["diff"] for p in result["plans"])


def test_a_flood_warning_reroutes_jakarta_orders(season):
    ents, result = season
    kirana = ents["kirana"].store.rows("decisions")
    assert any("express_sby" in d["decision"] for d in kirana)
    assert any("flood risk" in p["reason"] and p["diff"] for p in result["plans"])


def test_a_breakdown_forecast_makes_maklonnusa_reject_the_plan_without_showing_why(season):
    ents, result = season
    rejections = [m for m in result["messages"] if m["task"] == "plan" and m["message_type"] == "REJECT_PROPOSAL"]
    assert rejections and all(set(m["payload"]) == {"max_batches", "reason"} for m in rejections)   # no maintenance data
    week = EVENTS["line_breakdown"].start
    cap = CAPACITY_BATCHES - OTHER_CLIENTS[week] - 2
    assert rejections[0]["payload"]["max_batches"] == {str(week): cap}
    replan = next(p for p in result["plans"] if p["rounds"] > 1)
    assert next(r for r in replan["result"]["weeks"] if r["week"] == week)["batches"] <= cap
    assert any(d["decision"].startswith("Reject the plan") for d in ents["maklonnusa"].store.rows("decisions"))


def test_a_traffic_surge_reaches_kirana_and_the_coordinator_the_same_morning():
    local, eco = run("demand_surge", "local"), run("demand_surge", "ecosystem")
    week = EVENTS["demand_surge"].start
    signals = [m for m in eco["messages"] if m["task"] == "demand_signal"]
    assert {m["receiver"] for m in signals} == {"kirana.demand_planner", "control.coordinator"}
    assert {m["week"] for m in signals} == {week}
    assert any(p["week"] == week and "demand signal" in p["reason"] and p["diff"] for p in eco["plans"])
    assert not any(m["task"] == "demand_signal" for m in local["messages"])     # on its own, PasarNusa keeps it
    assert eco["ecosystem"]["fill_rate"] > 0.99


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s != "normal"])
def test_every_disruption_triggers_a_replan_that_changes_the_plan(scenario):
    eco = run(scenario, "ecosystem")
    triggered = [p for p in eco["plans"][1:] if "fortnightly" not in p["reason"]]
    assert triggered and any(p["diff"] for p in triggered)
    assert {e["key"] for e in eco["events"] if e["kind"] == "disruption"} == set(SCENARIOS[scenario][2])


# ---------------------------------------------------------------------------------------------- the servers
def enterprise_clients(tmp_path) -> dict:
    from fastapi.testclient import TestClient

    from marketmind.ecosystem.server import create_enterprise_app
    return {k: TestClient(create_enterprise_app(k, tmp_path / "data", research_run=None, frontend_dist=tmp_path / "no-build",
                                                allowed_hosts=None, token=None), base_url=f"http://localhost:{PORTS[k]}")
            for k in ORDER}


def test_an_enterprise_server_serves_its_card_its_a2a_endpoint_and_governed_data(tmp_path):
    c = enterprise_clients(tmp_path)["maklonnusa"]
    assert c.get("/.well-known/agent-card.json").json()["name"] == "MaklonNusa"
    assert c.get("/api/node").json()["kind"] == "enterprise"
    ask = MessageFactory("kirana").new("kirana.procurement", "maklonnusa.quotation", "REQUEST", "price_list", week=0)
    replies = c.post("/api/a2a/messages", json=ask.model_dump()).json()["replies"]
    assert replies[0]["message_type"] == "INFORM" and replies[0]["payload"]["unit_price"] == 25_000
    wrong = MessageFactory("kirana").new("kirana.procurement", "kemasprima.sales", "REQUEST", "price_list", week=0)
    assert c.post("/api/a2a/messages", json=wrong.model_dump()).status_code == 400
    assert c.get("/api/a2a/shared", params={"audience": "partner"}).json()["view"].get("freeCapacity")
    assert c.get("/api/data/MaintenanceLog", params={"role": "Sales"}).status_code == 403
    assert c.get("/api/data/MaintenanceLog", params={"role": "Maintenance Engineer"}).json()["rows"]
    assert c.get("/api/data/no_such_table").status_code == 404


def test_a_season_over_http_gives_the_same_result_as_in_process(tmp_path):
    """Each enterprise behind its own app and database, reached only through its API, as `up` runs them."""
    clients = {PORTS[k]: c for k, c in enterprise_clients(tmp_path).items()}

    def route(request: httpx.Request) -> httpx.Response:
        r = clients[request.url.port].request(request.method, request.url.path, params=request.url.params,
                                              content=request.content,
                                              headers={"content-type": request.headers.get("content-type", "")})
        return httpx.Response(r.status_code, content=r.content, headers=r.headers)

    transport = HttpTransport({k: f"http://localhost:{PORTS[k]}" for k in ORDER})
    transport.client = httpx.Client(transport=httpx.MockTransport(route))
    over_http = Ecosystem(transport, "line_breakdown", "ecosystem").run()
    assert over_http["ecosystem"] == run("line_breakdown", "ecosystem")["ecosystem"]


def test_the_control_center_runs_and_compares_a_scenario(tmp_path):
    from fastapi.testclient import TestClient

    from marketmind.ecosystem.control import create_control_app
    ents = build(tmp_path / "data")
    c = TestClient(create_control_app(InProcessTransport(ents), frontend_dist=tmp_path / "no-build", allowed_hosts=None,
                                      token=None), base_url="http://localhost:8100")
    node = c.get("/api/node").json()
    assert node["kind"] == "control" and [e["key"] for e in node["enterprises"]] == list(ORDER)
    assert all(e["online"] for e in c.get("/api/control/enterprises").json()["enterprises"])
    assert c.post("/api/control/runs", json={"scenario": "meteor"}).status_code == 400
    run_id = c.post("/api/control/runs", json={"scenario": "warehouse_flood", "mode": "compare"}).json()["id"]
    deadline = time.time() + 60
    while (rec := c.get(f"/api/control/runs/{run_id}").json())["status"] == "running" and time.time() < deadline:
        time.sleep(0.2)
    assert rec["status"] == "done", rec.get("error")
    assert {r["kpi"] for r in rec["comparison"]["rows"]} >= {"fill_rate", "total_profit_idr"}
    assert "messages" not in rec["results"]["ecosystem"]                      # the log is paged separately
    reroute = c.get(f"/api/control/runs/{run_id}/messages", params={"task": "reroute_options"}).json()
    assert reroute["total"] > 0 and "plan" in reroute["tasks"]
    assert c.get("/api/control/runs/latest").json()["id"] == run_id
    for e in ents.values():
        e.store.close()


def test_the_command_line_compares_both_modes(tmp_path, capsys):
    from marketmind.ecosystem.__main__ import main
    out = tmp_path / "surge.json"
    main(["run", "--scenario", "demand_surge", "--json", str(out)])
    printed = capsys.readouterr().out
    assert "demand_surge" in printed and out.exists()
    import json
    saved = json.loads(out.read_text(encoding="utf-8"))["demand_surge"]
    assert set(saved) == {"local", "ecosystem", "comparison"}
    assert len(ENTERPRISES) == len(ORDER) == 6 and WEEKS == 16
