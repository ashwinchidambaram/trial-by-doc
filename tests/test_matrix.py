"""Two-phase runner: full pass, resume, error rows, no silent gaps."""
import json

from conftest import DummyModel

from tbdoc.runner.matrix import run_matrix


def test_full_run_produces_scoreboard(tmp_path, dummy_factories):
    mf, bf = dummy_factories
    s = run_matrix(models=["m1", "m2"], benches=["b1"], model_factory=mf, bench_factory=bf,
                   results_dir=tmp_path, run_id="t1", log=lambda *_: None)
    assert s["infer"]["predicted"] == 8 and s["infer"]["errors"] == 0
    assert s["score"]["scored"] == 8
    run = tmp_path / "t1"
    assert (run / "manifest.json").exists()
    board = (run / "scoreboard.csv").read_text()
    assert "m1" in board and "b1" in board and "1.0" in board
    status = json.loads((run / "status.json").read_text())
    assert status["totals"]["done"] == 8


def test_resume_skips_done_and_model_load(tmp_path, dummy_factories):
    mf, bf = dummy_factories
    run_matrix(models=["m1"], benches=["b1"], model_factory=mf, bench_factory=bf,
               results_dir=tmp_path, run_id="t2", log=lambda *_: None)
    # second invocation: nothing to infer, nothing to re-score, model never loaded
    loads = []

    def counting_mf(k):
        m = DummyModel(k)
        orig = m.load
        m.load = lambda: (loads.append(k), orig())
        return m

    s2 = run_matrix(models=["m1"], benches=["b1"], model_factory=counting_mf, bench_factory=bf,
                    results_dir=tmp_path, run_id="t2", log=lambda *_: None)
    assert s2["infer"]["predicted"] == 0
    assert s2["score"]["scored"] == 0
    assert loads == []  # all cells complete -> load skipped entirely


def test_partial_resume(tmp_path, dummy_factories):
    _, bf = dummy_factories
    # first run: page2 fails -> error row recorded, not silently dropped
    def mf_fail(k):
        return DummyModel(k, fail_on={"page2"})
    s1 = run_matrix(models=["m1"], benches=["b1"], model_factory=mf_fail, bench_factory=bf,
                    results_dir=tmp_path, run_id="t3", log=lambda *_: None)
    assert s1["infer"]["errors"] == 1
    recs = (tmp_path / "t3" / "raw" / "m1" / "b1.jsonl").read_text().splitlines()
    assert len(recs) == 4  # 3 scored + 1 error row
    errs = [json.loads(r) for r in recs if json.loads(r).get("error")]
    assert len(errs) == 1 and "boom" in errs[0]["error"]


def test_rescore_without_reinference(tmp_path, dummy_factories):
    mf, bf = dummy_factories
    run_matrix(models=["m1"], benches=["b1"], model_factory=mf, bench_factory=bf,
               results_dir=tmp_path, run_id="t4", log=lambda *_: None)
    s = run_matrix(models=["m1"], benches=["b1"], model_factory=mf, bench_factory=bf,
                   results_dir=tmp_path, run_id="t4", rescore=True, phases=("score",),
                   log=lambda *_: None)
    assert s["score"]["scored"] == 4  # re-scored from saved predictions, no infer phase


def test_document_unit_dispatches_segment(tmp_path):
    from tbdoc.core.bench_adapter import BenchAdapter, Sample
    from tbdoc.core.structured_doc import Segmentation

    class SegModel(DummyModel):
        capabilities = frozenset({"page_markdown", "segmentation"})

        def segment(self, pages, boundary_judge=None):
            return Segmentation(boundaries=[2], method="native")

    class SegBench(BenchAdapter):
        tier, unit, provenance = "C", "document", "official"

        def load(self):
            yield Sample(id="doc0", gold=[2], pages=["p0", "p1", "p2", "p3"])

        def evaluate(self, sample, prediction, extractor=None):
            return {"primary": 1.0 if prediction.boundaries == sample.gold else 0.0}

    s = run_matrix(models=["seg"], benches=["segb"], model_factory=lambda k: SegModel(k),
                   bench_factory=lambda k: SegBench(k), results_dir=tmp_path, run_id="t5",
                   log=lambda *_: None)
    assert s["score"]["scored"] == 1
    rec = json.loads((tmp_path / "t5" / "raw" / "seg" / "segb.jsonl").read_text())
    assert rec["metrics"]["primary"] == 1.0


def test_load_failure_error_rows_not_crash(tmp_path, dummy_factories):
    _, bf = dummy_factories

    class Unloadable(DummyModel):
        def load(self):
            raise RuntimeError("missing required secrets: FAKE_KEY")

    s = run_matrix(models=["broken", "m1"], benches=["b1"],
                   model_factory=lambda k: Unloadable(k) if k == "broken" else DummyModel(k),
                   bench_factory=bf, results_dir=tmp_path, run_id="t6", log=lambda *_: None)
    assert s["infer"]["errors"] == 4          # broken model: all 4 cells error rows
    assert s["score"]["scored"] == 4          # m1 still ran fully
    board = (tmp_path / "t6" / "scoreboard.csv").read_text()
    assert "broken" in board and "m1" in board
