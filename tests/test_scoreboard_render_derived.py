from pathlib import Path

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import render


def _seed(tmp_path: Path):
    store = CheckpointStore(tmp_path)
    # one core bench + two scanned-degradation variants for the same model
    store.record("m1", "realdoc_qa", "q1", metrics={"primary": 0.9})
    store.record("m1", "realdoc_qa", "q2", metrics={"primary": 0.7})
    store.record("m1", "realdoc_qa_scanned_light", "q1", metrics={"primary": 0.6})
    store.record("m1", "realdoc_qa_scanned_heavy", "q1", metrics={"primary": 0.3})
    return tmp_path


def test_main_table_excludes_scanned_benches_by_default(tmp_path: Path):
    out = render(_seed(tmp_path))
    assert "realdoc_qa" in out
    # derived scanned variants must NOT become leaderboard columns
    assert "realdoc_qa_scanned_light" not in out
    assert "realdoc_qa_scanned_heavy" not in out
    # footer counts only the shown (core) bench samples, not the scanned ones
    assert "2 scored samples" in out


def test_include_derived_opt_in_shows_scanned(tmp_path: Path):
    out = render(_seed(tmp_path), include_derived=True)
    assert "realdoc_qa_scanned_light" in out
    assert "realdoc_qa_scanned_heavy" in out
    assert "4 scored samples" in out
