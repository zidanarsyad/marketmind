"""The LLM client against a fake OpenAI-style HTTP API: no network, no API key, no cost.

Covers the request it sends, response parsing, token counting, caching, the retry on rate limits, the
fallback when JSON mode is unsupported, replacing a retired model, and failing softly on HTTP errors.
"""
from __future__ import annotations

import copy
import json

import pytest

from marketmind.core import llm as llm_module
from marketmind.core.llm import LLMClient


class FakeResponse:
    def __init__(self, status: int = 200, payload: dict | None = None, text: str = "", headers: dict | None = None):
        self.status_code, self._payload, self.headers = status, payload or {}, headers or {}
        self.text = text or json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


def ok(content: str, prompt_tokens: int = 12, completion_tokens: int = 3) -> FakeResponse:
    return FakeResponse(payload={"choices": [{"message": {"content": content}}],
                                 "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}})


@pytest.fixture
def fake_api(monkeypatch):
    """Queue responses for requests.post; every request sent is recorded in `sent`."""
    queue, sent = [], []

    def post(url, json=None, headers=None, timeout=None):
        sent.append(dict(url=url, payload=copy.deepcopy(json), headers=dict(headers or {})))  # the client reuses its dict
        return queue.pop(0)

    monkeypatch.setattr(llm_module.requests, "post", post)
    monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: sent.append(dict(slept=seconds)))
    return queue, sent


def client(tmp_path, provider: str = "groq") -> LLMClient:
    c = LLMClient(provider=provider, api_key="test-key")
    c.cache_dir, c.min_interval = tmp_path, 0.0
    return c


def test_completion_is_parsed_counted_and_cached_without_leaking_the_key(tmp_path, fake_api):
    queue, sent = fake_api
    queue.append(ok("  Halo!  "))
    c = client(tmp_path)
    assert c.complete("You are terse.", "Say hello", agent="test") == "Halo!"
    request = sent[0]
    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert [m["role"] for m in request["payload"]["messages"]] == ["system", "user"]
    assert request["payload"]["model"] == "llama-3.3-70b-versatile"
    assert c.complete("You are terse.", "Say hello", agent="test") == "Halo!"    # served from the cache
    assert len(sent) == 1 and c.stats.cache_hits == 1 and c.stats.calls == 1
    assert (c.stats.prompt_tokens, c.stats.completion_tokens) == (12, 3)
    assert all("test-key" not in p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json"))


def test_rate_limit_is_retried_after_the_advised_wait(tmp_path, fake_api):
    queue, sent = fake_api
    queue += [FakeResponse(429, headers={"retry-after": "7"}), ok("done")]
    assert client(tmp_path).complete("s", "p") == "done"
    assert {"slept": 7.0} in sent


def test_http_errors_return_none_and_record_the_reason(tmp_path, fake_api):
    queue, _ = fake_api
    queue.append(FakeResponse(401, text="invalid api key"))
    c = client(tmp_path)
    assert c.complete("s", "p") is None
    assert c.last_error.startswith("HTTP 401") and c.stats.failures == 1
    assert not list(tmp_path.glob("*.json"))                               # failures are never cached


def test_json_mode_is_dropped_when_the_provider_rejects_it(tmp_path, fake_api):
    queue, sent = fake_api
    queue += [FakeResponse(400, text="response_format is not supported"), ok('{"a": 1}')]
    assert client(tmp_path).complete_json("s", "p") == {"a": 1}
    assert "response_format" in sent[0]["payload"] and "response_format" not in sent[1]["payload"]


def test_a_retired_model_is_replaced_from_the_providers_model_list(tmp_path, fake_api, monkeypatch):
    queue, sent = fake_api
    queue += [FakeResponse(404, text="The model `llama-3.3-70b-versatile` does not exist"), ok("hi")]
    models = {"data": [{"id": "whisper-large-v3"}, {"id": "llama-3.3-70b-specdec"}, {"id": "qwen-2.5-32b"}]}
    monkeypatch.setattr(llm_module.requests, "get", lambda url, headers=None, timeout=None: FakeResponse(payload=models))
    c = client(tmp_path)
    assert c.complete("s", "p") == "hi"
    assert c.model == sent[1]["payload"]["model"] == "llama-3.3-70b-specdec"   # speech models are skipped


def test_a_provider_without_a_key_runs_offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    c = LLMClient(provider="gemini")
    assert not c.available and c.complete("s", "p") is None
    assert "no API key found" in c.describe()
