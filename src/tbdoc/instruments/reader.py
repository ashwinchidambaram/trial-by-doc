"""Pluggable Tier-B B.2 comprehension reader: markdown+question -> answer.

Satisfies the Extractor Protocol (.identity + .answer). Backends: local vLLM small model
(default Qwen2.5-3B — never the 7B, which stays the Tier C judge), Anthropic, OpenAI. API
readers are text-only and fall back to the local default when their key is absent, so
key-less clones still run. Deterministic where the backend allows (temperature=0)."""
from __future__ import annotations

from typing import Any

from tbdoc.core.ratelimit import RetryableError

_SYSTEM = (
    "You extract answers from a document's parsed text. Use ONLY the text provided — do not use "
    "outside knowledge and do not guess. If the answer is not present, reply exactly: not found. "
    "Reply with ONLY the answer value, as short as possible, no punctuation around it.")

_MAX_MD = 48000


def _user(md: str, q: str) -> str:
    return f"Document text:\n\n{(md or '')[:_MAX_MD]}\n\nQuestion: {q}\nAnswer:"


class AnthropicReader:
    def __init__(self, api_model_id: str, secrets: list[str] | None = None, pricing: dict | None = None):
        self.api_model_id = api_model_id
        self.identity = f"anthropic:{api_model_id}"
        self._pricing = pricing or {}
        self._client = None

    def _c(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def answer(self, markdown: str, question: str) -> str:
        import anthropic
        try:
            r = self._c().messages.create(
                model=self.api_model_id, max_tokens=64, temperature=0, system=_SYSTEM,
                messages=[{"role": "user", "content": _user(markdown, question)}])
        except (anthropic.RateLimitError, anthropic.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()


class OpenAIReader:
    def __init__(self, api_model_id: str, secrets: list[str] | None = None, pricing: dict | None = None):
        self.api_model_id = api_model_id
        self.identity = f"openai:{api_model_id}"
        self._pricing = pricing or {}
        self._client = None

    def _c(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def answer(self, markdown: str, question: str) -> str:
        import openai
        try:
            r = self._c().chat.completions.create(
                model=self.api_model_id, temperature=0, max_tokens=64,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": _user(markdown, question)}])
        except (openai.RateLimitError, openai.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        return (r.choices[0].message.content or "").strip()


def _build_local(cfg: dict) -> Any:
    from tbdoc.instruments.vllm_extractor import VLLMExtractor
    loc = (cfg or {}).get("default_local") or {}
    repo = loc.get("repo", "Qwen/Qwen2.5-3B-Instruct")
    return VLLMExtractor(repo=repo, revision=loc.get("revision"))


def build_reader(name: str, cfg: dict) -> Any:
    """Select a reader by name. 'local' -> the small default. An API backend name ->
    the API reader if its key is present, else a graceful fallback to the local default."""
    from tbdoc.core.secrets import missing_secrets
    if name in ("local", "default", None):
        return _build_local(cfg)
    b = ((cfg or {}).get("backends") or {}).get(name)
    if not b:
        return _build_local(cfg)
    if missing_secrets(b.get("secrets", [])):
        return _build_local(cfg)          # key-less fallback
    kind = b.get("backend")
    if kind == "anthropic":
        return AnthropicReader(b["api_model_id"], b.get("secrets"), b.get("pricing"))
    if kind == "openai":
        return OpenAIReader(b["api_model_id"], b.get("secrets"), b.get("pricing"))
    return _build_local(cfg)
