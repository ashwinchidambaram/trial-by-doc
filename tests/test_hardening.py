"""Hardening regressions: reader retry, per-sample scorer isolation, error forwarding,
reader spend estimation, and merge-on-write for the tracked run artifacts
(manifest.json / status.json / scoreboard.csv — each was clobbered at least once)."""
from __future__ import annotations

import csv
import json

import pytest
from conftest import DummyBench, DummyModel

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.core.manifest import build_manifest, write_manifest
from tbdoc.core.ratelimit import RetryableError
from tbdoc.instruments.reader import OpenRouterReader, api_backend, estimate_call_usd
from tbdoc.runner.matrix import run_matrix

# ---- reader retry (C1) ------------------------------------------------------------


def test_api_reader_retries_transient_errors(monkeypatch):
    monkeypatch.setattr("tbdoc.core.ratelimit.time.sleep", lambda *_: None)
    r = OpenRouterReader("openai/some-model", retry={"max_attempts": 4, "base_s": 0.01})
    calls = []

    def flaky(md, q):
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("429")
        return "answer"

    monkeypatch.setattr(r, "_call", flaky)
    assert r.answer("md", "q") == "answer"
    assert len(calls) == 3  # two transient failures absorbed, third attempt succeeds


def test_api_reader_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("tbdoc.core.ratelimit.time.sleep", lambda *_: None)
    r = OpenRouterReader("openai/some-model", retry={"max_attempts": 2, "base_s": 0.01})
    monkeypatch.setattr(r, "_call", lambda md, q: (_ for _ in ()).throw(RetryableError("429")))
    with pytest.raises(RetryableError):
        r.answer("md", "q")


def test_reader_cost_stamping():
    r = OpenRouterReader("openai/some-model",
                         pricing={"per_mtok_in_usd": 1.0, "per_mtok_out_usd": 10.0})
    r._stamp_usage(1_000_000, 100_000)
    assert r.last_cost_usd == pytest.approx(2.0)  # $1 in + $1 out
    r._stamp_usage(None, 5)  # usage missing from the response -> no fabricated cost
    assert r.last_cost_usd is None


# ---- reader spend estimation (C3) -------------------------------------------------


def test_estimate_call_usd_upper_bound():
    per_call = estimate_call_usd({"per_mtok_in_usd": 0.75, "per_mtok_out_usd": 4.50})
    # 12k-token worst-case input + 64 out ≈ the ladder study's empirical ~$0.01/call
    assert 0.005 < per_call < 0.015
    assert estimate_call_usd({}) is None
    assert estimate_call_usd(None) is None


def test_api_backend_resolution(monkeypatch):
    cfg = {"local_variants": {"local_qwen15": {"repo": "q"}},
           "backends": {"gpt5mini": {"backend": "openrouter", "api_model_id": "openai/x",
                                     "secrets": ["FAKE_READER_KEY"]}}}
    assert api_backend("local", cfg) is None
    assert api_backend("local_qwen15", cfg) is None
    monkeypatch.delenv("FAKE_READER_KEY", raising=False)
    assert api_backend("gpt5mini", cfg) is None      # key absent -> local fallback
    monkeypatch.setenv("FAKE_READER_KEY", "x")
    assert api_backend("gpt5mini", cfg)["api_model_id"] == "openai/x"


# ---- per-sample scorer isolation (C2) + error forwarding (C4) ---------------------


class ExplodingBench(DummyBench):
    """evaluate() raises for one sample — must become ONE error row, not kill the cell."""

    def evaluate(self, sample, prediction, extractor=None):
        if sample.id == "s1":
            raise RuntimeError("reader blew up")
        return super().evaluate(sample, prediction, extractor=extractor)


