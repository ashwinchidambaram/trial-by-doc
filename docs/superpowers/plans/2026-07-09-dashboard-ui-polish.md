# Dashboard UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the read-only `gauntlet ui` dashboard into a decision/diagnose/verify tool that surfaces every dimension the harness measures (accuracy + speed + cost + robustness), styled with the AC brand system.

**Architecture:** Backend stays FastAPI over the scored run dir; add thin read-only endpoints that reuse the report layer so numbers match `gauntlet scoreboard`. Frontend stays a single self-contained `static/index.html` (vanilla JS, no build) — enhanced with a decision cockpit, a diagnose workbench, verify affordances, an AC-branded theme system, and hand-rolled SVG visuals. Cost data consolidates into one code module consumed by the UI, `render_cost`, and the README.

**Tech Stack:** Python 3.12, FastAPI, pytest (`uv run --extra dev pytest`); vanilla HTML/CSS/JS; AC brand tokens (`~/dev/projects/ac-brand`); Playwright (already available as an MCP server) for end-to-end drive.

## Global Constraints

- Self-contained frontend: one `index.html`, no build step, no runtime code deps, no CDN **except** brand webfonts via `<link>` with graceful system fallback. Vendor brand assets into `static/`.
- Numbers must equal `gauntlet scoreboard`: reuse `report.scoreboard` collectors, never re-derive metric math in the UI.
- Localhost-only (127.0.0.1); every route taking `model`/`bench` uses the existing `_safe_seg` path guard.
- Palette discipline: navy `#0B1E36` + cream `#F4EFE6` dominate (~80%); terracotta `#D4745E` for primary/selection/focus/frontier only; sage = healthy/live, gold = achievement/leader, `--ac-danger` = errors only. No new hues, no pure black/white.
- Type: Space Grotesk (headings ≥18px), Inter (UI), JetBrains Mono (all tabular data/scores/timestamps/revisions).
- Focus-visible = 2px terracotta outline offset 2. Every control has default/hover/focus/active/disabled/loading. Motion 150–250ms, `prefers-reduced-motion` honored.
- Theme: auto (prefers-color-scheme) default, resolved before first paint (inline head snippet), auto→light→dark cycle control; persist only explicit choices.
- Banned in UI: rainbow heatmaps, side-stripe accents, identical-card grids, hero-metric stat cards, gradient text, em dashes in UI copy, emoji-as-icons (use inline SVG icon set), modal-first flows (image zoom is inline expand).
- All new hex/spacing via `--ac-*` tokens; no hard-coded values in component CSS.

---

## File Structure

- `src/tbdoc/report/cost_tables.py` (new) — single source of truth for cost data: classic-engine throughput/SKU map + per-model self-host figures. Consumed by `render_cost`, the README render, and the UI cost endpoint.
- `src/tbdoc/ui/data.py` (modify) — `perf_payload`, `tier_b_payload`, `cost_payload`, `robustness_payload`, `provenance_payload`; extend `sample_ids` → also return scored list.
- `src/tbdoc/ui/app.py` (modify) — routes `/api/perf`, `/api/tier-b`, `/api/cost`, `/api/robustness`, `/api/provenance`; extend `/api/samples`.
- `src/tbdoc/ui/static/ac-tokens.css` (new, vendored) — copy of `ac-brand/assets/tokens/tokens.css` + provenance header.
- `src/tbdoc/ui/static/ac-monogram-dark.svg`, `ac-monogram-light.svg` (new, vendored) — footer byline mark.
- `src/tbdoc/ui/static/index.html` (rewrite) — shell/theme/nav, cockpit, workbench, benches ledger, verify, icons.
- `tests/test_ui_routes.py` (modify) — endpoint + triage + security-regression coverage.
- `tests/test_cost_tables.py` (new) — cost-data arithmetic + shape.
- `scratchpad/drive_ui.py` (new, throwaway) — Playwright end-to-end drive + screenshot capture.

---

## Task 1: Consolidate cost data into `cost_tables.py`

**Files:**
- Create: `src/tbdoc/report/cost_tables.py`
- Create: `tests/test_cost_tables.py`
- Modify: `src/tbdoc/report/scoreboard.py` (`render_cost` reads from the new module)

