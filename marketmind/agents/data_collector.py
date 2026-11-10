"""Data Collection Agent: gathers internal datasets and live external data.

* Internal: the six research datasets (sales panel, catalogue, reviews, social, survey, market size).
* External, live: World Bank Open Data API (no key needed) for Indonesian macro indicators, with an
  on-disk cache so the pipeline also works offline.
* External, optional: recent Indonesian skincare news headlines from GNews or NewsAPI when a free
  key is configured (GNEWS_API_KEY / NEWSAPI_KEY).
"""
from __future__ import annotations

import json
import time

import pandas as pd
import requests

from .. import config
from ..config import DATA_EXTERNAL, DATASETS, env
from ..core.agent import BaseAgent
from ..core.findings import Finding
from .common import pct

WORLD_BANK = {
    "NY.GDP.PCAP.CD": ("GDP per capita", "US$"),
    "NY.GDP.MKTP.KD.ZG": ("Real GDP growth", "%"),
    "SP.POP.TOTL": ("Population", "people"),
    "SP.URB.TOTL.IN.ZS": ("Urban population share", "%"),
    "FP.CPI.TOTL.ZG": ("Consumer price inflation", "%"),
    "IT.NET.USER.ZS": ("Internet users", "% of population"),
    "NE.CON.PRVT.KD.ZG": ("Household consumption growth", "%"),
    "SP.POP.1564.TO.ZS": ("Working-age population (15-64)", "%"),
}
WB_URL = "https://api.worldbank.org/v2/country/IDN/indicator/{code}?format=json&date=2015:2025&per_page=100"
WB_CACHE = DATA_EXTERNAL / "worldbank_IDN.json"