def test_one_failing_sample_does_not_abort_the_cell(tmp_path):
    s = run_matrix(models=["m1"], benches=["b1"], model_factory=lambda k: DummyModel(k),
                   bench_factory=lambda k: ExplodingBench(k), results_dir=tmp_path,
                   run_id="iso", log=lambda *_: None)
    assert s["score"]["scored"] == 3
    assert s["score"]["errors"] == 1
    recs = [json.loads(line) for line in
            (tmp_path / "iso" / "raw" / "m1" / "b1.jsonl").read_text().splitlines()]
    errs = [r for r in recs if r.get("error")]
    assert len(errs) == 1 and errs[0]["sample_id"] == "s1"
    assert "reader blew up" in errs[0]["error"]
    assert errs[0]["metrics"]["primary"] is None
    # the other three scored normally
    assert sum(1 for r in recs if r.get("error") is None) == 3


class MarkerBench(DummyBench):
    """evaluate_batch returns the official-scorer failure marker for one sample."""

    def evaluate_batch(self, samples, predictions, extractor=None):
        out = super().evaluate_batch(samples, predictions, extractor=extractor)
        out["s0"] = {"primary": None, "error": "no scorer result"}
        return out


def test_scorer_failure_marker_is_forwarded_as_error_row(tmp_path):
    s = run_matrix(models=["m1"], benches=["b1"], model_factory=lambda k: DummyModel(k),
                   bench_factory=lambda k: MarkerBench(k), results_dir=tmp_path,
                   run_id="marker", log=lambda *_: None)
    assert s["score"]["scored"] == 3 and s["score"]["errors"] == 1
    recs = [json.loads(line) for line in
            (tmp_path / "marker" / "raw" / "m1" / "b1.jsonl").read_text().splitlines()]
    marked = [r for r in recs if r["sample_id"] == "s0"]
    assert marked and marked[0]["error"] == "no scorer result"  # top-level, not buried in metrics


# ---- merge-on-write for tracked run artifacts --------------------------------------


def test_manifest_merge_preserves_prior_invocations(tmp_path):
    m1 = build_manifest(run_id="r", models=["m1"], benches=["b1"],
                        model_fingerprints={"m1": {"revision": "r1"}},
                        bench_fingerprints={"b1": {"revision": "d1"}})
    write_manifest(tmp_path, m1)
    m2 = build_manifest(run_id="r", models=["m2"], benches=["b2"],
                        model_fingerprints={"m2": {"revision": "r2"}},
                        bench_fingerprints={"b2": {"revision": "d2"}})
    write_manifest(tmp_path, m2)
    got = json.loads((tmp_path / "manifest.json").read_text())
    assert set(got["models"]) == {"m1", "m2"}          # union, not clobber
    assert set(got["benchmarks"]) == {"b1", "b2"}
    assert got["created_at"] == m1["created_at"]       # first invocation wins
    assert len(got["invocations"]) == 2
    assert got["invocations"][0]["models"] == ["m1"]
    assert got["invocations"][1]["models"] == ["m2"]


def test_scoreboard_and_status_merge_across_scoped_invocations(tmp_path):
    store = CheckpointStore(tmp_path)
    store.record("m1", "b1", "s0", metrics={"primary": 1.0})
    store.write_scoreboard(["m1"], ["b1"])
    store.write_status(["m1"], ["b1"], totals={("m1", "b1"): 1})
    # a later invocation scoped to a DIFFERENT cell (the v1-baseline scanned add-on shape)
    store.record("m2", "b2", "s0", metrics={"primary": 0.5})
    store.write_scoreboard(["m2"], ["b2"])
    store.write_status(["m2"], ["b2"], totals={("m2", "b2"): 1})
    rows = {r["model"]: r for r in csv.DictReader((tmp_path / "scoreboard.csv").open())}
    assert rows["m1"]["b1"] == "1.0" and rows["m2"]["b2"] == "0.5"   # both survive
    status = json.loads((tmp_path / "status.json").read_text())
    cells = {(c["model"], c["bench"]) for c in status["cells"]}
    assert ("m1", "b1") in cells and ("m2", "b2") in cells
    assert status["totals"]["done"] == 2