**Interfaces:**
- Produces: `CLASSIC_ENGINES: dict[str, dict]` (per engine: `cpu_pages_hr`, `gpu_pages_hr`), `CPU_VM`/`GPU_VM` SKU dicts (`sku`, `usd_per_hr`, `source`), `SELF_HOST: list[dict]` (per model: `model`, `sku`, `usd_per_1k_single`, `usd_per_1k_batched`), `PRICING_AS_OF: str`; helpers `classic_cost_rows() -> list[dict]` and `self_host_rows() -> list[dict]`.

- [ ] **Step 1: Write the failing test** — `tests/test_cost_tables.py`:
```python
from tbdoc.report import cost_tables as ct

def test_classic_cost_rows_arithmetic():
    rows = ct.classic_cost_rows()
    # tesseract CPU: 3006 pages/hr at the CPU-VM $/hr → $/1k = usd_per_hr/3006*1000
    tess = next(r for r in rows if r["engine"] == "tesseract" and r["device"] == "CPU-VM")
    assert abs(tess["usd_per_1k"] - ct.CPU_VM["usd_per_hr"] / 3006 * 1000) < 1e-6
    # docTR has both CPU and GPU rows; easyocr too
    devs = {(r["engine"], r["device"]) for r in rows}
    assert ("doctr", "GPU-VM") in devs and ("easyocr", "GPU-VM") in devs
    # tesseract/rapidocr are CPU-only (no GPU row)
    assert ("tesseract", "GPU-VM") not in devs and ("rapidocr", "GPU-VM") not in devs

def test_self_host_rows_present_for_vlms():
    rows = ct.self_host_rows()
    models = {r["model"] for r in rows}
    assert {"olmocr2", "qwen25vl", "deepseek_ocr"} <= models
    olmo = next(r for r in rows if r["model"] == "olmocr2")
    assert olmo["usd_per_1k_single"] > 0 and olmo["sku"]
```
- [ ] **Step 2: Run to verify it fails** — `uv run --extra dev pytest tests/test_cost_tables.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `cost_tables.py`** — move the constants currently in `scoreboard.py` (`_CLASSIC_ENGINE_THROUGHPUT`, the CPU/GPU SKU + `$/hr` + source + `_PRICING_AS_OF`) into this module as public names, and add `SELF_HOST` by transcribing the README "Azure AI Foundry Managed Compute" table (the 9 model rows: `paddleocr_vl,lightonocr,got2,granite_docling,dots_ocr,deepseek_ocr` on T4-16GB; `qwen25vl,olmocr2,gemma4` on A100-80GB, with their `$/1k single`/`$/1k batched` values verbatim from README lines ~189-198, `—` batched for got2/granite). Provide `classic_cost_rows()` (emit CPU row for every engine; GPU row where `gpu_pages_hr` is not None; `usd_per_1k = vm_usd_per_hr / pages_hr * 1000`) and `self_host_rows()` (return `SELF_HOST`). Include a module docstring citing `findings/ws1-cpu-engines.md` and the README verified-date/source for each price.
- [ ] **Step 4: Refactor `scoreboard.py render_cost`** to build its markdown from `cost_tables.classic_cost_rows()` (delete the local duplicated constants; keep the identical caveat/footnote text and the `below` fix). Verify the README block is byte-identical after `uv run gauntlet scoreboard --run-id v1-baseline --readme-inject` (only intended: none — output unchanged).
- [ ] **Step 5: Run tests** — `uv run --extra dev pytest tests/test_cost_tables.py tests/test_scoreboard_cost.py -q` → PASS. Then re-inject and `git diff README.md` shows no change.
- [ ] **Step 6: Commit** — `git add src/tbdoc/report/cost_tables.py tests/test_cost_tables.py src/tbdoc/report/scoreboard.py && git commit`.

---

## Task 2: UI data endpoints (perf / tier-b / cost / robustness / provenance / scored samples)

**Files:**
- Modify: `src/tbdoc/ui/data.py`
- Modify: `src/tbdoc/ui/app.py`
- Modify: `tests/test_ui_routes.py`

**Interfaces:**
- Consumes: `report.scoreboard._perf`, `_collect_tier_b`, `_collect` (existing); `cost_tables.classic_cost_rows/self_host_rows` (Task 1).
- Produces (data.py): `perf_payload(run_dir) -> list[dict]`; `tier_b_payload(run_dir) -> list[dict]`; `cost_payload() -> dict`; `robustness_payload(run_dir) -> list[dict]`; `provenance_payload(run_dir) -> dict`; `scored_sample_ids(run_dir, model, bench, *, limit) -> list[dict]` (each `{sample_id, primary, error}`).
- Produces (app.py routes): `GET /api/perf|tier-b|cost|robustness|provenance`; `/api/samples` gains a `scored` key.

- [ ] **Step 1: Write failing tests** in `tests/test_ui_routes.py` (module already runs against real `v1-baseline`):
```python
def test_perf_endpoint_matches_report(client):
    body = client.get("/api/perf", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "olmocr2")
    assert row["median_s"] == 13.69 and row["peak_vram_gb"] == 28.8

