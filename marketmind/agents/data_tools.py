"""Read-only tools over a run's datasets, for the ReAct Data Agent (agents/data_agent.py).

The tables are the datasets the run studied (its data folder), cleaned with the Data Quality agent's own steps, so a
total computed here matches the study's. Every tool is deterministic and read-only: it runs no code, checks every
table, column and filter it is given, caps what it returns, and the review and post text it shows is masked for
personal details. A wrong argument comes back as an error the agent can read and correct, never as an exception.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import DATA_RAW, DATASETS
from ..core.privacy import mask_personal
from ..ml.text import ASPECT_LEXICON, normalize
from .data_quality import clean_tables

DATE_COLUMNS = {"sales": "month", "reviews": "review_date", "social": "post_date", "survey": "survey_date",
                "market_size": "year"}
TEXT_COLUMNS = {"reviews": "review_text", "social": "post_text"}
HIDDEN = {"reviewer_id", "respondent_id", "attention_check", "completion_time_sec", "has_text", "source"}
TABLE_ALIASES = {"market_sales_panel": "sales", "sales_panel": "sales", "panel": "sales", "product_reviews": "reviews",
                 "review": "reviews", "social_mentions": "social", "posts": "social", "consumer_survey": "survey",
                 "product_catalog": "catalog", "catalogue": "catalog", "products": "catalog", "market": "market_size"}
AGGS = ("sum", "mean", "median", "min", "max", "count", "nunique")
UNITS = {"revenue_idr": "rupiah", "avg_selling_price_idr": "rupiah per unit", "list_price_idr": "rupiah per unit",
         "discount_pct": "a fraction (0.12 means 12%)", "stockout_days": "days", "price_idr": "rupiah",
         "price_per_ml_idr": "rupiah per ml", "monthly_income_idr": "rupiah", "monthly_skincare_spend_idr": "rupiah",
         "market_value_idr_bn": "billion rupiah", "local_brand_share_pct": "percent", "online_share_pct": "percent",
         "yoy_growth_pct": "percent", "rating": "stars, 1-5", "rating_avg": "stars, 1-5",
         "nps_main_brand": "likelihood to recommend, 0-10", "concept_purchase_intent": "1-5 scale"}
MAX_ROWS = 15
# English words a question may use for the review aspects, to search Indonesian review text (ml/text.py lexicon)
ENGLISH_ASPECTS = {
    "texture": "tekstur", "sticky": "tekstur", "greasy": "tekstur", "absorb": "tekstur", "scent": "aroma",
    "smell": "aroma", "fragrance": "aroma", "perfume": "aroma", "packaging": "kemasan", "pump": "kemasan",
    "bottle": "kemasan", "leak": "kemasan", "price": "harga", "value": "harga", "expensive": "harga", "cheap": "harga",
    "delivery": "pengiriman", "shipping": "pengiriman", "seller": "pengiriman", "courier": "pengiriman",
    "breakout": "reaksi_kulit", "breakouts": "reaksi_kulit", "irritation": "reaksi_kulit", "reaction": "reaksi_kulit",
    "acne": "reaksi_kulit", "itchy": "reaksi_kulit", "fake": "keaslian", "counterfeit": "keaslian",
    "authentic": "keaslian", "original": "keaslian", "stock": "stok", "effective": "efektivitas",
    "results": "efektivitas", "effectiveness": "efektivitas", "brightening": "efektivitas",
}
SEARCH_STOPWORDS = {"about", "the", "a", "an", "of", "on", "in", "with", "and", "or", "for", "to", "is", "are", "do",
                    "does", "what", "say", "says", "customers", "people", "reviews", "review", "posts", "mention",
                    "mentions", "complain", "complaints", "complaint", "their", "its", "it", "our", "we"}


class ToolError(ValueError):
    """A wrong argument. The agent sees it as an observation and can correct the call."""


@dataclass
class Observation:
    text: str                                 # what the agent reads: a sentence or a compact table
    data: Any = field(default=None)           # the numbers behind it, which ground the answer
    error: bool = False


# ------------------------------------------------------------------------------------------------ loading
_cache: dict[tuple, dict[str, pd.DataFrame]] = {}
_cache_lock = threading.Lock()


def run_data_dir(run) -> Path:
    """The data folder a saved run studied: its --data-dir, or the bundled data."""
    return Path((run.meta.get("options") or {}).get("data_dir") or DATA_RAW.parent)


def load_tables(data_dir: Path | str) -> dict[str, pd.DataFrame]:
    """The cleaned, masked datasets of a data folder, loaded once per folder and file version."""
    data_dir = Path(data_dir)
    files = {k: data_dir / "raw" / v["file"] for k, v in DATASETS.items() if k != "social_labels"}
    present = {k: f for k, f in files.items() if f.is_file()}
    key = (str(data_dir.resolve()), tuple(sorted((k, f.stat().st_mtime_ns) for k, f in present.items())))
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    tables = clean_tables({k: pd.read_csv(f) for k, f in present.items()})
    for name, col in TEXT_COLUMNS.items():
        if name in tables and col in tables[name]:
            tables[name][col] = tables[name][col].map(lambda t: mask_personal(t) if isinstance(t, str) else t)
    for name, col in DATE_COLUMNS.items():
        if name in tables and col in tables[name] and name != "market_size":
            tables[name][col] = pd.to_datetime(tables[name][col], errors="coerce")
            tables[name]["year"] = tables[name][col].dt.year
    with _cache_lock:
        _cache[key] = tables
    return tables


# ------------------------------------------------------------------------------------------------ helpers
def _plain(text: Any) -> str:
    """Lower case without accents, for matching names: 'Lumière Lab' -> 'lumiere lab'."""
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def _number(v: Any) -> Any:
    """A JSON-friendly Python number (numpy scalars and NaN handled)."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    return v


