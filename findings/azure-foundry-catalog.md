# Azure Foundry frontier models — catalog, pricing, and how we reach them

Research + wiring log for adding frontier API models to the gauntlet. Owner asked to
compare frontier models "available through Azure Foundry," including batched vs.
non-batched pricing. Dates on every claim; unverified items are called out explicitly.

## TL;DR

- We reach the Azure-hosted frontier models through the **OpenRouter gateway, pinned to
  the `azure` serving provider** — one `OPEN_ROUTER_API_KEY`, no per-vendor procurement,
  and the row honestly reads "Azure Foundry, via OpenRouter." (`OpenRouterVisionAdapter`.)
- **Batch is reported, never paid.** OpenRouter is real-time only. Azure's 50%-off Global
  Batch is computed as a *projection* from measured tokens × Azure's published batch rate.
- **Running now (2026-07-17):** `gpt41mini_azure` (~$1.35) + `mistral_ocr` (~$2.26), full
  v1. Both smoke-passed 10/10. `gpt54_azure` and `opus47_azure` are wired but **deferred**
  — each breaches the $10/model cap on the full matrix (see costs below).
  **SUPERSEDED 2026-07-22/23:** `gpt54_azure` and `kimi_k3` have since run and scored on the
  3 core benches + Tier D (Tier C dropped fits the cap) — see "RESULTS — frontier completion"
  below. Only `opus47_azure` remains deferred.
- **Mistral OCR is NOT on OpenRouter** — it needs a direct `MISTRAL_API_KEY`.

## The Azure Foundry batch constraint (research 2026-07-16)

Azure Global Batch: **50% off standard, 24h turnaround, separate enqueued quota, SKU
`GlobalBatch`.** The catch that shaped the whole plan: the batch-eligible model list is
**closed and lags the frontier** — it tops out at **GPT-5.4** and excludes the GPT-5.5 and
GPT-5.6 series. So "newest model" and "half price" are mutually exclusive on Foundry.

We considered building a two-phase submit/poll/reconcile batch lane and **rejected it**:
it's a real rewrite to save ~50% on a run that already costs single-digit dollars. Instead
we **report** the batch figure — measure real token counts via OpenRouter, multiply by
Azure's published standard AND batch rates, and print both columns. Zero batch spend, and
the projection is defensible because (see pricing) OpenRouter list == Azure Global Standard
for the OpenAI models.

## Why OpenRouter, pinned (not Azure SDK directly)

OpenRouter **multiplexes**: `anthropic/claude-opus-4.7` alone is served by Amazon Bedrock,
Anthropic, Google AND Azure — **7 endpoints, verified 2026-07-16**. Unpinned, each row of a
scored run could come from a different host and the fingerprint would be a lie.

`or_provider` in `configs/models.yaml` pins the serving host with
`allow_fallbacks: false` — the call **fails** rather than silently rerouting, and
`fingerprint()` stamps `or_provider` on every row. Pinning `or_provider: azure` is what
makes the "Azure Foundry" claim honest. Slug is lowercase `azure` (verified via
`/api/v1/providers`, 2026-07-16); region variants exist (`azure/swedencentral`).

**Ollama was ruled out** — it can't run closed frontier weights, and it's redundant with
the existing vLLM local lane.

## Pricing (per Mtok in / out, USD)

OpenRouter list price **equals Azure Global Standard** for the OpenAI-family models, which
is what makes the Azure projection nearly trivially defensible.

| Model | api_model_id | Standard in/out | Batch (−50%) | Source / verified |
|---|---|---|---|---|
| gpt-4.1-mini | `openai/gpt-4.1-mini` | $0.40 / $1.60 | $0.20 / $0.80 | OpenRouter catalog, 2026-07-16 |
| gpt-5.4 | `openai/gpt-5.4` | $2.50 / $15.00 | $1.25 / $7.50 | OpenRouter catalog, 2026-07-16 |
| claude-opus-4.7 | `anthropic/claude-opus-4.7` | $5.00 / $25.00 | n/a¹ | OpenRouter catalog, 2026-07-16 |
| mistral-ocr-4-0 | `mistral-ocr-4-0` | **$0.004 / page** | — | mistral.ai/pricing/api, 2026-07-17 |

