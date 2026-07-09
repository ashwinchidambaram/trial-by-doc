# Granite-Docling Tier-C (merged_forms) — marked N/A + revisit paths

**Date:** 2026-07-08
**Status:** Decision (a) taken by owner — granite Tier-C reported as **N/A**. Options (b)/(c) documented below for possible revisit.

## What happened

During the v1-baseline run, `granite_docling` completed Tier-A (olmocr_bench, omnidocbench) and
Tier-B (realdoc_qa) but **could not complete Tier-C (`custom/merged_forms`)**. It processed
streams `stream_000`–`stream_009` (10/15) and then stalled on **`stream_010`**, which renders a
**~145-megapixel** source page (PIL DecompressionBomb threshold is 89 MP). The other 5 streams
(`stream_010`–`stream_014`) are not done.

### Root cause (verified, not assumed)
- `granite_docling` runs on the **transformers backend** (`telemetry.backend == "transformers"`),
  whose image processor **does not downsize** oversized pages before tiling them into patches.
  On the 145 MP page this balloons host RAM to **~43 GB** and pins one CPU core for **10+ minutes
  on that single image with no GPU progress**.
- The other 7 models run on **vLLM**, whose multimodal preprocessor **resizes internally**, so they
  handled `stream_010` normally. This is a granite-backend limitation, not a merged_forms data bug
  per se (though the 145 MP page is itself unusually large — see option (c)).
- Original crash was a **global OOM at 18:31**: an interim omnidocbench scoring job (~43 GB) ran
  concurrently with granite's heavy stream (~38 GB) → 81 GB > 61 GB system RAM → kernel killed the
  driver. The concurrency was the trigger; the granite balloon is the underlying issue.

## Decision (a) — taken: report granite Tier-C as N/A
- granite is **excluded from the merged_forms scored row**; the scoreboard shows **N/A** with a
  footnote pointing here. Rationale: scoring granite on only the 10 "easy" streams it could finish
  would **flatter** it (the hard oversized stream is exactly where it fails) — a biased partial is
  less honest than N/A.
- granite's 10 completed `merged_forms` predictions remain on disk for provenance (not deleted).
- Streams `010`–`014` are marked with owner-decision **skip records** (`error=` set) so a future
  `gauntlet run --profile full` will **not** retry them and re-trigger the choke. Do the final
  scoring with `--phase score` (never `--profile full`) on this run-id.

## Alternative paths — if we revisit for a granite Tier-C number

### Option (b) — clamp granite's input image size (granite-only)
- **Change:** in the granite adapter's preprocessing, downsize any page whose pixel count exceeds a
  cap (e.g. ≤ 24–36 MP, preserving aspect ratio) before handing it to the transformers processor.
  File: `src/tbdoc/models/local/granite_docling.py` (adapter) — add a max-pixel resize in the
  image-prep path; mirror how vLLM's processor resizes so it's a comparable operation.
- **Re-run:** only granite × merged_forms:
  `gauntlet run --run-id <id> -m granite_docling -b merged_forms --phase infer` then re-score.
  First clear the skip records for `stream_010`–`014` (or use `--rescore`/a fresh run-id).
- **Cost / caveat:** granite would then run on **downsized** pages while the other 7 ran full-res →
  **not a like-for-like comparison**. Report granite Tier-C with an explicit asterisk. Also verify
  the clamp actually prevents the RAM balloon (the 145 MP page must be resized *before* patch
  tiling, not after).

### Option (c) — uniform pixel cap for ALL models (most consistent)
- **Change:** cap page resolution at the **bench-rendering layer** so every model sees the same
  (bounded) pixels. File: the merged_forms bench / its page renderer (where fitz rasterizes pages)
  — cap DPI or max pixels (e.g. render at a fixed max long-edge). This also removes the 145 MP
  outlier for everyone and likely speeds up all models' Tier-C.
- **Re-run:** all 8 models × merged_forms (Tier-C only): re-infer + re-score merged_forms for the
  full roster. Tier-A/B are unaffected and need not be redone.
- **Cost:** most work (redo everyone's segmentation inference), but the **only fully fair** way to
  include granite. Best if we ever want granite's Tier-C to sit in the same column as the others
  without an asterisk. Document the cap value + rationale in the merged_forms VALIDATION.md and
  re-stamp the run manifest.

## Recommendation
Keep (a) for the published v1 baseline (honest, unblocking). If a granite segmentation data point is
later wanted, prefer **(c)** over (b): a uniform cap keeps the comparison clean, whereas (b) leaves
granite on different inputs than everyone else.
