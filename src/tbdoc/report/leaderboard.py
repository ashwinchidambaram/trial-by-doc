"""Cross-run leaderboard — the four-tier gauntlet table, generated from tracked runs.

One data assembly (`leaderboard_data`) feeding renderers (`render_md`; the published
HTML artifact is generated from the same dict). Hand-editing the rendered
`docs/leaderboard.md` is pointless: `tests/test_leaderboard_drift.py` regenerates it
and diffs, the same guard pattern as `test_readme_drift`.

Provenance rules honored here:
- every populated cell carries the run_id it came from;
- missing cells are EXPLICIT (pending / deferred / n/a / not run), never blank-ambiguous;
- B.2 columns are labeled with the reader identity because the local reader differs
  between v1-baseline (Qwen2.5-1.5B) and the API-fleet run (Phi-4-mini) — the only
  cross-comparable B.2 column is the shared gpt-5.4-mini rescore.
"""
from __future__ import annotations

from pathlib import Path

from tbdoc.report.scoreboard import collect_grid, load_summary, tier_b_stats

#: Runs merged into the main grid, in precedence order (later wins a collision —
#: model sets are disjoint today, so this is belt-and-braces only).
DEFAULT_RUNS = ("v1-baseline", "tierc-floor-15", "run_20260717_095004")
#: Isolated B.2 rescore runs (gpt-5.4-mini reader); feed the B.2 table only.
B2_RESCORE_RUNS = ("v1-b2-gpt5mini", "run_20260717_095004-b2-gpt5mini")

#: Wired-but-unrun models shown as pending rows so the table states its own gaps.
#: Remove an entry once its run lands — regeneration then fills the real cells.
PENDING_MODELS: dict[str, str] = {}
#: (model, bench) cells intentionally skipped, with the reason shown in the legend.
DEFERRED_CELLS: dict[tuple[str, str], str] = {
    ("gpt54_azure", "merged_forms"): "deferred",
    ("kimi_k3", "merged_forms"): "deferred",
}

TIER_ORDER = ("A", "B", "C", "D")
TIERS = {
    "A": ("Parse fidelity", "Grade the OCR markdown directly — deterministic official scorers,"
          " no LLM anywhere in the loop."),
    "B": ("Downstream extraction", "Model markdown → frozen extractor → exact-match/ANLS."
          " Headline is B.1 field-value presence (reader-independent, deterministic);"
          " B.2 comprehension is secondary and reader-mediated."),
    "C": ("Document segmentation", "Multi-doc PDF streams → boundary F1 / PQ / STP via the frozen"
          " boundary judge. Every VLM and API model scored to date lands BELOW the trivial"
          " pixel-diff floor (0.226); only classic engines exceed it, and none clear a bar"
          " we'd call solved — floor baseline rows included for honesty."),
    "D": ("Robustness", "Tier-B pages under deterministic scan/fax degradation (light/heavy),"
          " scored with reader-independent B.1 — a stress axis over Tier B, not a fourth"
          " orthogonal capability."),
}

_READER_SHORT = {
    "Qwen/Qwen2.5-1.5B-Instruct": "Qwen2.5-1.5B (local)",
    "microsoft/Phi-4-mini-instruct": "Phi-4-mini (local)",
    "openrouter:openai/gpt-5.4-mini": "gpt-5.4-mini (API)",
}


def _reader_label(reader: str | None) -> str:
    if not reader:
        return "?"
    base = reader.split("@", 1)[0]
    return _READER_SHORT.get(base, base)


def _model_group(key: str, registry) -> str:
    if key.startswith("baseline_"):
        return "floor"
    entry = (registry.models or {}).get(key) or {}
    return "api" if entry.get("kind") == "api" else "local"


