# C3a — read-only results dashboard UI (`gauntlet ui`)

**Date:** 2026-07-09
**Status:** approved scope; building C3a now. C3b (below) is explicitly deferred/owner-gated.

## 1. Goal

`uv run gauntlet ui` starts a local, read-only FastAPI server (default `127.0.0.1:8000`) serving a
self-contained frontend (single static HTML page + vanilla JS, no npm/webpack build step) that lets
the owner browse the existing `results/runs/<id>/` output: the leaderboard, the benchmark/dataset
catalog, and a per-example "extracted markdown vs ground truth" review view.

This is purely a viewer over data the harness already produced. It does not run models, call APIs,
touch GPU, or write anything under `results/`. It imports and reuses the same bench loaders
(`src/tbdoc/benches/**`) and scoreboard collectors (`src/tbdoc/report/scoreboard.py`) that scored the
run, so the UI's page image + gold + scores are guaranteed to match what was actually measured — no
re-implementation of gold parsing or metric math.

## 2. Scope

**In scope (C3a, this build):**
- Leaderboard view — the scoreboard matrix (model × bench primary means), per-tier/per-category
  toggle, provenance + license labels, sortable, linking each cell into the per-example view.
- Benchmark & dataset explorer — one card per bench (what it tests, tier, provenance, license, sample
  count) with a small **license-gated** example-image gallery.
- Per-example review — pick (run, model, bench, sample) → page image on the left; the model's
  extracted markdown vs. ground truth + the score record on the right. This is the centerpiece.
- A `gauntlet ui` CLI command (`--run-id`, `--host`, `--port`, `--no-browser`).

**Out of scope / deferred to C3b (owner-gated, later — NOT built here):**
- Any interactive config UI (editing `configs/*.yaml`, launching new runs from the browser).
- A per-model system-prompt editor.
- Any write path back into `results/`, `configs/`, or model adapters.
- Auth / multi-user / remote hosting — this is a localhost-only dev tool.

## 3. Data contracts (read, not re-derived)

- `results/runs/<id>/scoreboard.csv` — derived leaderboard CSV (informational only; the UI recomputes
  the same numbers live from the JSONL source of truth via `CheckpointStore`, exactly like
  `report/scoreboard.py` does, so a UI page reload always reflects the freshest scored rows even while
  a run is still writing).
- `results/runs/<id>/raw/<model>/<bench>.jsonl` — one record per scored sample: `sample_id`,
  `category`, `metrics` (`primary` + tier-specific fields — Tier A: `overall_edit_dist`/`pass_rate`
  components; Tier B: `b1`/`b2`/`extractive`/`reader`/`answer`; Tier C: `pq`/`boundary_f1`/`method`),
  `telemetry`, `error`, `model_revision`. Source of truth (`CheckpointStore`, append-only, last record
  per sample id wins on `--rescore`).
- `results/runs/<id>/predictions/<model>/<bench>.jsonl` — one record per sample: `sample_id`, `kind`
  (`structured_doc` | `page_docs` | `segmentation` | `error`), `prediction` (a `StructuredDoc`-shaped
  dict with `.markdown`, or a list of them for `page_docs`, or `{"boundaries": [...]}`-shaped for
  `segmentation`).
- `results/runs/<id>/manifest.json` — run provenance (models, benches, instruments, hardware, harness
  git SHA).
- `configs/benchmarks.yaml` / `configs/models.yaml` via `Registry("configs")` — tier/provenance/
  license/specialty metadata.
- Benchmark gold: each bench's own data dir, read **through the bench's own `BenchAdapter.load()`**
  wherever `Sample.gold` is populated (RealDoc-QA family: `sample.gold` = list of accepted answers,
  `sample.question`; merged_forms: `sample.gold` = boundary indices). Two Tier-A benches
  (omnidocbench, olmocr_bench) score against gold that lives *inside the official scorer's own data
  files*, not as a `Sample.gold` value — see §4.3 for how the UI still surfaces a human-readable gold
  view for those without reimplementing the official scorer.

## 4. Backend design (`src/tbdoc/ui/`, new package)

### 4.1 Module layout
- `src/tbdoc/ui/app.py` — `create_app(results_dir="results/runs", config_dir="configs") -> FastAPI`.
  Mounts the JSON API under `/api/*` and serves `src/tbdoc/ui/static/index.html` (+ same-dir CSS/JS)
  at `/`. No database; every request reads the filesystem directly (results are small — 10s–100s of
  JSONL rows per cell — so no caching layer is needed for a local dev tool; the one exception is a
  small in-process LRU over "which bench adapter instance is loaded" to avoid re-importing/re-parsing
  YAML on every request).