def test_tier_b_endpoint_has_reader_and_coverage(client):
    body = client.get("/api/tier-b", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "olmocr2")
    assert row["b1"] == 0.689 and row["coverage"]["extractive"] == 90

def test_robustness_endpoint_curve(client):
    body = client.get("/api/robustness", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "tesseract")
    assert row["clean"] > row["light"] > row["heavy"]      # monotone degradation
    assert 0 <= row["retained_pct"] <= 100

def test_cost_endpoint_has_classic_and_self_host(client):
    body = client.get("/api/cost").json()
    assert any(r["engine"] == "tesseract" for r in body["classic"])
    assert any(r["model"] == "olmocr2" for r in body["self_host"])

def test_provenance_endpoint(client):
    body = client.get("/api/provenance", params={"run_id": "v1-baseline"}).json()
    assert "hardware" in body and "git_sha" in body

def test_samples_scored_sorts_worst_first(client):
    body = client.get("/api/samples", params={
        "run_id": "v1-baseline", "model": "tesseract", "bench": "realdoc_qa"}).json()
    scored = body["scored"]
    prims = [s["primary"] for s in scored if s["primary"] is not None]
    assert prims == sorted(prims)   # ascending = worst first (endpoint returns worst-first)

def test_new_routes_reject_traversal(client):
    for route in ["/api/samples"]:
        r = client.get(route, params={"run_id": "v1-baseline",
                                      "model": "../../etc", "bench": "x"})
        assert r.status_code == 400
