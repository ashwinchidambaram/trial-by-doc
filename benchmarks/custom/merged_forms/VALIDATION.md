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
- pixel_diff vs content models: (stamped after v1 run)
- human spot-check: PENDING