- `src/tbdoc/ui/runs.py` — `list_runs(results_dir)`, `resolve_run(results_dir, run_id|None)` (defaults
  to the most-recently-modified directory under `results_dir` — NOTE this deliberately does **not**
  reuse `cli.py`'s existing `_latest_run()`, which globs `run_*` and would silently return nothing for
  every run in this repo, none of which are named `run_*` (`v1-baseline`, `gate1`, `smoke-a2`, ...);
  see §7 brief-contradiction).
- `src/tbdoc/ui/data.py` — read-only data access: scoreboard rows (reuses
  `tbdoc.report.scoreboard._collect` + `CheckpointStore` directly — same source of truth as `gauntlet
  scoreboard`), per-category breakdowns, per-bench sample counts, prediction/raw record lookup by
  `(model, bench, sample_id)`.
- `src/tbdoc/ui/gold.py` — the per-example "ground truth view" join (§4.3): given a bench key and
  `sample_id`, returns a bench-appropriate gold rendering by calling the SAME `BenchAdapter.load()`
  used at scoring time (imported from `src/tbdoc/benches/**` via the `Registry`), plus, only for the
  two benches whose gold isn't on `Sample.gold`, a light read of that bench's own already-downloaded
  data file (never the official scorer subprocess — read-only, no re-scoring).

### 4.2 Routes

- `GET /api/runs` → `[{"run_id", "mtime", "models": [...], "benches": [...]}]` for every dir under
  `results/runs/` that has a `raw/` subdirectory (skips stray/empty dirs).
- `GET /api/scoreboard?run_id=` → `{"models": [...], "benches": [...], "cells": {"model|bench":
  {"mean": float|null, "n": int}}, "categories": {...}, "bench_meta": {bench: {tier, provenance,
  license, unit}}}` — built from `tbdoc.report.scoreboard._collect(run_dir)` (identical numbers to
  `gauntlet scoreboard`), joined with `Registry.benchmarks` for tier/provenance/license labels.
- `GET /api/benchmarks` → one entry per registered bench: `{key, tier, unit, provenance, license,
  revision, sample_count, description, gallery_allowed}`. `sample_count` = count from
  `BenchAdapter.load()` capped at a small preview limit for speed on the 1651-page benches (full count
  reported separately as `total_hint` from `benchmarks.yaml`/known dataset size where cheap; otherwise
  the capped count is labeled `~`). `gallery_allowed` = license is on a redistribution allowlist
  (`odc-by`, `cc-by-4.0`, `cc0`, `mit`, `apache-2.0`, `public-domain`); anything `unspecified` or
  absent is **not** allowed — matches the brief's "if unsure, don't expose the image, metadata only."
- `GET /api/benchmarks/{bench}/gallery?n=6` → license-gated only: `403` with `{"reason": "license
  <value> not on the redistribution allowlist"}` if `gallery_allowed` is false; else up to `n`
  `{sample_id, category, thumbnail_url}` where `thumbnail_url` points at `/api/page-image`.
- `GET /api/example?run_id=&model=&bench=&sample_id=` → the per-example join: `{sample_id, model,
  bench, category, tier, image_url, prediction: {kind, markdown|boundaries|...}, gold: {kind, ...},
  metrics, telemetry, error, license, provenance}`. `image_url` always points at `/api/page-image`
  (unrestricted here — this is the core review feature working over the owner's own already-scored
  local run, not a public gallery; see §7 on the one place this reads more permissively than the
  explorer gallery, which the brief itself scopes the license gate to).
- `GET /api/page-image?run_id=&bench=&sample_id=&page=0` → `image/png`, rendered by calling the SAME
  bench's `load()` (or, for PDF-backed benches, the same `_render_pdf` helper) and breaking out of the
  generator as soon as the matching `sample_id` is found (cheap for the 30–300-sample cells this run
  has; documented as a known cost if ever pointed at a full 1651-page bench with a late-order sample).

### 4.3 The Tier-A gold gap, and how the UI closes it without touching the scorer

`omnidocbench` and `olmocr_bench` both score via an OUT-OF-PROCESS official scorer that reads gold
directly off disk (`OmniDocBench.json`, `bench_data/<category>.jsonl`); `Sample.gold` is `None` for
both (`src/tbdoc/benches/official/omnidocbench.py:57`, `olmocr_bench.py:50`) — there is nothing to
show by construction. Reimplementing the official scorer's exact rendering is out of scope (it would
duplicate scored-and-frozen logic). Instead, `ui/gold.py` does a **read-only, best-effort
reconstruction for human review only** (never fed back into scoring):
- **omnidocbench** — reads the same `OmniDocBench.json` the adapter reads, finds the page entry by
  `image_path` basename, and joins non-ignored `layout_dets[*].text` in `order` — a rough
  reading-order transcript. Tagged `"kind": "page_annotation"` with an explicit
  `"note": "approximate reconstruction from layout_dets order; not the exact official scorer input"`.