```
- [ ] **Step 2: Run to verify failures** — `uv run --extra dev pytest tests/test_ui_routes.py -q -k "perf or tier_b or robustness or cost or provenance or scored or traversal"` → FAIL.
- [ ] **Step 3: Implement `data.py` payloads.** `perf_payload` = wrap `_perf(run_dir)` into `[{model, **fields}]`. `tier_b_payload` = wrap `_collect_tier_b`. `cost_payload` = `{"classic": classic_cost_rows(), "self_host": self_host_rows()}`. `robustness_payload` = for each model, clean = mean primary of `realdoc_qa` cell (from `_collect`), light/heavy = mean primary of `realdoc_qa_scanned_light/heavy` cells; `retained_pct = round(heavy/clean*100)` when clean>0 else None. `provenance_payload` = read `manifest.json`, return `{hardware, seeds, config_hashes, git_sha, models:{<m>:revision}}`. `scored_sample_ids` = read `raw/<model>/<bench>.jsonl`, last record per sample_id, return `[{sample_id, primary, error}]` sorted primary-ascending (None-last).
- [ ] **Step 4: Implement `app.py` routes** — five new `@app.get` handlers calling the payloads (perf/tier-b/robustness/provenance take `run_id` via `_safe_run_dir`; cost takes none); extend `api_samples` to also return `"scored": uidata.scored_sample_ids(...)` (keep `sample_ids` for back-compat), guarded by the existing `_safe_seg(model)/_safe_seg(bench)`.
- [ ] **Step 5: Run tests** — the `-k` subset then the full `tests/test_ui_routes.py` → PASS.
- [ ] **Step 6: Commit.**

---

## Task 3: Vendor AC brand assets into the static dir

**Files:**
- Create: `src/tbdoc/ui/static/ac-tokens.css`, `src/tbdoc/ui/static/ac-monogram-dark.svg`, `src/tbdoc/ui/static/ac-monogram-light.svg`
- Modify: `src/tbdoc/ui/app.py` (serve the static dir if not already; the app serves `index.html` via `_STATIC_DIR` — add a static mount or per-file routes for the css/svg)

**Interfaces:**
- Produces: `/ac-tokens.css`, `/ac-monogram-dark.svg`, `/ac-monogram-light.svg` served from `_STATIC_DIR`.

- [ ] **Step 1:** Copy files: `cp ~/dev/projects/ac-brand/assets/tokens/tokens.css src/tbdoc/ui/static/ac-tokens.css`; `cp ~/dev/projects/ac-brand/assets/logo/monogram-dark.svg src/tbdoc/ui/static/ac-monogram-dark.svg`; same for `monogram-light.svg`. Prepend a one-line provenance comment to the CSS (`/* vendored from ac-brand @ <short-sha>; do not edit here */`).
- [ ] **Step 2:** In `app.py`, mount static: `from fastapi.staticfiles import StaticFiles; app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")` OR add explicit `@app.get("/ac-tokens.css")` / `.svg` `FileResponse` routes (choose the mount; simpler). Keep `/` serving `index.html`.
- [ ] **Step 3:** Verify: start server, `curl -s localhost:8000/ac-tokens.css | head -1` shows the provenance comment; `curl -sI localhost:8000/ac-monogram-dark.svg` → `image/svg+xml`. Kill server by PID.
- [ ] **Step 4: Commit.**

---

## Task 4: Frontend rewrite — shell, theme system, and Decision Cockpit

**Files:** Rewrite `src/tbdoc/ui/static/index.html` (this task lands the shell + cockpit; Tasks 5–6 extend the same file sequentially).

Build against the Task-2 endpoints. Key implementation notes (concrete code for the hard parts):

- **Head/theme-before-paint** (no flash):
```html
<link rel="stylesheet" href="/ac-tokens.css">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script>
  (function () {
    var stored = localStorage.getItem("ac-theme");         // only explicit choices persisted
    var mode = stored || "auto";
    var dark = mode === "dark" || (mode === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "deepspace" : "cosmic");
    window.__acThemeMode = mode;
  })();
</script>
```
  Live-respond while in auto: `matchMedia("(prefers-color-scheme: dark)").addEventListener("change", ...)` re-applies when mode==="auto". Cycle control (auto→light→dark) in the top bar sets `data-theme`, persists only light/dark, clears the key for auto.
- **App CSS maps to AC tokens** — redefine the app's component variables from `--ac-*` (e.g. `--bg:var(--ac-bg); --panel:var(--ac-surface); --accent:var(--ac-accent); --text:var(--ac-text); --muted:var(--ac-text-sec); --good:var(--ac-secondary-text); --warn:var(--ac-highlight-text); --bad:var(--ac-danger)`), fonts from `--ac-font-*`, radius/space from `--ac-*`. Data cells/tables use `--ac-font-mono`; view titles use `--ac-font-display`.
- **Icon set** — define an inline `<svg><symbol>` sprite (check/x/warning/info/external/frontier/orbit), each `viewBox="0 0 16 16"`, referenced via `<svg class="icon"><use href="#i-check"/></svg>`. No emoji anywhere.
- **Cockpit heatmap (navy-ramp intensity, not rainbow):** per accuracy column, map the model's value between the column min/max to an intensity `t∈[0,1]`; set the cell background to a navy-tint via `background: color-mix(in srgb, var(--ac-surface) ${(1-t)*100}%, var(--ac-surface-alt))` (deeper = better), keeping text `--ac-text`. Crown the column max with a gold left-dot (`--ac-highlight-text`), not a fill. Mark value-frontier models with a terracotta dot in the model cell.
- **Pareto frontier** (pure JS): a model is on the frontier if no other model is ≥ on a chosen quality metric (default: mean of the accuracy columns) AND ≤ on `$/1k` AND ≤ on `median_s`. Compute once from the joined payloads.
- **Tradeoff scatter (inline SVG, ~50 lines):** axes = accuracy (y) vs `$/1k` (x, log-ish or clamped); one `<circle>` per model (terracotta for frontier, `--ac-text-ter` otherwise, gold for the single best-accuracy); frontier drawn as a `<polyline>`; a toggle swaps x to `median_s`. Hover sets a `<title>`; click scrolls the table to that model row.
- **Controls:** search `<input>` filters model rows (case-insensitive substring); tier filter chips (A/B/C) toggle which bench columns show; a "show speed/cost/robustness" checkbox toggles those columns. All controls carry the mandated interaction states (focus-visible terracotta outline).
- **Verify inline:** run selector shows `hardware · seed · git-sha` (from `/api/provenance`) with an info-icon button opening an inline popover (not a modal) listing hardware, seeds, config hashes, per-model revisions.
- Fetch `/api/scoreboard`, `/api/perf`, `/api/cost`, `/api/robustness` in parallel; join by model.

