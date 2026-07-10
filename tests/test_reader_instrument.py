import pytest
from tbdoc.instruments.reader import build_reader, AnthropicReader, OpenAIReader, OpenRouterReader


READER_CFG = {
    "default_local": {"repo": "Qwen/Qwen2.5-1.5B-Instruct", "revision": "main"},
    "local_variants": {
        "local_other": {"repo": "Qwen/Qwen2.5-0.5B-Instruct", "revision": "main"},
    },
    "backends": {
        "haiku45": {"backend": "anthropic", "api_model_id": "claude-haiku-4-5-20251001",
                    "secrets": ["ANTHROPIC_API_KEY"]},
        "gpt5mini": {"backend": "openai", "api_model_id": "gpt-5.4-mini",
                     "secrets": ["OPENAI_API_KEY"]},
        "haiku45_or": {"backend": "openrouter", "api_model_id": "anthropic/claude-haiku-4.5",
                       "secrets": ["OPEN_ROUTER_API_KEY"]},
    },
}

def test_local_default_selected_and_is_small_model():
    r = build_reader("local", READER_CFG)
    assert "Qwen2.5-1.5B" in r.identity   # NOT the 7B (and Apache-2.0, not the research-licensed 3B)

def test_api_reader_falls_back_to_local_when_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = build_reader("haiku45", READER_CFG)
    assert "Qwen2.5-1.5B" in r.identity   # graceful fallback, key-less clones still run

def test_api_reader_built_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    r = build_reader("haiku45", READER_CFG)
    assert isinstance(r, AnthropicReader)
    assert r.identity == "anthropic:claude-haiku-4-5-20251001"

def test_openai_reader_identity(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    r = build_reader("gpt5mini", READER_CFG)
    assert isinstance(r, OpenAIReader)
    assert r.identity == "openai:gpt-5.4-mini"

def test_named_local_variant_selected_by_name():
    r = build_reader("local_other", READER_CFG)
    assert "Qwen2.5-0.5B" in r.identity   # picked the named rung, not default_local

def test_local_variant_name_does_not_shadow_default():
    default = build_reader("local", READER_CFG)
    variant = build_reader("local_other", READER_CFG)
    assert default.identity != variant.identity

def test_openrouter_reader_falls_back_to_local_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    r = build_reader("haiku45_or", READER_CFG)
    assert "Qwen2.5-1.5B" in r.identity   # graceful fallback, key-less clones still run

def test_openrouter_reader_built_when_key_present(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "x")
    r = build_reader("haiku45_or", READER_CFG)
    assert isinstance(r, OpenRouterReader)
    assert r.identity == "openrouter:anthropic/claude-haiku-4.5"
    assert r._BASE_URL == "https://openrouter.ai/api/v1"   # no paid call made — construction only

def test_reader_identity_distinct_from_frozen_judge():
    # Extractor Protocol requires the B.2 reader identity to never collide with the frozen
    # Tier-C judge identity, so scoreboard rows can never be misattributed.
    from tbdoc.instruments.vllm_extractor import VLLMExtractor
    judge_identity = VLLMExtractor().identity
    assert judge_identity == "Qwen/Qwen2.5-7B-Instruct@a09a35458c70"
    phi4_cfg = {"default_local": {"repo": "microsoft/Phi-4-mini-instruct",
                                   "revision": "cfbefacb99257ffa30c83adab238a50856ac3083"}}
    reader_identity = build_reader("local", phi4_cfg).identity
    assert reader_identity != judge_identity
    assert build_reader("local_other", READER_CFG).identity != judge_identity
