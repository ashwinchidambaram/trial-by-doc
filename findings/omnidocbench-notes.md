# OmniDocBench end2end wiring — investigation + validation notes (2026-07-07)

## What unblocked it
The prior attempt (ocparse repo, findings/S9 + benchmarks/_scorers/omnidocbench/README.md there)
stalled on the `omnidocbench` **PyPI** package: its `evaluate_page` wants a `{blocks, relations}`
GT format and ships no converter from the dataset's `layout_dets` format. The fix is to skip the
PyPI wrapper entirely: the **official GitHub repo** (opendatalab/OmniDocBench) consumes the
dataset's `OmniDocBench.json` AS-IS. Its end-to-end entrypoint is
`python pdf_validation.py --config configs/end2end.yaml` → `src.core.pipeline.run_config`, with
GT = OmniDocBench.json and predictions = a folder of `<image_basename_minus_ext>.md` files
(`End2EndDataset._resolve_prediction_path`). Verified live at commit
`2b161d010d2e3aff77a0edef359ea3a6411d23cd` (main, v1.7 code; evaluates the v1.6 dataset).

Two properties make the harness integration clean:
- **Page matching is strictly per-page** (`_match_single_page`), so subsetting the GT json to the
  sampled pages is exact — it only changes which pages are averaged.
- The pipeline natively writes **per-page dumps** to `./result/`:
  `*_per_page_edit.json` (official upper_len-weighted page edit dist per element) and
  `*_per_table_TEDS.json` — exactly what a per-sample scoreboard needs. No reimplementation.

## What was implemented
- `benchmarks/_scorers/omnidocbench/` — isolated venv scorer (Python 3.11: official pins are
  `>=3.10,<3.12`, numpy 1.24 / scipy 1.10 / lxml 4.9 / pylatexenc 2.10; NEVER in the main venv).
  `requirements.txt` pip-installs the official repo from GitHub at the pinned commit (it ships a
  top-level `src` package). `score.py` speaks the repo's batch JSONL contract
  (stdin `{pdf_id, markdown}` → stdout per-page result lines + one `__aggregate__` line with the
  official aggregate numbers), builds the pred dir + GT subset in a tempdir, runs
  `run_config` with the standard end2end quick_match config **minus CDM**, and reads the
  official per-page dumps. Official pipeline stdout is redirected to stderr (JSONL protocol).
- `src/tbdoc/benches/official/omnidocbench.py` — `OmniDocBench(BenchAdapter)`: loads
  `OmniDocBench.json` + `images/`, stratified round-robin over the 10 `data_source` categories,
  `evaluate_batch` via `score_batch_venv`. Primary = `1 - overall_edit_dist` (mean of the page's
  present per-element official edit dists; higher = better); components incl. table TEDS kept.
- `configs/benchmarks.yaml` entry `omnidocbench` (tier A, page, official,
  hf_repo opendatalab/OmniDocBench @ `d386947f` = the "add v1.6" commit of 2026-04-10;
  **license: unspecified — VERIFIED: the HF dataset card has no license tag/field**; eval code
  repo is Apache-2.0). Dataset (1651 pages, 1.4GB) copied from the ocparse download into
  `benchmarks/official/omnidocbench/data/` (gitignored, pinned revision in the manifest there).

## Validation (real numbers, 2026-07-07)
Scorer venv, 3 pages (table page / equation_hard page / plain text page):
- **GT-as-prediction (perfect)**: text ED 0.0 / 0.0 / 0.0028; formula ED 0.0; table ED 0.0,
  TEDS 1.0, TEDS_structure 1.0; order ED 0.077 / 0.0 / 0.0 → overall ED 0.026 / 0.0 / 0.0014.
  (Gotcha found while building the fixture: the GT `latex` field ALREADY contains `$$…$$`;
  double-wrapping it tanks formula ED to 0.89.)
- **Garbage prediction**: text ED 0.98–0.99, formula ED 1.0, table ED 1.0, TEDS 0.0,
  order ED 0.92 → overall ED 0.95–0.97.
- **Empty markdown on a text page**: text/order ED 1.0 (pages don't silently drop).
- **All-null page**: `..._page_001.png` (colorful_textbook cover) has only `text_mask`/`figure`
  GT → all metrics null, primary None — correct exclusion, not a bug.
- **Adapter end-to-end** (Registry → load → evaluate_batch → venv): perfect pages primary 1.0,
  garbage 0.25, no-element page None. Repo tests: 18/18 pass; `gauntlet list benches` shows it.

## Caveats / follow-ups
1. **CDM excluded** (`cdm_excluded: true` on every row): formula CDM needs TeX Live +
   ImageMagick + Ghostscript (official system deps). Formulas still get the official Edit_dist.
   Consequence: the v1.5+ leaderboard headline `Overall = ((1-text_ED)*100 + TEDS + CDM)/3` is
   NOT computable; we report `overall_edit_dist` (v1.0-style mean of element edit dists).
   If CDM is ever needed: build a TeX-capable container (repo pins: Ghostscript 9.55,
   ImageMagick 7.1.1 with PDF policy enabled, TeX Live with CJK).
2. **latexml not installed** — only matters for models that emit LaTeX tables (official code
   shells out to `latexmlc` for LaTeX→HTML before TEDS; markdown/HTML tables are native).
3. **Reference numbers**: the repo's committed `result/` demo outputs are v1.5-era (2025-04-09)
   and predate the 2026-04-10 v1.6 matching overhaul — our current-code demo run agrees on
   TEDS_structure_only exactly (0.9115886967813946) but differs on text/formula ED as expected
   from the documented v1.6 changes, so they're not a valid reference. True repro = full-run a
   leaderboard model (e.g. Qwen2.5-VL-7B) over all 1651 pages and compare the `__aggregate__`
   line to the README leaderboard columns (one GPU pass; deliberately not run yet).
4. Full-run cost is dominated by quick_match + TEDS; both are parallel
   (SCORER_MATCH_WORKERS / SCORER_TEDS_WORKERS, default min(8, cpus)). The 3-page batch takes
   ~40s including venv cold start.
