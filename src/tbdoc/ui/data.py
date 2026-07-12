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
from tbdoc.report.scoreboard import _is_derived_bench
from tbdoc.report.scoreboard import collect_grid as _collect_grid
from tbdoc.report.scoreboard import load_summary as _load_summary

# License tags this dashboard will redistribute a thumbnail for. Anything else
# (including "unspecified" / absent) is gated — metadata-only in the explorer gallery.
# See docs/superpowers/specs/2026-07-09-dashboard-ui-design.md §4.2.
GALLERY_LICENSE_ALLOWLIST = {
    "odc-by", "cc-by-4.0", "cc0", "mit", "apache-2.0", "public-domain",
}


def scoreboard_payload(run_dir: Path, registry) -> dict[str, Any]:
    """Leaderboard matrix + per-category breakdown, provenance/license-labeled.

    Numbers come straight from `report.scoreboard.collect_grid` (the same source
    `gauntlet scoreboard` prints — raw records, else the tracked summary.json on a
    fresh clone), so a UI reload always matches the CLI exactly.
    """
    try:
        models, benches, cells, cats, from_summary = _collect_grid(run_dir)
    except FileNotFoundError:
        models, benches, cells, cats, from_summary = [], [], {}, {}, False
    # scanned-degradation variants are a robustness study, not core leaderboard columns —
    # they surface via the robustness endpoint / the cockpit's robust column, not here
    # (mirrors report.scoreboard.render). Keeps the leaderboard the canonical tiers.
    benches = [b for b in benches if not _is_derived_bench(b)]
    bmeta = registry.benchmarks if registry else {}

    def mean_n(stat: dict | None) -> dict[str, Any]:
        if not stat or stat.get("mean") is None:
            return {"mean": None, "n": (stat or {}).get("n", 0)}
        return {"mean": round(stat["mean"], 4), "n": stat["n"]}

    cell_out = {f"{m}|{b}": mean_n(cells.get((m, b))) for m in models for b in benches}
    cat_out: dict[str, dict[str, dict[str, Any]]] = {}
    for (m, b, c), stat in cats.items():
        cat_out.setdefault(f"{m}|{b}", {})[c] = mean_n(stat)

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
        "n_scored": sum(s.get("n", 0) for (m, b), s in cells.items() if b in set(benches)),
        "source": "summary" if from_summary else "raw",
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
    """{model, bench, n} for every (model, bench) cell — raw records, else summary.json."""
    raw = run_dir / "raw"
    if raw.exists():
        out = []
        for model_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
            for jl in sorted(model_dir.glob("*.jsonl")):
                n = sum(1 for line in jl.read_text().splitlines() if line.strip())
                out.append({"model": model_dir.name, "bench": jl.stem, "n": n})
        return out
    s = _load_summary(run_dir)
    if not s:
        return []
    out = []
    for key, stat in sorted((s.get("cells") or {}).items()):
        m, b = key.split("|", 1)
        out.append({"model": m, "bench": b, "n": (stat or {}).get("n", 0)})
    return out


def perf_payload(run_dir: Path) -> list[dict[str, Any]]:
    """Per-model latency / VRAM / $per-page — prediction telemetry, else summary.json."""
    from tbdoc.report.scoreboard import perf_stats
    perf, _ = perf_stats(run_dir)
    return [{"model": m, **d} for m, d in perf.items()]


def tier_b_payload(run_dir: Path) -> list[dict[str, Any]]:
    """Per-model Tier-B: B.1 (extraction), coverage, B.2 (comprehension), reader identity."""
    from tbdoc.report.scoreboard import tier_b_stats
    per, _ = tier_b_stats(run_dir)
    out = []
    for m, d in per.items():
        out.append({"model": m,
                    "b1": round(d["b1"], 3) if d["b1"] is not None else None,
                    "coverage": {"extractive": d["n_extractive"], "total": d["n_total"]},
                    "b2": round(d["b2"], 3) if d["b2"] is not None else None,
                    "reader": d["reader"]})
    return out


def cost_payload() -> dict[str, Any]:
    """Classic-engine CPU/GPU rows + per-model self-host rows (single source of truth)."""
    from tbdoc.report import cost_tables as ct
    return {"classic": ct.classic_cost_rows(), "self_host": ct.self_host_rows()}


