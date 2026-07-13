# Statistical significance: paired bootstrap CIs on the close calls

_2026-07-12. Grounds the "treat sub-0.05 gaps as ties" guidance in actual intervals.
Method + helper: `src/tbdoc/report/stats.py` (`paired_bootstrap_diff`, seed=0, 10k
resamples); reproduce any pair with `gauntlet scoreboard --run-id <id> --ci A,B
--bench <b> --metric <b1|b2|primary>`._

## Why paired

Every model is scored on the **same items** with deterministic scorers, so a
model-vs-model comparison is paired: each bootstrap round resamples item indices once and
reads both models at those indices. Pairing cancels item-difficulty variance — far more
powerful than comparing two independent means, and the honest test for "is this gap real?"

## B.2 leading trio (run `v1-b2-gpt5mini`, gpt-5.4-mini reader, n=100)

The README calls olmocr2 / qwen25vl / dots_ocr a *leading group, not a podium*. The CIs
confirm it — every pairwise gap spans 0:

| pair | Δ (mean B.2) | 95% CI | verdict |
|---|---|---|---|
| olmocr2 − qwen25vl | +0.030 | [−0.060, +0.120] | tie |
| olmocr2 − dots_ocr | +0.050 | [−0.050, +0.150] | tie |
| qwen25vl − dots_ocr | +0.020 | [−0.090, +0.130] | tie |

## B.1 extraction, RealDoc-QA (run `v1-baseline`, n=90 extractive)

The stronger and more surprising result: **the entire B.1 top four is a statistical
tie.** Adjacent pairs, and the full-spread top-vs-4th:

| pair | Δ (mean B.1) | 95% CI | verdict |
|---|---|---|---|
| olmocr2 − doctr | +0.007 | [−0.078, +0.093] | tie |
| doctr − lightonocr | +0.024 | [−0.024, +0.074] | tie |
| lightonocr − qwen25vl | +0.021 | [−0.062, +0.106] | tie |
| **olmocr2 − qwen25vl** (0.689 vs 0.637) | +0.052 | [−0.032, +0.140] | **tie** |

The method is not just saying "everything ties" — it discriminates real gaps cleanly:

| pair | Δ | 95% CI | verdict |
|---|---|---|---|
| olmocr2 − deepseek_ocr | +0.220 | [+0.149, +0.294] | **significant** |
| olmocr2 − got2 | +0.514 | [+0.428, +0.598] | **significant** |

## Takeaways

1. **On RealDoc B.1 at n=90, differences below ~0.10 are within noise.** The prior
   "sub-0.05 → directional" rule of thumb was, if anything, too permissive — olmocr2's
   0.052 lead over qwen25vl is not distinguishable from zero. Read the B.1 leaderboard as
   a *lead group* (olmocr2, doctr, lightonocr, qwen25vl), not a strict ranking.
2. **"Best overall extraction" claims should name the group, not a single winner** on this
   benchmark. olmocr2's cross-benchmark consistency (it also leads Tier A) is the real
   basis for calling it the top pick — not its RealDoc B.1 margin, which is a tie.
3. **The gaps that carry the headlines are real**: olmocr2 vs. the mid-pack (deepseek,
   got2, granite) is comfortably significant. The scoreboard's *coarse* structure is
   sound; only the fine adjacent-rank ordering is noise-limited.

## Scope / caveats

- Per-category cells (n≈14–25) are even noisier — treat those as illustrative only.
- CIs need per-sample scores. These are now persisted (as scalars, not the bulky
  predictions) in each run's tracked `summary.json` under `samples`, so `--ci` reproduces
  from a fresh clone — `per_sample_metric` falls back to `summary.json` when `raw/` is
  absent. (Verified: fresh-clone CIs match the raw-scored CIs byte-for-byte.)
- These are marginal CIs per pair; no multiple-comparison correction is applied (would
  only widen them, i.e. make more pairs ties).
