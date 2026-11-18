"""The six enterprises of the ecosystem, and the ports their servers listen on."""
from __future__ import annotations

from pathlib import Path

from .base import Agent, Enterprise
from .kemasprima import KemasPrima
from .kirana import Kirana
from .kirimcepat import KirimCepat
from .maklonnusa import MaklonNusa
from .pasarnusa import PasarNusa
from .research import Research

ENTERPRISES: dict[str, type[Enterprise]] = {
    "kirana": Kirana, "maklonnusa": MaklonNusa, "kemasprima": KemasPrima, "kirimcepat": KirimCepat,
    "pasarnusa": PasarNusa, "research": Research}
ORDER = ("research", "pasarnusa", "kemasprima", "kirimcepat", "maklonnusa", "kirana")   # who acts first each week
PORTS = {"control": 8100, "kirana": 8101, "maklonnusa": 8102, "kemasprima": 8103, "kirimcepat": 8104,
         "pasarnusa": 8105, "research": 8106}


def create(key: str, data_dir: Path | str, seed: int = 7, research_run: str | None = None) -> Enterprise:
    cls = ENTERPRISES[key]
    if key == "research":
        return Research(data_dir, seed, run=research_run)
    return cls(data_dir, seed)


__all__ = ["Agent", "ENTERPRISES", "Enterprise", "ORDER", "PORTS", "create"]
