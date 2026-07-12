"""Published-run replicability: the tracked summary.json must let a fresh clone
(no raw/ or predictions/ — both gitignored) render the same scoreboard the owner
published, and truly-empty runs must fail loudly instead of printing an empty table."""
from __future__ import annotations

import json
import shutil

import pytest
from conftest import DummyModel

from tbdoc.report.scoreboard import (
    SUMMARY_NOTE,
    collect_grid,
    render,
    render_tier_b,
    write_summary,
)
from tbdoc.runner.matrix import run_matrix


def _strip_note(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line != SUMMARY_NOTE).rstrip()


@pytest.fixture
def scored_run(tmp_path, dummy_factories):
    mf, bf = dummy_factories
    run_matrix(models=["m1", "m2"], benches=["b1"], model_factory=mf, bench_factory=bf,
               results_dir=tmp_path, run_id="pub", log=lambda *_: None)
    return tmp_path / "pub"


def test_score_phase_writes_summary(scored_run):
    s = json.loads((scored_run / "summary.json").read_text())
    assert s["run_id"] == "pub"
    assert s["cells"]["m1|b1"]["n"] == 4
    assert isinstance(s["cells"]["m1|b1"]["mean"], float)


def test_render_from_summary_matches_raw(scored_run):
    with_raw = render(scored_run)
    shutil.rmtree(scored_run / "raw")
    shutil.rmtree(scored_run / "predictions")
    from_summary = render(scored_run)
    assert SUMMARY_NOTE in from_summary          # provenance note is visible
    assert _strip_note(from_summary) == with_raw  # numbers byte-identical


def test_empty_run_raises_instead_of_empty_table(tmp_path):
    run = tmp_path / "empty"
    run.mkdir()
    with pytest.raises(FileNotFoundError, match="no per-sample records"):
        collect_grid(run)


def test_reading_does_not_scaffold_run_dirs(tmp_path):
    # regression: constructing the store for READING used to mkdir raw/, which made a
    # nonexistent run look scored to the dashboard's run discovery
    run = tmp_path / "ghost"
    run.mkdir()
    with pytest.raises(FileNotFoundError):
        collect_grid(run)
    assert not (run / "raw").exists()


def test_tier_b_falls_back_to_summary(tmp_path):
    from tbdoc.core.checkpoint import CheckpointStore
    run = tmp_path / "tb"
    store = CheckpointStore(run)
    for i, (b1, b2) in enumerate([(1.0, 0.0), (0.0, 1.0)]):
        store.record("m1", "realdoc_qa", f"q{i}",
                     metrics={"primary": b1, "b1": b1, "b2": b2, "extractive": True,
                              "reader": "openrouter:openai/gpt-5.4-mini"})
    with_raw = render_tier_b(run)
    assert write_summary(run) is not None
    shutil.rmtree(run / "raw")
    from_summary = render_tier_b(run)
    assert "openrouter:openai/gpt-5.4-mini" in from_summary
    assert _strip_note(from_summary).rstrip() == with_raw.rstrip()


def test_summary_merges_partial_regeneration(tmp_path, dummy_factories):
    mf, bf = dummy_factories
    run_matrix(models=["m1"], benches=["b1"], model_factory=mf, bench_factory=bf,
               results_dir=tmp_path, run_id="mrg", log=lambda *_: None)
    run = tmp_path / "mrg"
    # simulate a machine that holds raw for a DIFFERENT model only: m1's raw is gone,
    # m2 gets scored — the regenerated summary must keep m1's tracked aggregates
    shutil.rmtree(run / "raw")
    run_matrix(models=["m2"], benches=["b1"], model_factory=mf, bench_factory=bf,
               results_dir=tmp_path, run_id="mrg", log=lambda *_: None)
    s = json.loads((run / "summary.json").read_text())
    assert "m1|b1" in s["cells"] and "m2|b1" in s["cells"]


def test_partial_error_run_summary_counts_only_clean_rows(tmp_path, dummy_factories):
    _, bf = dummy_factories
    run_matrix(models=["m1"], benches=["b1"],
               model_factory=lambda k: DummyModel(k, fail_on={"page2"}), bench_factory=bf,
               results_dir=tmp_path, run_id="err", log=lambda *_: None)
    s = json.loads((tmp_path / "err" / "summary.json").read_text())
    assert s["cells"]["m1|b1"]["n"] == 3  # the error row is excluded from the mean's n
