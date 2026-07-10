# Part D — scan/fax robustness: BUILD complete, awaiting controller's scored run

**Date:** 2026-07-09
**Spec:** `docs/superpowers/specs/2026-07-09-scanned-robustness-design.md`
**Scope of this pass:** BUILD + cheap VALIDATE only (per owner instruction). The full/scored
Part-D comparison (8-model roster × `realdoc_qa_scanned_{light,heavy}` × 100 questions each) was
explicitly **not run** — that is the controller's job on GPU.

## What was built

- `src/tbdoc/benches/degrade.py` — deterministic, seeded `degrade(img, level, seed) -> img`
  (`level` ∈ `{"light", "heavy"}`), ported verbatim (parameters and pipeline order) from the
  owner-validated reference `faxify()` script (scan-comparison panel, 2026-07-09). Frozen params:
  light = `scale=0.62 blur=0.6 noise=7 angle=0.6 jpeg=45`; heavy = `scale=0.42 blur=1.0 noise=15
  angle=1.5 jpeg=27` + a post-noise contrast push (`(x-110)*1.5+128`). Pure PIL/numpy, no torch.
- `src/tbdoc/benches/official/realdoc_qa_scanned.py` — `RealDocQAScanned(RealDocQA)`. Calls
  `super().load()` unchanged (same `qa_bank.json`, same gold, same stratified doc sampling) and
  only degrades the rendered page image before re-yielding the Sample. Sample ids are byte-identical
  to clean `realdoc_qa` (`finance_q1`, etc.) so clean/light/heavy join per (model, question).
  `level` comes from the registry entry (`entry["level"]`), so one class serves both variants.
  Scoring is 100% inherited from `RealDocQA.evaluate()` — no scorer code touched.
- **Registered** in `configs/benchmarks.yaml`: `realdoc_qa_scanned_light`,
  `realdoc_qa_scanned_heavy`, both pointing `data_dir` at the existing
  `benchmarks/official/realdoc_qa/data` (reuses the PDFs + qa_bank.json on disk verbatim, no new
  download).
- **Profile**: added a new `partd_scanned` profile to `configs/matrix.yaml` (mirrors the existing
  `tierc_floor` pattern — a separate profile rather than folding into `full`, since this is a
  distinct axis staged after the Part-A gate, not part of the v1 comparison) with the same 8-model
  roster and cap 100 on each of the two new bench keys. **Not run** in this pass.

## Implementation decision flagged for the owner

The spec (§4.1) says "seed is fixed per (sample, level)." `RealDocQA.load()` already renders each
source PDF **once per document** and shares that single image across every question asked of it
(`by_doc[src]`) — this mirrors a real reader seeing one scanned page and answering several
questions about it. `RealDocQAScanned` preserves that sharing: the page is degraded **once per
(source_file, level)**, seeded from `sha256(f"{source_file}|{level}")`, and the same degraded pixels
are reused for every question sample drawn from that document — rather than re-degrading
independently per question (which would make "the same page" look subtly different depending on
which question you asked about it, which is not representative of a real scan and would also
undercut the "identical gold annotation as its clean twin" pairing guarantee in §2). This is filling
an implementation detail the spec left open ("two registered variants ... — implementation detail
for the plan"), not a contradiction of an explicit requirement — flagging it here per the
verify-never-assume house rule in case the owner intended per-question degradation instead.

## Validation performed (cheap, no scoring, no GPU)

1. **Registry wiring** — `Registry("configs").bench("realdoc_qa_scanned_light"/"_heavy")` resolves,
   `level` and `fingerprint()` (incl. `degrade_params`) are correct for each.
2. **Determinism + differentiation** (standalone script, `benchmarks/official/realdoc_qa/data`):
   loaded the first 3 samples of clean `realdoc_qa`, `realdoc_qa_scanned_light`, and
   `realdoc_qa_scanned_heavy`. All three streams emit the SAME sample ids (`finance_q1/q2/q3`);
   pixel arrays are pairwise different for every (clean, light), (clean, heavy), (light, heavy) pair
   for all 3 samples (`np.array_equal` == False in every case). `meta["severity"]` and
   `meta["degrade_seed"]` populated correctly (seed identical across the 3 samples because they
   share one source document, per the sharing decision above).
3. **CLI infer smoke** (tesseract, cheapest CPU-only contender, 3 samples, `--phase infer` only —
   no scoring):
   ```
   uv run gauntlet run --profile full -m tesseract -b realdoc_qa_scanned_light \
     --run-id partd-validate-light --max-samples 3 --phase infer
   uv run gauntlet run --profile full -m tesseract -b realdoc_qa_scanned_heavy \
     --run-id partd-validate-heavy --max-samples 3 --phase infer
   ```
   Both: `{"predicted": 3, "errors": 0}`. `sample_id`s in the prediction JSONL are
   `finance_q1`/`finance_q2`/`finance_q3` for both variants (matching clean Tier-B naming).
   Predictions are non-trivial markdown (light: 3819 chars, readable OCR text; heavy: 5080 chars,
   visibly more garbled OCR — e.g. light reads "Copy of the Notice of Information Practices..."
   while heavy reads "Capstone geeinatty TaN se Sa TER..." on the same underlying page) — a first
   qualitative signal that heavier degradation does degrade OCR output, consistent with the
   robustness hypothesis this bench exists to measure (not a claim about scored accuracy, which is
   the controller's job).
4. **Unit tests**: `tests/test_degrade.py` (8 tests — determinism, light≠heavy≠clean, grayscale
   invariant, frozen-params regression, invalid-level rejection) and
   `tests/test_realdoc_qa_scanned.py` (4 tests — sample-id parity with clean, pairwise pixel
   difference, per-doc degraded-image reuse, invalid-level rejection). Full suite:
   `uv run --extra dev pytest -q` → **90 passed** (78 pre-existing + 12 new), 0 failures.

## What was NOT done (by design, per scope)

- No scored comparison (`realdoc_qa_scanned_{light,heavy}` were never run with a real reader
  instrument or scored against gold on the full roster).
- No `findings/` robustness-curve table (clean→light→heavy B.1 deltas) — that is downstream of the
  scored run.
- No real-scan validation lane (§4.3, `olmocr_bench/old_scans` breakout) — separate deliverable, not
  requested in this pass.
- `realdoc_qa.py` itself, its scorer, and `configs/models.yaml` were not touched.

## Next step for the controller

Run `uv run gauntlet run --profile partd_scanned` (GPU, full roster, both severities, cap 100 each)
to produce the scored comparison, then the clean→light→heavy B.1 delta table + findings note per
spec §5.