¹ Claude batch on Azure uses opaque CCU (compute-credit-unit) pricing, not a clean −50% —
left out rather than guessed.

## Full-v1 cost (fixed cost-guard estimator, v1 caps: 100/100/100/15 → 564 pages/model)

| Model | olmocr | omnidoc | realdoc | merged | **Total** | vs $10 cap |
|---|---|---|---|---|---|---|
| gpt41mini_azure | $0.24 | $0.24 | $0.09 | $0.78 | **$1.35** | ✅ |
| mistral_ocr | $0.40 | $0.40 | $0.15 | $1.30 | **$2.26** | ✅ |
| gpt54_azure | $2.00 | $2.00 | $0.76 | $6.52 | **$11.28** | ❌ over |
| opus47_azure | $3.50 | $3.50 | $1.33 | $11.41 | **$19.74** | ❌ over |

Note: **Tier C (merged_forms) is ~58% of spend** for the expensive models — on the tier
where the README shows every VLM scoring below the trivial pixel-diff floor. Dropping
Tier C puts gpt54 and opus47 under the cap; that decision is **owner-gated, not yet made**.

The cost-guard estimator itself had a bug (counted samples, not page inferences) that
under-quoted API runs by **1.79×** — found and fixed via TDD this session
(`_count_samples`, `tests/test_cost_estimate.py`).

## Published frontier benchmark scores — essentially unusable as scoreboard rows

Owner asked whether frontier models already have published scores on our benchmarks. Found
very little, and none we can honestly put in the table:
- **olmOCR-Bench:** only **Mistral OCR 72.0** is published — and that was an *older* Mistral
  OCR release, not the OCR-4 we're measuring, so it's not even a clean self-comparison.
- **OmniDocBench v1.7:** has GPT-5.2 and Gemini rows but **no Claude / no Llama**.

Why they can't be scoreboard rows: bench revisions have moved; carried-forward rows are
undated; unpinned serving endpoints; and model-authored-test contamination risk. They stay
as *external context*, never as rows stamped with our provenance.

## Mistral OCR pin (verified 2026-07-17)

`/v1/models` resolves three names to the **same** OCR-4 model:
`mistral-ocr-latest` (floats to OCR 5) = `mistral-ocr-4` (floats to 4.x) =
**`mistral-ocr-4-0`** (concrete 4.0 pin — what we use). No dated YYMM snapshot exists for
OCR 4 yet (OCR 3 has `mistral-ocr-2512`); `-4-0` is the most-pinned id available.
`_api_version` still stamps whatever the API resolves, per call.

## UNVERIFIED — re-check before publishing any Azure-Foundry claim

- **Foundry availability of Claude Opus 4.7 AND 4.8 is UNCONFIRMED.** `opus47_azure` carries
  a warning comment in `models.yaml`. Opus 4.8 is on OpenRouter at the identical $5/$25
  (strictly newer, same price) — but neither's presence in an actual Azure Foundry
  deployment is confirmed.
- Whether OpenRouter's `azure` provider maps to the **exact** Azure Foundry region/deployment
  an owner would provision (region variants exist). The pin makes the host honest; it does
  not prove it's *your* tenant.
- Microsoft Learn docs returned **stale mixed-vintage content** (headlined GPT-4o/o3-mini as
  current in July 2026) — do not trust MS Learn for the live catalog; use the provider
  pricing pages and the live OpenRouter catalog.

## Status (2026-07-17)

- Wired: `gpt41mini_azure`, `gpt54_azure`, `opus47_azure` (OpenRouter+azure pin), `mistral_ocr` (direct).
- Smoke 10/10: `gpt41mini_azure`, `mistral_ocr`.
- Running full v1: `gpt41mini_azure` + `mistral_ocr`.
- Deferred (owner decision on cap vs. dropping Tier C): `gpt54_azure`, `opus47_azure`.

## RESULTS — run `run_20260717_095004` (2026-07-17)

Full v1 gauntlet, both models, all four tiers. 507 scored samples, **0 error rows**.

### Scoreboard (B.1 is the Tier-B headline; reader-independent)