def leaderboard_data(results_dir: Path, registry,
                     run_ids: tuple[str, ...] = DEFAULT_RUNS,
                     b2_run_ids: tuple[str, ...] = B2_RESCORE_RUNS) -> dict:
    """Merge tracked runs into one explicit-celled grid. Pure read; no scoring math."""
    cells: dict[tuple[str, str], dict] = {}
    models: list[str] = []
    run_meta: dict[str, dict] = {}
    for rid in run_ids:
        rd = Path(results_dir) / rid
        ms, _bs, cs, _cats, from_summary = collect_grid(rd)
        s = load_summary(rd) or {}
        run_meta[rid] = {"models": ms, "generated_at": s.get("generated_at"),
                         "source": "summary" if from_summary else "raw"}
        for m in ms:
            if m not in models:
                models.append(m)
        for (m, b), st in cs.items():
            if st and st.get("n") and st.get("mean") is not None:
                cells[(m, b)] = {"mean": st["mean"], "n": st["n"], "run_id": rid}

    # B.2 per reader identity (see module docstring for why reader labels matter)
    tier_b: dict[str, dict] = {}
    for rid in (*run_ids, *b2_run_ids):
        per, _ = tier_b_stats(Path(results_dir) / rid)
        for m, d in per.items():
            row = tier_b.setdefault(m, {"b1": d.get("b1"), "b2": {}})
            if d.get("b2") is not None and d.get("reader"):
                row["b2"][_reader_label(d["reader"])] = {"value": d["b2"], "run_id": rid}

    for m in PENDING_MODELS:
        if m not in models:
            models.append(m)

    # benches grouped by tier, registry declaration order within tier
    benches_by_tier: dict[str, list[str]] = {t: [] for t in TIER_ORDER}
    bench_meta: dict[str, dict] = {}
    for b, meta in (registry.benchmarks or {}).items():
        t = meta.get("tier", "?")
        # a bench earns a column when any merged run scored it (registry order kept)
        if t in benches_by_tier and any(mb == b for (_m, mb) in cells):
            benches_by_tier[t].append(b)
            src = meta.get("source") or {}
            bench_meta[b] = {"tier": t, "provenance": meta.get("provenance"),
                             "hf_repo": src.get("hf_repo"), "revision": src.get("revision"),
                             "license": src.get("license")}

    # group + order models: local (by realdoc B.1 desc), api, floor
    def _b1_key(m: str) -> float:
        st = cells.get((m, "realdoc_qa"))
        return -(st["mean"] if st else -1)
    grouped = {g: [] for g in ("local", "api", "floor")}
    for m in models:
        grouped[_model_group(m, registry)].append(m)
    grouped["local"].sort(key=_b1_key)
    grouped["api"].sort(key=lambda m: (m in PENDING_MODELS, _b1_key(m)))

    return {"cells": {f"{m}|{b}": v for (m, b), v in cells.items()},
            "models_by_group": grouped, "benches_by_tier": benches_by_tier,
            "bench_meta": bench_meta, "tier_b": tier_b, "run_meta": run_meta,
            "pending_models": dict(PENDING_MODELS),
            "deferred_cells": {f"{m}|{b}": r for (m, b), r in DEFERRED_CELLS.items()}}


def _cell_str(data: dict, m: str, b: str) -> str:
    st = data["cells"].get(f"{m}|{b}")
    if st:
        return f"{st['mean']:.3f}"
    if f"{m}|{b}" in data["deferred_cells"]:
        return "deferred"
    if m in data["pending_models"]:
        return "pending"
    if m.startswith("baseline_"):
        return "n/a"
    return "—"


_GROUP_TITLES = {"local": "Local models (VLMs + classic engines)",
                 "api": "Frontier API models",
                 "floor": "Tier-C trivial floor baselines (no model, no LLM)"}