class DataCollectionAgent(BaseAgent):
    name = "Data Collection Agent"
    role = "Data engineer. Gathers internal research datasets and live external market data, and records provenance."
    goal = "Give the team complete, well-documented inputs, with live external context whenever it is reachable."

    def register_tools(self):
        self.tool("load_internal_datasets", self._load_internal, "read the internal research datasets")
        self.tool("fetch_world_bank_indicators", self._fetch_world_bank, "call the World Bank API for Indonesian macro data")
        self.tool("fetch_news_headlines", self._fetch_news, "pull recent skincare news (GNews / NewsAPI, optional key)")

    def execute(self) -> str:
        raw, catalog = self.use("load_internal_datasets")
        self.put("datasets.raw", raw, "Raw internal datasets")
        self.put("data.catalog", catalog, "Dataset inventory with provenance")
        self.put("data.provenance", self.manifest, "What the study's data is: real or simulated, source and licence")
        macro, source = self.use("fetch_world_bank_indicators")
        self.put("external.macro", macro, f"World Bank indicators for Indonesia ({source})")
        news = self.use("fetch_news_headlines")
        self.put("external.news", news, "Recent news headlines")
        total = int(catalog["rows"].sum())
        dated = catalog[catalog["coverage"] != "n/a"]
        span = (f" ({'sales panel' if dated['dataset'].iloc[0] == 'sales' else dated['dataset'].iloc[0]} "
                f"{dated['coverage'].iloc[0]})") if len(dated) else ""
        kind = "real" if self.manifest["kind"] == "real" else "internal"
        self.publish(Finding(
            id="DAT-01", agent=self.name, area="data", title="Evidence base",
            statement=f"The team analysed {len(raw)} {kind} datasets with {total:,} records{span}, plus "
                      f"{macro['indicator'].nunique() if not macro.empty else 0} World Bank macro indicators ({source}).",
            metrics=dict(datasets=len(raw), records=total, macro_indicators=int(macro["indicator"].nunique()) if not macro.empty else 0),
            evidence=list(catalog["dataset"]), impact=1, confidence=1.0, tags=["methodology"]))
        if not macro.empty:
            self._macro_finding(macro, source)
        return f"Loaded {len(raw)} datasets ({total:,} rows); macro data: {source}; news items: {len(news)}"

    # ------------------------------------------------------------------ tools
    def _load_internal(self) -> tuple[dict, pd.DataFrame]:
        raw, rows = {}, []
        self.manifest = config.data_manifest(config.DATA_RAW)
        real = self.manifest["kind"] == "real"
        for key, spec in DATASETS.items():
            path = config.DATA_RAW / spec["file"]
            if not path.exists():
                if real:   # a real-data folder holds only what its source has: say so, quietly
                    self.think(f"{spec['file']} is not part of this real-data folder; analyses that need it are left out.")
                else:
                    self.warn(f"{spec['file']} is missing - run scripts/generate_data.py")
                continue
            df = pd.read_csv(path)
            raw[key] = df
            dc = spec["date_col"]
            coverage = f"{df[dc].min()} to {df[dc].max()}" if dc and dc in df else "n/a"
            rows.append(dict(dataset=key, file=spec["file"], rows=len(df), columns=df.shape[1], coverage=coverage,
                             size_kb=round(path.stat().st_size / 1024),
                             source=self.manifest["datasets"].get(key, {}).get("source", spec["source"]),
                             description=spec["description"],
                             modified=time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))))
        catalog = pd.DataFrame(rows)
        catalog["coverage"] = catalog["coverage"].astype(str)
        catalog = catalog.sort_values("dataset", key=lambda s: s.map({"sales": 0}).fillna(1)).reset_index(drop=True)
        return raw, catalog

    def _fetch_world_bank(self) -> tuple[pd.DataFrame, str]:
        records, source = [], "live World Bank API"
        try:
            for code, (label, unit) in WORLD_BANK.items():
                r = requests.get(WB_URL.format(code=code), timeout=15)
                r.raise_for_status()
                payload = r.json()
                for item in (payload[1] if len(payload) > 1 and payload[1] else []):
                    if item.get("value") is not None:
                        records.append(dict(indicator=label, code=code, unit=unit, year=int(item["date"]),
                                            value=float(item["value"])))
            if not records:
                raise ValueError("empty response")
            WB_CACHE.parent.mkdir(parents=True, exist_ok=True)
            WB_CACHE.write_text(json.dumps(dict(fetched=time.strftime("%Y-%m-%d %H:%M"), records=records), indent=1),
                                encoding="utf-8")
        except Exception as exc:
            if WB_CACHE.exists():
                blob = json.loads(WB_CACHE.read_text(encoding="utf-8"))
                records, source = blob["records"], f"cached World Bank data from {blob['fetched']}"
                self.warn(f"World Bank API unreachable ({type(exc).__name__}); using {source}")
            else:
                self.warn(f"World Bank API unreachable ({type(exc).__name__}) and no cache; continuing without macro data")
                return pd.DataFrame(columns=["indicator", "code", "unit", "year", "value"]), "unavailable"
        return pd.DataFrame(records).sort_values(["indicator", "year"]).reset_index(drop=True), source

    def _fetch_news(self) -> pd.DataFrame:
        cols = ["published", "source", "title", "description", "url"]
        gnews, newsapi = env("GNEWS_API_KEY"), env("NEWSAPI_KEY")
        try:
            if gnews:
                r = requests.get("https://gnews.io/api/v4/search", timeout=15, params=dict(
                    q="skincare", lang="id", country="id", max=20, sortby="publishedAt", apikey=gnews))
                r.raise_for_status()
                items = r.json().get("articles", [])
                return pd.DataFrame([dict(published=a.get("publishedAt", "")[:10], source=(a.get("source") or {}).get("name"),
                                          title=a.get("title"), description=a.get("description"), url=a.get("url"))
                                     for a in items], columns=cols)
            if newsapi:
                r = requests.get("https://newsapi.org/v2/everything", timeout=15, params=dict(
                    q="skincare OR \"perawatan kulit\"", language="id", sortBy="publishedAt", pageSize=30, apiKey=newsapi))
                r.raise_for_status()
                items = r.json().get("articles", [])
                return pd.DataFrame([dict(published=a.get("publishedAt", "")[:10], source=(a.get("source") or {}).get("name"),
                                          title=a.get("title"), description=a.get("description"), url=a.get("url"))
                                     for a in items], columns=cols)
        except Exception as exc:
            self.warn(f"News API call failed ({type(exc).__name__}); continuing without news")
        return pd.DataFrame(columns=cols)

    def _macro_finding(self, macro: pd.DataFrame, source: str) -> None:
        def latest(label):
            s = macro[macro["indicator"] == label].sort_values("year")
            return (s.iloc[-1]["value"], int(s.iloc[-1]["year"]), s) if len(s) else (None, None, s)

        gdp, gy, gdp_s = latest("GDP per capita")
        net, ny, _ = latest("Internet users")
        urb, uy, _ = latest("Urban population share")
        pop, py, _ = latest("Population")
        metrics, parts = {}, []
        if gdp is not None:
            base = gdp_s[gdp_s["year"] == 2019]["value"]
            g = (gdp / base.iloc[0] - 1) if len(base) else None
            metrics.update(gdp_per_capita_usd=round(gdp), gdp_year=gy)
            parts.append(f"GDP per capita reached US${gdp:,.0f} in {gy}" + (f" ({pct(g)} vs 2019)" if g is not None else ""))
            if g is not None:
                metrics["gdp_pc_growth_since_2019"] = round(g, 3)
        if pop is not None:
            metrics.update(population_mn=round(pop / 1e6, 1))
            parts.append(f"population {pop / 1e6:,.1f} million")
        if urb is not None:
            metrics.update(urban_share_pct=round(urb, 1))
            parts.append(f"{urb:.1f}% urban")
        if net is not None:
            metrics.update(internet_users_pct=round(net, 1), internet_year=ny)
            parts.append(f"{net:.1f}% of people online ({ny})")
        self.publish(Finding(
            id="MAC-01", agent=self.name, area="market", title="Macro tailwinds",
            statement="Indonesia's macro backdrop supports premiumisation and digital commerce: " + "; ".join(parts) + ".",
            metrics=metrics, evidence=[f"World Bank Open Data ({source})"], impact=2, confidence=0.9, swot="O",
            tags=["macro"]))
