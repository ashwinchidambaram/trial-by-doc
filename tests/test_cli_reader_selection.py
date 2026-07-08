from tbdoc.instruments.reader import build_reader


def test_default_reader_is_local_small(monkeypatch):
    cfg = {"default_local": {"repo": "Qwen/Qwen2.5-3B-Instruct", "revision": "main"}, "backends": {}}
    r = build_reader("local", cfg)
    assert "3B" in r.identity and "7B" not in r.identity