| model | olmocr_bench | omnidocbench | realdoc_qa (B.1) | merged_forms (Tier C) |
|---|---|---|---|---|
| gpt41mini_azure | **0.571** | 0.745 | 0.736 | 0.082 |
| mistral_ocr | 0.407 | **0.868** | **0.776** | 0.079 |

- ⚠ **The mistral olmocr 0.407 above is WRONG** — a 5/100-sample partial score; and with it the
  "gpt-4.1-mini leads olmocr" read. See the CORRECTION in the frontier-completion section below
  (real value 0.696; kimi-k3 leads olmocr). gpt-4.1-mini's 0.571 also moved to **0.581** after a
  silent-empty page was re-inferred (see the incident note below).
- Mistral OCR (purpose-built) leads on omnidocbench and realdoc-B.1; gpt-4.1-mini leads on olmocr_bench.
- **Tier C ≈ 0.08 for both** — consistent with the standing README finding that every VLM scores
  below the trivial pixel-diff floor on segmentation. Confirmed, not worth its cost for API models.

### Tier-B B.2 dual-reader (comprehension ceiling; B.2 is explicitly secondary)

| model | B.2 exact (Phi-4-mini, local) | B.2 exact (gpt-5.4-mini) | B.2 ANLS (gpt-5.4-mini) |
|---|---|---|---|
| gpt41mini_azure | 0.210 | **0.590** (2.8×) | 0.878 |
| mistral_ocr | 0.180 | **0.590** (3.3×) | 0.920 |

- gpt-5.4-mini rescore is an **isolated run** (`run_20260717_095004-b2-gpt5mini`); primary run's Phi-4
  B.2 untouched. Matches the `v1-b2-gpt5mini` methodology so these two slot into that table.
- **Same-vendor caveat (gpt-4.1-mini × OpenAI reader):** flagged as a potential family-bias risk.
  The data shows **no inflation** — the two models tie on B.2 exact (0.590) and Mistral is *higher*
  on ANLS (0.920 vs 0.878). If OpenAI-family favoritism were present, gpt-4.1-mini would have pulled
  ahead; it didn't. Caveat stands methodologically; empirically not observed here.
- **API-reader reproducibility caveat (unchanged):** gpt-5.4-mini via OpenRouter is temp=0 and
  stamped but not revision-pinnable/seedable → that column is not byte-reproducible. Phi-4 local is.

### Spend (actual)

| item | actual | vs estimate |
|---|---|---|
| gpt41mini_azure inference (626 page-calls) | $2.26 | est $1.35 — **1.7× over** |
| mistral_ocr inference (626 page-calls @ $0.004) | $2.50 | est $2.26 — on-model |
| gpt-5.4-mini B.2 rescore (~200 reader calls) | ~$2 (not stamped; ladder rate ~$0.01/call) | — |
| **total exercise** | **~$6.8** | both models well under $10/model cap |

- **gpt-4.1-mini ran 1.7× over estimate**, driven almost entirely by **merged_forms token truncation**:
  52% of Tier C form pages hit the 4096 `max_completion_tokens` cap (~4× the estimator's assumed
  1000 out-tokens/page). Live evidence for the `token-cap v2` owner-gated item: negligible on prose
  (olmocr/omnidoc truncated 2–9%), severe on dense forms. Mistral is flat per-page so immune.

### Operational finding — score-phase engine co-residence crash (worked around, not yet code-fixed)

A single `run --phase score` over benches that need BOTH a Tier-B reader (Phi-4-mini) AND the Tier-C
boundary_judge (Qwen-7B) **crashes**: both vLLM engines request `gpu_memory_utilization=0.90`
(`boundary_judge.py:58`, `vllm_extractor.py:66`), so the second engine finds ~1 GiB free on the 31 GiB
card and dies with `EngineCore failed … Free memory … less than desired`. Reader≠judge model → no
engine sharing. **Workaround (no code change):** split scoring into two invocations —
`-b olmocr_bench,omnidocbench,realdoc_qa` then `-b merged_forms` — so only one 0.90 engine is resident
at a time. v1-baseline must have been scored tier-by-tier for the same reason. **Candidate code fix
(owner):** sequence-and-unload the reader before the judge, or lower the instruments' util so two fit.

### Status (2026-07-17 — superseded by the frontier-completion section below)

