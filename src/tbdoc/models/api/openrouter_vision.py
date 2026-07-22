"""Frontier vision models reached through the OpenRouter gateway, PINNED to one host.

Why this exists: one `OPEN_ROUTER_API_KEY` reaches the OpenAI-, Anthropic- and
Mistral-family models in one lane (no per-vendor procurement). But OpenRouter
multiplexes — `anthropic/claude-opus-4.7` is served by Amazon Bedrock, Anthropic,
Google AND Azure (7 endpoints, verified 2026-07-16). Unpinned, each row of a scored
run could come from a different host and the fingerprint would be meaningless.

So `or_provider` in models.yaml pins the serving host with `allow_fallbacks: false`
— the call FAILS rather than silently rerouting, and `fingerprint()` discloses who
served it. Pinning `or_provider: Azure` is what makes an Azure Foundry claim honest.

Normalization owned by this adapter (part of the measured system, keep stable):
page -> PNG data-URL (longest side 1540) -> DEFAULT_OCR_PROMPT -> markdown, fences
stripped, temperature=0. Identical to OpenAIVisionAdapter — only the transport differs.

NOTE: OpenRouter has no batch API (real-time only, same as instruments/reader.py).
Azure's 50%-off Global Batch is therefore a REPORTED projection, never incurred here.
"""
from __future__ import annotations

import os
from typing import Any

from tbdoc.models.api.openai_vision import OpenAIVisionAdapter

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterVisionAdapter(OpenAIVisionAdapter):

    def _client(self) -> Any:
        from openai import OpenAI
        return OpenAI(base_url=_BASE_URL, api_key=os.environ["OPEN_ROUTER_API_KEY"])

    def _extra_body(self) -> dict:
        body: dict = {}
        prov = self.entry.get("or_provider")
        if prov:                           # unpinned: OpenRouter's own routing, disclosed as such
            body["provider"] = {"order": [prov], "allow_fallbacks": False}
        # Reasoning VLMs (kimi-k3) spend the whole max_completion_tokens budget thinking
        # on dense pages -> finish=length with EMPTY content (verified 2026-07-22:
        # 4093/4096 reasoning tokens on an arxiv math page). Transcription needs no
        # chain-of-thought, so entries may pass e.g. `or_reasoning: {enabled: false}`.
        reasoning = self.entry.get("or_reasoning")
        if reasoning is not None:
            body["reasoning"] = reasoning
        return body

    def fingerprint(self) -> dict[str, Any]:
        fp = super().fingerprint()
        fp["or_provider"] = self.entry.get("or_provider")   # None = unpinned, honestly
        return fp