- [ ] **Step 1:** Rewrite `index.html` head + shell (header with wordmark, nav, run selector, theme cycle) + footer byline (inline monogram `<img src="/ac-monogram-dark.svg">` swapped by theme + two-line "Built by / Ashwin Chidambaram").
- [ ] **Step 2:** Implement the cockpit per the notes above.
- [ ] **Step 3:** Manual smoke: start server, load `#/`, confirm 14 rows, all columns populated, heatmap/frontier/scatter render, theme cycle works, no console errors (verified thoroughly in Task 7). Kill server.
- [ ] **Step 4:** Extend `tests/test_ui_routes.py` only if new endpoints were added here (none expected). Run full `pytest -q`.
- [ ] **Step 5: Commit** the cockpit.

---

## Task 5: Frontend — Diagnose workbench

**Files:** Modify `src/tbdoc/ui/static/index.html` (extends Task 4).

- **Layout:** left page-image panel (click to toggle an inline enlarged view, not a modal — expand the panel / open an inline overlay within `#app`); right = N model panels (default 2) side-by-side, `[+ model]` up to 3, `[x]` to remove; each panel header = model + primary/B.1 with a check/x icon.
- **Markdown toggle** per panel: `[rendered | raw]`. Rendered uses a small inline renderer covering headings (`#`), tables (`|`), lists (`-`/`1.`), bold/italic, code fences — enough to judge document parse quality; raw is the `<pre>` we already show.
- **Right/wrong highlighting:** for Tier-B (`gold.kind==="qa"`), wrap occurrences of each accepted gold value found in the prediction markdown in a sage highlight; if a value is absent, show a "value not found" chip in `--ac-danger`. For Tier-A (`unit_tests`) keep the existing ✓/✗ (now SVG icons). For Tier-C show the boundary summary.
- **Triage bar:** replace the plain sample dropdown with a list from `/api/samples` `scored`: a sort control (`worst first` / `best first` / `file order`), a `failures only` checkbox (primary===0 or error), and prev/next buttons that walk the current filtered list. Selecting updates the hash.
- **Score row** (verify): b1/b2/reader/latency/model_revision inline, mono font.
- Comparison state (models) encoded in the hash: `#/example?run_id=&bench=&sample_id=&models=a,b`.

- [ ] **Step 1:** Implement the triage bar (scored list, sort/filter/prev-next).
- [ ] **Step 2:** Implement N side-by-side panels + add/remove model + hash sync.
- [ ] **Step 3:** Implement the inline markdown renderer + raw/rendered toggle.
- [ ] **Step 4:** Implement gold-value highlighting (found → sage, missing → danger chip).
- [ ] **Step 5:** Implement inline image enlarge.
- [ ] **Step 6:** Manual smoke (full drive in Task 7). Run `pytest -q`. **Commit.**

---

## Task 6: Frontend — Benchmarks ledger + robustness drill-down + icon/copy polish

**Files:** Modify `src/tbdoc/ui/static/index.html`.

