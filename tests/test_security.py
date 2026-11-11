"""Trust and security: credentials never leave the process, a shared server needs its access token, and personal
details in review text are masked. (The approval gates that never approve on a reviewer's behalf are tested with the
other agentic behaviour, in test_agentic.py.)
"""
from __future__ import annotations

import json
import os
import zipfile

import pandas as pd
import pytest

from marketmind.core.access import TOKEN_ENV, hostname, is_local, token_matches
from marketmind.core.privacy import mask_personal
from marketmind.core.redact import REDACTED, scrub, scrub_obj

FAKE_KEY = "gsk_test_0123456789abcdefSECRET"
TOKEN = "s3cret-token-123"


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv("MARKETMIND_TEST_API_KEY", FAKE_KEY)
    return FAKE_KEY


# ---------------------------------------------------------------------------------------------- credentials
def test_scrub_replaces_credential_values_and_leaves_other_text_alone(fake_key):
    assert scrub(f"HTTP 401: invalid key {fake_key}") == f"HTTP 401: invalid key {REDACTED}"
    assert scrub_obj({"error": [f"x{fake_key}", 3], "n": 1.5}) == {"error": [f"x{REDACTED}", 3], "n": 1.5}
    assert scrub("nothing secret here") == "nothing secret here" and scrub("") == ""


def test_no_credential_reaches_the_trace_the_saved_run_or_an_llm_error(fake_key, tmp_path):
    from marketmind.core.blackboard import Blackboard
    from marketmind.core.events import Tracer
    from marketmind.core.llm import LLMClient
    from marketmind.core.store import save_run

    tracer = Tracer("t")
    ev = tracer.emit("Analyst", "error", f"provider said: bad key {fake_key}", detail={"url": f"https://x/?k={fake_key}"})
    assert fake_key not in ev.message and fake_key not in json.dumps(ev.data)
    llm = LLMClient(provider="none")
    llm.last_error = f"HTTP 401: {fake_key} is not valid"            # as if a provider echoed the key back
    assert llm.last_error == f"HTTP 401: {REDACTED} is not valid"
    bb = Blackboard()
    bb.put("report.markdown", f"# Report\nkey {fake_key}", agent="Report Writer")
    bb.put("notes", {"llm_error": fake_key}, agent="Report Writer")
    bb.put("quotes", pd.DataFrame({"text": [fake_key, "fine"]}), agent="Consumer Insight")
    save_run(tmp_path, bb, tracer, {"llm": {"description": f"offline - {llm.last_error}"}, "error": fake_key})
    written = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    assert {"report.md", "notes.json", "quotes.csv", "run_meta.json", "trace.jsonl", "findings.json"} <= set(written)
    assert [name for name, text in written.items() if fake_key in text] == []
    assert REDACTED in written["report.md"] and REDACTED in written["quotes.csv"] and REDACTED in written["trace.jsonl"]
    assert pd.read_csv(tmp_path / "tables" / "quotes.csv")["text"].tolist() == [REDACTED, "fine"]   # still a clean CSV


# ---------------------------------------------------------------------------------------------- access token
def test_hosts_and_token_comparison():
    assert [hostname(h) for h in ("localhost:8000", "[::1]:8000", "127.0.0.1", "192.168.1.5:8501")] == \
        ["localhost", "::1", "127.0.0.1", "192.168.1.5"]
    assert is_local("localhost:8501") and is_local("[::1]:8501") and not is_local("192.168.1.5:8501")
    assert token_matches(TOKEN, TOKEN) and not token_matches(TOKEN + "x", TOKEN)
    assert not token_matches(None, TOKEN) and not token_matches("", TOKEN) and not token_matches(TOKEN, None)


def network_client(tmp_path, token=TOKEN):
    """The API as `python -m api --host 0.0.0.0` serves it: any host name, behind the access token."""
    from fastapi.testclient import TestClient

    from api.app import create_app
    from marketmind.core.llm import LLMClient
    app = create_app(llm=LLMClient(provider="none"), frontend_dist=tmp_path / "no-build", allowed_hosts=None, token=token)
    return TestClient(app, base_url="http://192.168.1.5:8000", follow_redirects=False)


