#!/bin/bash
# Finalize v1-baseline scoring after all inference is complete.
# CRITICAL: every command MUST carry --run-id v1-baseline or it creates a fresh empty run.
# Tier B (realdoc) is intentionally deferred to the post-merge B.1/B.2 rescore.
# granite is EXCLUDED from merged_forms (owner decision (a): Tier-C N/A). Per-bench => low RAM.
cd /home/ashwinc/dev/projects/trial-by-doc
G=".venv/bin/gauntlet"
RID="v1-baseline"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

# 1) Tier A: fill dots/paddle/deepseek olmocr (5->100) + granite olmocr+omni (0->100)
log "Tier A scoring (olmocr_bench,omnidocbench) run-id=$RID ..."
stdbuf -oL -eL $G run --profile full --phase score --no-llm-instruments --run-id "$RID" \
  -b olmocr_bench,omnidocbench -m dots_ocr,paddleocr_vl,deepseek_ocr,granite_docling \
  >> results/score-tierA.log 2>&1
log "Tier A done."

# 2) Tier C: merged_forms for 6 vLLM models (deterministic native scorer; granite excluded -> N/A)
log "Tier C scoring (merged_forms) run-id=$RID ..."
stdbuf -oL -eL $G run --profile full --phase score --no-llm-instruments --run-id "$RID" \
  -b merged_forms -m olmocr2,qwen25vl,got2,dots_ocr,paddleocr_vl,deepseek_ocr \
  >> results/score-tierC.log 2>&1
log "Tier C done."

# 3) final coverage map
log "=== FINAL SCORING COVERAGE (raw/ line counts) ==="
for m in olmocr2 qwen25vl got2 dots_ocr paddleocr_vl deepseek_ocr granite_docling lightonocr; do
  printf "%-16s olmocr=%s omni=%s realdoc=%s merged=%s\n" "$m" \
    "$(wc -l < results/runs/$RID/raw/$m/olmocr_bench.jsonl 2>/dev/null||echo -)" \
    "$(wc -l < results/runs/$RID/raw/$m/omnidocbench.jsonl 2>/dev/null||echo -)" \
    "$(wc -l < results/runs/$RID/raw/$m/realdoc_qa.jsonl 2>/dev/null||echo -)" \
    "$(wc -l < results/runs/$RID/raw/$m/merged_forms.jsonl 2>/dev/null||echo -)"
done
log "FINALIZE_SCORING_COMPLETE_V2"
