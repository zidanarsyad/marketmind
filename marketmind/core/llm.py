"""Provider-agnostic LLM client.

Supported providers (pick with ``LLM_PROVIDER`` in ``.env``; ``auto`` uses the first key found):

* ``gemini``      Google AI Studio free tier       (GEMINI_API_KEY)
* ``groq``        Groq free tier                   (GROQ_API_KEY)
* ``openrouter``  OpenRouter ``:free`` models      (OPENROUTER_API_KEY)
* ``ollama``      local models, no key             (OLLAMA_BASE_URL optional)
* ``openai_compatible``  any OpenAI-style endpoint (LLM_BASE_URL + LLM_API_KEY + LLM_MODEL)
* ``anthropic``   Claude via the official SDK      (ANTHROPIC_API_KEY or an ``ant auth login`` profile)
* ``none``        offline: agents use their deterministic, template-based reasoning

Design rules: the LLM is only used for *language* (planning a brief, writing narrative,
answering questions). Every number comes from deterministic tools, and the Critic agent
verifies that LLM prose does not invent numbers. Responses are cached on disk, free-tier
rate limits are respected, and any failure returns ``None`` so callers fall back gracefully.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from ..config import CACHE_DIR, env

OPENAI_STYLE = {
    "gemini": dict(base_url="https://generativelanguage.googleapis.com/v1beta/openai", key_env="GEMINI_API_KEY",
                   model="gemini-2.5-flash", prefer=["flash"], min_interval=4.0),
    "groq": dict(base_url="https://api.groq.com/openai/v1", key_env="GROQ_API_KEY",
                 model="llama-3.3-70b-versatile", prefer=["llama-3.3-70b", "70b", "llama", "qwen"], min_interval=2.0),
    "openrouter": dict(base_url="https://openrouter.ai/api/v1", key_env="OPENROUTER_API_KEY",
                       model="meta-llama/llama-3.3-70b-instruct:free", prefer=[":free"], min_interval=3.0),
    "ollama": dict(base_url="http://localhost:11434/v1", key_env=None, model="llama3.1", prefer=[], min_interval=0.0),
    "openai_compatible": dict(base_url=None, key_env="LLM_API_KEY", model=None, prefer=[], min_interval=1.0),
}
ANTHROPIC_DEFAULT_MODEL = "claude-opus-5-5"
ANTHROPIC_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
AUTO_ORDER = ["gemini", "groq", "openrouter", "anthropic", "openai_compatible"]
SKIP_MODEL_WORDS = ("embed", "tts", "image", "audio", "live", "vision", "guard", "whisper", "aqa", "imagen", "veo",
                    "learnlm", "native", "transcribe", "moderation")


@dataclass
class LLMStats:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(calls=self.calls, cache_hits=self.cache_hits, failures=self.failures,
                    seconds=round(self.seconds, 1), prompt_tokens=self.prompt_tokens,
                    completion_tokens=self.completion_tokens)


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, use_cache: bool = True, timeout: float = 90.0):
        requested = (provider or env("LLM_PROVIDER", "auto")).strip().lower()
        self.provider = self._resolve(requested, api_key)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or env("LLM_MODEL")
        self.timeout = timeout
        self.use_cache = use_cache
        self.cache_dir = CACHE_DIR / "llm"
        self.stats = LLMStats()
        self.last_error: str | None = None
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._anthropic = None
        self._configure()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _resolve(requested: str, api_key: str | None) -> str:
        if requested in ("", "none", "off", "offline"):
            return "none"
        if requested != "auto":
            return requested
        for name in AUTO_ORDER:
            key_env = "ANTHROPIC_API_KEY" if name == "anthropic" else OPENAI_STYLE[name]["key_env"]
            if name == "openai_compatible" and not env("LLM_BASE_URL"):
                continue
            if env(key_env):
                return name
        return "none"

    def _configure(self) -> None:
        p = self.provider
        if p == "none":
            return
        if p == "anthropic":
            self.api_key = self.api_key or env("ANTHROPIC_API_KEY")
            self.model = self.model or ANTHROPIC_DEFAULT_MODEL
            self.min_interval = float(env("LLM_MIN_INTERVAL", "0.5"))
            return
        if p not in OPENAI_STYLE:
            self.last_error = f"Unknown LLM provider '{p}'"
            self.provider = "none"
            return
        spec = OPENAI_STYLE[p]
        if p == "ollama":
            self.base_url = self.base_url or env("OLLAMA_BASE_URL", spec["base_url"])
        elif p == "openai_compatible":
            self.base_url = self.base_url or env("LLM_BASE_URL")
        else:
            self.base_url = self.base_url or spec["base_url"]
        if spec["key_env"]:
            self.api_key = self.api_key or env(spec["key_env"])
        self.model = self.model or spec["model"]
        self.min_interval = float(env("LLM_MIN_INTERVAL", str(spec["min_interval"])))
        if p != "ollama" and not self.api_key:
            self.last_error = f"{p}: no API key found ({spec['key_env']})"
            self.provider = "none"
        if p == "openai_compatible" and (not self.base_url or not self.model):
            self.last_error = "openai_compatible needs LLM_BASE_URL and LLM_MODEL"
            self.provider = "none"

    @property
    def available(self) -> bool:
        return self.provider != "none"

    def describe(self) -> str:
        if not self.available:
            return "offline (deterministic reasoning)" + (f" - {self.last_error}" if self.last_error else "")
        return f"{self.provider} / {self.model}"

    # ------------------------------------------------------------------ public API
    def complete(self, system: str, prompt: str, max_tokens: int = 1200, json_mode: bool = False,
                 temperature: float = 0.3, agent: str = "") -> str | None:
        if not self.available:
            return None
        key = self._cache_key(system, prompt, json_mode, max_tokens)
        cached = self._cache_get(key)
        if cached is not None:
            with self._lock:
                self.stats.cache_hits += 1
            return cached
        self._throttle()
        t0 = time.time()
        try:
            if self.provider == "anthropic":
                text = self._call_anthropic(system, prompt)
            else:
                text = self._call_openai_style(system, prompt, max_tokens, json_mode, temperature)
        except Exception as exc:  # network errors, malformed responses, SDK errors
            text = None
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
        dt = time.time() - t0
        with self._lock:
            self.stats.calls += 1
            self.stats.seconds += dt
            if not text:
                self.stats.failures += 1
            self.stats.log.append(dict(agent=agent, ok=bool(text), seconds=round(dt, 2), chars=len(text or "")))
        if text:
            text = text.strip()
            self._cache_put(key, text)
        return text or None

    def complete_json(self, system: str, prompt: str, max_tokens: int = 1500, agent: str = "") -> dict | list | None:
        text = self.complete(system, prompt + "\n\nReturn only valid JSON, no markdown fences.",
                             max_tokens=max_tokens, json_mode=True, temperature=0.1, agent=agent)
        return parse_json(text) if text else None

    def ping(self) -> tuple[bool, str]:
        if not self.available:
            return False, self.describe()
        old = self.use_cache
        self.use_cache = False
        try:
            out = self.complete("You are a health check.", "Reply with the single word OK.", max_tokens=20, agent="ping")
        finally:
            self.use_cache = old
        return (bool(out), out or (self.last_error or "no response"))

    # ------------------------------------------------------------------ providers
    def _call_openai_style(self, system: str, prompt: str, max_tokens: int, json_mode: bool,
                           temperature: float) -> str | None:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "openrouter":
            headers["X-Title"] = "MarketMind"
        budget = max_tokens * 3 if self.provider == "gemini" else max_tokens  # leave room for thinking tokens
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": budget,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        rediscovered = False
        for attempt in range(4):
            r = requests.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers,
                              timeout=self.timeout)
            if r.status_code == 429:
                wait = float(r.headers.get("retry-after", 0) or 0) or min(5 * 2 ** attempt, 30)
                self.last_error = f"rate limited, retrying in {wait:.0f}s"
                time.sleep(wait)
                continue
            if r.status_code in (400, 404) and "response_format" in payload and "response_format" in r.text:
                payload.pop("response_format")
                continue
            if r.status_code in (400, 404) and not rediscovered and "model" in r.text.lower():
                new_model = self._discover_model()
                rediscovered = True
                if new_model and new_model != self.model:
                    self.model = payload["model"] = new_model
                    continue
            if r.status_code >= 400:
                self.last_error = f"HTTP {r.status_code}: {r.text[:240]}"
                return None
            data = r.json()
            usage = data.get("usage") or {}
            with self._lock:
                self.stats.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.stats.completion_tokens += int(usage.get("completion_tokens") or 0)
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not content and choice.get("finish_reason") == "length" and attempt < 3:
                payload["max_tokens"] = payload["max_tokens"] * 2
                continue
            return content
        return None

    def _discover_model(self) -> str | None:
        """Pick a currently served chat model when the configured one has been retired."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = requests.get(f"{self.base_url.rstrip('/')}/models", headers=headers, timeout=20)
            ids = [m.get("id", "") for m in r.json().get("data", [])]
        except Exception:
            return None
        ids = [i.removeprefix("models/") for i in ids if i and not any(w in i.lower() for w in SKIP_MODEL_WORDS)]
        for pattern in OPENAI_STYLE.get(self.provider, {}).get("prefer", []):
            matches = sorted((i for i in ids if pattern in i.lower()), reverse=True)
            if matches:
                return matches[0]
        return ids[0] if ids else None

    def _call_anthropic(self, system: str, prompt: str) -> str | None:
        import anthropic  # optional dependency, imported lazily

        if self._anthropic is None:
            kwargs = {"timeout": self.timeout * 2, "max_retries": 2}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            self._anthropic = anthropic.Anthropic(**kwargs)
        request = dict(model=self.model, max_tokens=16000, system=system,
                       messages=[{"role": "user", "content": prompt}])
        if not self.model.startswith(("claude-haiku-4", "claude-3", "claude-sonnet-4-5")):
            request["output_config"] = {"effort": "medium"}
        try:
            if self.model in ANTHROPIC_FALLBACK_MODELS:
                resp = self._anthropic.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                resp = self._anthropic.messages.create(**request)
        except anthropic.AuthenticationError:
            self.last_error = "anthropic: invalid API key"
            return None
        except anthropic.RateLimitError as exc:
            self.last_error = f"anthropic: rate limited ({exc.message})"
            return None
        except anthropic.APIStatusError as exc:
            self.last_error = f"anthropic: HTTP {exc.status_code} {exc.message}"[:300]
            return None
        except anthropic.APIConnectionError:
            self.last_error = "anthropic: network error"
            return None
        if resp.stop_reason == "refusal":
            self.last_error = "anthropic: request declined"
            return None
        with self._lock:
            self.stats.prompt_tokens += int(getattr(resp.usage, "input_tokens", 0) or 0)
            self.stats.completion_tokens += int(getattr(resp.usage, "output_tokens", 0) or 0)
        return "".join(b.text for b in resp.content if b.type == "text")

    # ------------------------------------------------------------------ plumbing
    def _throttle(self) -> None:
        with self._lock:
            wait = self._last_call + getattr(self, "min_interval", 0.0) - time.time()
            self._last_call = max(time.time(), self._last_call + getattr(self, "min_interval", 0.0))
        if wait > 0:
            time.sleep(wait)

    def _cache_key(self, system: str, prompt: str, json_mode: bool, max_tokens: int) -> str:
        raw = json.dumps([self.provider, self.model, system, prompt, json_mode, max_tokens], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _cache_get(self, key: str) -> str | None:
        if not self.use_cache:
            return None
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))["text"]
            except Exception:
                return None
        return None

    def _cache_put(self, key: str, text: str) -> None:
        if not self.use_cache:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")


def parse_json(text: str | None):
    """Parse JSON from an LLM response, tolerating code fences and leading prose."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None
