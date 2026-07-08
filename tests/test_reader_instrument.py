import pytest
from tbdoc.instruments.reader import build_reader, AnthropicReader, OpenAIReader


READER_CFG = {
    "default_local": {"repo": "Qwen/Qwen2.5-1.5B-Instruct", "revision": "main"},
    "backends": {
        "haiku45": {"backend": "anthropic", "api_model_id": "claude-haiku-4-5-20251001",
                    "secrets": ["ANTHROPIC_API_KEY"]},
        "gpt5mini": {"backend": "openai", "api_model_id": "gpt-5.4-mini",
                     "secrets": ["OPENAI_API_KEY"]},
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