def render_md(data: dict) -> str:
    out: list[str] = []
    w = out.append
    w("# trial-by-doc — Leaderboard")
    w("")
    w("<!-- GENERATED by `gauntlet leaderboard` — do not hand-edit; "
      "tests/test_leaderboard_drift.py regenerates and diffs this file. -->")
    w("")
    w("A model-agnostic OCR / document-intelligence gauntlet. **No LLM-as-judge**: every score "
      "below is a deterministic algorithm; LLMs appear only as *frozen instruments* (the Tier-B "
      "extractor and Tier-C boundary judge — pinned revision, temp=0, seeded, identical for every "
      "model). Instrument-mediated columns are marked ⚙.")
    w("")
    w("## The four tiers")
    w("")
    w("| tier | axis | benches | metric | caveat |")
    w("|---|---|---|---|---|")
    tier_benches = {t: ", ".join(f"`{b}`" for b in bs) for t, bs in data["benches_by_tier"].items()}
    tier_metric = {"A": "official scorer pass-rate / composite", "B": "B.1 field-value presence",
                   "C": "boundary-judge PQ ⚙", "D": "B.1 under degradation"}
    tier_caveat = {"A": "—", "B": "B.2 comprehension is secondary, reader-mediated ⚙",
                   "C": "every VLM/API model scores below the trivial floor",
                   "D": "stress axis over Tier B; synthetic (seeded) degradation"}
    for t in TIER_ORDER:
        name, desc = TIERS[t]
        w(f"| **{t}** | **{name}** — {desc} | {tier_benches.get(t) or '—'} | "
          f"{tier_metric[t]} | {tier_caveat[t]} |")
    w("")
    w("## Scoreboard")
    w("")
    ordered_benches = [b for t in TIER_ORDER for b in data["benches_by_tier"][t]]
    header = "| model | " + " | ".join(
        f"{b} (T{data['bench_meta'][b]['tier']})" for b in ordered_benches) + " |"
    for g in ("local", "api", "floor"):
        ms = data["models_by_group"].get(g) or []
        if not ms:
            continue
        w(f"### {_GROUP_TITLES[g]}")
        w("")
        w(header)
        w("|---" * (len(ordered_benches) + 1) + "|")
        for m in ms:
            w(f"| {m} | " + " | ".join(_cell_str(data, m, b) for b in ordered_benches) + " |")
        w("")
    w("_`—` = not run yet · `pending` = wired, run owner-gated · `deferred` = intentionally "
      "skipped (below-floor tier, cost not justified) · `n/a` = floor baselines run Tier C only._")
    w("")
    w("## Tier B, second axis: B.2 comprehension by reader ⚙")
    w("")
    w("B.1 above is the reader-independent headline. B.2 (did a reader answer questions from the "
      "model's markdown?) depends on the reader, so it is reported per reader identity. Only the "
      "**gpt-5.4-mini** column is comparable across every model — the local reader differs "
      "between run generations (Qwen2.5-1.5B for v1-baseline, Phi-4-mini for the API fleet).")
    w("")
    readers = sorted({r for d in data["tier_b"].values() for r in d["b2"]})
    w("| model | B.1 | " + " | ".join(f"B.2 ({r})" for r in readers) + " |")
    w("|---" * (len(readers) + 2) + "|")
    for g in ("local", "api"):
        for m in data["models_by_group"].get(g) or []:
            d = data["tier_b"].get(m)
            if not d:
                continue
            b1 = f"{d['b1']:.3f}" if d.get("b1") is not None else "—"
            row = [f"{d['b2'][r]['value']:.3f}" if r in d["b2"] else "—" for r in readers]
            w(f"| {m} | {b1} | " + " | ".join(row) + " |")
    w("")
    w("## Findings")
    w("")
    w("- **Scan/fax robustness splits the field (Tier D).** VLMs retain 75–80% of clean "
      "extraction under heavy degradation (olmocr2, gemma4); tesseract and easyocr collapse to "
      "22–29%. docTR is the robust classic exception (58%). Among API models mistral_ocr is the "
      "standout — 95% heavy retention (0.734) vs kimi-k3 86% and the GPTs 71–76%. "
      "Clean-benchmark rankings do not survive scanned input.")
    w("- **OCR-specialized beats generalist at doc-parse.** mistral_ocr tops omnidocbench "
      "(0.868) and both scanned benches; kimi-k3 tops olmocr_bench (0.717) and realdoc B.1 "
      "(0.801) and was the only API model with a zero-error run. gpt-5.4 leads no bench "
      "despite being the priciest model in the fleet.")
    w("- **Tier C is unsolved.** Every VLM and API model scores ≈0.01–0.16 PQ — below the "
      "trivial pixel-diff floor (0.226). Classic engines score higher (easyocr 0.397) but "
      "nothing clears a bar we'd call solved. This is why Tier C was deferred for the frontier "
      "API runs (gpt-5.4, kimi-k3).")
    w("- **No same-vendor B.2 inflation observed.** Under the OpenAI gpt-5.4-mini reader, "
      "gpt-4.1-mini and mistral_ocr tie on B.2 exact (0.590) and Mistral is higher on ANLS "
      "(0.920 vs 0.878).")
    w("- **Output-token truncation caveat (Tier C).** Dense form pages truncate at the 4096-token "
      "cap (52% of Tier-C pages for gpt-4.1-mini vs 2–9% on prose), so API Tier-C scores partly "
      "reflect truncation; resolving the cap is an open owner decision.")
    w("")
    w("## Reproducibility")
    w("")
    w("| run | models | rendered from | generated |")
    w("|---|---|---|---|")
    for rid, meta in data["run_meta"].items():
        w(f"| `{rid}` | {len(meta['models'])} | {meta['source']} | {meta.get('generated_at') or '?'} |")
    w("")
    w("Bench datasets (pinned): " + " · ".join(
        f"`{b}` = {bm['hf_repo']}@{bm['revision']} ({bm['license']})"
        for b, bm in data["bench_meta"].items() if bm.get("hf_repo")) + ".")
    w("")
    w("_Every populated cell traces to its run's `manifest.json` (model fingerprint, bench "
      "revision, scorer identity, seeds, hardware). Regenerate this file with "
      "`uv run gauntlet leaderboard`._")
    w("")
    return "\n".join(out)
