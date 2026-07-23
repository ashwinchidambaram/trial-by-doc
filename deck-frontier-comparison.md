# Deck datapoint 2 — frontier hosted models vs the self-host fleet

## Premise correction (important, saves the spend)

The prompt's premise — "the API fleet is wired but has **no scored rows**" — is out of date.
`docs/REFERENCE.md#gaps` predates the frontier runs: the fleet was fully run and scored on
**2026-07-17 → 07-23** under run `run_20260717_095004`, on exactly the four benches the deck
cites, at the same `--max-samples 100` caps as `v1-baseline`. **No new paid run was needed;
new spend for this datapoint: $0.** (A `frontier-v1` re-run would duplicate ~$12 of spend for
identical-methodology data.)

Fleet reality check: the wired + scored hosted models are **gpt-4.1-mini (Azure)**,
**gpt-5.4 (Azure)**, **kimi-k3 (Moonshot)**, and **Mistral OCR** — all provider-pinned via
OpenRouter except Mistral (direct). *Gemini Flash-Lite and Claude (opus-4.7) are wired but
never run (unscored; opus is cost-gated).* If the deck names the fleet, name the four scored ones.

## The table

Scores are B.1 (reader-independent field-value presence) for realdoc columns; olmocr_bench is
the official deterministic scorer. Self-host reference rows from `v1-baseline` +
`docs/REFERENCE.md` cost tables (batched Azure self-host $/1k pages).

| model | realdoc_qa (clean) | light | heavy | heavy retained % | olmocr_bench | $/1k pages |
|---|---|---|---|---|---|---|
| **mistral_ocr** (hosted) | 0.776 | 0.810 | **0.734** | **95%** | 0.696 | $4.00 (flat rate) |
| **kimi_k3** (hosted) | **0.801** | 0.795 | 0.689 | 86% | **0.717** | ~$21.75 |
| **gpt54_azure** (hosted) | 0.765 | 0.767 | 0.582 | 76% | 0.575 | ~$17.49 |
| **gpt41mini_azure** (hosted) | 0.736 | 0.728 | 0.519 | 71% | 0.581 | ~$2.32 |
| olmocr2 (self-host, A100) | 0.689 | 0.657 | 0.514 | 75% | 0.836 | $1.19 |
| lightonocr (self-host, T4) | 0.658 | 0.602 | 0.408 | 62% | 0.675 | $0.18 |
| tesseract (self-host, CPU) | 0.580 | 0.395 | 0.171 | 29% | 0.296 | $0.057 |

Hosted $/1k = measured spend over unique billed pages in the run (deduped by `api_request_id`;
Mistral bills a flat $4/1k). Self-host $/1k = published batched Managed-Compute figures.

## Does any frontier model beat olmOCR-2 on heavy degradation (0.514)?

**Yes — two do, decisively; two are statistical ties.** Paired bootstrap on per-sample B.1
(10k resamples, seed 0, n=90 shared samples — same method as
`findings/statistical-significance.md`):

| vs olmocr2 heavy (0.514) | diff | 95% CI | p (two-sided) | verdict |
|---|---|---|---|---|
| mistral_ocr (0.734) | +0.220 | [+0.129, +0.310] | <0.001 | **real win** |
| kimi_k3 (0.689) | +0.175 | [+0.095, +0.259] | <0.001 | **real win** |
| gpt54_azure (0.582) | +0.068 | [−0.011, +0.148] | 0.097 | **tie** — do not present as a lead |
| gpt41mini_azure (0.519) | +0.005 | [−0.071, +0.083] | 0.900 | **tie** |

So the deck's argument survives contact with the frontier, but must be stated precisely:
**generalist frontier VLMs (both GPTs) do NOT beat the best open-weights self-host model on
degraded scans — only the OCR-specialized hosted services (Mistral OCR, kimi-k3) do.**

## The cost sentence the deck needs

- **Mistral OCR is the interesting one**: +0.220 heavy-degradation B.1 over olmocr2 at
  $4.00/1k vs $1.19/1k — ~3.4× the self-host cost for a large, significant robustness gain
  and no GPU fleet to run.
- **gpt-5.4 is the cautionary one**: ~$17.49/1k — **~15× olmocr2's cost for a statistical
  tie on heavy scans and a *worse* olmocr_bench score (0.575 vs 0.836).** Say that plainly.
- kimi-k3 wins clean extraction (0.801) and heavy robustness significantly, but at ~$21.75/1k
  — ~18× olmocr2 — and its weights/license are unpublished until 2026-07-27.
- gpt-4.1-mini at ~$2.32/1k is price-competitive but ties olmocr2 on heavy and loses clean.

## Caveats the deck must carry

1. **Not byte-reproducible.** Hosted models can't be revision-pinned or seeded. Every record
   stamps the serving provider, API model id, request id, and call date
   (`run_20260717_095004` manifest + per-row telemetry); pins: gpt-* → Azure via OpenRouter
   (`allow_fallbacks: false`), kimi → Moonshot, Mistral direct. Called 2026-07-17 (gpt-4.1-mini,
   mistral) and 2026-07-22/23 (gpt-5.4, kimi-k3).
2. **Run-id differs from the prompt's `frontier-v1`** — the data lives in
   `run_20260717_095004` (plus `run_20260717_095004-b2-gpt5mini` for B.2). Same caps, same
   benches, same scorers as v1-baseline.
3. Hosted $/1k reflects these documents at 1540px renders with 4096-token output caps —
   it scales with page density, unlike flat-rate Mistral / fixed-throughput self-host.
4. gpt-5.4 carries one unresolved error row (0.5% of omnidocbench, empty completions across
   retries); all other cells are complete. kimi-k3 was a zero-error run.
