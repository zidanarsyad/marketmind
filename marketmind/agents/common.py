"""Small helpers shared by the agents (time windows, formatting, safe maths)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def windows(dates: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Return (last month, start of last-12-months, start of prior-12-months)."""
    last = pd.Timestamp(dates.max()).to_period("M").to_timestamp()
    l12 = last - pd.DateOffset(months=11)
    p12 = last - pd.DateOffset(months=23)
    return last, l12, p12


def growth(cur: float, prev: float) -> float:
    return float(cur / prev - 1) if prev else float("nan")


def idr(x: float) -> str:
    """Human-readable rupiah: Rp 38.3 tn / Rp 845 bn / Rp 89k."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    a = abs(x)
    if a >= 1e12:
        return f"Rp {x / 1e12:,.2f} tn"
    if a >= 1e9:
        return f"Rp {x / 1e9:,.1f} bn"
    if a >= 1e6:
        return f"Rp {x / 1e6:,.1f} mn"
    return f"Rp {x:,.0f}"


def pct(x: float, digits: int = 1, sign: bool = True) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"


def pp(x: float, digits: int = 1) -> str:
    return f"{x * 100:+.{digits}f} pp"


def r(x, digits: int = 3):
    try:
        return None if x is None or np.isnan(x) else round(float(x), digits)
    except TypeError:
        return x


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def minmax(s: pd.Series) -> pd.Series:
    rng = s.max() - s.min()
    return (s - s.min()) / rng if rng else s * 0 + 0.5


def client_key(client: str) -> str:
    return client.split()[0].lower().replace("è", "e")
