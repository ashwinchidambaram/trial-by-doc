# Learnings & roadmap

Living document: what building this taught us, and what's worth doing next.
(Append per milestone; date every entry.)

## Engineering learnings (v1 build, 2026-07-07)

1. **Version pins are load-bearing, not paranoia.** Two live examples in one day:
   uv resolved vLLM 0.24 (unverified on sm_120 → pinned back to 0.22.x) and
   transformers 5.13 silently broke dots.ocr's remote-code registration
   (`'str' object has no attribute '__module__'`) — 5.11 works. Rule confirmed:
   pin what you verified, bump deliberately with a re-verification step.
2. **The two-phase split (infer → score) pays for itself immediately.** We re-scored
   gate1 through the container scorer without re-running the model, and the Tier-B/C
   instrument GPU sequencing (7B extractor/judge after OCR models unload) falls out
   for free.
3. **LLM instruments must share engines when pins match.** Extractor and boundary
   judge use the same frozen Qwen2.5-7B pin → one vLLM engine serves both; a second
   co-resident 7B would OOM the 32GB card.
4. **Append-only JSONL + last-record-wins is the right resumability primitive**, but
   every aggregator must dedupe (a --rescore appends; we shipped and fixed a
   double-count bug same-day).
5. **Official scorers differ in hidden config.** The old repo's olmocr numbers used
   SCORER_RENDER_CAP=2 (sampled render tests); uncapped scoring changes pass rates on
   math/table-heavy pages while native tests agree 100/100. When comparing across
   harnesses, compare the *scorer configuration*, not just the scorer.
6. **Degenerate baselines are cheap and clarifying.** PQ correctly zeroes
   every-page/no-boundary strategies that boundary-F1 flatters; pixel-diff (PQ 0.226)
   sets the honest floor and doubles as the seam canary.
7. **Sandbox/process-lifecycle gotchas**: nohup+disown still got reaped when the
   launching shell exited (use harness-tracked background jobs); a `pgrep -f` in a
   watcher matched its own command line and spun forever (make patterns
   self-excluding); `grep` in a logging pipeline block-buffers (use --line-buffered).
8. **Eager sample materialization costs RAM** (~39GB RSS with all four benchmarks'
   images loaded up front). Fine on this box; see roadmap.
9. **OmniDocBench unblock**: the PyPI wrapper needs a GT converter that doesn't
   exist, but the official GitHub pipeline consumes the HF dataset directly.
   When a wrapper stalls, check whether the upstream repo IS the API.

## Future enhancements (candidates, unprioritized)

### Harness
- **Lazy sample loading** (store paths, open images at predict-time) → cut the ~39GB
  RSS spike; enables much larger benchmark caps.
- **Intra-cell concurrency for API models** (the sequential-load constraint is
  GPU-only); config `concurrency: N` per model.
- **`gauntlet verify-env`**: one command that checks GPU capability, pins
  (torch/vLLM/transformers), scorer venvs/images, and dataset revisions against the
  lockfile — the fresh-clone story's missing preflight.
- **Per-run cost & wall-clock report**: aggregate telemetry (latency, VRAM,
  tokens/s, $/page) into the scoreboard as first-class columns → feeds the README
  "cost to self-host" table automatically.
- **Structured resume report**: on resume, print what's done/pending per cell.

### Benchmarks
- **OmniDocBench CDM** via a TeX Live container → restores the official v1.5+
  headline metric (Overall = (100·(1−textED) + TEDS + CDM)/3).
- **RealDoc-Layout lane** (Hungarian F1/mAP) for box-emitting models
  (dots_ocr, deepseek_ocr) — the layout-detection axis is currently unmeasured.
- **merged_forms v2**: add NIST SD6 (hand-printed variant → handwriting robustness),
  CORD/SROIE receipt streams (modern doc type), and page-order shuffling
  (DocSplit-style) as a harder variant. Human spot-check of N=10 boundaries (owner)
  still pending for VALIDATION.md.
- **DocSplit-Mono public comparison lane** (HF amazon/doc_split, CC BY-NC 4.0) —
  positions our custom Tier C against a citable public benchmark.
- **Multi-page Tier B** (all-pages-OCR → concat → extract) — would re-admit DocVQA
  multi-page and mirror real pipelines.

### Models
- **API fleet scoring** when keys land: mistral_ocr + gemini_flash_lite are wired
  (~$3 total for a full run at verified 2026-07 prices); then Textract/Azure/
  Google Doc AI.
- **Azure DI self-hosted container lane** (`deployment: self_hosted_container`,
  localhost endpoint) — the privacy-sensitive deployment option; connected-container
  billing caveat documented in the plan.
- **Native segmenters for Tier C**: Azure custom classifier `splitMode=auto` adapter;
  a cheap embedding-similarity boundary detector as a non-LLM composed alternative
  to the boundary judge.
- **Quantized variants** (AWQ/GPTQ of the 7B leaders) — the production question is
  often "best model that fits on smaller hardware".

### Reporting
- **README auto-refresh workflow**: `gauntlet scoreboard --readme-inject` extended
  with per-tier tables + cost columns; optionally a GitHub Action that regenerates
  README tables from the latest committed run.
- **Confidence intervals**: bootstrap CIs on cell means (n≈100) so per-category
  "winners" carry error bars.
- **Prediction diff viewer**: small HTML page rendering page-image vs two models'
  markdown side-by-side for qualitative review (feeds the example gallery).

### Process
- **Bump-and-verify lane for pins**: scheduled job that tries latest
  vLLM/transformers on a smoke slice and reports drift, so pins don't fossilize.
- **Score-equivalence regression test in CI**: tiny fixture predictions + frozen
  expected scores per scorer, so scorer upgrades can't silently shift numbers.
