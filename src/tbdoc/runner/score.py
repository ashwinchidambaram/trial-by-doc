"""Phase 2 — scoring. Batch per (model, bench) cell; no GPU needed for Tier A/C.

Reads predictions JSONL, rebuilds typed predictions, calls bench.evaluate_batch()
(official scorers run in their isolated venv/container in ONE batch), records into
the CheckpointStore (which derives scoreboard.csv + status.json).
"""
from __future__ import annotations

from typing import Any, Callable

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.core.structured_doc import Segmentation, StructuredDoc
from tbdoc.runner.infer import PredictionStore


def _rebuild(rec: dict, boundary_judge: Any | None = None) -> Any:
    if rec["kind"] == "structured_doc":
        return StructuredDoc.from_dict(rec["prediction"])
    if rec["kind"] == "segmentation":
        d = rec["prediction"]
        return Segmentation(boundaries=d["boundaries"], method=d.get("method", "native"),
                            raw=d.get("raw") or {})
    if rec["kind"] == "page_docs":
        if boundary_judge is None:
            return None  # can't compose without the instrument (--no-llm-instruments)
        mds = [(d.get("markdown") or "") for d in rec["prediction"]]
        return Segmentation(boundaries=boundary_judge.boundaries(mds),
                            method="judge_composed", raw={"judge": boundary_judge.identity()})
    return None  # error row


def run_score(*, models: list[str], benches: list[str],
              bench_factory: Callable[[str], Any],
              preds: PredictionStore, store: CheckpointStore,
              bench_samples: dict[str, list],
              model_fingerprints: dict[str, dict] | None = None,
              extractor: Any | None = None, boundary_judge: Any | None = None,
              rescore: bool = False,
              hardware: dict | None = None,
              log: Callable[[str], None] = print) -> dict:
    n_scored = n_err = 0
    totals = {(m, b): len(bench_samples[b]) for m in models for b in benches}
    fps = model_fingerprints or {}
    for m in models:
        for b in benches:
            ba = bench_factory(b)
            cell = preds.load_cell(m, b)
            samples = [s for s in bench_samples[b] if str(s.id) in cell]
            pending = [s for s in samples if rescore or not store.is_done(m, b, s.id)]
            if not pending:
                continue
            sample_pred, sample_err = [], []
            for s in pending:
                rec = cell[str(s.id)]
                p = _rebuild(rec, boundary_judge=boundary_judge)
                (sample_err if p is None else sample_pred).append((s, rec.get("error"), p))
            # propagate inference errors as error rows (never a silent gap)
            for s, err, _ in sample_err:
                store.record(m, b, s.id, metrics={"primary": None}, error=err or "inference failed")
                n_err += 1
            if sample_pred:
                ss = [s for s, _, _ in sample_pred]
                pp = [p for _, _, p in sample_pred]
                use_ex = extractor if ba.requires_extractor else None
                try:
                    results = ba.evaluate_batch(ss, pp, extractor=use_ex)
                except Exception as e:
                    for s in ss:
                        store.record(m, b, s.id, metrics={"primary": None},
                                     error=f"scorer: {type(e).__name__}: {e}")
                    n_err += len(ss)
                    results = {}
                for s, p in zip(ss, pp):
                    if str(s.id) not in results and s.id not in results:
                        continue
                    metrics = results.get(str(s.id), results.get(s.id))
                    tel = p.telemetry.to_dict() if hasattr(p, "telemetry") else {}
                    # scorers mark per-sample failures inside metrics["error"] (always with
                    # primary=None) — surface that as a real error row, never a silent gap
                    err = metrics.get("error") if isinstance(metrics, dict) else None
                    store.record(m, b, s.id, metrics=metrics, telemetry=tel,
                                 category=metrics.get("category", s.category),
                                 model_revision=(fps.get(m) or {}).get("revision")
                                 or (fps.get(m) or {}).get("api_version"),
                                 error=err)
                    if err is None:
                        n_scored += 1
                    else:
                        n_err += 1
            store.write_status(models, benches, totals=totals, hardware=hardware,
                               current={"model": m, "bench": b, "phase": "score"})
            log(f"[score] {m} × {b}: {len(pending)} samples")
    store.write_scoreboard(models, benches)
    store.write_status(models, benches, totals=totals, hardware=hardware, current=None)
    return {"scored": n_scored, "errors": n_err}
