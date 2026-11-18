"""What every enterprise in the ecosystem shares: the model E_i = (U_i, M_i, D_i, A_i, P_i, G_i), its own database,
its message handling, its decision trace and its settlement ledger.

An enterprise is reached only through ``receive`` (a message from another enterprise or the Control Center),
``tick`` (a simulated week begins: its agents act on their own data and sensors) and ``end_week``; and it shows the
outside world only ``shared(audience)``, which its governance filters. Everything it does lands in its own database:
the messages it sent and received, every decision with the reasoning and the inputs behind it, and a ledger of the
money it owes or is owed (all synthetic).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..governance import Governance, Role, visible_row
from ..protocol import Message, MessageFactory
from ..store import DocumentStore, SQLiteStore
from ..world import PRICE, PRODUCT, SKU


@dataclass
class Agent:
    name: str
    title: str
    kind: str            # predictive | planning | negotiation | monitoring | operations | service
    description: str
    model: str = ""
    status: str = "idle"
    last_action: str = ""
    last_week: int | None = None

    def card(self) -> dict:
        return {"name": self.name, "title": self.title, "kind": self.kind, "description": self.description,
                "model": self.model, "status": self.status, "last_action": self.last_action, "last_week": self.last_week}


class Enterprise:
    key = ""
    name = ""
    industry = ""
    description = ""
    city = ""
    # identity colours, validated as chart colours for every pair of enterprises that negotiate (light and dark)
    accent, accent_dark = "#0b6e5f", "#3fbfa4"
    store_kind = "sqlite"
    roles: tuple[Role, ...] = ()
    modules: tuple[tuple[str, str], ...] = ()
    platform: dict = {}
    governance = Governance()
    private_datasets: tuple[str, ...] = ()

    def __init__(self, data_dir: Path | str, seed: int = 7):
        self.data_dir = Path(data_dir)
        self.seed = seed
        self.store = (SQLiteStore(self.data_dir / f"{self.key}.db") if self.store_kind == "sqlite"
                      else DocumentStore(self.data_dir / self.key))
        self.agents: dict[str, Agent] = {a.name: a for a in self.make_agents()}
        self.mode, self.scenario, self.week = "ecosystem", "normal", 0
        self.reset()

    # ------------------------------------------------------------------ to override
    def make_agents(self) -> list[Agent]:
        return []

    def setup(self) -> None:
        """Seed the enterprise's own datasets and its starting state (called by ``reset``)."""

    def on_tick(self, week: int, leading: dict, actual: dict) -> list[Message]:
        return []

    def on_end_week(self, week: int) -> list[Message]:
        return []

    def view(self) -> dict:
        """Every fact the enterprise could share; ``governance.share`` decides who sees which."""
        return {}

    def kpis(self) -> dict:
        return {}

    # ------------------------------------------------------------------ lifecycle
    def reset(self, mode: str | None = None, scenario: str | None = None, seed: int | None = None) -> None:
        self.mode = mode or self.mode
        self.scenario = scenario or self.scenario
        if seed is not None:
            self.seed = seed
        self.week = 0
        self._handling: int | None = None
        self.msg = MessageFactory(self.key)
        self.negotiations: dict[str, dict] = {}
        self.store.reset()
        for a in self.agents.values():
            a.status, a.last_action, a.last_week = "idle", "", None
        self.setup()

    @property
    def now(self) -> int:
        """The week this enterprise acts in: its own clock, or the week of the message it is handling when that is
        later (the Control Center's messages at the start of a week arrive before the enterprise's own tick)."""
        return self.week if self._handling is None else max(self.week, self._handling)

    def receive(self, m: Message) -> list[Message]:
        self._log(m, "in")
        handler = (getattr(self, f"on_{m.message_type.lower()}_{m.task}", None)
                   or getattr(self, f"on_{m.message_type.lower()}", None))
        self._handling = m.week
        try:
            out = handler(m) if handler else []
        finally:
            self._handling = None
        for o in out:
            self._log(o, "out")
        return out

    def tick(self, week: int, signals: dict | None = None) -> list[Message]:
        self.week = week
        signals = signals or {}
        out = self.on_tick(week, signals.get("leading", {}), signals.get("actual", {}))
        for o in out:
            self._log(o, "out")
        return out

    def end_week(self, week: int) -> list[Message]:
        self.week = week
        out = self.on_end_week(week)
        for o in out:
            self._log(o, "out")
        return out

    # ------------------------------------------------------------------ messages
    def send(self, agent: str, receiver: str, message_type: str, task: str, payload: dict | None = None, *,
             reply_required: bool = False, conversation_id: str | None = None) -> Message:
        self._touch(agent, f"{message_type.lower()} {task} to {receiver}")
        return self.msg.new(f"{self.key}.{agent}", receiver, message_type, task, payload, week=self.now,
                            reply_required=reply_required, conversation_id=conversation_id)

    def reply(self, m: Message, agent: str, message_type: str, payload: dict | None = None, *, task: str | None = None,
              reply_required: bool = False) -> Message:
        self._touch(agent, f"{message_type.lower()} {task or m.task} to {m.sender}")
        return self.msg.reply(m, f"{self.key}.{agent}", message_type, payload, task=task, reply_required=reply_required)

    def negotiate(self, m: Message, tactic, value: float, issue: str, agent: str, on_agree, on_fail, *,
                  counter_type: str, decimals: int = 0, extra: dict | None = None) -> list[Message]:
        """One turn of alternating offers on ``m``'s conversation: accept the other side's ``value`` (AC-next), give
        up at the deadline, or answer with this side's next offer. Both sides count every offer made so far as the
        round, so they share the clock without sharing their reservation values."""
        state = self.negotiations.setdefault(m.conversation_id, {"history": [], "issue": issue})
        state["history"].append({"round": len(state["history"]), "by": m.sender_enterprise, "value": value})
        rnd = len(state["history"]) - 1
        if tactic.accepts(value, rnd):
            on_agree(value)
            return [self.reply(m, agent, "ACCEPT_PROPOSAL", {issue: value, "rounds": rnd + 1, **(extra or {})})]
        if rnd + 1 > tactic.deadline:
            on_fail()
            return [self.reply(m, agent, "REJECT_PROPOSAL", {"reason": "deadline reached without agreement",
                                                             "rounds": rnd + 1})]
        nxt = round(tactic.offer(rnd + 1), decimals)
        state["history"].append({"round": rnd + 1, "by": self.key, "value": nxt})
        return [self.reply(m, agent, counter_type, {issue: nxt, "round": rnd + 1, **(extra or {})})]

    def open_offer(self, m: Message, tactic, issue: str, agent: str, *, decimals: int = 0,
                   extra: dict | None = None) -> list[Message]:
        """Answer a call for proposals with this side's opening offer (round 0)."""
        value = round(tactic.offer(0), decimals)
        self.negotiations[m.conversation_id] = {"history": [{"round": 0, "by": self.key, "value": value}], "issue": issue}
        return [self.reply(m, agent, "PROPOSE", {issue: value, "round": 0, **(extra or {})})]

    def on_request_shared_view(self, m: Message) -> list[Message]:
        audience = "control" if m.sender_enterprise == "control" else "partner"
        return [self.reply(m, self.service_agent(), "INFORM", {"enterprise": self.key, "audience": audience,
                                                               "mode": self.mode, "view": self.shared(audience)})]

    def service_agent(self) -> str:
        return next(iter(self.agents))

    def on_propose_plan(self, m: Message) -> list[Message]:
        agent = m.receiver.split(".", 1)[1]
        self.decide(agent, "Accept the ecosystem plan proposal", "It stays within the limits I share.", refs=[m.message_id])
        return [self.reply(m, agent, "ACCEPT_PROPOSAL", {})]

    def on_confirm_plan(self, m: Message) -> list[Message]:
        agent = m.receiver.split(".", 1)[1]
        self.decide(agent, f"Ecosystem plan rev. {m.payload.get('revision')} confirmed", m.payload.get("reason", ""),
                    refs=[m.message_id])
        return []

    def on_inform_environment_change(self, m: Message) -> list[Message]:
        self.decide(self.service_agent(), f"Noted: {m.payload.get('title', 'environment change')}",
                    m.payload.get("detail", ""), inputs=m.payload, refs=[m.message_id])
        return []

    # ------------------------------------------------------------------ records
    def _touch(self, agent: str, action: str) -> None:
        a = self.agents.get(agent)
        if a:
            a.status, a.last_action, a.last_week = "active", action, self.now

    def _log(self, m: Message, direction: str) -> None:
        self.store.insert("messages", {"direction": direction, "week": m.week, "message_id": m.message_id,
                                       "conversation_id": m.conversation_id, "sender": m.sender, "receiver": m.receiver,
                                       "message_type": m.message_type, "task": m.task, "payload": m.payload,
                                       "in_reply_to": m.in_reply_to or ""})

    def decide(self, agent: str, decision: str, reasoning: str, *, inputs: dict | None = None,
               outputs: dict | None = None, refs: list[str] | tuple = ()) -> None:
        self._touch(agent, decision)
        self.store.insert("decisions", {"week": self.now, "agent": agent, "decision": decision, "reasoning": reasoning,
                                        "inputs": inputs or {}, "outputs": outputs or {}, "messages": list(refs)})

    def book(self, counterparty: str, item: str, amount_idr: float, units: int = 0, note: str = "") -> None:
        """A settlement line: positive is money the enterprise receives, negative money it pays (synthetic)."""
        self.store.insert("ledger", {"week": self.now, "counterparty": counterparty, "item": item, "units": int(units),
                                     "amount_idr": round(float(amount_idr)), "note": note})

    def ledger_total(self, item: str | None = None, counterparty: str | None = None) -> float:
        return float(sum(r["amount_idr"] for r in self.store.rows("ledger")
                         if (item is None or r["item"] == item) and (counterparty is None or r["counterparty"] == counterparty)))

    # ------------------------------------------------------------------ outward views
    def shared(self, audience: str) -> dict:
        return self.governance.share(self.view(), audience, self.mode)

    def role(self, name: str | None) -> Role:
        return next((r for r in self.roles if r.name == name), self.roles[0])

    def datasets(self, role: str | None = None) -> list[dict]:
        r = self.role(role)
        out = []
        for t in self.store.tables():
            out.append({"name": t, "rows": self.store.count(t), "open_to_role": r.may_open(t),
                        "private": t in self.private_datasets})
        return out

    def dataset(self, table: str, role: str | None = None, limit: int = 200, offset: int = 0) -> dict:
        r = self.role(role)
        if not r.may_open(table):
            raise PermissionError(f"the {r.name} role cannot open {table}")
        rows = [visible_row(x, r) for x in self.store.rows(table, limit, offset)]
        return {"name": table, "total": self.store.count(table), "offset": offset, "rows": rows, "role": r.name}

    def spec(self) -> dict:
        return {
            "U_users_roles": [{"role": r.name, "description": r.description, "can_approve": r.can_approve}
                              for r in self.roles],
            "M_modules": [{"module": m, "description": d} for m, d in self.modules],
            "D_datasets": {"store": self.store.kind, "private": list(self.private_datasets)},
            "A_agents": [a.card() for a in self.agents.values()],
            "P_protocol": self.platform,
            "G_governance": self.governance.describe(),
        }

    def status(self) -> dict:
        return {"key": self.key, "name": self.name, "industry": self.industry, "city": self.city, "accent": self.accent,
                "accent_dark": self.accent_dark, "mode": self.mode, "scenario": self.scenario, "week": self.week,
                "agents": [a.card() for a in self.agents.values()], "kpis": self.kpis()}

    def node(self) -> dict:
        return {"kind": "enterprise", "key": self.key, "name": self.name, "industry": self.industry,
                "description": self.description, "city": self.city, "accent": self.accent,
                "accent_dark": self.accent_dark,
                "product": {"sku": SKU, "name": PRODUCT, "price_idr": PRICE},
                "roles": [{"name": r.name, "description": r.description, "can_approve": r.can_approve}
                          for r in self.roles],
                "modules": [{"module": m, "description": d} for m, d in self.modules],
                "platform": self.platform, "governance": self.governance.describe()}
