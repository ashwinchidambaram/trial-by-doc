# Dashboard UI polish — design spec (C3a v2)

**Status:** approved (functional design); aesthetics/branding explicitly deferred to a later
styling layer (owner brand guidelines incoming). Builds on the shipped read-only dashboard
`gauntlet ui` (spec `2026-07-09-dashboard-ui-design.md`).

**Owner steer:** "imagine you're a user — make it as easy as possible to use, and show what you'd
want to see when reviewing results. Vet function/UX before aesthetics." This spec is the vetted
functional design; a follow-up brand pass restyles on top of it.

## Problem

The harness *measures* five things per model — accuracy (per tier), latency, VRAM, $/page,
scan-robustness — but the dashboard surfaces only the first. `render_perf` / `render_tier_b` /
`render_cost` and the Part-D scanned records exist in the report layer and the README, but the UI's
data API never exposes them. So the dashboard cannot answer the harness's own headline question,
*"which model should I trust / which is best value?"* Secondary gaps: no model comparison on a shared
document, raw-text markdown (not rendered), no right/wrong evidence, no failure triage, no provenance,
invisible errors, a flat un-scannable grid, and a slow benchmarks page.

## Goals

Serve three jobs, ranked, in one tool:
1. **Decide** (landing) — compare all models across accuracy + speed + cost + robustness; make the
   value tradeoff obvious.
2. **Diagnose** (one click from any number) — per-example review with side-by-side models, rendered
   markdown, right/wrong highlighting, failure triage.
3. **Verify** (woven through both) — every number links to its evidence; provenance and errors are
   always visible. Not a separate tab.

## Non-goals

- **Aesthetics / branding** — colors, type, spacing, logo. Deferred to a styling layer that consumes
  the CSS-variable seams this design preserves. Do not hand-tune visual design in this pass.
- No write actions, no config editing, no model runs (that is C3b, owner-gated).
- No new framework, build step, or runtime dependency (see Approach).

## Approach — enhance in place (vanilla, self-contained)

Keep the current architecture: FastAPI backend + **one self-contained `static/index.html`** (vanilla
JS, no build, no CDN, localhost-only). New visuals are hand-rolled: heatmap = CSS; scatter and
robustness curves = inline SVG (~40–60 lines each); markdown rendering = a small inline renderer
(headings, tables, lists, code — enough to judge document parse quality, not a full CommonMark impl).
Rationale: preserves the zero-dependency "clone it and run it" character; matches the existing spec;
lowest review/maintenance surface for a single-user local tool.

**Theming seam:** all color/spacing stays in `:root` CSS variables (already the pattern). The brand
pass will re-map those variables and add a stylesheet; component structure/classes are stable so it
needs no markup changes.

## Data contracts — new read-only endpoints

All reuse the report layer's existing collectors so numbers stay identical to `gauntlet scoreboard`;
no metric math is re-derived in the UI. All are `GET`, run-scoped, and inherit the existing
`_safe_seg` path-guard + localhost binding.

- `GET /api/perf?run_id=` → `[{model, median_s, mean_s, p90_s, peak_vram_gb, cost_per_page_usd, n}]`
  — wraps `report.scoreboard._perf` (already scanned-excluded).
- `GET /api/tier-b?run_id=` → `[{model, b1, coverage:{extractive,total}, b2, reader}]` — wraps
  `_collect_tier_b`.
- `GET /api/cost` → `{classic:[{engine,device,sku,pages_hr,usd_per_1k}], self_host:[{model,sku,
  usd_per_1k_single,usd_per_1k_batched}]}`. **All cost data consolidates into one new module
  `src/tbdoc/report/cost_tables.py`** holding both the classic-engine throughput/SKU map (moved from
  `scoreboard.py`) and the per-model self-host figures (promoted from the README's hand-authored
  Azure table into code). `render_cost`, the README Azure-table render, and this endpoint all read
  from that single source — so per-model cost has one code source of truth and the last
  hand-maintained README table becomes code-generated.
- `GET /api/robustness?run_id=` → `[{model, clean, light, heavy, retained_pct}]` — clean B.1 from the
  core `realdoc_qa` cell; light/heavy from the `realdoc_qa_scanned_*` cells (raw records). Matches
  `findings/partd-scanned-robustness.md`.
- `GET /api/samples` **extended** → `{sample_ids:[...], scored:[{sample_id, primary, error}]}` — adds
  each sample's primary score + error flag so the workbench can sort worst-first and filter failures.
  Back-compat: keep `sample_ids` for existing callers.

A `GET /api/provenance?run_id=` → `manifest.json` subset (hardware, seeds, config hashes, git SHA,
per-model revisions) powers the verify popover (or fold into `/api/runs`).

## Surface 1 — Decision Cockpit (landing, `#/`)

