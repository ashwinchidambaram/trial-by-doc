# Tier-B B.2 re-scored with gpt-5.4-mini (run `v1-b2-gpt5mini`)

_2026-07-10 run, written up 2026-07-11. Follow-up to
[partb-reader-ladder.md](partb-reader-ladder.md); owner-directed ("re-score with the
Anthropic/OpenAI readers, not Phi"; scope narrowed to gpt-5.4-mini only)._

## What was run

The full 14-model `v1-baseline` Tier-B lane, re-scored with the **gpt-5.4-mini** reader
(`openai/gpt-5.4-mini` via OpenRouter) instead of the historical Qwen2.5-1.5B:

- **No re-inference.** `predictions/` and `raw/` were copied verbatim from `v1-baseline`
  into the isolated run-id `v1-b2-gpt5mini`, then `gauntlet run --phase score --rescore
  --reader gpt5mini` re-scored them. `v1-baseline` itself is untouched.
- **B.1 is byte-identical to v1-baseline** across all 14 models (frozen extractor, same
  predictions) — verified by rendering `render_tier_b` on both runs. Any B.2 movement is
  the reader and only the reader.
- 14 models × 100 samples = 1,400/1,400 scored, 0 errors. ~1,400 OpenRouter reader calls
  ≈ **$14** at the ladder study's empirical ~$0.01/call rate.
- Reader identity is stamped per-record (`openrouter:openai/gpt-5.4-mini`); pricing
  ($0.75/$4.50 per Mtok in/out, as of 2026-07-09) is in the run manifest.
- Provenance: `results/runs/v1-b2-gpt5mini/{manifest.json,scoreboard.csv,status.json}`
  (tracked); harness at `abd1afb`, configs hashed in the manifest.

## Results (B.2 exact-match, sorted by new B.2)

| model | B.1 extract | B.2 (Qwen2.5-1.5B, historical) | B.2 (gpt-5.4-mini) | lift |
|---|---|---|---|---|
| olmocr2 | 0.689 | 0.130 | **0.500** | 3.8× |
| qwen25vl | 0.637 | 0.140 | 0.470 | 3.4× |
| dots_ocr | 0.549 | 0.130 | 0.450 | 3.5× |
| doctr | 0.682 | 0.100 | 0.390 | 3.9× |
| lightonocr | 0.658 | 0.130 | 0.370 | 2.8× |
| tesseract | 0.580 | 0.110 | 0.350 | 3.2× |
| paddleocr_vl | 0.542 | 0.090 | 0.320 | 3.6× |
| easyocr | 0.583 | 0.090 | 0.270 | 3.0× |
| rapidocr | 0.499 | 0.060 | 0.260 | 4.3× |
| gemma4 | 0.564 | 0.050 | 0.230 | 4.6× |
| deepseek_ocr | 0.469 | 0.080 | 0.220 | 2.8× |
| kosmos25 | 0.565 | 0.070 | 0.210 | 3.0× |
| granite_docling | 0.035 | 0.000 | 0.040 | — |
| got2 | 0.175 | 0.010 | 0.030 | 3.0× |

Mean B.2 across the roster: **0.085 → 0.294** (~3.5× average; per-model 2.8–4.6×).

## Takeaways

1. **The leader flips to match B.1.** Under Qwen2.5-1.5B the B.2 column was compressed
   into 0.00–0.14 and led by qwen25vl (0.14) — barely above the pack. With a capable
   reader, olmocr2 leads (0.500), followed by qwen25vl (0.470) and dots_ocr (0.450) —
   the same models that lead extraction. Rank agreement with B.1 rises (Spearman
   0.71 → 0.78).
2. **The reader confound goes both directions.** The ladder study showed a capable
   reader can paper over OCR slips; this rescore shows a weak reader also *floors* the
   metric — with Qwen2.5-1.5B, nearly all model-to-model signal in B.2 was reader
   noise. The design stance is unchanged (B.1 primary, B.2 secondary), but the
   gpt-5.4-mini column is the honest "does this feed a downstream QA step" number.
3. **doctr again punches up**: best classic engine at 0.390, 4th overall, ahead of
   several VLMs — consistent with its B.1 standing.
4. **gemma4 / kosmos25 / deepseek_ocr underperform their B.1 rank on B.2** (e.g.
   gemma4 B.1 0.564 → B.2 0.230, below tesseract). Their markdown apparently preserves
   gold values in a form the deterministic B.1 check credits but a reader uses less
   reliably — worth a per-sample look before drawing conclusions.
5. **Not run: the haiku45 rung.** Owner scoped this rescore to gpt-5.4-mini only. A
   claude-haiku-4.5 column would need a fresh cost sign-off (~$14 by the same rate;
   note `gauntlet estimate-cost` does *not* cover B.2 reader spend — it only estimates
   OCR models-under-test).

## Where the numbers surface

- README → Scores → "Tier-B B.2, re-scored" subsection (hand-authored, outside the
  auto-injected block, which stays single-run `v1-baseline`).
- `gauntlet scoreboard --tier-b --run-id v1-b2-gpt5mini` reproduces the table.
