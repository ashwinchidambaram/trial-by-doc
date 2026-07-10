"""Read-only data access over a scored run directory.

Reuses the SAME source-of-truth readers the CLI uses (`CheckpointStore`,
`tbdoc.report.scoreboard`) so the dashboard's numbers are always identical to
`gauntlet scoreboard`'s — no metric math is re-derived here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import _collect as _collect_scoreboard

# License tags this dashboard will redistribute a thumbnail for. Anything else
# (including "unspecified" / absent) is gated — metadata-only in the explorer gallery.
# See docs/superpowers/specs/2026-07-09-dashboard-ui-design.md §4.2.
GALLERY_LICENSE_ALLOWLIST = {
    "odc-by", "cc-by-4.0", "cc0", "mit", "apache-2.0", "public-domain",
}


def scoreboard_payload(run_dir: Path, registry) -> dict[str, Any]:
    """Leaderboard matrix + per-category breakdown, provenance/license-labeled.

    Numbers come straight from `report.scoreboard._collect` (the same function
    `gauntlet scoreboard` prints), so a UI reload always matches the CLI exactly.
    """
    models, benches, cells, cats = _collect_scoreboard(run_dir)
    bmeta = registry.benchmarks if registry else {}

    def mean_n(vals: list[float]) -> dict[str, Any]:
        return {"mean": round(sum(vals) / len(vals), 4) if vals else None, "n": len(vals)}

    cell_out = {f"{m}|{b}": mean_n(cells.get((m, b), [])) for m in models for b in benches}
    cat_out: dict[str, dict[str, dict[str, Any]]] = {}
    for (m, b, c), vals in cats.items():
        cat_out.setdefault(f"{m}|{b}", {})[c] = mean_n(vals)

    bench_meta = {}
    for b in benches:
        meta = bmeta.get(b, {})
        src = meta.get("source") or {}
        bench_meta[b] = {
            "tier": meta.get("tier", "?"),
            "unit": meta.get("unit", "page"),
            "provenance": meta.get("provenance", "?"),
            "license": src.get("license"),
            "revision": src.get("revision"),
        }
    return {
        "run_id": run_dir.name,
        "models": models,
        "benches": benches,
        "cells": cell_out,
        "categories": cat_out,
        "bench_meta": bench_meta,
        "n_scored": sum(len(v) for v in cells.values()),
    }


def bench_catalog(registry, *, preview_cap: int = 300) -> list[dict[str, Any]]:
    """One entry per registered benchmark: tier/provenance/license/sample-count/gallery flag.

    `sample_count` is capped at `preview_cap` for speed — iterating `BenchAdapter.load()`
    fully decodes every page image for benches with 1000+ pages (omnidocbench), which is
    wasteful just to print a count. A `~` prefix on `sample_count_exact=False` tells the
    frontend the number is a floor, not the full dataset size.
    """
    out = []
    for key, meta in registry.benchmarks.items():
        src = meta.get("source") or {}
        license_ = src.get("license")
        entry: dict[str, Any] = {
            "key": key,
            "tier": meta.get("tier", "?"),
            "unit": meta.get("unit", "page"),
            "provenance": meta.get("provenance", "?"),
            "license": license_,
            "revision": src.get("revision"),
            "scorer": (meta.get("scorer") or {}).get("kind"),
            "gallery_allowed": (license_ or "").lower() in GALLERY_LICENSE_ALLOWLIST,
        }
        try:
            ba = registry.bench(key)
            n = 0
            for _ in ba.load():
                n += 1
                if n >= preview_cap:
                    break
            entry["sample_count"] = n
            entry["sample_count_exact"] = n < preview_cap
            entry["categories"] = ba.categories()
        except Exception as e:  # data not downloaded, custom validation_doc missing, etc.
            entry["sample_count"] = None
            entry["sample_count_exact"] = False
            entry["categories"] = None
            entry["load_error"] = str(e)
        out.append(entry)
    return out


def prediction_record(run_dir: Path, model: str, bench: str, sample_id: str) -> dict[str, Any] | None:
    path = run_dir / "predictions" / model / f"{bench}.jsonl"
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if str(rec.get("sample_id")) == str(sample_id):
            last = rec  # last record wins (rescore appends)
    return last


def raw_record(run_dir: Path, model: str, bench: str, sample_id: str) -> dict[str, Any] | None:
    store = CheckpointStore(run_dir)
    for rec in reversed(store.cell_records(model, bench)):
        if str(rec.get("sample_id")) == str(sample_id):
            return rec
    return None


def list_cells(run_dir: Path) -> list[dict[str, Any]]:
    """{model, bench, n} for every (model, bench) cell that has raw records."""
    raw = run_dir / "raw"
    if not raw.exists():
        return []
    out = []
    for model_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        for jl in sorted(model_dir.glob("*.jsonl")):
            n = sum(1 for line in jl.read_text().splitlines() if line.strip())
            out.append({"model": model_dir.name, "bench": jl.stem, "n": n})
    return out


def sample_ids(run_dir: Path, model: str, bench: str, *, limit: int = 500) -> list[str]:
    path = run_dir / "raw" / model / f"{bench}.jsonl"
    if not path.exists():
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            sid = str(json.loads(line).get("sample_id"))
        except Exception:
            continue
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
        if len(ids) >= limit:
            break
    return ids
