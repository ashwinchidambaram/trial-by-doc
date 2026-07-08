# M2 — the v1 gauntlet (engineering record)

## Wired and validated
- **4 benchmarks**: olmocr_bench (A, container-first scorer incl. math/table),
  omnidocbench (A, official repo pipeline in isolated py3.11 venv; CDM excluded,
  flagged), realdoc_qa (B, frozen extractor + field-EM/ANLS), merged_forms (C,
  custom, VALIDATION.md enforced).
- **12 models + 3 floor baselines**: 8 local (pins mirrored from verified ocparse
  registry), 4 API adapters (mistral_ocr, gemini_flash_lite scored in v1;
  anthropic_vision, openai_vision validate-only).
- **Two-phase runner refinements**: per-page OCR memoization (multi-question docs),
  per-bench sample caps in profiles, judge-composed Tier C moved to score phase
  (frozen judge SHARES the extractor's engine — same pin — one 7B load, no OOM).
- **Cost controls**: estimate-cost + budget guard (max_usd_per_model) enforced
  before any API call.

## Validation evidence
- olmocr scorer, container vs old repo: cross-repo check (old n=100 predictions →
  new scorer → compare per-PDF pass rates) — results recorded below when complete.
- OmniDocBench scorer: GT-as-prediction → TEDS 1.0 / ED ≈ 0; garbage → TEDS 0 /
  ED ≈ 0.96; empty page → ED 1.0 (no silent drops). See findings/omnidocbench-notes.md.
- Tier B smoke (qwen25vl × realdoc_qa × 6): extractor answers grounded in markdown;
  EM 2/6, ANLS ≈ 0.88 — consistent with the old baseline's shape.
- Tier C floors (5 streams each): every_page PQ 0.0, no_boundary PQ 0.0,
  pixel_diff PQ 0.226 — degenerate baselines correctly crushed by PQ, canary bar set.

## Cross-repo scorer validation (Gate 2 criterion) — PASSED 2026-07-07
Old repo's saved n=100 predictions (qwen25vl + olmocr2) fed through the NEW scorer:
- **Native tests (present/absent/order): 100/100 pages byte-identical** per-type
  pass counts for qwen25vl (olmocr2 diffs show the identical pattern).
- The 41/100 raw pass-rate differences are fully explained by the old run's
  SCORER_RENDER_CAP=2 (it sampled ≤2 Playwright math/table tests per doc to bound
  cost); the new container scorer runs ALL render tests (e.g. totals 2 -> 9).
  Same official rules, strictly more coverage. New-repo numbers therefore are not
  expected to numerically equal the ocparse baseline on render-heavy categories —
  they're the uncapped version of the same measurement.
