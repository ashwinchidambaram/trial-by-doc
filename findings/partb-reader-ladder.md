# Part B — Tier-B B.2 reader-sensitivity ladder

The B.2 "comprehension" signal is reader-confounded by design (B.1 is the reader-independent primary).
This study quantifies that confound: **hold the OCR input fixed, vary only the reader**, and measure
the comprehension floor (small local model) vs ceiling (frontier API models).

## Method

- **Fixed input:** olmocr2's `realdoc_qa` OCR markdown for the 100-sample stratified Tier-B set
  (olmocr2 = the strongest Tier-A parser, so the reader gets clean text — the score reflects reader
  comprehension, not OCR quality). Predictions were copied from `v1-baseline` into isolated `rl-*`
  run-ids (v1-baseline untouched); only the score phase re-ran, with `--reader` swapped.
- **Readers:** Phi-4-mini-instruct (3.8B, local vLLM — the new default) · gpt-5.4-mini · claude-haiku-4.5.
  API readers via the OpenRouter gateway (real-time, one key). Deterministic (temperature 0).
- **Metrics:** B.2 exact-match (`field_aware_exact_match`, strict) and B.2 ANLS (fuzzy string similarity).
- **Spend:** ~$2 total (200 real-time OpenRouter calls), within the ~$5–10 pre-authorized lane. 0 errors.

## Result

| reader | params | B.2 exact-match | B.2 ANLS |
|---|---|---|---|
| Phi-4-mini-instruct (local, default) | 3.8B | 0.18 | 0.692 |
| **gpt-5.4-mini** (OpenRouter) | API | **0.50** | **0.844** |
| claude-haiku-4.5 (OpenRouter) | API | 0.41 | 0.761 |

## Findings

1. **Reader choice moves B.2 by ~2.8× on exact-match** (0.18 → 0.50). The B.2 metric is therefore a
   statement about the *reader* at least as much as the OCR — which is exactly why **B.1 (deterministic
   field-value presence) remains the Tier-B headline** and B.2 is explicitly secondary. This ladder is
   the evidence for that framing.
2. **The gap shrinks under fuzzy scoring** (ANLS 0.692 → 0.844, ~1.2×). The small local model usually
   finds the right *region* / near-answer but fails strict exact-match formatting (units, punctuation,
   trailing words); the frontier readers nail the exact surface form more often.
3. **gpt-5.4-mini > claude-haiku-4.5** on this task (0.50 vs 0.41 exact; 0.844 vs 0.761 ANLS), both
   far above the local floor. Either API reader is a materially stronger comprehension instrument than
   the local default.
4. **Practical guidance:** keep **Phi-4-mini as the default** (free, local, reproducible, key-less
   clones still run) for routine B.2; select `--reader gpt5mini` / `--reader haiku45` when a
   comprehension *ceiling* estimate is wanted. B.1 is unaffected by the choice (verified: reader-
   independent, unchanged across all three passes).

## Reproduce

`configs/models.yaml` `instruments.reader` (default_local=Phi-4-mini; `local_variants.local_qwen15`
retains the old Qwen2.5-1.5B rung; `backends.gpt5mini`/`haiku45` → OpenRouter, slugs+pricing verified
live 2026-07-09). Run-ids `rl-phi4` / `rl-gpt5` / `rl-haiku`. Co-load rule honored (Tier-B-only
invocations; the local reader's vLLM engine never shared the GPU with the Tier-C judge).
