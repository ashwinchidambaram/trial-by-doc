# OmniDocBench end2end scorer (isolated venv, wraps the OFFICIAL pipeline)

Wraps the official opendatalab/OmniDocBench evaluation toolkit (`python pdf_validation.py
--config configs/end2end.yaml` in the official repo). We pip-install the official repo at a
pinned commit — it ships as a top-level `src` package (`omnidocbench-eval`, v1.7 code, evaluates
the v1.6 dataset) — and drive `src.core.pipeline.run_config` directly. Matching (quick_match),
normalization, Edit_dist and TEDS are 100% the official code; nothing is reimplemented.

NOTE: this is the official GITHUB pipeline, NOT the `omnidocbench` PyPI wrapper — the PyPI
package needs a `{blocks, relations}` GT format and ships no converter from the dataset's
`layout_dets` format (that dead end is documented in the ocparse repo, findings/S9). The GitHub
pipeline consumes the dataset's `OmniDocBench.json` as-is.

## Rebuild
    uv venv --python 3.11 .venv        # official pins need >=3.10,<3.12 (numpy 1.24, scipy 1.10)
    uv pip install --python .venv/bin/python -r requirements.txt

## Invoke (from repo root)
JSON lines {pdf_id, markdown} on stdin, pdf_id = GT image basename (e.g. `xxx.png`):

    .venv/bin/python score.py benchmarks/official/omnidocbench/data/OmniDocBench.json

One JSON result line per page (per-page metrics come from the official per-page dumps:
upper_len-weighted text/formula/table/order edit distances, per-table TEDS), plus one
`{"pdf_id": "__aggregate__", ...}` line with the OFFICIAL aggregate numbers for the batch.
Batch is mandatory-cheap: one official pipeline run scores the whole (model, benchmark) cell.
Env: SCORER_MATCH_WORKERS / SCORER_TEDS_WORKERS (default min(8, cpus)).

## Known limitations (flagged in output)
- **CDM excluded** (`cdm_excluded: true`). Formula CDM renders LaTeX via TeX Live + ImageMagick +
  Ghostscript (per the official repo's system-dependencies). Not installed here; formulas are
  still scored with the official Edit_dist. Consequence: the v1.5+ leaderboard headline
  `Overall = ((1-text_ED)*100 + table_TEDS + formula_CDM)/3` cannot be computed — we report
  `overall_edit_dist` (mean of the present per-element edit dists, the v1.0-style overall)
  and each component separately. Add a TeX-capable container later if CDM is required.
- **latexml not installed**: models that emit LaTeX (not markdown/HTML) tables would need
  `latexmlc` for the official LaTeX->HTML conversion before TEDS.

## Reference reproduction (what was and wasn't validated — 2026-07-07)
- Sanity-validated: GT-derived "perfect" predictions score ~0 edit dist / TEDS 1.0; garbage
  scores ~1.0 / TEDS 0.0; empty markdown on a text page scores 1.0 (see
  findings/omnidocbench-notes.md for the numbers).
- The repo's committed `result/` demo outputs are from 2025-04-09 (v1.5-era) and predate the
  2026-04-10 v1.6 matching overhaul — they do NOT match current-code output exactly
  (TEDS_structure_only agrees to the last digit; text/formula Edit_dist differ due to the
  documented v1.6 hybrid-matching changes), so they are not a usable reference for the pinned
  commit.
- TRUE reference repro: the README leaderboard publishes per-model text Edit_dist / table TEDS
  computed by this pipeline over all 1651 pages. Run a listed model (e.g. Qwen2.5-VL-7B) over
  `images/`, feed all 1651 pages through score.py, compare the `__aggregate__` line
  (`text_block.page_ALL.Edit_dist`, `table.all.TEDS`) to the leaderboard row. Needs one full
  GPU inference pass — deliberately not run yet.
