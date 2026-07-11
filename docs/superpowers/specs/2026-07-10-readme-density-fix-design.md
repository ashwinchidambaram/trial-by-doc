# README density + takeaway fix — design

_2026-07-10. Follow-up to `2026-07-10-readme-restructure-design.md`. Owner-approved in
conversation._

## Problem

After the first restructure (concepts before scores, glossary added), the owner's
feedback: the README still doesn't leave a reader with a clear takeaway, and at ~490
lines / ~4600 words across 12 sections it reads as dense reference material. Root cause
of the takeaway problem: the actual synthesized findings already exist
(`findings/a4-expanded-roster.md`'s headline findings, the scan-robustness study's
takeaway paragraph) but were never surfaced in the README itself — a reader has to
derive conclusions from a raw 14×4 table unassisted.

## Fix (two moves)

1. **New `## Bottom line` section**, placed right after the Contents/TOC, before
   `## Benchmarks`. Plain-language synthesis, verified against the actual scoreboard
   and findings docs (not restated from memory):
   - No single model wins everything: VLMs (olmocr2, dots_ocr) win Tier A; classic CPU
     engines (easyocr, docTR, tesseract) win Tier C by up to 2.5× the best VLM.
   - docTR is the standout generalist: 2nd-best B.1 (0.682, behind olmocr2's 0.689),
     competitive Tier C, free (CPU).
   - Scanned/faxed input flips the ranking: olmocr2/gemma4 retain 75–80% of clean
     accuracy under heavy degradation; tesseract/easyocr collapse to 22–29%.
   - Cost spans three orders of magnitude: $0.057/1k pages (tesseract, CPU) to
     $10.60/1k pages (gemma4, A100 single-stream) — see the Dashboard's value frontier.
   - Quick picks: cleanest OCR → olmocr2 (olmocr_bench) / dots_ocr (omnidocbench) ·
     cheapest competitive → tesseract/docTR · scan-robust → olmocr2/gemma4 · best
     splitting → easyocr.

2. **New `docs/REFERENCE.md`** — the full 17-row Models roster (params/license/
   commercial-use/specialty columns) + the Azure self-host cost tables + the full
   8-bullet Gaps list, moved verbatim out of README.md.
   - README's `## Models` section shrinks to a ~4-row "notable picks" teaser table
     linking to `docs/REFERENCE.md`.
   - README's `## Gaps` section shrinks to a one-line summary of the biggest open item
     (API fleet unscored) + a link to `docs/REFERENCE.md#gaps`.

## Explicitly unchanged

Benchmarks, Scores (including the auto-injected `SCOREBOARD:BEGIN/END` block — not
touched by this pass either), Dashboard, Scanned robustness, Example documents, "What
the harness actually is", Setup, Hardware, Glossary, Credits. Only the TOC (new anchor
for Bottom line) and the Models/Gaps sections change in README.md.

## Verification plan

- Re-run the `inject_readme` round-trip check (same method as the first restructure)
  to confirm the marker automation still works.
- Markdown table column-count sanity check across both README.md and the new
  docs/REFERENCE.md.
- Confirm every fact in the Bottom Line section against the actual scoreboard.csv /
  findings docs before publishing (prime directive: verify, never assume).