- **Done & scored:** `gpt41mini_azure`, `mistral_ocr` — all four tiers, both B.2 readers.
- **Deferred (owner):** `gpt54_azure`, `opus47_azure` (cap vs. drop-Tier-C); `token-cap v2`;
  the score-phase co-residence code fix.

## RESULTS — frontier completion, runs of 2026-07-22/23 (same run-id `run_20260717_095004`)

`gpt54_azure` (Azure-pinned via OpenRouter) and `kimi_k3` (moonshotai-pinned, reasoning disabled)
ran the 3 agreed benches + both Tier-D scanned benches; Tier D also backfilled for the 07-17 pair.
Tier C stays deferred for the frontier pair (below-floor tier, cost not justified).

### Scoreboard (B.1 headline; full grid in docs/leaderboard.md + HTML artifact)

| model | olmocr | omnidoc | realdoc B.1 | scanned_light | scanned_heavy | heavy retention |
|---|---|---|---|---|---|---|
| kimi_k3 | **0.717** | 0.849 | **0.801** | 0.795 | 0.689 | 86% |
| mistral_ocr | 0.696 | **0.868** | 0.776 | **0.810** | **0.734** | **95%** |
| gpt54_azure | 0.575 | 0.803 | 0.765 | 0.767 | 0.582 | 76% |
| gpt41mini_azure | 0.581 | 0.745 | 0.736 | 0.728 | 0.519 | 71% |

- **CORRECTION to the 07-17 table above:** mistral olmocr_bench is **0.696**, not 0.407 — the
  original score pass covered only 5/100 of its olmocr samples (status.json `done: 5`); the
  07-22 completion scored the remaining 95. The 07-17 claim "gpt-4.1-mini leads olmocr" is
  therefore wrong; kimi-k3 leads, mistral second.
- **kimi_k3 was the only zero-error run** (500/500 after a one-page gateway-hiccup sweep).
  gpt-5.4 carries one permanent honest error row: an omnidocbench Chinese-textbook page that
  returned `empty completion (finish_reason=stop)` across 2×5 retry attempts (content filter
  suspected; the artifact stamps only the empty completion, not a filter verdict).
- B.2 (gpt-5.4-mini reader, isolated `-b2-gpt5mini` run): kimi 0.630, mistral/gpt-4.1-mini 0.590,
  gpt-5.4 0.570 — again no same-vendor inflation (the OpenAI reader ranks gpt-5.4 last).
- **Silent-empty incident (caught by the 2026-07-23 verification review):** gpt-4.1-mini's
  07-17 olmocr cell contained ONE non-error row with empty markdown (`0097571b…page_7_pg1.pdf`,
  no retries) — inferred before the retry-on-empty guard existed, i.e. exactly the failure
  class that guard now catches. Page re-inferred + cell rescored 2026-07-23:
  olmocr **0.571 → 0.581**. All 22 prediction files re-audited: zero other silent-empties.

### Spend (actual, OpenRouter balance deltas)

Whole frontier exercise (gpt-5.4 full, kimi full, Tier-D backfill ×2 models, sweeps, B.2 rescore):
**≈ $12.2** ($16.92 → $4.74). kimi ≈ $6.6 actual vs $6.59 estimate (deduped by `api_request_id`;
raw per-row telemetry sums read ~1.7× higher because memoized realdoc pages duplicate one call's
telemetry across QA rows — 99 duplicated request-ids spanning 284 rows). All under the $10/model cap.

### Operational finding — co-residence has a HOST-RAM flavor too (OOM incident 2026-07-22 20:35)

Each `gauntlet run` **materializes every requested bench's page images in host RAM up front**
(`matrix.py` builds `bench_samples` for all benches before phase dispatch) — ~38–46 GB for the
5-bench set on a 61 GB host. Running a second gauntlet concurrently (kimi infer + sweep/score
chain) triggered the kernel OOM killer, which killed the kimi run mid-bench (SIGKILL: no traceback,
buffered stdout lost; append-only predictions survived, resume lost nothing). **Rule: one gauntlet
process at a time — API-vs-GPU parallelism does not make it safe.** Candidate code fix (owner):
lazy page loading, or materialize only benches with pending work on resume.
