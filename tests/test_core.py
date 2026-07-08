"""Registry enforcement, ratelimit/backoff, secrets, Segmentation groups."""
import time

import pytest

from tbdoc.core.ratelimit import RetryableError, TokenBucket, with_backoff
from tbdoc.core.secrets import missing_secrets, require_secrets
from tbdoc.core.structured_doc import Segmentation


def test_custom_bench_refused_without_validation_doc(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "models.yaml").write_text("models: {}")
    (tmp_path / "configs" / "benchmarks.yaml").write_text(
        "benchmarks:\n"
        "  sketchy:\n"
        "    adapter: 'conftest:DummyBench'\n"
        "    provenance: custom\n")
    monkeypatch.chdir(tmp_path)
    from tbdoc.core.registry import Registry
    reg = Registry(tmp_path / "configs")
    with pytest.raises(RuntimeError, match="VALIDATION"):
        reg.bench("sketchy")


def test_custom_bench_accepted_with_validation_doc(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "models.yaml").write_text("models: {}")
    (tmp_path / "VALIDATION.md").write_text("validated.")
    (tmp_path / "configs" / "benchmarks.yaml").write_text(
        "benchmarks:\n"
        "  fine:\n"
        "    adapter: 'conftest:DummyBench'\n"
        "    provenance: custom\n"
        f"    validation_doc: {tmp_path / 'VALIDATION.md'}\n")
    monkeypatch.chdir(tmp_path)
    from tbdoc.core.registry import Registry
    assert Registry(tmp_path / "configs").bench("fine").provenance == "custom"


def test_backoff_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("429")
        return "ok"

    out, retries = with_backoff(flaky, max_attempts=5, base_s=0.01)
    assert out == "ok" and retries == 2


def test_backoff_gives_up():
    with pytest.raises(RetryableError):
        with_backoff(lambda: (_ for _ in ()).throw(RetryableError("x")),
                     max_attempts=2, base_s=0.01)


def test_token_bucket_throttles():
    tb = TokenBucket(rps=50, burst=1)
    tb.acquire()
    t0 = time.monotonic()
    tb.acquire()
    assert time.monotonic() - t0 >= 0.015  # had to wait ~1/50s


def test_secrets(monkeypatch):
    monkeypatch.setenv("TBD_A", "x")
    monkeypatch.delenv("TBD_B", raising=False)
    assert missing_secrets(["TBD_A", "TBD_B"]) == ["TBD_B"]
    with pytest.raises(RuntimeError, match="TBD_B"):
        require_secrets(["TBD_B"], context="test")


def test_segmentation_groups():
    seg = Segmentation(boundaries=[2, 5])
    assert seg.groups(7) == [[0, 1], [2, 3, 4], [5, 6]]
    assert Segmentation(boundaries=[]).groups(3) == [[0, 1, 2]]
    # out-of-range and duplicate boundaries are ignored
    assert Segmentation(boundaries=[0, 2, 2, 99]).groups(4) == [[0, 1], [2, 3]]
