# Dashboard UI polish — design spec (C3a v2)

**Status:** approved (functional design); branding now specified below (owner provided the AC brand
system at `~/dev/projects/ac-brand`). Builds on the shipped read-only dashboard `gauntlet ui`
(spec `2026-07-09-dashboard-ui-design.md`).

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

- No write actions, no config editing, no model runs (that is C3b, owner-gated).
- No new framework, build step, or runtime *code* dependency (see Approach). The only network fetch is
  brand webfonts via `<link>`, which degrade gracefully to system fallbacks offline.
- No multi-run comparison this pass (single-run selector stays).

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
- **Heatmap (on-brand, not a rainbow):** accuracy cells scale per column in **navy-ramp intensity**
  (monochrome depth, staying inside the Deep Space palette) so leaders read without introducing hues;
  the **column leader** gets a gold accent (achievement, used sparingly); a `warning` SVG icon marks
  fragile-on-scans (retained < ~40%). Never multi-hue — "colorful" is off-brand.
- **Value frontier:** compute the Pareto-optimal set over (quality, $/1k, speed); mark with a
  terracotta indicator (primary/selection). Pure frontend from the joined payloads.
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

- **Ledger, not a card grid.** The current same-size-card grid is a banned cliché; restructure as a
  ledger/table of benchmarks (tier, unit, provenance, license, scorer, count) with a small thumbnail
  strip per row where the license permits. One benchmark per row reads as intentional, not template.
- **Remove the synchronous preview decode** that makes the page slow: render the ledger immediately
  from `/api/benchmarks` metadata, lazy-load thumbnails after paint (the `<img loading>` is already
  lazy; the blocker is server-side count/decoding — cache sample counts on disk keyed by
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

## Branding — AC brand system (product register)

Source: `~/dev/projects/ac-brand`. A dashboard is a **product-register** surface: restrained color,
predictable grids, the tool disappears into the task. Copy the needed static assets into
`src/tbdoc/ui/static/` so the app stays self-contained.

- **Tokens:** vendor `ac-brand/assets/tokens/tokens.css` into the static dir and drive the whole app
  from `--ac-*` variables (the app already centralizes color in `:root`). No hard-coded hex.
- **Palette discipline:** navy `#0B1E36` + cream `#F4EFE6` dominate (~80%); terracotta `#D4745E` for
  primary actions, selection, focus, and the value frontier only; sage and gold season (~10%). Never
  pure black/white. Introduce no new hues.
- **Status colors (map onto our semantics):** sage = healthy/live (e.g. a clean cell, "0 errors");
  gold = achievement (column leader, best-in-class); terracotta = primary/action/selected;
  `--ac-danger` = error rows/flags only.
- **Type:** Space Grotesk (`--ac-font-display`) for view titles/headings ≥18px; Inter
  (`--ac-font-ui`) for controls/body; **JetBrains Mono (`--ac-font-mono`) for all tabular numbers,
  scores, timestamps, revisions**. Load via one Google Fonts `<link>` with the existing system stack
  as fallback (graceful offline). Table header labels: small uppercase tracked Inter.
- **Icons:** one small inline-SVG icon set (single family, fixed viewBox) for ✓/✗/warning/info/
  external-link/frontier. **No emoji as icons.**
- **Interaction states (mandatory on every control):** default, hover (color/border/shadow only, no
  layout-shifting scale), focus-visible (2px terracotta outline, offset 2), active, disabled (45%
  opacity, `not-allowed`), loading (disable + inline spinner + `aria-busy`). Interactive table rows
  hover to `--ac-surface-alt`.
- **Theme:** auto-follows-OS by default via `prefers-color-scheme`, resolved before first paint with a
  tiny inline `<head>` snippet (no flash), live-responds to OS changes while in auto; an unobtrusive
  auto→light→dark cycle control in the top bar; persist only explicit choices. Both themes fully
  styled (tokens already provide `deepspace`/`cosmic`). The sticky header may use the glass token;
  content panels stay solid.
- **Motion:** product-surface discipline — 150–250ms, state-conveying only, no entrance
  choreography; honor `prefers-reduced-motion`.
- **Logo (two-logo rule):** trial-by-doc keeps its wordmark in the header (the product slot); Ashwin's
  Orbit AC monogram is demoted to a small "Built by Ashwin Chidambaram" footer byline (inline the
  `monogram-*.svg`, theme-appropriate). The product mark and the personal mark never share a slot.
- **Anti-patterns to avoid (from `guidelines/06-patterns.md`):** no rainbow heatmaps, no side-stripe
  accents (use background shifts / leading dot / full borders), no identical-card grids (the
  benchmarks explorer becomes a ledger/table, not repeated cards), no hero-metric stat cards, no
  gradient text, no em dashes in UI copy, modals only as last resort (prefer inline — image zoom is an
  inline expand, not a modal-first flow).
- **Voice:** plain, warm, technically precise. Clarity over cleverness.

Aesthetics apply *on top of* the functional structure above; where a brand rule and a functional
choice conflict, the brand rule wins on presentation, the functional requirement wins on behavior.

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
  (side-by-side + rendered markdown + highlighting + triage + inline zoom), verify popover, benches
  ledger, theme system, branded per the AC tokens.
- `src/tbdoc/ui/static/ac-tokens.css` + `src/tbdoc/ui/static/monogram-*.svg` — vendored from
  `~/dev/projects/ac-brand` (keeps the app self-contained; record provenance in a header comment).
- `tests/test_ui_routes.py` — new endpoint + triage + security regression coverage.

## Post-build deliverables (owner request)

- High-resolution screenshots of every view (leaderboard/cockpit, workbench, benchmarks) in both
  themes for owner review.
- Add selected UI screenshots to the README. Evaluate whether the data visualizations (tradeoff
  scatter, robustness curve) are better shown as a static generated image embedded in the README or
  linked from the live dashboard; recommend and apply.
