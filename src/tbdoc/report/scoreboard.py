"""Scoreboard rendering: per-model × per-bench primary means, provenance-labeled.

Data source: results/runs/<id>/raw/*.jsonl via CheckpointStore (the source of truth),
not scoreboard.csv (which is derived).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tbdoc.core.checkpoint import CheckpointStore


def _collect(run_dir: Path):
    store = CheckpointStore(run_dir)
    cells: dict[tuple[str, str], list[float]] = defaultdict(list)
    cats: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    models, benches = [], []
    latest: dict[tuple[str, str, str], dict] = {}   # last record per sample wins (--rescore appends)
    for r in store.iter_records():
        m, b = r["model"], r["bench"]
        if m not in models:
            models.append(m)
        if b not in benches:
            benches.append(b)
        latest[(m, b, str(r.get("sample_id")))] = r
    for (m, b, _sid), r in latest.items():
        v = (r.get("metrics") or {}).get("primary")
        if isinstance(v, (int, float)) and r.get("error") is None:
            cells[(m, b)].append(v)
            if r.get("category"):
                cats[(m, b, r["category"])].append(v)
    return models, benches, cells, cats


def _mean(vals: list[float]) -> str:
    return f"{sum(vals)/len(vals):.3f}" if vals else "—"


def _perf(run_dir: Path):
    """Per-model performance from prediction telemetry: latency/page, peak VRAM, $/page.

    Reads predictions/*.jsonl (structured_doc = one telemetry; page_docs = one per page).
    """
    import json
    from statistics import median
    root = Path(run_dir) / "predictions"
    per: dict[str, dict[str, list]] = {}
    for f in root.rglob("*.jsonl"):
        model = f.parent.name
        d = per.setdefault(model, {"lat": [], "vram": [], "cost": []})
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            try:
                pred = json.loads(line).get("prediction")
            except Exception:
                continue
            tels = ([pred.get("telemetry")] if isinstance(pred, dict)
                    else [x.get("telemetry") for x in pred] if isinstance(pred, list) else [])
            for t in tels:
                if not t:
                    continue
                if t.get("latency_s") is not None:
                    d["lat"].append(t["latency_s"])
                if t.get("peak_vram_mb"):
                    d["vram"].append(t["peak_vram_mb"])
                if t.get("cost_usd"):
                    d["cost"].append(t["cost_usd"])
    out = {}
    for m, d in per.items():
        if not d["lat"]:
            continue
        out[m] = {
            "n": len(d["lat"]),
            "median_s": round(median(d["lat"]), 2),
            "mean_s": round(sum(d["lat"]) / len(d["lat"]), 2),
            "p90_s": round(sorted(d["lat"])[int(len(d["lat"]) * 0.9)], 2),
            "peak_vram_gb": round(max(d["vram"]) / 1024, 1) if d["vram"] else None,
            "cost_per_page_usd": round(sum(d["cost"]) / len(d["cost"]), 5) if d["cost"] else None,
        }
    return out


def render_perf(run_dir: Path, models: list[str] | None = None) -> str:
    perf = _perf(run_dir)
    order = [m for m in (models or perf) if m in perf]
    if not order:
        return "_no timing telemetry_"
    out = ["| model | median s/page | mean s/page | p90 s/page | peak VRAM | $/page |",
           "|---|---|---|---|---|---|"]
    for m in order:
        p = perf[m]
        vram = f"{p['peak_vram_gb']} GB" if p["peak_vram_gb"] else "— (API)"
        cost = f"${p['cost_per_page_usd']}" if p["cost_per_page_usd"] else "—"
        out.append(f"| {m} | {p['median_s']} | {p['mean_s']} | {p['p90_s']} | {vram} | {cost} |")
    return "\n".join(out)


def render(run_dir: Path, *, fmt: str = "md", by: str = "bench", registry=None) -> str:
    models, benches, cells, cats = _collect(run_dir)
    bmeta = (registry.benchmarks if registry else {}) or {}

    if by == "category":
        lines = []
        for b in benches:
            keys = sorted({c for (m, bb, c) in cats if bb == b})
            if not keys:
                continue
            lines.append(f"\n### {b} by category")
            lines.append("| model | " + " | ".join(keys) + " |")
            lines.append("|---" * (len(keys) + 1) + "|")
            for m in models:
                lines.append(f"| {m} | " + " | ".join(
                    _mean(cats.get((m, b, c), [])) for c in keys) + " |")
        return "\n".join(lines) or "no per-category data"

    def col_label(b: str) -> str:
        meta = bmeta.get(b, {})
        tag = f" ({meta.get('provenance', '?')}, tier {meta.get('tier', '?')})"
        return b + (tag if by in ("provenance", "tier") else "")

    header = ["model", *[col_label(b) for b in benches]]
    rows = [[m, *[_mean(cells.get((m, b), [])) for b in benches]] for m in models]
    if fmt == "csv":
        return "\n".join(",".join(r) for r in [header, *rows])
    out = ["| " + " | ".join(header) + " |", "|---" * len(header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    n = sum(len(v) for v in cells.values())
    out.append(f"\n_{n} scored samples · run: {Path(run_dir).name}_")
    return "\n".join(out)


def _collect_tier_b(run_dir):
    store = CheckpointStore(run_dir)
    per = {}   # model -> {b1: [...], n_total, n_extractive, b2: [...], reader}
    latest = {}
    for r in store.iter_records():
        if r.get("bench") != "realdoc_qa":
            continue
        latest[(r["model"], str(r.get("sample_id")))] = r
    for (m, _sid), r in latest.items():
        d = per.setdefault(m, {"b1": [], "n_total": 0, "n_extractive": 0, "b2": [], "reader": None})
        mt = r.get("metrics") or {}
        d["n_total"] += 1
        if mt.get("extractive"):
            d["n_extractive"] += 1
            if isinstance(mt.get("b1"), (int, float)):
                d["b1"].append(mt["b1"])
        if isinstance(mt.get("b2"), (int, float)):
            d["b2"].append(mt["b2"])
        d["reader"] = d["reader"] or mt.get("reader")
    return per


def render_tier_b(run_dir, models=None):
    per = _collect_tier_b(run_dir)
    order = [m for m in (models or per) if m in per]
    if not order:
        return "_no Tier-B records_"
    out = ["| model | B.1 extract | coverage | B.2 comp | reader |", "|---|---|---|---|---|"]
    for m in order:
        d = per[m]
        b1 = f"{sum(d['b1'])/len(d['b1']):.3f}" if d["b1"] else "—"
        cov = f"{d['n_extractive']}/{d['n_total']}"
        b2 = f"{sum(d['b2'])/len(d['b2']):.3f}" if d["b2"] else "—"
        out.append(f"| {m} | {b1} | {cov} | {b2} | {d['reader'] or '—'} |")
    return "\n".join(out)


README_BEGIN, README_END = "<!-- SCOREBOARD:BEGIN -->", "<!-- SCOREBOARD:END -->"


def inject_readme(run_dir: Path, readme_path: Path, *, registry=None,
                  extra_md: str = "") -> None:
    """Replace the README's scoreboard block with this run's rendered scores."""
    md = render(run_dir, fmt="md", by="bench", registry=registry)
    body = f"{README_BEGIN}\n{md}\n{extra_md}\n{README_END}"
    text = readme_path.read_text()
    import re
    new = re.sub(re.escape(README_BEGIN) + r".*?" + re.escape(README_END),
                 body, text, flags=re.S)
    readme_path.write_text(new)
