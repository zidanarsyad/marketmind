"""Structured insight objects exchanged between agents.

A ``Finding`` is the unit of knowledge in the system: a one-sentence, number-backed statement
with provenance (evidence), an impact score, a confidence score and a SWOT hint. Analysis agents
publish findings; the Strategy agent ranks and combines them; the Critic checks that every
number in the final report can be traced back to one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

AREAS = ("data", "market", "competition", "consumer", "segmentation", "pricing", "forecast", "strategy")


@dataclass
class Finding:
    id: str
    agent: str
    area: str
    title: str
    statement: str
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    impact: int = 3            # 1 (minor) .. 5 (critical)
    confidence: float = 0.7    # 0 .. 1
    swot: str | None = None    # "S", "W", "O" or "T" from the client's point of view
    tags: list[str] = field(default_factory=list)

    @property
    def priority(self) -> float:
        return round(self.impact * self.confidence, 3)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)

    def as_text(self) -> str:
        return f"[{self.id}] {self.title}: {self.statement}"
