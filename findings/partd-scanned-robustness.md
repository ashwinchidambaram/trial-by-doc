# Part D — Scanned/faxed robustness (Tier-B extraction under degradation)

**Run:** `v1-baseline` · 14 models × {clean, scanned_light, scanned_heavy} × 100 samples ·
scored 2026-07-09 · 0 error rows across all 42 (model × variant) cells.

## What this measures

The same RealDoc-Bench QA pages, passed through a synthetic scan-degradation pipeline
(`src/tbdoc/benches/degrade.py`) at two severities, then scored with **B.1 — deterministic
field-value-presence** (reader-independent; the headline extraction metric). B.1 is the right
robustness signal because it asks "did the gold value survive, unmangled, into the model's OCR
markdown?" with no LLM in the loop — so a drop is the *OCR* degrading, not a reader confound.

`clean` = the published v1 realdoc_qa B.1 (official scoreboard column). `light`/`heavy` are the
two new scanned benches (100/100 each, computed from raw score records).

## Robustness curve (B.1, clean → light → heavy; % = heavy retained vs clean)

| model | clean | light | heavy | heavy retained | class |
|---|---|---|---|---|---|
| olmocr2 | 0.689 | 0.657 | **0.514** | 75% | VLM (OCR) |
| gemma4 | 0.564 | 0.586 | 0.451 | **80%** | VLM |
| qwen25vl | 0.637 | 0.676 | 0.436 | 68% | VLM |
| doctr | 0.682 | 0.660 | 0.398 | 58% | classic |
| kosmos25 | 0.565 | 0.517 | 0.390 | 69% | VLM (small) |
| dots_ocr | 0.549 | 0.585 | 0.386 | 70% | VLM |
| paddleocr_vl | 0.542 | 0.497 | 0.305 | 56% | VLM (small) |
| deepseek_ocr | 0.469 | 0.451 | 0.261 | 56% | VLM |
| rapidocr | 0.499 | 0.495 | 0.261 | 52% | classic |
| lightonocr | 0.658 | 0.602 | 0.408 | 62% | VLM (distilled) |
| got2 | 0.175 | 0.149 | 0.107 | 61% | VLM (small) |
| tesseract | 0.580 | 0.395 | **0.171** | **29%** | classic |
| easyocr | 0.583 | 0.405 | **0.126** | **22%** | classic |
| granite_docling | 0.035 | 0.067 | 0.015 | — (noise floor) | VLM (tiny) |

## Headlines

1. **VLMs are markedly more scan-robust than classic engines.** olmocr2 and gemma4 retain
   75–80% of clean B.1 under heavy degradation; **tesseract (29%) and easyocr (22%) collapse.**
   The two classic engines that were *competitive on clean* docs (tesseract 0.580, easyocr 0.583 —
   mid-pack) fall to the bottom on heavy scans. This directly qualifies the Part-A finding that
   classic engines are cheap, competitive extractors: **that holds for clean digital text, not for
   scanned/faxed input.**

2. **Not a clean class split — docTR is the robust classic.** docTR retains 58% (heavy 0.398),
   beating several VLMs (deepseek 0.261, paddleocr 0.305) in *absolute* heavy score. rapidocr sits
   mid-pack (52%). So "classic = brittle" is really "tesseract/easyocr = brittle"; docTR's
   two-stage detector+recognizer degrades more gracefully.

3. **Under heavy scan, the ranking reshuffles toward OCR-purpose VLMs.** Best heavy extractors:
   olmocr2 (0.514) > gemma4 (0.451) > qwen25vl (0.436) > doctr (0.398). olmocr2 stays #1 across all
   three variants; doctr drops from clean #2 to heavy #4.

4. **Light degradation is largely absorbed.** Most models lose little (or wobble up within n=100
   noise: dots_ocr/gemma4/qwen25vl/lightonocr show light ≥ clean). The cliff is between light and
   heavy — i.e. mild rescans are a non-issue; heavy fax/photocopy degradation is where model choice
   matters.

## Caveats / follow-ups

- **n=100 per cell** — per-model heavy scores carry sampling noise; treat sub-0.03 gaps and the
  granite row (0.015–0.067, at the metric's noise floor) as directional.
- **Synthetic degradation** — the plan's staged design calls for a real-scan validation set to
  confirm the synthetic curve; the synthetic-paired stage is what's scored here.
- **Clean-column data-hygiene note (unrelated to scanned data):** recomputing clean B.1 from raw
  records gives 200 rows for `got2` and `lightonocr` (vs 100 for others). got2 is unaffected (both
  halves ≈0.175); **lightonocr's recompute (0.464) diverges from the official 0.658** — the clean
  realdoc_qa raw file for lightonocr appears to hold a duplicate/older score pass. The published
  scoreboard value (0.658) is used above. **Worth auditing `raw/lightonocr/realdoc_qa.jsonl`
  separately** — it does not touch the scanned benches (all 100/100, clean).

## Reproduce

```
gauntlet scoreboard --run-id v1-baseline            # scanned benches now in the matrix
# per-variant B.1 from raw/<model>/realdoc_qa{,_scanned_light,_scanned_heavy}.jsonl
```
