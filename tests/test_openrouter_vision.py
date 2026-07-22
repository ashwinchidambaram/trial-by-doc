"""OpenRouter vision lane — the gateway must be PINNED to one serving provider.

OpenRouter multiplexes: claude-opus-4.7 alone is served by Bedrock, Anthropic, Google
AND Azure (7 endpoints, verified 2026-07-16). Unpinned, a scored run's rows would each
have come from an unknown host, making the fingerprint a lie. We pin to Azure so the
row honestly says "Azure Foundry, reached via the OpenRouter gateway".
"""
from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from tbdoc.models.api.openrouter_vision import OpenRouterVisionAdapter


class _FakeCompletions:
    def __init__(self):
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        raise _Stop  # we only assert on the request; no network


class _Stop(Exception):
    pass


class _FakeClient:
    def __init__(self):
        self.chat = type("C", (), {"completions": _FakeCompletions()})()


def _adapter(**entry_extra):
    entry = {"api_model_id": "openai/gpt-4.1-mini", "provider": "openrouter",
             "secrets": ["OPEN_ROUTER_API_KEY"], **entry_extra}
    ad = OpenRouterVisionAdapter("or_gpt41mini", entry)
    ad.client = _FakeClient()
    return ad


def _call(ad):
    with pytest.raises(_Stop):
        ad._call_api(Image.new("RGB", (12, 12), "white"))
    return ad.client.chat.completions.kwargs


def test_client_points_at_the_openrouter_gateway(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-test-not-real")
    client = OpenRouterVisionAdapter("k", {"api_model_id": "m"})._client()
    assert str(client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"


def test_pins_serving_provider_and_forbids_fallback():
    """`azure` is the real OpenRouter provider slug (verified via /api/v1/providers)."""
    kwargs = _call(_adapter(or_provider="azure"))
    assert kwargs["extra_body"]["provider"] == {"order": ["azure"], "allow_fallbacks": False}


def test_unpinned_entry_sends_no_provider_block():
    """No or_provider -> OpenRouter's own routing; we must not invent a pin."""
    assert "provider" not in (_call(_adapter()).get("extra_body") or {})


def test_fingerprint_records_the_pinned_serving_provider():
    """A row must disclose WHO served it, not just that we used the gateway."""
    fp = _adapter(or_provider="azure").fingerprint()
    assert fp["provider"] == "openrouter"
    assert fp["or_provider"] == "azure"


def test_temperature_is_zero_for_determinism():
    assert _call(_adapter(or_provider="azure"))["temperature"] == 0
