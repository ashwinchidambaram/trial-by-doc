"""Tier-D scanned benches on the scoreboard (contract since the 2026-07-22 promotion).

Before the promotion the scanned variants were a 'derived' robustness study excluded
from the main grid (opt-in via ``include_derived``). They are now official Tier-D
leaderboard columns: always rendered. They remain excluded from the perf
characterization only (latency/VRAM/$ is a clean-page property).
"""
import json
from pathlib import Path

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import _is_robustness_bench, render, render_perf


def _seed(tmp_path: Path):
    store = CheckpointStore(tmp_path)
    # one core bench + two Tier-D scanned variants for the same model
    store.record("m1", "realdoc_qa", "q1", metrics={"primary": 0.9})
    store.record("m1", "realdoc_qa", "q2", metrics={"primary": 0.7})
    store.record("m1", "realdoc_qa_scanned_light", "q1", metrics={"primary": 0.6})
    store.record("m1", "realdoc_qa_scanned_heavy", "q1", metrics={"primary": 0.3})
    return tmp_path


def test_main_table_includes_tier_d_scanned_benches(tmp_path: Path):
    out = render(_seed(tmp_path))
    assert "realdoc_qa" in out
    # Tier-D scanned variants ARE leaderboard columns since the promotion
    assert "realdoc_qa_scanned_light" in out
    assert "realdoc_qa_scanned_heavy" in out
    # footer counts every shown bench's samples, scanned included
    assert "4 scored samples" in out


def test_perf_still_excludes_scanned_pages(tmp_path: Path):
    """Perf (latency/VRAM/$) stays a clean-page characterization: a model with telemetry
    only under a scanned bench must not appear in the perf table."""
    _seed(tmp_path)
    pred = tmp_path / "predictions" / "m1"
    pred.mkdir(parents=True)
    rec = {"sample_id": "q1", "prediction": {"telemetry": {"latency_s": 1.5}}}
    (pred / "realdoc_qa_scanned_light.jsonl").write_text(json.dumps(rec) + "\n")
    assert render_perf(tmp_path) == "_no timing telemetry_"


def test_is_robustness_bench_classifier():
    assert _is_robustness_bench("realdoc_qa_scanned_light")
    assert _is_robustness_bench("realdoc_qa_scanned_heavy")
    assert not _is_robustness_bench("realdoc_qa")
    assert not _is_robustness_bench("olmocr_bench")