def robustness_payload(run_dir: Path) -> list[dict[str, Any]]:
    """Per-model scan-robustness curve: clean -> light -> heavy B.1, and heavy-retained %.

    clean = realdoc_qa primary; light/heavy = the scanned-variant benches. Only models with
    scanned data are returned. Matches findings/partd-scanned-robustness.md.
    """
    try:
        _models, _benches, cells, _cats, _ = _collect_grid(run_dir)
    except FileNotFoundError:
        return []

    def cell_mean(model: str, bench: str) -> float | None:
        stat = cells.get((model, bench))
        if not stat or stat.get("mean") is None:
            return None
        return round(stat["mean"], 3)

    out = []
    for m in _models:
        light = cell_mean(m, "realdoc_qa_scanned_light")
        heavy = cell_mean(m, "realdoc_qa_scanned_heavy")
        if light is None and heavy is None:
            continue
        clean = cell_mean(m, "realdoc_qa")
        retained = (round(heavy / clean * 100) if clean and heavy is not None and clean > 0
                    else None)
        out.append({"model": m, "clean": clean, "light": light, "heavy": heavy,
                    "retained_pct": retained})
    return out


def qa_value_presence(markdown: str, golds: list[str]) -> dict[str, Any]:
    """Per-value presence for the BEST gold variant, mirroring `field_value_presence`.

    The B.1 scorer parses a `key=value` gold into fields and checks whether each VALUE
    (e.g. ``12800``) appears in the OCR markdown — numeric-tolerant, with an ANLS fuzzy
    fallback. It never looks for the literal ``automobile_premium=12800`` string. This
    reuses the frozen scorer's own `_parse_fields`/`_value_in_markdown` so the workbench's
    highlight + "missing" chips agree with the b1 number by construction (no re-derived
    heuristic that would contradict the score). Returns the value list to highlight plus the
    present/missing split for the variant the scorer would have credited (highest hit rate).
    """
    from tbdoc.scoring.scorers import _parse_fields, _value_in_markdown
    md = markdown or ""
    best: tuple[float, list[str], list[str], list[str]] | None = None
    for g in golds:
        fields = _parse_fields(g)
        vals = [v for v in (list(fields.values()) if fields else [g]) if v]
        if not vals:
            continue
        present, missing = [], []
        for v in vals:
            (present if _value_in_markdown(v, md, 0.8) else missing).append(v)
        frac = len(present) / len(vals)
        if best is None or frac > best[0]:
            best = (frac, vals, present, missing)
    if best is None:
        return {"values": [], "present": [], "missing": []}
    return {"values": best[1], "present": best[2], "missing": best[3]}


def provenance_payload(run_dir: Path) -> dict[str, Any]:
    """Reproducibility fingerprint from manifest.json for the verify popover."""
    mf = run_dir / "manifest.json"
    if not mf.exists():
        return {}
    m = json.loads(mf.read_text())
    harness = m.get("harness") or {}
    models = m.get("models") or {}
    return {
        "run_id": m.get("run_id"),
        "created_at": m.get("created_at"),
        "hardware": m.get("hardware") or {},
        "seeds": m.get("seeds"),
        "config_hashes": m.get("configs"),
        "git_sha": harness.get("git_sha"),
        "git_dirty": harness.get("git_dirty"),
        "python": harness.get("python"),
        "models": {k: (v.get("revision") if isinstance(v, dict) else v) for k, v in models.items()},
    }


def scored_sample_ids(run_dir: Path, model: str, bench: str, *, limit: int = 500) -> list[dict[str, Any]]:
    """Sample ids with their primary score + error, sorted worst-first (None primary last).

    Powers the workbench failure-triage list. Last record per sample_id wins (rescore appends).
    """
    path = run_dir / "raw" / model / f"{bench}.jsonl"
    if not path.exists():
        return []
    latest: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        latest[str(rec.get("sample_id"))] = rec
    out = []
    for sid, rec in latest.items():
        prim = (rec.get("metrics") or {}).get("primary")
        out.append({"sample_id": sid,
                    "primary": prim if isinstance(prim, (int, float)) else None,
                    "error": rec.get("error")})
    out.sort(key=lambda r: (r["primary"] is None, r["primary"] if r["primary"] is not None else 0.0))
    return out[:limit]


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