def fmt(v: Any) -> str:
    """A number as the observation shows it: thousands separators, at most 4 significant decimals."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        f = float(v)
        if abs(f) >= 1000:
            return f"{f:,.0f}" if abs(f - round(f)) < 1e-9 or abs(f) >= 1e6 else f"{f:,.2f}"
        return f"{f:.4g}" if abs(f) < 1 else f"{f:,.2f}"
    return str(v)


def period_bounds(spec: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """'2025' -> the year, '2025-03' -> the month, '2024-07..2025-06' or [a, b] -> from the start of a to the end of b."""
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return period_bounds(spec[0])[0], period_bounds(spec[1])[1]
    s = str(spec).strip()
    if ".." in s:
        a, b = s.split("..", 1)
        return period_bounds(a)[0], period_bounds(b)[1]
    if re.fullmatch(r"\d{4}", s):
        return pd.Timestamp(f"{s}-01-01"), pd.Timestamp(f"{s}-12-31 23:59:59")
    if re.fullmatch(r"\d{4}-\d{1,2}", s):
        start = pd.Timestamp(f"{s}-01")
        return start, start + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", s):
        day = pd.Timestamp(s)
        return day, day + pd.Timedelta(hours=23, minutes=59, seconds=59)
    raise ToolError(f"cannot read the period {spec!r}; write 2025, 2025-03 or 2024-07..2025-06")


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max}


def safe_arithmetic(expression: str) -> float:
    """Evaluate arithmetic on numbers (+ - * / ** %, round, abs, min, max) without executing anything else."""
    if len(expression) > 200:
        raise ToolError("the expression is too long (200 characters at most)")
    try:
        tree = ast.parse(expression.replace(",", "") if re.search(r"\d,\d{3}", expression) else expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"cannot read the expression: {exc.msg}") from exc

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ToolError("exponents above 12 are not allowed")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
                and not node.keywords and len(node.args) <= 4):
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ToolError("only numbers, + - * / ** %, parentheses and round/abs/min/max are allowed")

    try:
        value = ev(tree)
    except ZeroDivisionError as exc:
        raise ToolError("division by zero") from exc
    return float(value)


# ------------------------------------------------------------------------------------------------ the toolkit
class DataToolkit:
    """The ReAct Data Agent's tools. ``run(action, args)`` returns an Observation for any input, even a wrong one."""

    DESCRIPTIONS = {
        "list_tables": "list_tables(): every table with its size, date range and columns.",
        "describe": "describe(table, column=None): a column's values (with counts) or statistics; without a column, "
                    "the table's columns.",
        "aggregate": "aggregate(table, measure='rows', agg='sum', by=None, filters=None, start=None, end=None, top=15, "
                     "order='desc'): a total, average or count, optionally grouped by up to two columns and sorted. "
                     "agg is one of sum, mean, median, min, max, count, nunique; measure 'rows' counts rows.",
        "share": "share(table, measure='rows', by, filters=None, start=None, end=None, top=15): each group's share of "
                 "the total, in percent (sum of the measure, or the row count).",
        "compare": "compare(table, measure, period_a, period_b, by=None, agg='sum', filters=None, top=15): the measure "
                   "in two periods and the change in percent, overall or per group.",
        "trend": "trend(table, measure='rows', agg='sum', freq='month', filters=None, start=None, end=None): the "
                 "measure per month, quarter or year, with the first, last, lowest and highest period.",
        "search_text": "search_text(query, table='reviews', filters=None, start=None, end=None, limit=5): how many "
                       "reviews (or social posts) mention every word of the query, with examples; English aspect "
                       "words (texture, scent, packaging, price, delivery, breakout, fake, stock) also match their "
                       "Indonesian terms.",
        "calculate": "calculate(expression): arithmetic on numbers taken from observations, for example "
                     "'(1520 - 1210) / 1210 * 100'.",
    }

    def __init__(self, tables: dict[str, pd.DataFrame]):
        self.tables = {k: v for k, v in tables.items() if isinstance(v, pd.DataFrame)}
        self.tools = {"list_tables": self.list_tables, "describe": self.describe, "aggregate": self.aggregate,
                      "share": self.share, "compare": self.compare, "trend": self.trend,
                      "search_text": self.search_text, "calculate": self.calculate}

    # -------------------------------------------------------------- dispatch
    def run(self, action: Any, args: Any) -> Observation:
        fn = self.tools.get(str(action))
        if fn is None:
            return Observation(f"Error: there is no tool {action!r}. The tools are: {', '.join(self.tools)}.", error=True)
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return Observation("Error: args must be a JSON object, for example {\"table\": \"sales\"}.", error=True)
        try:
            return fn(**args)
        except ToolError as exc:
            return Observation(f"Error: {exc}", error=True)
        except TypeError as exc:
            return Observation(f"Error: wrong arguments for {action}: {exc}. Usage: {self.DESCRIPTIONS[str(action)]}",
                               error=True)
        except Exception as exc:  # a tool must never break the agent's loop
            return Observation(f"Error: {action} failed ({type(exc).__name__}: {exc}).", error=True)

    def tool_help(self) -> str:
        return "\n".join(f"- {d}" for d in self.DESCRIPTIONS.values())

    # -------------------------------------------------------------- schema
    def columns(self, name: str) -> dict[str, list[str]]:
        df = self.tables[name]
        measures, dims, text = [], [], []
        for c in df.columns:
            if c in HIDDEN or c == DATE_COLUMNS.get(name) or pd.api.types.is_datetime64_any_dtype(df[c]):
                continue
            if c == TEXT_COLUMNS.get(name):
                text.append(c)
            elif pd.api.types.is_bool_dtype(df[c]):
                dims.append(c)
            elif pd.api.types.is_numeric_dtype(df[c]) and c != "year":
                measures.append(c)
            elif c == "year" or df[c].nunique(dropna=True) <= 80:
                dims.append(c)
        return dict(measures=measures, dimensions=dims, text=text)

    def schema_text(self) -> str:
        """The tables as the agent's system prompt describes them: columns, date range and example values."""
        lines = []
        for name, df in self.tables.items():
            cols = self.columns(name)
            date = DATE_COLUMNS.get(name)
            span = ""
            if date in df:
                lo, hi = df[date].min(), df[date].max()
                span = (f"; dates in {date} from {lo:%Y-%m} to {hi:%Y-%m}" if isinstance(lo, pd.Timestamp)
                        else f"; {date} from {lo} to {hi}")
            lines.append(f"* {name} ({len(df):,} rows{span})")
            lines.append(f"  measures: {', '.join(_families(cols['measures'])) or '-'}")
            units = [f"{c}: {UNITS[c]}" for c in cols["measures"] if c in UNITS]
            if units:
                lines.append(f"  units: {'; '.join(units)}")
            flags = []
            for d in cols["dimensions"]:
                if pd.api.types.is_bool_dtype(df[d]) or set(df[d].dropna().unique()) <= {0, 1}:   # True == 1
                    flags.append(d)
                    continue
                if d == "year":
                    continue
                values = df[d].dropna().astype(str).value_counts().index.tolist()
                if len(values) > 30:
                    lines.append(f"  {d}: {len(values)} values (list them with describe)")
                    continue
                shown = ", ".join(values[:7]) + (f", ... ({len(values)} values)" if len(values) > 7 else "")
                lines.append(f"  {d}: {shown}")
            if flags:
                lines.append(f"  yes/no columns: {', '.join(_families(flags))}")
            if "year" in df:
                lines.append("  year: the calendar year of the date, for grouping")
            if cols["text"]:
                lines.append(f"  text: {', '.join(cols['text'])} (searchable with search_text)")
        return "\n".join(lines)

    # -------------------------------------------------------------- argument checks
    def _table(self, table: Any) -> tuple[str, pd.DataFrame]:
        name = _plain(table).replace(" ", "_")
        name = TABLE_ALIASES.get(name, name)
        if name not in self.tables:
            raise ToolError(f"there is no table {table!r}; the tables are: {', '.join(self.tables)}")
        return name, self.tables[name]

    def _column(self, df: pd.DataFrame, column: Any, table: str) -> str:
        if column in df.columns and column not in HIDDEN:
            return column
        want = _plain(column).replace(" ", "_")
        for c in df.columns:
            if _plain(c) == want and c not in HIDDEN:
                return c
        shown = [c for c in df.columns if c not in HIDDEN]
        raise ToolError(f"table {table} has no column {column!r}; its columns are: {', '.join(shown)}")

    def _by(self, df: pd.DataFrame, table: str, by: Any) -> list[str]:
        if by in (None, "", []):
            return []
        cols = [by] if isinstance(by, str) else list(by)
        if len(cols) > 2:
            raise ToolError("group by at most two columns")
        return [self._column(df, c, table) for c in cols]

    def _match_values(self, series: pd.Series, value: Any, column: str) -> pd.Series:
        """Rows equal to ``value``: strings compared ignoring case and accents."""
        if isinstance(value, str) and not pd.api.types.is_numeric_dtype(series):
            want = _plain(value)
            mask = series.astype(str).map(_plain) == want
            if not mask.any():
                values = series.dropna().astype(str).value_counts().index.tolist()
                close = [v for v in values if want in _plain(v) or _plain(v) in want]
                hint = f"; did you mean {', '.join(close[:3])}?" if close else f"; its values include: {', '.join(values[:12])}"
                raise ToolError(f"no rows where {column} = {value!r}{hint}")
            return mask
        if isinstance(value, str) and pd.api.types.is_numeric_dtype(series):
            try:
                value = float(value)
            except ValueError as exc:
                raise ToolError(f"{column} is numeric; {value!r} is not a number") from exc
        if pd.api.types.is_bool_dtype(series) and isinstance(value, str):
            value = value.strip().lower() in ("true", "yes", "1")
        return series == value

    def _filter(self, df: pd.DataFrame, table: str, filters: Any) -> pd.DataFrame:
        if not filters:
            return df
        if not isinstance(filters, dict):
            raise ToolError("filters must be an object such as {\"brand\": \"Kirana Beauty\"}")
        mask = pd.Series(True, index=df.index)
        for column, cond in filters.items():
            c = self._column(df, column, table)
            s = df[c]
            if isinstance(cond, dict):
                for op, value in cond.items():
                    op = str(op).lower().lstrip("$")
                    if op in ("eq", "=", "=="):
                        mask &= self._match_values(s, value, c)
                    elif op in ("ne", "!=", "not"):
                        mask &= ~self._match_values(s, value, c)
                    elif op in ("in",):
                        mask &= np.logical_or.reduce([self._match_values(s, v, c) for v in (value or [])]) if value else False
                    elif op in ("contains",):
                        mask &= s.astype(str).map(_plain).str.contains(re.escape(_plain(value)), na=False)
                    elif op in ("gt", ">", "gte", ">=", "lt", "<", "lte", "<="):
                        if not pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_datetime64_any_dtype(s):
                            raise ToolError(f"{c} is not numeric, so {op} does not apply")
                        v = pd.Timestamp(str(value)) if pd.api.types.is_datetime64_any_dtype(s) else float(value)
                        fn = {"gt": operator.gt, ">": operator.gt, "gte": operator.ge, ">=": operator.ge,
                              "lt": operator.lt, "<": operator.lt, "lte": operator.le, "<=": operator.le}[op]
                        mask &= fn(s, v)
                    else:
                        raise ToolError(f"unknown filter operator {op!r}; use eq, ne, in, contains, gt, gte, lt, lte")
            elif isinstance(cond, (list, tuple, set)):
                if not cond:
                    raise ToolError(f"the list of values for {c} is empty")
                mask &= np.logical_or.reduce([self._match_values(s, v, c) for v in cond])
            else:
                mask &= self._match_values(s, cond, c)
        return df[mask]

    def _period(self, df: pd.DataFrame, table: str, start: Any, end: Any) -> pd.DataFrame:
        if start in (None, "") and end in (None, ""):
            return df
        date = DATE_COLUMNS.get(table)
        if date not in df:
            raise ToolError(f"table {table} has no date column, so start and end do not apply")
        if table == "market_size":
            lo = int(period_bounds(start)[0].year) if start not in (None, "") else -10**9
            hi = int(period_bounds(end)[1].year) if end not in (None, "") else 10**9
            return df[df[date].between(lo, hi)]
        lo = period_bounds(start)[0] if start not in (None, "") else pd.Timestamp.min
        hi = period_bounds(end)[1] if end not in (None, "") else pd.Timestamp.max
        return df[df[date].between(lo, hi)]

    def _between(self, df: pd.DataFrame, table: str, period: Any) -> pd.DataFrame:
        if period in (None, ""):
            raise ToolError("both periods are needed, for example period_a='2024', period_b='2025'")
        lo, hi = period_bounds(period)
        return self._period(df, table, lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))

    @staticmethod
    def _agg(agg: Any, measure: Any) -> str:
        agg = str(agg or "sum").lower()
        agg = {"avg": "mean", "average": "mean", "total": "sum", "distinct": "nunique"}.get(agg, agg)
        if agg not in AGGS:
            raise ToolError(f"unknown agg {agg!r}; use one of {', '.join(AGGS)}")
        if measure in (None, "", "rows", "*", "count") and agg not in ("count", "sum"):
            raise ToolError("measure 'rows' can only be counted; name a column to average it")
        return agg

    def _measure(self, df: pd.DataFrame, table: str, measure: Any, agg: str) -> str | None:
        if measure in (None, "", "rows", "*", "count"):
            return None
        c = self._column(df, measure, table)
        if agg in ("sum", "mean", "median", "min", "max") and not pd.api.types.is_numeric_dtype(df[c]):
            raise ToolError(f"{c} is not numeric; use agg='count' or 'nunique', or another measure")
        return c

    @staticmethod
    def _reduce(df: pd.DataFrame, col: str | None, agg: str, by: list[str]):
        if col is None:
            return df.groupby(by, observed=True).size() if by else len(df)
        grouped = df.groupby(by, observed=True)[col] if by else df[col]
        if agg == "count":
            return grouped.count()
        return getattr(grouped, agg)()

    @staticmethod
    def _label(col: str | None, agg: str) -> str:
        return "rows" if col is None else f"{agg}({col})"

    @staticmethod
    def _scope(filters: Any, start: Any, end: Any) -> str:
        parts = []
        if filters:
            parts.append(json.dumps(filters, ensure_ascii=False, default=str))
        if start not in (None, "") or end not in (None, ""):
            parts.append(f"period {start or '...'} to {end or '...'}")
        return f" [{'; '.join(parts)}]" if parts else ""

    @staticmethod
    def _table_text(rows: list[dict], columns: list[str]) -> str:
        head = " | ".join(columns)
        body = "\n".join(" | ".join(fmt(r.get(c)) for c in columns) for r in rows)
        return f"{head}\n{body}"

    # -------------------------------------------------------------- tools
    def list_tables(self) -> Observation:
        lines, data = [], {}
        for name, df in self.tables.items():
            cols = self.columns(name)
            date = DATE_COLUMNS.get(name)
            span = ""
            if date in df:
                lo, hi = df[date].min(), df[date].max()
                span = f", {lo:%Y-%m} to {hi:%Y-%m}" if isinstance(lo, pd.Timestamp) else f", {lo} to {hi}"
            lines.append(f"{name}: {len(df):,} rows{span}; measures: {', '.join(cols['measures']) or '-'}; "
                         f"dimensions: {', '.join(cols['dimensions']) or '-'}"
                         + (f"; text: {', '.join(cols['text'])}" if cols["text"] else ""))
            data[name] = len(df)
        return Observation("\n".join(lines), data=data)

    def describe(self, table: str, column: str | None = None) -> Observation:
        name, df = self._table(table)
        if column is None:
            cols = self.columns(name)
            return Observation(f"{name}: {len(df):,} rows. Measures: {', '.join(cols['measures'])}. Dimensions: "
                               f"{', '.join(cols['dimensions'])}." + (f" Text: {', '.join(cols['text'])}." if cols["text"] else ""),
                               data={"rows": len(df)})
        c = self._column(df, column, name)
        s = df[c]
        if c == TEXT_COLUMNS.get(name):
            return Observation(f"{c} is free text ({int(s.notna().sum()):,} non-empty); search it with search_text.",
                               data={"non_empty": int(s.notna().sum())})
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            stats = dict(count=int(s.count()), mean=_number(s.mean()), median=_number(s.median()),
                         min=_number(s.min()), max=_number(s.max()), sum=_number(s.sum()))
            return Observation(f"{name}.{c}: " + ", ".join(f"{k} {fmt(v)}" for k, v in stats.items()), data=stats)
        if pd.api.types.is_datetime64_any_dtype(s):
            return Observation(f"{name}.{c}: from {s.min():%Y-%m-%d} to {s.max():%Y-%m-%d}", data={})
        counts = s.astype(str).value_counts()
        rows = [dict(value=k, rows=int(v)) for k, v in counts.head(MAX_ROWS).items()]
        return Observation(f"{name}.{c}: {len(counts)} distinct values\n" + self._table_text(rows, ["value", "rows"]),
                           data=dict(distinct=len(counts), values=rows))

    def aggregate(self, table: str, measure: str = "rows", agg: str = "sum", by: Any = None, filters: Any = None,
                  start: Any = None, end: Any = None, top: int = MAX_ROWS, order: str = "desc") -> Observation:
        name, df = self._table(table)
        agg = self._agg(agg, measure)
        col = self._measure(df, name, measure, agg)
        by_cols = self._by(df, name, by)
        df = self._period(self._filter(df, name, filters), name, start, end)
        label = self._label(col, agg)
        scope = self._scope(filters, start, end)
        if df.empty:
            return Observation(f"No rows match{scope}.", data={"rows": 0})
        result = self._reduce(df, col, agg, by_cols)
        if not by_cols:
            value = _number(result)
            return Observation(f"{name}: {label} = {fmt(value)} over {len(df):,} rows{scope}",
                               data={"value": value, "rows": len(df)})
        result = result.sort_values(ascending=str(order).lower() == "asc")
        top = max(1, min(int(top or MAX_ROWS), 50))
        total = _number(result.sum()) if agg in ("sum", "count") or col is None else None
        rows = [dict(**({c: k for c, k in zip(by_cols, key if isinstance(key, tuple) else (key,), strict=True)}),
                     value=_number(v)) for key, v in result.head(top).items()]
        more = f" ({len(result) - top} more groups not shown)" if len(result) > top else ""
        tail = f"\nTotal over all groups: {fmt(total)}" if total is not None else ""
        return Observation(f"{name}: {label} by {', '.join(by_cols)}{scope}{more}\n"
                           + self._table_text(rows, by_cols + ["value"]) + tail,
                           data={"groups": rows, "total": total, "n_groups": len(result)})

    def share(self, table: str, by: Any = None, measure: str = "rows", filters: Any = None, start: Any = None,
              end: Any = None, top: int = MAX_ROWS) -> Observation:
        name, df = self._table(table)
        if by in (None, "", []):
            raise ToolError("share needs by, the column whose groups to compare (for example 'brand')")
        col = self._measure(df, name, measure, "sum")
        by_cols = self._by(df, name, by)
        df = self._period(self._filter(df, name, filters), name, start, end)
        scope = self._scope(filters, start, end)
        if df.empty:
            return Observation(f"No rows match{scope}.", data={"rows": 0})
        result = self._reduce(df, col, "sum", by_cols).sort_values(ascending=False)
        total = float(result.sum())
        if total == 0:
            return Observation(f"The total is 0{scope}, so there are no shares.", data={"total": 0})
        top = max(1, min(int(top or MAX_ROWS), 50))
        rows = [dict(**({c: k for c, k in zip(by_cols, key if isinstance(key, tuple) else (key,), strict=True)}),
                     value=_number(v), share_pct=round(float(v) / total * 100, 2)) for key, v in result.head(top).items()]
        return Observation(f"{name}: share of {self._label(col, 'sum')} by {', '.join(by_cols)}{scope}\n"
                           + self._table_text(rows, by_cols + ["value", "share_pct"]) + f"\nTotal: {fmt(_number(total))}",
                           data={"groups": rows, "total": _number(total)})

    def compare(self, table: str, measure: str = "rows", period_a: Any = None, period_b: Any = None, by: Any = None,
                agg: str = "sum", filters: Any = None, top: int = MAX_ROWS) -> Observation:
        name, df = self._table(table)
        agg = self._agg(agg, measure)
        col = self._measure(df, name, measure, agg)
        by_cols = self._by(df, name, by)
        df = self._filter(df, name, filters)
        a, b = self._between(df, name, period_a), self._between(df, name, period_b)
        label = self._label(col, agg)
        pa, pb = str(period_a), str(period_b)
        scope = self._scope(filters, None, None)
        if not by_cols:
            va, vb = (_number(self._reduce(x, col, agg, [])) if len(x) else None for x in (a, b))
            pct = round((vb - va) / abs(va) * 100, 2) if va not in (None, 0) and vb is not None else None
            change = _number(vb - va) if va is not None and vb is not None else None
            return Observation(f"{name}: {label}{scope}: {pa} = {fmt(va)}, {pb} = {fmt(vb)}, change = {fmt(change)} "
                               f"({'n/a' if pct is None else f'{pct:+.2f}%'})",
                               data=dict(value_a=va, value_b=vb, change=change, change_pct=pct))
        ra, rb = self._reduce(a, col, agg, by_cols), self._reduce(b, col, agg, by_cols)
        both = pd.concat([ra.rename("a"), rb.rename("b")], axis=1)
        both["change_pct"] = (both["b"] - both["a"]) / both["a"].abs() * 100
        both = both.sort_values("change_pct", ascending=False, na_position="last")
        top = max(1, min(int(top or MAX_ROWS), 50))
        rows = []
        for key, r in both.head(top).iterrows():
            keys = key if isinstance(key, tuple) else (key,)
            rows.append(dict(**{c: k for c, k in zip(by_cols, keys, strict=True)}, value_a=_number(r["a"]),
                             value_b=_number(r["b"]), change_pct=_number(round(r["change_pct"], 2))
                             if pd.notna(r["change_pct"]) else None))
        return Observation(f"{name}: {label} by {', '.join(by_cols)}{scope}, {pa} (value_a) against {pb} (value_b), "
                           "sorted by change_pct\n" + self._table_text(rows, by_cols + ["value_a", "value_b", "change_pct"]),
                           data={"groups": rows})

    def trend(self, table: str, measure: str = "rows", agg: str = "sum", freq: str = "month", filters: Any = None,
              start: Any = None, end: Any = None) -> Observation:
        name, df = self._table(table)
        date = DATE_COLUMNS.get(name)
        if date not in df:
            raise ToolError(f"table {name} has no date column")
        agg = self._agg(agg, measure)
        col = self._measure(df, name, measure, agg)
        df = self._period(self._filter(df, name, filters), name, start, end)
        scope = self._scope(filters, start, end)
        if df.empty:
            return Observation(f"No rows match{scope}.", data={"rows": 0})
        freq = str(freq or "month").lower()
        code = {"month": "M", "monthly": "M", "quarter": "Q", "quarterly": "Q", "year": "Y", "yearly": "Y",
                "annual": "Y"}.get(freq)
        if code is None:
            raise ToolError("freq must be month, quarter or year")
        if name == "market_size":
            key = df[date].astype(int).astype(str)
        else:
            key = df[date].dt.to_period(code).astype(str)
        series = self._reduce(df.assign(_period=key), col, agg, ["_period"]).sort_index()
        points = [dict(period=k, value=_number(v)) for k, v in series.items()]
        first, last = points[0], points[-1]
        peak = max(points, key=lambda p: p["value"] if p["value"] is not None else -math.inf)
        low = min(points, key=lambda p: p["value"] if p["value"] is not None else math.inf)
        pct = (round((last["value"] - first["value"]) / abs(first["value"]) * 100, 2)
               if first["value"] not in (None, 0) and last["value"] is not None else None)
        shown = points if len(points) <= 48 else points[:12] + points[-36:]
        text = (f"{name}: {self._label(col, agg)} per {freq}{scope}: "
                + ", ".join(f"{p['period']} {fmt(p['value'])}" for p in shown)
                + f"\nfirst {first['period']} = {fmt(first['value'])}; last {last['period']} = {fmt(last['value'])}; "
                f"change {'n/a' if pct is None else f'{pct:+.2f}%'}; highest {peak['period']} = {fmt(peak['value'])}; "
                f"lowest {low['period']} = {fmt(low['value'])}")
        return Observation(text, data=dict(points=points, first=first, last=last, peak=peak, low=low, change_pct=pct))

    def search_text(self, query: str, table: str = "reviews", filters: Any = None, start: Any = None,
                    end: Any = None, limit: int = 5) -> Observation:
        name, df = self._table(table)
        text_col = TEXT_COLUMNS.get(name)
        if text_col not in df:
            raise ToolError(f"table {name} has no text to search; search 'reviews' or 'social'")
        groups = search_terms(query)
        if not groups:
            raise ToolError("the query has no searchable words")
        df = self._period(self._filter(df, name, filters), name, start, end)
        base = df[df[text_col].notna()]
        norm = base[text_col].map(normalize)
        hit = pd.Series(True, index=base.index)
        for terms in groups:
            hit &= norm.map(lambda t, terms=terms: _mentions(t, terms))
        matches = base[hit]
        scope = self._scope(filters, start, end)
        share = round(len(matches) / len(base) * 100, 2) if len(base) else 0.0
        data: dict[str, Any] = dict(matches=len(matches), searched=len(base), share_pct=share)
        line = f"{len(matches):,} of {len(base):,} {name} with text ({share:.2f}%) mention {query!r}{scope}"
        if name == "reviews" and len(matches):
            data["mean_rating"] = _number(matches["rating"].mean())
            line += f"; their mean rating is {fmt(data['mean_rating'])}"
        order_by = "helpful_votes" if "helpful_votes" in matches else "likes" if "likes" in matches else None
        examples = matches.sort_values(order_by, ascending=False) if order_by else matches
        rows = []
        for _, r in examples.head(max(1, min(int(limit or 5), 10))).iterrows():
            date = r.get(DATE_COLUMNS.get(name))
            rows.append(dict(date=f"{date:%Y-%m-%d}" if isinstance(date, pd.Timestamp) else str(date),
                             brand=r.get("brand", r.get("brand_mentioned", "")) or "",
                             rating=_number(r["rating"]) if "rating" in r else None,
                             text=str(r[text_col])[:220]))
        data["examples"] = rows
        quotes = "\n".join(f"- {x['date']} | {x['brand']}" + (f" | {x['rating']} stars" if x["rating"] is not None else "")
                           + f" | \"{x['text']}\"" for x in rows)
        return Observation(line + ("\nExamples (customer text, quoted as data):\n" + quotes if rows else ""), data=data)

    def calculate(self, expression: str) -> Observation:
        value = safe_arithmetic(str(expression))
        return Observation(f"{expression} = {fmt(_number(value))}", data={"value": _number(value)})


