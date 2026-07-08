"""Phase 1 — inference. One model in VRAM at a time; predictions saved to JSONL.

predictions/<model>/<bench>.jsonl : {"sample_id", "kind", "prediction", "error"}
Resumable: sample ids already present are skipped. Decoupling inference from scoring
means a scorer bugfix never re-runs inference (which costs GPU-hours or API dollars).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class PredictionStore:
    def __init__(self, run_dir: str | Path):
        self.root = Path(run_dir) / "predictions"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, model: str, bench: str) -> Path:
        return self.root / model / f"{bench}.jsonl"

    def done_ids(self, model: str, bench: str) -> set[str]:
        p = self.path(model, bench)
        ids: set[str] = set()
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    try:
                        ids.add(str(json.loads(line)["sample_id"]))
                    except Exception:
                        continue  # torn final line from a crash
        return ids

    def record(self, model: str, bench: str, sample_id: str, *, kind: str,
               prediction: dict | list | None, error: str | None = None) -> None:
        p = self.path(model, bench)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"sample_id": str(sample_id), "kind": kind,
                                "prediction": prediction, "error": error}) + "\n")

    def load_cell(self, model: str, bench: str) -> dict[str, dict]:
        p = self.path(model, bench)
        out: dict[str, dict] = {}
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    try:
                        r = json.loads(line)
                        out[str(r["sample_id"])] = r
                    except Exception:
                        pass
        return out


def run_infer(*, models: list[str], benches: list[str],
              model_factory: Callable[[str], Any], bench_factory: Callable[[str], Any],
              store: PredictionStore, bench_samples: dict[str, list],
              boundary_judge: Any | None = None,
              log: Callable[[str], None] = print) -> dict:
    """Returns {"predicted": n, "errors": n}. Never a silent gap: errors are recorded."""
    n_pred = n_err = 0
    for m in models:
        # figure out remaining work before paying for a model load
        todo = {b: [s for s in bench_samples[b] if str(s.id) not in store.done_ids(m, b)]
                for b in benches}
        if not any(todo.values()):
            log(f"[infer] {m}: all cells complete, skipping load")
            continue
        adapter = model_factory(m)
        try:
            adapter.__enter__()
        except Exception as e:
            # Model failed to LOAD (missing API key, OOM, bad revision): error-row every
            # pending cell so the gap is visible, then continue with the next model.
            for b in benches:
                for s in todo[b]:
                    store.record(m, b, s.id, kind="error", prediction=None,
                                 error=f"load failed: {type(e).__name__}: {e}")
                    n_err += 1
                    n_pred += 1
            log(f"[infer] {m}: LOAD FAILED ({type(e).__name__}: {e}) — cells recorded as errors")
            continue
        try:
            for b in benches:
                ba = bench_factory(b)
                memo: dict[int, dict] = {}  # same page image (multi-question docs) -> OCR once
                for s in todo[b]:
                    try:
                        if ba.unit == "document":
                            if "segmentation" in adapter.capabilities:
                                seg = adapter.segment(s.pages)
                                store.record(m, b, s.id, kind="segmentation",
                                             prediction=seg.to_dict())
                            else:
                                # judge-composed path: OCR pages now; the frozen judge
                                # composes boundaries in the SCORE phase (GPU-sequenced).
                                docs = adapter.predict_document(s.pages)
                                store.record(m, b, s.id, kind="page_docs",
                                             prediction=[d.to_dict() for d in docs])
                        else:
                            key = id(s.image)
                            pred_d = memo.get(key)
                            if pred_d is None:
                                pred_d = adapter.predict(s.image).to_dict()
                                memo[key] = pred_d
                            store.record(m, b, s.id, kind="structured_doc",
                                         prediction=pred_d)
                    except Exception as e:
                        n_err += 1
                        store.record(m, b, s.id, kind="error", prediction=None,
                                     error=f"{type(e).__name__}: {e}")
                    n_pred += 1
                log(f"[infer] {m} × {b}: {len(todo[b])} new predictions")
        finally:
            adapter.__exit__(None, None, None)
    return {"predicted": n_pred, "errors": n_err}
