"""Negotiation between enterprises: alternating offers with time-dependent tactics, and Contract Net option ranking.

**Alternating offers.** Each side has a private ``Tactic``: the value it opens with (its target), the worst value it
would accept (its reservation, never revealed), a deadline in rounds and a concession curve (Faratin, Sierra and
Jennings 1998, "Negotiation decision functions for autonomous agents"): ``offer(t) = target + a(t) * (reservation -
target)`` with ``a(t) = (t / deadline) ** (1 / beta)``. ``beta < 1`` is Boulware (holds out, concedes near the deadline),
``beta > 1`` is Conceder. A side accepts the other's offer when it is within its reservation and worth at least as
much as the offer it would make next (the AC-next rule). The messages carry only offers, never reservations.

**Contract Net.** For a call for proposals with several answers (rerouting options during a flood), the caller ranks
the proposals by a weighted, normalised score over its own criteria (cost, delay, risk).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tactic:
    issue: str
    target: float
    reservation: float
    beta: float = 1.0
    deadline: int = 8

    def offer(self, rnd: int) -> float:
        t = min(max(rnd, 0), self.deadline) / self.deadline
        return self.target + (t ** (1.0 / self.beta)) * (self.reservation - self.target)

    def utility(self, value: float) -> float:
        """1 at the target, 0 at the reservation, below 0 beyond it."""
        span = self.reservation - self.target
        return 1.0 if span == 0 else 1.0 - (value - self.target) / span

    def acceptable(self, value: float) -> bool:
        return self.utility(value) >= -1e-9

    def accepts(self, value: float, rnd: int) -> bool:
        return self.acceptable(value) and self.utility(value) >= self.utility(self.offer(rnd + 1)) - 1e-9


def alternating_offers(opener: Tactic, responder: Tactic) -> dict:
    """Play a whole negotiation offline (for tests and the docs); the enterprises play the same rules over messages.

    ``opener`` makes the first offer. Returns the agreement (or none) and the history of offers."""
    history = []
    sides = (("opener", opener), ("responder", responder))
    deadline = max(opener.deadline, responder.deadline)
    for rnd in range(deadline + 1):
        who, me = sides[rnd % 2]
        other_name, other = sides[(rnd + 1) % 2]
        value = me.offer(rnd)
        history.append({"round": rnd, "by": who, "value": round(value, 2), "utility_opener": round(opener.utility(value), 3),
                        "utility_responder": round(responder.utility(value), 3)})
        if other.accepts(value, rnd):
            return {"agreed": True, "value": round(value, 2), "rounds": rnd + 1, "accepted_by": other_name,
                    "history": history}
    return {"agreed": False, "value": None, "rounds": deadline + 1, "accepted_by": None, "history": history}


def rank_options(options: list[dict], weights: dict[str, float]) -> list[dict]:
    """Score Contract Net proposals: each criterion is min-max normalised (lower is better) and weighted."""
    ranked = []
    for o in options:
        score = 0.0
        for crit, w in weights.items():
            vals = [x[crit] for x in options]
            lo, hi = min(vals), max(vals)
            score += w * (0.0 if hi == lo else (o[crit] - lo) / (hi - lo))
        ranked.append({**o, "score": round(score, 4)})
    return sorted(ranked, key=lambda o: o["score"])