One row per model; columns = accuracy per bench (heatmap) + `median s/page` + `peak VRAM` +
`$/1k pages` + `heavy-retained %`. Behaviors:
- **Heatmap:** accuracy cells background-scaled per column (best→worst) via CSS; perf/cost/robustness
  as plain values with a ⚠ marker on fragile-on-scans (retained < ~40%).
- **Value frontier:** compute the Pareto-optimal set over (quality, $/1k, speed); mark with ★. Pure
  frontend from the joined payloads.
- **Tradeoff scatter:** inline SVG, accuracy↔cost (toggle to accuracy↔speed), one dot per model,
  frontier drawn as a line; hover shows the model; click a dot → filter/scroll the table to it.
- **Controls:** model search box; tier filters (A/B/C); a toggle to hide perf/cost columns for an
  accuracy-only view.
- **Sort:** any column asc/desc (existing behavior, extended to the new columns).
- **Evidence:** every accuracy cell click-throughs to the workbench (existing `openExample`).
- **Verify inline:** run selector shows `hardware · seed · git-sha` summary with a `verify ⓘ` popover
  (`/api/provenance`); cells with error rows get an error marker linking to those samples.

## Surface 2 — Diagnose Workbench (`#/example`)

Left: page image (click to zoom via a lightbox overlay). Right: **N model panels side-by-side** on the
same sample (default 2, `[+ model]` up to 3, `[×]` to remove). Each panel:
- header: model name + its primary/B.1 score with ✓/✗;
- **markdown toggle** `[rendered | raw]` — rendered uses the inline renderer (tables/headings/lists);
- **right/wrong highlighting:** for Tier-B, highlight the gold value where present in the markdown, or
  a "gold value MISSING" flag; for Tier-A, the existing ✓/✗ unit-test list; for Tier-C, existing
  boundary summary.
- **Sample triage bar:** the sample selector becomes a sorted/filterable list from the extended
  `/api/samples` — `worst-first` / `best-first` / `file order`, a `☐ failures only` filter, and
  `◀ prev / next ▶` to walk the current list.
- **Score row** (verify): b1/b2/reader identity/latency/model revision inline.

Comparison state (models chosen) is encoded in the hash so a diagnosis view is shareable/bookmarkable.

## Benchmarks explorer (`#/benches`) — fix + enrich

- **Remove the synchronous preview decode** that makes the page slow: render cards immediately from
  `/api/benchmarks` metadata, lazy-load gallery thumbnails per card after paint (the `<img loading>`
  is already lazy; the blocker is server-side count/decoding — cache sample counts on disk keyed by
  bench+config hash, computed once).
- **Robustness drill-down:** the cockpit's heavy-retained % is clickable → a small inline
  clean→light→heavy curve (SVG) for that model (from `/api/robustness`). No new tab.

## Testing

Extend `tests/test_ui_routes.py` (FastAPI `TestClient` over the real `v1-baseline`):
- each new endpoint returns real, non-empty data for `v1-baseline` and matches the report layer
  (e.g. `/api/perf` medians equal `render_perf`; `/api/robustness` retained% matches the findings);
- extended `/api/samples` `scored` list is present and sortable; worst-first ordering is correct;
- **regression-protect security:** path-traversal on `model`/`bench` still 400s on every new route
  that takes them; localhost-bind guard unchanged.
- Frontend logic (Pareto-frontier computation, markdown-render of a table) stays in small pure JS
  functions. The repo is Python-only (pytest) and this pass adds **no JS test runner** (keeps the
  zero-dep character), so those functions are validated by a documented manual smoke against
  `v1-baseline`, not an automated JS suite. Automated coverage lives at the API/contract layer, which
  is where the numbers that matter are produced.

## Deferred (explicit)

- Brand/aesthetic styling pass (own follow-up; consumes the CSS-variable seams).
- C3b interactive config / system-prompt editor (owner-gated).
- Static shareable "decision report" export (Approach C idea) — not now.
- Multi-run comparison (compare two run-ids) — future; the run selector stays single-run this pass.

## Files (anticipated)

- `src/tbdoc/ui/data.py` — add `perf_payload`, `tier_b_payload`, `cost_payload`, `robustness_payload`,
  extend `sample_ids` → scored; `provenance_payload`.
- `src/tbdoc/ui/app.py` — add the new routes (guarded like existing ones).
- `src/tbdoc/report/cost_tables.py` (new) — per-model self-host cost as code; consumed by the UI cost
  endpoint and the README Azure-table render.
- `src/tbdoc/ui/static/index.html` — cockpit (heatmap + scatter + frontier + controls), workbench
  (side-by-side + rendered markdown + highlighting + triage + zoom), verify popover, benches fix.
- `tests/test_ui_routes.py` — new endpoint + triage + security regression coverage.
