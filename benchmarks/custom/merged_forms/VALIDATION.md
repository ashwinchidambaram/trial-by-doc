# VALIDATION — merged_forms (custom benchmark)

STATUS: PROVISIONAL — determinism + seam checks below run at generation; human
spot-check pending owner review. (The registry requires this doc to exist; treat
scores as provisional until all three checks are ✅.)

## What this benchmark is
30 streams, each 3–4 NIST SD2 tax-submission packets (900 available, public-domain
US-gov work) concatenated. Same 1988 IRS form faces, different simulated filer data
→ boundaries are content-detectable only (the production hard case).

## Ground truth
Boundaries = packet edges, known by construction (manifest.json, seed=0).

## Checks
1. **Generator determinism**: same seed → identical manifest (sha256 recorded below).
2. **Seam-artifact canary**: baseline_pixel_diff must NOT beat content-based models;
   if visual deltas at seams outperform content reading, the merge leaks. Floor rows
   (every_page/no_boundary/pixel_diff) are published on the scoreboard.
3. **Human spot-check**: N=10 stream boundaries eyeballed against page images (owner).

## Results
- determinism sha256: 940b95ddeaf8644f (regenerated twice, identical — 2026-07-07)
- pixel_diff vs content models: **canary PARTIALLY FIRES** (stamped 2026-07-12, run
  `tierc-floor-15`: all 3 floors × the same 15 streams the models scored; an earlier
  n=5 floor run had accidentally inherited the smoke profile's sample cap).
  baseline_pixel_diff PQ **0.226** vs content-based models: the four classic engines
  beat it (easyocr 0.397, doctr 0.336, tesseract 0.330, rapidocr 0.258) but **every
  VLM scores below it** (best: kosmos25 0.204; olmocr2 0.070; dots_ocr 0.006).
  Interpretation: the merge does not leak trivially detectable seams *to content-blind
  diffing better than content reading in general* — the strongest splitters are
  content-based — but VLM `judge_composed` scores must NOT be cited as competent
  splitting; they fail the floor test. The README Tier C claims are caveated
  accordingly. every_page / no_boundary floors: 0.0.
- human spot-check: PENDING (owner: eyeball N=10 stream boundaries against page
  images — until then scores stay provisional per the header)
