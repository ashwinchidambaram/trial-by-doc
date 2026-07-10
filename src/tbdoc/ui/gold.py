"""The per-example ground-truth join.

Reuses each bench's own `BenchAdapter.load()` (the exact same generator the harness used
to produce the samples that were scored) to find a `Sample` by id, then — for the two
Tier-A benches whose gold isn't on `Sample.gold` because their official scorer reads gold
directly off disk out-of-process (see docs/superpowers/specs/2026-07-09-dashboard-ui-design.md
§4.3) — does a light, read-only reconstruction of a human-readable gold view from that same
data file. Never touches the official scorer subprocess; never re-scores anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tbdoc.core.bench_adapter import Sample


def find_sample(ba: Any, sample_id: str) -> Sample | None:
    """Iterate `ba.load()`, stopping as soon as the matching sample is found.

    Cheap for the 30-300-sample cells this run has (the scored subset sits early in each
    bench's deterministic round-robin ordering); documented as a known cost for a
    late-order sample_id on a bench with a much larger full dataset (e.g. omnidocbench's
    1651 pages) — see spec §4.2.
    """
    for s in ba.load():
        if str(s.id) == str(sample_id):
            return s
    return None


def _omnidocbench_gold(ba: Any, sample_id: str) -> dict[str, Any]:
    gt_path = Path(ba.data_dir) / "OmniDocBench.json"
    pages = json.loads(gt_path.read_text(encoding="utf-8"))
    for p in pages:
        if Path(p["page_info"]["image_path"]).name == sample_id:
            blocks = sorted(
                (b for b in p.get("layout_dets", []) if not b.get("ignore") and b.get("text")),
                key=lambda b: b.get("order", 0),
            )
            text = "\n\n".join(b["text"] for b in blocks)
            return {
                "kind": "page_annotation",
                "reconstructed_text": text,
                "n_blocks": len(blocks),
                "note": "approximate reconstruction from layout_dets order; not the exact "
                        "official scorer input (that also uses table/formula-specific "
                        "serialization this view does not replicate)",
            }
    return {"kind": "page_annotation", "reconstructed_text": None,
            "note": f"no page_info.image_path matched sample_id={sample_id!r} in {gt_path}"}


def _olmocr_bench_gold(ba: Any, sample_id: str, category: str | None,
                       raw_metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not category:
        return {"kind": "unit_tests", "tests": [], "note": "no category on the raw record"}
    jl_path = Path(ba.data_dir) / "bench_data" / f"{category}.jsonl"
    if not jl_path.exists():
        return {"kind": "unit_tests", "tests": [],
                "note": f"expected test file missing: {jl_path}"}
    fail_ids = {f.get("id") for f in (raw_metrics or {}).get("fails", []) or []}
    fail_reason = {f.get("id"): f.get("reason") for f in (raw_metrics or {}).get("fails", []) or []}
    tests = []
    for line in jl_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if Path(row.get("pdf", "")).name != sample_id:
            continue
        tid = row.get("id")
        tests.append({
            "id": tid, "type": row.get("type"),
            "assertion": row.get("math") or row.get("text") or row.get("before") or row.get("after"),
            "passed": None if tid not in fail_ids and tid is None else (tid not in fail_ids),
            "fail_reason": fail_reason.get(tid),
        })
    return {"kind": "unit_tests", "tests": tests,
            "note": "pass/fail badges are read from the raw score record's metrics.fails, "
                    "produced by the official olmocr.bench.tests runner"}


def _qa_gold(sample: Sample) -> dict[str, Any]:
    return {"kind": "qa", "question": sample.question, "answers": sample.gold}


def _segmentation_gold(sample: Sample, raw_metrics: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "kind": "segmentation",
        "boundaries": sample.gold,
        "n_pages": len(sample.pages),
        "predicted_boundaries": None,
        "note": "predicted boundaries are not persisted (only aggregate PQ/boundary_f1/"
                "boundary_precision/boundary_recall are, in the raw score record's metrics)",
    }


def gold_view(bench_key: str, ba: Any, sample: Sample,
              raw_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bench-appropriate ground-truth view for `sample`. See spec §4.3 for the per-bench shapes."""
    if bench_key == "omnidocbench":
        return _omnidocbench_gold(ba, sample.id)
    if bench_key == "olmocr_bench":
        return _olmocr_bench_gold(ba, sample.id, sample.category, raw_metrics)
    if bench_key.startswith("realdoc_qa"):
        return _qa_gold(sample)
    if bench_key == "merged_forms":
        return _segmentation_gold(sample, raw_metrics)
    if sample.gold is not None:
        return {"kind": "raw_gold", "value": sample.gold}
    return {"kind": "unknown", "note": f"no gold view implemented for bench '{bench_key}'"}