- **olmocr_bench** — reads `bench_data/<category>.jsonl`, filters rows whose `pdf` basename matches
  `sample_id`, and returns the list of unit-test assertions (`type`, `math`/`text`, `max_diffs`) —
  tagged `"kind": "unit_tests"`. Cross-referenced against the raw record's `metrics.fails` so each
  assertion in the UI gets a pass/fail badge — this is the *actual* signal the official scorer
  produced, just re-displayed per-test instead of only as an aggregate pass rate.
- **realdoc_qa / realdoc_qa_scanned_light / realdoc_qa_scanned_heavy** — `sample.gold` (list of
  accepted answers) + `sample.question`, used directly. `"kind": "qa"`.
- **merged_forms** — `sample.gold` (0-based boundary indices) + `len(sample.pages)`. `"kind":
  "segmentation"`. The model's *predicted* boundaries are not persisted to `raw/predictions` (only
  aggregate PQ/F1 are), so the UI shows the model's per-page markdown stream next to the gold
  boundaries and the aggregate segmentation metrics, not a predicted-vs-gold boundary diff — noted in
  the API response (`"predicted_boundaries": null, "note": "not persisted; see metrics for aggregate
  PQ/F1"`).

### 4.4 Dependencies

`fastapi` + `uvicorn` added as a new `ui` extra in `pyproject.toml` (both already resolvable in the
project's `.venv` — verified 2026-07-09: fastapi 0.136.3, uvicorn 0.50.2). No other new dependencies;
no npm, no bundler.

## 5. Frontend (`src/tbdoc/ui/static/`)

One self-contained `index.html` (inline `<style>` + `<script>`, no build step), hash-routed between
three views, all driven by `fetch()` against `/api/*`:

1. **Leaderboard** (`#/`) — scoreboard table, columns sortable by click, a tier/category toggle, a
   provenance/license badge per bench column header, each cell links to `#/example?...` pre-filled
   with that (model, bench) and its first sample.
2. **Explorer** (`#/benches`) — a card per bench (tier, provenance, license, sample count,
   description) + a gallery strip that calls the gallery endpoint and renders either thumbnails or a
   "gated — license unspecified" placeholder.
3. **Example review** (`#/example`) — four selects (run, model, bench, sample) driving
   `/api/example`; left pane = page image; right pane = extracted markdown (rendered as preformatted
   text, not full markdown rendering, to avoid any risk of HTML injection from model output) side by
   side with the gold view, a metrics table, and, for `qa`/`unit_tests` gold kinds, a per-field/
   per-test right/wrong badge row.

## 6. Verification plan

- `uv run gauntlet ui --no-browser --port 8000`, then `curl` against run-id `v1-baseline`:
  `/api/runs` lists it; `/api/scoreboard?run_id=v1-baseline` has 14 models; `/api/example` for a real
  (model, bench, sample_id) triple returns non-empty `prediction.markdown` + a non-null `gold`;
  `/api/page-image` returns real PNG bytes (`file` / magic-byte check). Server killed by PID afterward
  — never left running, never bound to `0.0.0.0`.
- `uv run --extra dev pytest -q` — route tests via FastAPI's `TestClient` against the real
  `results/runs/v1-baseline` fixture (read-only; the large concurrent Part-D run writing into
  `results/runs/v1-baseline` is never modified or deleted by this UI or its tests).

## 7. Brief-contradictions found while implementing

- `cli.py`'s existing `_latest_run()` helper (used by `gauntlet scoreboard`/`status`) globs `run_*`,
  which matches none of this repo's actual run directories (`v1-baseline`, `gate1`, `smoke-*`, ...).
  It is unrelated pre-existing code and out of scope to fix (measurement-path CLI, not part of this
  UI's scope) — the UI implements its own `resolve_run()` (mtime-based) rather than depending on it.
- The brief's route sketch lists `image_url` gating ("license-gated — only serve images...") under
  `/api/benchmarks`; the per-example review route (`/api/example` / `/api/page-image`) is listed
  separately with no gating language, and gating the core review feature by dataset license would make
  it non-functional for `omnidocbench` (`license: unspecified`) despite that data already being
  present, downloaded, and scored locally by the owner's own run. Read literally, the brief only asks
  for gating on the explorer's example gallery; that is what §4.2/§4.3 implement.
