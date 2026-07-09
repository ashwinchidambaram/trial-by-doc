# Goal

Measure how well every roster model extracts **correct content** from **scanned/faxed** documents,
not just clean digital uploads — a production-critical axis the v1 harness never isolated. This is
**Part D** of the scope expansion (after Part A roster, alongside/after Part B reader).

**Date:** 2026-07-09
**Status:** approved (owner decisions locked 2026-07-09) — not yet implemented.
**Owner decisions:** (1) **Both, staged** — synthetic paired degradation as the primary metric,
validated against real scans; (2) **light + heavy** severities; (3) **Tier-B extraction only**.

## 1. Motivation & the gap

A production owner uploads two kinds of document: **clean** (born-digital PDF or a crisp office
scan) and **degraded** (faxed, photocopied, or scanned-over-scanned — the "3rd-generation fax"
look). The v1 harness measures the clean case (Tier B is born-digital PDFs) and, incidentally, some
real scans buried in `olmocr_bench/old_scans` (28 pages) and the NIST SD2 tax forms — but the SD2
forms are used **only for Tier-C segmentation**, and nothing measures **content-extraction accuracy
under scan degradation** for the full roster. So today we cannot answer "which model still reads the
invoice total correctly after it's been faxed?" — the exact question the owner needs.

## 2. Why the primary metric already measures *content correctness*

The owner's binding requirement: **correct content extraction is critical, not just field
identification.** The existing Tier-B primary already satisfies this — no new scorer is required for
the headline:

- **B.1 = `field_value_presence(markdown, golds)`** (`src/tbdoc/scoring/scorers.py:206`) scores the
  fraction of gold field **values** that survive in the OCR'd markdown. It credits the *value*, not
  the *location* — there is no "found the field" partial credit.
- It is **content-type aware** (`_value_in_markdown`, `scorers.py:172`): numbers match via a
  tolerant numeric-token comparison (`$1,234.56` must actually appear as that number); booleans must
  canonicalize from the real checkbox glyph (`[X]` / `☑`); strings need a canonical substring **or**
  a sliding-window ANLS ≥ 0.8. Scan noise that corrupts a digit or drops a word → the value scores
  **absent** → the number falls. That drop *is* the robustness signal.
- **Paired design guarantees attribution:** the degraded image reuses the *identical* gold
  annotation as its clean twin, so a score delta is attributable purely to the degradation, not to a
  harder document.

**Fuzziness is deliberate.** The ANLS ≥ 0.8 string tolerance means a near-miss transcription still
counts — we want "did the value essentially survive," which is the right robustness question. If a
**strict** exact-match rung is later wanted, `field_aware_exact_match` (`scorers.py:118`, already
driving B.2) is available to add as a second column without touching B.1.

**B.1 scores only extractive golds** (`is_extractive_gold`); derived/reasoned answers are excluded
from the primary and tested only via the optional B.2 reader — inherited from v1, unchanged.

## 3. Scope

| Dimension | Decision |
|---|---|
| Approach | **Both, staged** — synthetic paired (primary) + real-scan validation |
| Severities | **light** (clean office scan) **and heavy** (worst-case fax) |
| Tiers | **Tier B extraction only** (realdoc_qa docs) |
| Metric | **B.1 (reader-independent) is the headline**; B.2 reader ladder is a stricter bonus |
| Models | every roster contender that runs Tier B (classic OCR, vision-OCR, APIs) |

Out of scope: degrading Tier A or Tier C (Tier C is already scanned NIST forms); a bespoke strict
scorer (deferred, available if asked); new document sources beyond realdoc_qa + the existing real
scans.

## 4. Design

### 4.1 Degradation pipeline (`src/tbdoc/benches/degrade.py`, net-new)

A deterministic, **seeded** image→image function `degrade(img, level, seed) -> img`. Ordered to
mimic a real scan/fax path (validated visually against the owner's comparison panel, 2026-07-09):

1. grayscale (fax is 1-bit/grayscale)
2. resolution loss — downscale then upscale back (loses fine glyph detail)
3. skew — small rotation (scanner misfeed), white fill
4. Gaussian blur (optics / paper contact)
5. Gaussian sensor noise
6. JPEG recompression (transport artifacts)
7. (**heavy** only) contrast push (toner/photocopy saturation)

**Parameters** (frozen, recorded in the bench for reproducibility):

| | downscale | blur σ | noise σ | skew° | JPEG q | contrast |
|---|---|---|---|---|---|---|
| **light** | 0.62 | 0.6 | 7 | 0.6 | 45 | — |
| **heavy** | 0.42 | 1.0 | 15 | 1.5 | 27 | 1.5 |

Seed is fixed per (sample, level) so a page degrades identically on every run — a degraded image is
as reproducible as the clean one.

### 4.2 New bench `realdoc_qa_scanned` (`src/tbdoc/benches/official/realdoc_qa_scanned.py`)

Subclass / thin wrapper of `RealDocQA` that reuses its `qa_bank.json` + gold + stratified sampling
verbatim, and **only** interposes `degrade()` on the rendered page image before it is handed to the
adapter. It emits the **same `Sample` ids** as clean Tier B, tagged with the severity, so the
scoreboard can join clean↔light↔heavy per (model, question). Two registered variants
(`realdoc_qa_scanned_light`, `realdoc_qa_scanned_heavy`) or one bench with a `level` config knob —
implementation detail for the plan. `tier="B"`, `unit="page"`, `requires_extractor=True`
(reader optional, same as clean B).

Scoring is **unchanged** — it flows through the identical `evaluate()` (B.1 primary + optional B.2),
so no scorer code changes and B.1's v1 numbers on clean docs are untouched.

### 4.3 Real-scan validation lane (staged part 2)

To check the synthetic ranking reflects reality:
- **Free now:** break out the `olmocr_bench/old_scans` category (28 real-scan pages, already scored
  in Tier A) as a real-scan parse-fidelity reference — a report-only slice, no new runs.
- **Optional:** if field-level GT can be sourced for NIST SD2, score those real scans on B.1 too.
  Verify GT exists before promising extraction numbers (verify-never-assume) — otherwise SD2 stays
  Tier-C-only and we rely on old_scans for the real-world sanity check.

The claim we publish: *the synthetic robustness ranking (who degrades least) holds on real scans* —
High confidence for relative ranking, Medium for absolute real-world numbers.

## 5. Deliverables

- **Robustness curve per model:** `clean B.1 → light B.1 → heavy B.1`, plus the delta (points lost)
  — the headline "who survives a fax" table.
- A `findings/` note interpreting it (which model class — classic OCR vs small VLM vs API — is most
  scan-robust; where each cliff is), + the real-scan validation slice.
- Auto-injected into the README Tier-B section via the Part-C scoreboard inject (C2).

## 6. Reproducibility

Degraded images are seeded and parameter-frozen (§4.1). Every scanned row carries the same
provenance stamps as clean Tier B (model revision, seed, scorer identity, hardware fingerprint) plus
the degradation `(level, params-hash, seed)` so a reviewer can regenerate the exact degraded page.

## 7. Sequencing

Part D runs **after Part A** (so every contender exists to get a scan row) and can reuse Part B's
upgraded reader for the B.2 bonus rung if that has landed. It does **not** block the Part-A gate.
Build order: degradation pipeline + its validation → bench adapter → wire into a scored run →
findings + README.
