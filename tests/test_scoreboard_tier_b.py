from pathlib import Path
from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import render_tier_b


def test_tier_b_view_reports_b1_and_coverage(tmp_path: Path):
    store = CheckpointStore(tmp_path)
    store.record("m1", "realdoc_qa", "q1", metrics={"primary": 1.0, "b1": 1.0, "extractive": True,
                 "b2": 1.0, "reader": "anthropic:claude-haiku-4-5-20251001", "category": "finance"})
    store.record("m1", "realdoc_qa", "q2", metrics={"primary": None, "b1": None, "extractive": False,
                 "b2": 0.0, "reader": "anthropic:claude-haiku-4-5-20251001", "category": "finance"})
    out = render_tier_b(tmp_path)
    assert "B.1" in out and "coverage" in out.lower()
    assert "1/2" in out or "0.50" in out   # 1 of 2 items extractive
    assert "haiku" in out
