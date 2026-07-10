# Part B — B.2 reader upgrade: local smoke result (Phi-4-mini)

**Date:** 2026-07-09
**Run:** `results/runs/partb-localsmoke` (untracked — ad hoc smoke, not committed; same convention
as the other `smoke-*` run dirs already in this tree).
**Command:**
```
uv run gauntlet run --profile full -m tesseract -b realdoc_qa --run-id partb-localsmoke \
  --max-samples 5 --reader local --phase all
```
(ran in two invocations in practice — `--phase infer` completed instantly with tesseract
predictions, `--phase score` needed a first-time Phi-4-mini weight download, ~7.7GB, which was
slow on this network; both phases are resumable and the run command is idempotent either way.)

## Result

- **Reader identity confirmed:** `microsoft/Phi-4-mini-instruct@cfbefacb99257ffa30c83adab238a50856ac3083`
  in every scored record's `metrics.reader` field — not Qwen2.5-1.5B, confirming the
  `default_local` swap took effect and `--reader local` resolves to the new default.
- **B.2 answers produced:** all 5 samples have a non-empty `metrics.answer` and computed
  `metrics.b2` / `metrics.b2_anls` scores (e.g. `automobile_premium=12800` scored `b2=1.0`).
- **B.1 unaffected:** `metrics.b1` / `metrics.extractive` / `metrics.primary` are populated by the
  existing deterministic B.1 path exactly as before (untouched code) — 4/5 items extractive,
  1/5 correctly excluded (`extractive: false`, `b1: null`, not counted as a failure).
  `status.json` reports `primary_mean: 0.75` = mean of the 4 scored B.1 items
  ((1.0+1.0+1.0+0.0)/4), consistent with the per-record values.
- **Errors:** `{"scored": 5, "errors": 0}` — clean run, `error: null` on every record.
- **GPU teardown:** `nvidia-smi` showed 22 MiB used / 0% util both before and after the run — no
  leaked VRAM, no orphaned vLLM/python processes (`ps aux | grep vllm` empty post-run).
- **Co-load rule honored:** only `realdoc_qa` (Tier B) was scored in this invocation; no Tier-C
  (`merged_forms`) bench was included, so the reader's vLLM engine never had to share the GPU with
  the Tier-C judge's engine.

## Notes

- The Phi-4-mini weight download (2 safetensors shards, 4.9GB + 2.77GB) was slow/bursty on this
  network (~15 minutes with visible stalls) but completed without corruption — verified via
  `hf download` exit + symlink resolution check before scoring. This is an environment/network
  characteristic, not a code issue; once cached, engine load + 5-sample scoring took under a
  minute (see log timestamps 15:22:06–15:22:23).
- No paid API calls were made anywhere in this verification pass (per the Part B scope boundary).
