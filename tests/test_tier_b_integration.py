"""End-to-end SCORE phase integration test (no GPU, no network).

Drives run_score() with a synthetic prediction cell and a fake B.2 reader instrument,
and asserts both B.1 (primary, deterministic) and B.2 (via the reader) land in the
CheckpointStore records for a single (model, bench, sample) cell.

Note on PredictionStore's API: the store's write method is `record(...)`, not
`append(...)` (there is no `.append` on PredictionStore — see
src/tbdoc/runner/infer.py). The fake reader answers in the gold's `key=value`
format ("amount=8500") rather than a bare "8500": field_aware_exact_match parses
key=value pairs on both sides (src/tbdoc/scoring/scorers.py), so a bare "8500"
would not match "amount=8500" and B.2 would score 0.0 instead of 1.0 (mirrors the
convention already used in tests/test_realdoc_eval_split.py).
"""
from pathlib import Path

from tbdoc.core.bench_adapter import Sample
from tbdoc.instruments.extractor import FunctionExtractor


def test_score_phase_records_b1_primary(tmp_path: Path):
    from tbdoc.benches.official.realdoc_qa import RealDocQA
    from tbdoc.core.checkpoint import CheckpointStore
    from tbdoc.runner.infer import PredictionStore
    from tbdoc.runner.score import run_score

    preds = PredictionStore(tmp_path)
    preds.record("m1", "realdoc_qa", "q1", kind="structured_doc",
                 prediction={"markdown": "Amount: 8500", "layout_boxes": [], "telemetry": {}})
    samples = [Sample(id="q1", gold=["amount=8500"], question="What is the amount paid?",
                      category="finance")]
    store = CheckpointStore(tmp_path)
    reader = FunctionExtractor(lambda md, q: "amount=8500", identity="fake-reader")
    run_score(models=["m1"], benches=["realdoc_qa"],
              bench_factory=lambda k: RealDocQA(k), preds=preds, store=store,
              bench_samples={"realdoc_qa": samples}, extractor=reader)
    rec = next(r for r in store.iter_records() if r["model"] == "m1")
    assert rec["metrics"]["b1"] == 1.0
    assert rec["metrics"]["primary"] == 1.0
    assert rec["metrics"]["b2"] == 1.0
