"""Number grounding: does every number in a text appear in the evidence?

The Critic checks the report with it, and the two on-demand agents check their own answers with it (the agentic-RAG
Analyst Chat against the passages it retrieved, the ReAct Data Agent against its tools' observations), so no agent
releases a number that no tool produced.

A written number is grounded when an evidence number lies within half a unit of its last written decimal place, or
within 0.5% of it. Evidence numbers are expanded with x100 (ratios of 3 or less, which prose writes as percentages)
and /10^3 to /10^12 (rupiah written in thousands, millions, billions or trillions). Small integers (0 to 12) and years
(1990 to 2035) always pass.
"""
from __future__ import annotations

import bisect
import re
from typing import Any

NUM = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
CURRENCY = re.compile(r"(?<![A-Za-z])(Rp|IDR|USD|US\$|\$)(?=\d)")


def numbers_in(text: str) -> list[tuple[float, int, str]]:
    """(value, decimals as written, raw text) for every number in ``text``; 'Rp2,126' reads as 2,126."""
    out = []
    for m in NUM.finditer(CURRENCY.sub(r"\1 ", text or "")):
        raw = m.group(0)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        try:
            out.append((float(raw.replace(",", "")), decimals, raw))
        except ValueError:
            continue
    return out


def expand(v: float) -> set[float]:
    """An evidence number and the forms prose may write it in (percentages, thousands to trillions)."""
    vals = {v, abs(v)}
    if abs(v) <= 3:
        vals |= {v * 100, abs(v * 100)}
    for div in (1e3, 1e6, 1e9, 1e12):
        if abs(v) >= div:
            vals.add(v / div)
    return vals


def evidence_numbers(*objs: Any) -> list[float]:
    """Every number inside the given strings, numbers, dicts and lists, expanded and sorted: the allowed set."""
    vals: set[float] = set()

    def absorb(obj: Any) -> None:
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, (int, float)):
            if obj == obj and abs(obj) != float("inf"):          # NaN and infinity are not evidence
                vals.update(expand(float(obj)))
        elif isinstance(obj, str):
            for v, _, _ in numbers_in(obj):
                vals.update(expand(v))
        elif isinstance(obj, dict):
            for v in obj.values():
                absorb(v)
        elif isinstance(obj, (list, tuple, set)):
            for v in obj:
                absorb(v)
        elif hasattr(obj, "item"):                                # numpy scalars
            try:
                absorb(obj.item())
            except (TypeError, ValueError):
                pass

    for o in objs:
        absorb(o)
    return sorted(vals)


def grounded(x: float, decimals: int, allowed: list[float]) -> bool:
    """True when ``x``, written with ``decimals`` decimal places, matches an evidence number (see the module doc)."""
    if decimals == 0 and (0 <= abs(x) <= 12 or 1990 <= x <= 2035):
        return True
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    for target in (x, abs(x)):
        i = bisect.bisect_left(allowed, target - tol)
        if i < len(allowed) and allowed[i] <= target + tol:
            return True
        j = bisect.bisect_left(allowed, target * 0.995)
        if j < len(allowed) and allowed[j] <= target * 1.005:
            return True
    return False


def ungrounded(text: str, allowed: list[float]) -> list[str]:
    """The numbers written in ``text`` that the evidence does not contain, as written."""
    return [raw for x, dec, raw in numbers_in(text) if not grounded(x, dec, allowed)]
