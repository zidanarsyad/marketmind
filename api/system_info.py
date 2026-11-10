"""What the app needs before a study: the data on disk, the brands in it, the default brief, and the LLM's status."""
from __future__ import annotations

import subprocess
import sys
import threading

import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from marketmind import config
from marketmind.config import DATASETS, DEFAULT_BRIEF, DEFAULT_CLIENT, DEFAULT_REAL_BRIEF, ROOT, data_manifest

from .security import scrub

router = APIRouter(prefix="/api", tags=["app"])

SENTIMENT_DATA = {"study": "The study's reviews (default)", "study+real": "The study's reviews + real reviews",
                  "real": "Real reviews only"}
_brands: dict[tuple, list[str]] = {}
_generate_lock = threading.Lock()


def data_ready() -> bool:
    """Anything to study: the simulated data, or a real-data folder with reviews or a catalogue."""
    return any((config.DATA_RAW / DATASETS[k]["file"]).is_file() for k in ("sales", "reviews", "catalog"))


def brands_in_data() -> list[str]:
    """Brands in the data folder, most records first: from the sales panel, or the reviews or catalogue without one."""
    for key in ("sales", "reviews", "catalog"):
        f = config.DATA_RAW / DATASETS[key]["file"]
        if f.is_file():
            cache_key = (str(f), f.stat().st_mtime_ns)
            if cache_key not in _brands:
                _brands[cache_key] = [str(b) for b in pd.read_csv(f, usecols=["brand"])["brand"].value_counts().index]
            return _brands[cache_key]
    return [DEFAULT_CLIENT]


def llm_status(llm) -> dict:
    return dict(available=llm.available, provider=llm.provider, model=llm.model if llm.available else None,
                description=scrub(llm.describe()))


@router.get("/health")
def health() -> dict:
    return dict(ok=True)


@router.get("/config")
def app_config(request: Request) -> dict:
    """Everything the new-study form needs, and what the sidebar shows about the data and the LLM."""
    from marketmind.ml import real_reviews
    manifest = data_manifest(config.DATA_RAW)
    real = manifest.get("kind") == "real"
    sentiment = list(SENTIMENT_DATA) if real_reviews.available() else ["study"]
    return dict(
        data=dict(ready=data_ready(), kind=manifest.get("kind"), source=manifest.get("source"),
                  licence=manifest.get("licence")),
        brands=brands_in_data() if data_ready() else [], default_client=DEFAULT_CLIENT,
        default_brief=DEFAULT_REAL_BRIEF if real else DEFAULT_BRIEF,
        sentiment_options=[dict(value=k, label=SENTIMENT_DATA[k]) for k in sentiment],
        datasets=[dict(name=k, file=v["file"], description=v["description"], source=v["source"]) for k, v in DATASETS.items()],
        llm=llm_status(request.app.state.llm))


@router.get("/llm")
def llm_info(request: Request) -> dict:
    return llm_status(request.app.state.llm)


@router.post("/llm/ping")
def llm_ping(request: Request) -> dict:
    """Send one tiny request to the configured LLM (uncached) and report whether it answered."""
    ok, message = request.app.state.llm.ping()
    return dict(ok=ok, message=scrub(str(message))[:300])


@router.post("/data/generate")
def generate_data() -> dict:
    """Generate the simulated datasets (scripts/generate_data.py) when the data folder has none."""
    if data_ready():
        raise HTTPException(409, "The datasets are already there.")
    if not _generate_lock.acquire(blocking=False):
        raise HTTPException(409, "The datasets are being generated.")
    try:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_data.py")], cwd=ROOT,
                              capture_output=True, text=True, timeout=900)
    finally:
        _generate_lock.release()
    if done.returncode != 0:
        raise HTTPException(500, "Generating the datasets failed: " + scrub(done.stderr[-600:]))
    _brands.clear()
    return dict(ok=True, ready=data_ready())