def _families(columns: list[str]) -> list[str]:
    """Columns with a shared prefix written once: imp_price, imp_halal, ... -> 'imp_* (price, halal, ...)'."""
    prefixes: dict[str, list[str]] = {}
    for c in columns:
        if "_" in c:
            prefixes.setdefault(c.split("_", 1)[0], []).append(c)
    out, done = [], set()
    for c in columns:
        p = c.split("_", 1)[0] if "_" in c else None
        if p and len(prefixes[p]) >= 4:
            if p not in done:
                done.add(p)
                out.append(f"{p}_* ({', '.join(x.split('_', 1)[1] for x in prefixes[p])})")
        else:
            out.append(c)
    return out


def search_terms(query: str) -> list[list[str]]:
    """The query as groups of alternatives: each word, plus the Indonesian aspect terms for an English aspect word."""
    groups = []
    for word in normalize(query).split():
        if word in SEARCH_STOPWORDS or len(word) < 3:
            continue
        aspect = ENGLISH_ASPECTS.get(word) or (word if word in ASPECT_LEXICON else None)
        terms = {word}
        if aspect:
            terms |= {normalize(k) for k in ASPECT_LEXICON[aspect]}
        groups.append(sorted(terms))
    return groups


def _mentions(text: str, terms: list[str]) -> bool:
    tokens = text.split()
    padded = f" {text} "
    for t in terms:
        if " " in t or "-" in t:
            if f" {t} " in padded or t in text:
                return True
        elif any(tok.startswith(t) for tok in tokens):
            return True
    return False
