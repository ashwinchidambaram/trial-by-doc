"""Pluggable Tier-B B.2 comprehension reader: markdown+question -> answer.

Satisfies the Extractor Protocol (.identity + .answer). Backends: local vLLM small model
(default Phi-4-mini-instruct, MIT — never the 7B, which stays the Tier C judge; Qwen2.5-1.5B
retained as a named local ladder rung, see `local_variants`), Anthropic (direct), OpenAI
(direct), OpenRouter (OpenAI-compatible gateway; one key serves both Anthropic- and
OpenAI-family models). API readers are text-only and fall back to the local default when their
key is absent, so key-less clones still run. Deterministic where the backend allows
(temperature=0).

API readers retry transient failures (429/timeout) with exponential backoff so one blip
never aborts a whole scoring cell, and stamp per-call token usage + cost (from the
registry pricing dict) on `last_usage` / `last_cost_usd` for the bench to record."""
from __future__ import annotations

import os
from typing import Any

from tbdoc.core.ratelimit import RetryableError, with_backoff

_SYSTEM = (
    "You extract answers from a document's parsed text. Use ONLY the text provided — do not use "
    "outside knowledge and do not guess. If the answer is not present, reply exactly: not found. "
    "Reply with ONLY the answer value, as short as possible, no punctuation around it.")

_MAX_MD = 48000

#: pricing-derived per-call bound used by the pre-run budget guard when no empirical
#: rate is available: worst-case input (_MAX_MD chars ≈ /4 tokens) + max_tokens out.
_EST_IN_TOKENS = _MAX_MD // 4
_EST_OUT_TOKENS = 64


def _user(md: str, q: str) -> str:
    return f"Document text:\n\n{(md or '')[:_MAX_MD]}\n\nQuestion: {q}\nAnswer:"


def estimate_call_usd(pricing: dict | None) -> float | None:
    """Upper-bound cost of ONE reader call from a registry pricing dict."""
    p = pricing or {}
    if not p.get("per_mtok_in_usd"):
        return None
    return (_EST_IN_TOKENS / 1e6 * float(p["per_mtok_in_usd"])
            + _EST_OUT_TOKENS / 1e6 * float(p.get("per_mtok_out_usd") or 0))


class _ApiReader:
    """Shared plumbing for API-backed readers: backoff retry + usage/cost stamping."""

    def __init__(self, api_model_id: str, secrets: list[str] | None = None,
                 pricing: dict | None = None, retry: dict | None = None):
        self.api_model_id = api_model_id
        self._pricing = pricing or {}
        self._retry = retry or {}
        self._client = None
        self.last_usage: dict | None = None       # {"input_tokens", "output_tokens"} of last call
        self.last_cost_usd: float | None = None   # from registry pricing; None if unpriced

    def _stamp_usage(self, in_tok: int | None, out_tok: int | None) -> None:
        self.last_usage = {"input_tokens": in_tok, "output_tokens": out_tok}
        p = self._pricing
        if in_tok is None or out_tok is None or not p.get("per_mtok_in_usd"):
            self.last_cost_usd = None
            return
        self.last_cost_usd = round(in_tok / 1e6 * float(p["per_mtok_in_usd"])
                                   + out_tok / 1e6 * float(p.get("per_mtok_out_usd") or 0), 6)

    def _call(self, markdown: str, question: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def answer(self, markdown: str, question: str) -> str:
        out, _ = with_backoff(
            lambda: self._call(markdown, question),
            max_attempts=int(self._retry.get("max_attempts", 5)),
            base_s=float(self._retry.get("base_s", 1.0)))
        return out


class AnthropicReader(_ApiReader):
    def __init__(self, api_model_id: str, secrets: list[str] | None = None,
                 pricing: dict | None = None, retry: dict | None = None):
        super().__init__(api_model_id, secrets, pricing, retry)
        self.identity = f"anthropic:{api_model_id}"

    def _c(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _call(self, markdown: str, question: str) -> str:
        import anthropic
        try:
            r = self._c().messages.create(
                model=self.api_model_id, max_tokens=64, temperature=0, system=_SYSTEM,
                messages=[{"role": "user", "content": _user(markdown, question)}])
        except (anthropic.RateLimitError, anthropic.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        u = getattr(r, "usage", None)
        self._stamp_usage(getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()


class OpenAIReader(_ApiReader):
    def __init__(self, api_model_id: str, secrets: list[str] | None = None,
                 pricing: dict | None = None, retry: dict | None = None):
        super().__init__(api_model_id, secrets, pricing, retry)
        self.identity = f"openai:{api_model_id}"

    def _c(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def _call(self, markdown: str, question: str) -> str:
        import openai
        try:
            r = self._c().chat.completions.create(
                model=self.api_model_id, temperature=0, max_tokens=64,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": _user(markdown, question)}])
        except (openai.RateLimitError, openai.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        u = getattr(r, "usage", None)
        self._stamp_usage(getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None))
        return (r.choices[0].message.content or "").strip()


class OpenRouterReader(OpenAIReader):
    """OpenAI-compatible client pointed at OpenRouter's gateway. One key
    (`OPEN_ROUTER_API_KEY`) reaches both Anthropic- and OpenAI-family models — no batch API,
    real-time only. Same prompts/sampling/retry contract as `OpenAIReader`."""

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_model_id: str, secrets: list[str] | None = None,
                 pricing: dict | None = None, retry: dict | None = None):
        super().__init__(api_model_id, secrets, pricing, retry)
        self.identity = f"openrouter:{api_model_id}"

    def _c(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(base_url=self._BASE_URL, api_key=os.environ["OPEN_ROUTER_API_KEY"])
        return self._client


def _build_local(cfg: dict, variant: dict | None = None) -> Any:
    from tbdoc.instruments.vllm_extractor import VLLMExtractor
    loc = variant if variant is not None else ((cfg or {}).get("default_local") or {})
    repo = loc.get("repo", "Qwen/Qwen2.5-1.5B-Instruct")
    return VLLMExtractor(repo=repo, revision=loc.get("revision"))


def api_backend(name: str, cfg: dict) -> dict | None:
    """The API backend entry `build_reader(name, cfg)` would use, or None if it would
    fall back to a local reader (unknown name, local rung, or missing key). Lets the
    CLI budget guard price reader spend with the exact same resolution logic."""
    from tbdoc.core.secrets import missing_secrets
    if name in ("local", "default", None):
        return None
    if name in ((cfg or {}).get("local_variants") or {}):
        return None
    b = ((cfg or {}).get("backends") or {}).get(name)
    if not b or missing_secrets(b.get("secrets", [])):
        return None
    return b


def build_reader(name: str, cfg: dict) -> Any:
    """Select a reader by name.
    - 'local' / 'default' / None -> `default_local` (the key-less default rung).
    - a name in `local_variants` -> that named local rung (e.g. 'local_qwen15').
    - a name in `backends` -> the API reader if its key is present, else a graceful
      fallback to the local default (key-less clones still run)."""
    b = api_backend(name, cfg)
    if b is None:
        variants = (cfg or {}).get("local_variants") or {}
        if name in variants:
            return _build_local(cfg, variants[name])
        return _build_local(cfg)
    kind = b.get("backend")
    args = (b["api_model_id"], b.get("secrets"), b.get("pricing"), b.get("retry"))
    if kind == "anthropic":
        return AnthropicReader(*args)
    if kind == "openai":
        return OpenAIReader(*args)
    if kind == "openrouter":
        return OpenRouterReader(*args)
    return _build_local(cfg)