- **Benchmarks ledger:** replace the card grid with a table (one bench per row: name, tier badge, unit, provenance, license, scorer, count) + a small thumbnail strip cell where `gallery_allowed`, lazy-loaded after paint. Render immediately from metadata; do not block on thumbnails.
- **Robustness drill-down:** the cockpit heavy-retained % cell is clickable → an inline expander showing that model's clean→light→heavy curve as a small SVG sparkline (from `/api/robustness`). Inline, not a new route.
- **Polish pass:** replace any remaining emoji/unicode-symbol icons with the SVG set; remove em dashes from all UI copy (colons/commas/periods); confirm no side-stripe accents; confirm empty states have a display-font title + one hint + action; verify all controls have focus-visible/disabled/hover states.

- [ ] **Step 1:** Benchmarks ledger + lazy thumbnails.
- [ ] **Step 2:** Robustness drill-down sparkline.
- [ ] **Step 3:** Icon/copy/state audit and fixes.
- [ ] **Step 4:** `pytest -q`. **Commit.**

---

## Task 7: End-to-end drive with Playwright + high-res screenshots

**Files:** Create `scratchpad/drive_ui.py` (throwaway).

- [ ] **Step 1:** Start the server in the background: `uv run gauntlet ui --no-browser --port 8765` (localhost). Confirm up via `curl`.
- [ ] **Step 2:** Drive via the Playwright MCP tools (browser_navigate/click/snapshot/console): load `#/`; assert the leaderboard has 14 rows and the perf/cost/robustness columns are populated; toggle the theme cycle and assert `data-theme` flips with no console errors; click a cell → assert it lands on `#/example` with panels; in the workbench add a 2nd model, switch a panel to rendered markdown, toggle `failures only` and step next; open `#/benches` and assert the ledger renders and a thumbnail loads. Capture `browser_console_messages` after each view; **fail loudly on any console error**.
- [ ] **Step 3:** Capture high-res screenshots (deviceScaleFactor 2, wide viewport ~1600px) of each view in BOTH themes → `docs/ui/`: `cockpit-dark.png`, `cockpit-light.png`, `workbench-dark.png`, `benches-dark.png`, plus a `scatter`/`robustness` close-up.
- [ ] **Step 4:** Kill the server by PID. Fix any defect the drive surfaced (loop until clean). **Commit** screenshots under `docs/ui/`.

---

## Task 8: README — embed UI screenshots + decide on data-viz presentation

**Files:** Modify `README.md`; maybe add a generated static image.

- [ ] **Step 1:** Add a short "Dashboard (`gauntlet ui`)" section to the README with 1–2 embedded screenshots (cockpit + workbench) from `docs/ui/`, one line on how to launch it.
- [ ] **Step 2:** Decide data-viz presentation: the scatter/robustness are interactive in the live app; for the README, embed a static generated PNG of the robustness curve or the tradeoff scatter (rendered headless via the drive script) rather than trying to make the README interactive. Recommend + apply: a single static "value tradeoff" or "scan-robustness" figure near the scanned-robustness section, captioned, linking to the live dashboard for the interactive version.
- [ ] **Step 3:** Confirm the README still renders (headings, image paths relative). **Commit.**

---

## Verification (end to end)

- `uv run --extra dev pytest -q` all green (cost, endpoints, triage, security regression).
- Playwright drive completes with zero console errors across all views + both themes.
- Numbers in the UI equal `gauntlet scoreboard` (perf medians, tier-b, robustness retained%).
- Brand: navy/cream dominant, terracotta only for primary/selection/frontier, JetBrains-Mono data, SVG icons (no emoji), no em dashes in UI copy, focus-visible outlines, theme auto-default with no flash.
- Self-contained: only network fetch is webfonts; app works offline with fallback fonts.

## Self-Review notes

- Spec coverage: cockpit (T4), workbench (T5), verify (T4 provenance + T5 score row), benches+robustness (T6), plumbing/cost consolidation (T1–T2), branding (T3–T6), testing (T2 pytest + T7 Playwright), screenshots+README (T7–T8). Covered.
- No JS unit runner (per spec) — frontend validated by Playwright drive + API-layer pytest.
