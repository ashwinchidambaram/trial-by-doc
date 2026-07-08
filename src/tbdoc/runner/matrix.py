"""Orchestrate a run: manifest -> infer (phase 1) -> score (phase 2) -> scoreboard.

Invariants (carried over from the proven ocparse loop):
  - sequential model loading (one model in VRAM at a time)
  - resumable at (model, bench, sample, phase) granularity
  - no silent gaps: every failure is an error row
  - live status.json after every cell
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.core.manifest import build_manifest, write_manifest
from tbdoc.runner.infer import PredictionStore, run_infer
from tbdoc.runner.score import run_score


def new_run_id() -> str:
    return datetime.now().strftime("run_%Y%m%d_%H%M%S")


def run_matrix(*, models: list[str], benches: list[str],
               model_factory: Callable[[str], Any], bench_factory: Callable[[str], Any],
               results_dir: str | Path = "results/runs", run_id: str | None = None,
               max_samples: int | dict | None = None, phases: tuple[str, ...] = ("infer", "score"),
               extractor: Any | None = None, boundary_judge: Any | None = None,
               hardware: dict | None = None, rescore: bool = False,
               instruments_meta: dict | None = None,
               log: Callable[[str], None] = print) -> dict:
    run_id = run_id or new_run_id()
    run_dir = Path(results_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Materialize bench adapters + samples ONCE (reused across models & phases).
    bench_adapters = {b: bench_factory(b) for b in benches}
    bench_samples: dict[str, list] = {}
    for b in benches:
        samples = list(bench_adapters[b].load())
        cap = max_samples.get(b) if isinstance(max_samples, dict) else max_samples
        if cap is not None:
            samples = samples[:cap]
        bench_samples[b] = samples

    # Manifest first — provenance before any compute/spend.
    model_fps = {m: model_factory(m).fingerprint() for m in models}
    bench_fps = {b: bench_adapters[b].fingerprint() for b in benches}
    manifest = build_manifest(run_id=run_id, models=models, benches=benches,
                              model_fingerprints=model_fps, bench_fingerprints=bench_fps,
                              instruments=instruments_meta, hardware=hardware)
    write_manifest(run_dir, manifest)
    log(f"[run] {run_id}: {len(models)} models × {len(benches)} benches "
        f"({sum(len(v) for v in bench_samples.values())} samples/model)")

    preds = PredictionStore(run_dir)
    store = CheckpointStore(run_dir)
    summary: dict[str, Any] = {"run_id": run_id, "run_dir": str(run_dir)}
    if "infer" in phases:
        summary["infer"] = run_infer(models=models, benches=benches,
                                     model_factory=model_factory,
                                     bench_factory=lambda b: bench_adapters[b],
                                     store=preds, bench_samples=bench_samples,
                                     boundary_judge=boundary_judge, log=log)
    if "score" in phases:
        summary["score"] = run_score(models=models, benches=benches,
                                     bench_factory=lambda b: bench_adapters[b],
                                     preds=preds, store=store, bench_samples=bench_samples,
                                     model_fingerprints=model_fps, extractor=extractor,
                                     boundary_judge=boundary_judge,
                                     rescore=rescore, hardware=hardware, log=log)
    return summary