def test_shared_on_a_network_the_api_shows_nothing_without_the_access_token(tmp_path):
    client = network_client(tmp_path)
    refused = client.get("/api/runs")
    assert refused.status_code == 401 and "access token" in refused.json()["detail"]
    page = client.get("/")
    assert page.status_code == 401 and "Access token needed" in page.text
    assert client.get("/api/health", headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    assert client.get("/?token=wrong-token").status_code == 401
    # scripts send the token as a bearer header
    assert client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"}).json() == {"ok": True}


def test_the_link_with_the_token_sets_a_cookie_and_leaves_the_address_bar(tmp_path):
    client = network_client(tmp_path)
    login = client.get(f"/runs?token={TOKEN}&tab=report")
    assert login.status_code == 303 and login.headers["location"] == "/runs?tab=report"
    cookie = login.headers["set-cookie"].lower()
    assert f"marketmind_token={TOKEN}" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/health").json() == {"ok": True}          # the browser now sends the cookie by itself


def test_without_a_token_the_api_on_this_computer_is_open_as_before(tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.security import LOCAL_HOSTS
    from marketmind.core.llm import LLMClient
    app = create_app(llm=LLMClient(provider="none"), frontend_dist=tmp_path / "no-build", allowed_hosts=LOCAL_HOSTS,
                     token=None)
    assert TestClient(app, base_url="http://localhost").get("/api/health").json() == {"ok": True}


def test_serving_on_a_network_makes_up_a_token_and_prints_the_link(monkeypatch, capsys):
    import uvicorn

    from api import __main__ as cli
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("MARKETMIND_ALLOWED_HOSTS", raising=False)
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    cli.main(["--host", "0.0.0.0", "--port", "8123"])
    token = os.environ[TOKEN_ENV]
    assert len(token) >= 20 and calls[0]["host"] == "0.0.0.0" and os.environ["MARKETMIND_ALLOWED_HOSTS"] == "*"
    assert f"http://localhost:8123/?token={token}" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------- personal details
@pytest.mark.parametrize("text, masked", [
    ("WA aku 0812-3456-7890 ya", "WA aku [phone] ya"),
    ("hubungi +62 812 3456 7890", "hubungi [phone]"),
    ("nomor 6281234567890.", "nomor [phone]."),
    ("email budi.s@gmail.com dong", "email [email] dong"),
    ("kata @budi_santoso. mantap", "kata [user]. mantap"),
    # left alone: prices, dates, times, sizes, an "@" between numbers, too many digits for a phone number
    ("harga Rp 85.000, dulu Rp 628.500.000", "harga Rp 85.000, dulu Rp 628.500.000"),
    ("beli 2024-08-12 jam 08.30, isi 30ml 0.8%", "beli 2024-08-12 jam 08.30, isi 30ml 0.8%"),
    ("kode 085000 dan 2@50rb, 08123456789012345", "kode 085000 dan 2@50rb, 08123456789012345"),
])
def test_personal_details_are_masked_and_prices_and_dates_are_not(text, masked):
    assert mask_personal(text) == masked


def test_review_quotes_picked_for_the_report_are_masked():
    from marketmind.agents.consumer_insight import ConsumerInsightAgent
    agent = ConsumerInsightAgent.__new__(ConsumerInsightAgent)
    agent.client = "GlowNesia"
    scored = pd.DataFrame(dict(brand=["GlowNesia"], pred=["positive"], score=[0.99],
                               review_text=["Suka! Order lagi ke 0812 3456 7890 atau glow.fan@mail.com"]))
    quotes = agent._examples(scored, asp=pd.DataFrame(), anomalies=pd.DataFrame())
    assert quotes["text"].tolist() == ["Suka! Order lagi ke [phone] atau [email]"]


def test_the_tokopedia_importer_masks_personal_details_in_review_text(tmp_path):
    from test_real_data import product   # the Kaggle row layout, shared with the importer tests

    from marketmind.adapters import tokopedia
    rows = [product(1, "Kecantikan|Perawatan Wajah", "Wardah Lightening Facial Wash 100ml", 11,
                    [(5, "mantap, WA saya 0812-3456-7890 atau budi@mail.com, kata @budi_s", "2024-05-12 10:22:01")])]
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tokopedia_products_with_review.csv", pd.DataFrame(rows).to_csv(index=False))
    reviews = tokopedia.convert(tokopedia.read_beauty_products(path))[0]
    assert reviews["review_text"].tolist() == ["mantap, WA saya [phone] atau [email], kata [user]"]
