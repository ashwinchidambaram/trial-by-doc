# Reference

Detail moved out of the main [README](../README.md) to keep it skimmable: the full
model roster with license/cost detail, and the complete list of known limitations.
See the README's [Bottom line](../README.md#bottom-line) and
[Scores](../README.md#scores) for the actual results and takeaways.

**Contents:** [Models](#models) · [Gaps](#gaps)

## Models

All wired via one adapter + one registry entry (`configs/models.yaml`). Usage rights
verified against the live model cards / provider terms at pin time (re-verify before
you rely on them — licenses move).

| Model | Params | Runs via | License | Commercial use | Declared specialty |
|---|---|---|---|---|---|
| [olmOCR-2](https://huggingface.co/allenai/olmOCR-2-7B-1025) | 7B | vLLM (local) | Apache-2.0 | ✅ | purpose-built OCR |
| [Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) | 7B | vLLM (local) | Apache-2.0 | ✅ | general VLM, strong tables |
| [GOT-OCR 2.0](https://huggingface.co/stepfun-ai/GOT-OCR-2.0-hf) | 580M | transformers (local) | Apache-2.0 | ✅ | small OCR specialist |
| [dots.ocr](https://huggingface.co/rednote-hilab/dots.ocr) | 1.7B | vLLM (local) | MIT | ✅ | layout JSON (bbox+category), tables |
| [PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) | 0.9B | vLLM (local) | Apache-2.0 | ✅ | element-level OCR |
| [DeepSeek-OCR](https://huggingface.co/deepseek-ai/DeepSeek-OCR) | 3B | vLLM (local) | MIT | ✅ | markdown + grounding boxes |
| [granite-docling](https://huggingface.co/ibm-granite/granite-docling-258M) | 258M | transformers (local) | Apache-2.0 | ✅ | DocTags → markdown, tiny |
| [LightOnOCR](https://huggingface.co/lightonai/LightOnOCR-1B-1025) | 1B | vLLM (local) | Apache-2.0 | ✅ | distilled OCR, math |
| [Gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) | 4.5B-eff | vLLM (local) | Apache-2.0† | ✅ | general multimodal; OCR, doc/PDF parsing, handwriting, charts |
| [Kosmos-2.5](https://huggingface.co/microsoft/kosmos-2.5) | 1.3B | transformers (local) | MIT | ✅ | dense document OCR → markdown (`<md>` task) |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | classic engine | pytesseract (CPU) | Apache-2.0 | ✅ | classic OCR; plain text; weak on tables/multi-column |
| [docTR](https://github.com/mindee/doctr) | classic engine | PyTorch (CPU/GPU) | Apache-2.0 | ✅ | modern classic OCR (Mindee, det+reco); word-level boxes |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | classic engine | ONNXRuntime (CPU) | Apache-2.0 | ✅ | modern classic OCR (PP-OCR-derived); CPU-only on this box |
| [EasyOCR](https://github.com/JaidedAI/EasyOCR) | classic engine | PyTorch (CPU/GPU) | Apache-2.0 | ✅ | modern classic OCR (JaidedAI, CRAFT+CRNN); line-level boxes |
| Mistral OCR | API | Mistral API | API terms | ✅ | purpose-built OCR API, native markdown ($0.004/page, verified 2026-07-07) — **scored** (`run_20260717_095004`) |
| GPT-4.1-mini / GPT-5.4 | API | Azure via OpenRouter (pinned, no-fallback) | API terms | ✅ | generalist frontier VLMs — **scored** (`run_20260717_095004`) |
| Kimi-K3 | API | Moonshot via OpenRouter (pinned) | weights license unpublished until 2026-07-27 | ❌ re-check 07-27 | reasoning VLM run with reasoning disabled — **scored** (`run_20260717_095004`) |
| Gemini Flash-Lite | API | Google API | API terms | ✅ | cheapest credible VLM baseline (~$0.0005/page est.); wired, unscored |
| Claude (opus-4.7) vision | API | Azure via OpenRouter | API terms | ✅ | adapter built; unscored (cost-gated: full matrix breaches the $10/model cap) |

† Gemma-4 ships under **Apache-2.0** per its HF model card and API metadata (verified live
2026-07-08, `google/gemma-4-E4B-it` @ `fee6332`) — a departure from the custom *Gemma Terms of
Use* that governed earlier Gemma releases. Confirm against the model card before you rely on it.

**Self-host cost — Azure AI Foundry Managed Compute** (per-GPU-VM-hour billing; the service
that hosts arbitrary open-weights models, *not* Azure Document Intelligence). Per model we pick
the smallest GPU SKU that fits its parameter footprint, then compute cost = SKU $/hr ÷ pages/hr.
We publish **both** a single-stream figure (conservative) and a batched figure (vLLM continuous
batching, measured N=24). Prices are on-demand, region-dependent, **verified 2026-07-08** via
Vantage/CloudPrice: **T4-16GB ≈ $0.53/hr** (≤3B models), **A100-80GB ≈ $3.67/hr** (7–8B models).

| Model | SKU | $/1k pages (single-stream) | $/1k pages (batched) |
|---|---|---|---|
| paddleocr_vl | T4-16GB | $0.52 | $0.13 |
| lightonocr | T4-16GB | $0.63 | $0.18 |
| got2 | T4-16GB | $0.78 | — (transformers backend) |
| granite_docling | T4-16GB | $0.81 | — (transformers backend) |
| dots_ocr | T4-16GB | $0.87 | $0.11 |
| deepseek_ocr | T4-16GB | $0.97 | $0.11 |
| qwen25vl | A100-80GB | $7.85 | $1.38 |
| olmocr2 | A100-80GB | $8.67 | $1.19 |
| gemma4 | A100-80GB | $10.60 | $1.08 |

> ⚠️ **Read these as a same-hardware relative comparison, not an Azure invoice.** Throughput is
> measured on our **RTX 5090**; a T4 or A100 runs slower, so real Azure $/page will be **higher** —
> these are optimistic floors that correctly rank models by cost-efficiency and show the ~7–10×
> gain from batching and the ~10× gap between T4-class (≤3B) and A100-class (7–8B) hosting.
> got2/granite run the transformers backend (no vLLM continuous batching), so only single-stream is
> given. Re-pin SKU prices + region before quoting. API rows carry the exact resolved model version
> + called-on date (remote models drift; we stamp it honestly).

## Gaps

Honest limitations, current as of the v1 baseline:

- **API lanes: LANDED (2026-07-17 → 07-23).** Four hosted models are fully scored in
  `run_20260717_095004` at the v1 caps — Mistral OCR, GPT-4.1-mini, GPT-5.4 (both
  Azure-pinned via OpenRouter), and Kimi-K3 — including both Tier-D scanned benches and a
  gpt-5.4-mini B.2 rescore. Measured spend per 1k pages (deduped by request id): Mistral
  $4.00 flat, gpt-4.1-mini ~$2.32, gpt-5.4 ~$17.49, kimi ~$21.75. Full grid:
  `docs/leaderboard.md`. Still unscored: Gemini Flash-Lite (wired) and opus-4.7 (wired,
  cost-gated). The 14-model local scoreboard and cost tables above are unchanged.
- **DocVQA / DocBench not included**: DocVQA's visual-spatial questions measure the
  extractor, not the OCR (deferred with cause); DocBench requires an LLM judge —
  excluded by the no-judge rule.
- **OmniDocBench CDM excluded** (formula render metric needs TeX Live in a container);
  we report the official edit-distance + TEDS set and flag `cdm_excluded` per row.
- **RealDoc-Layout not wired** (box-emitting models only; optional lane).
- **API fleet partially scored** (updated 2026-07-23): Mistral OCR + GPT-4.1-mini + GPT-5.4 +
  Kimi-K3 are scored (`run_20260717_095004`; no API rows in `v1-baseline` itself — the
  cross-run leaderboard merges them). Gemini Flash-Lite and opus-4.7 remain wired-but-unscored;
  Textract/Azure/Google Doc AI lanes are designed, not wired. API rows are not
  byte-reproducible (no revision pin/seed) — each stamps provider, model version, request id,
  and call date.
- **Florence-2 and Phi-4-multimodal adapters are built but unregistered** — blocked on the
  pinned **transformers 5.11** (distinct pre-v5 remote-code incompatibilities per model). Kept
  out of `configs/models.yaml` (commented block, see each adapter's docstring) and out of the
  scored roster. Revisit only if upstream ports them to native v5.
- **granite_docling OOMs on Tier C** (`merged_forms`) — shown as `—` in the scoreboard;
  deferred rather than forced through, not a bug to chase blindly.
- **merged_forms is synthesized** (no public dataset covers the similar-forms case —
  verified against the PSS literature and HF). Mitigations: public-domain source
  data, seeded determinism, published floor rows, seam canary, VALIDATION.md. Its
  `custom` provenance is labeled on every scoreboard.
- **Tier B/C instrument coupling**: extractor and boundary-judge quality bound what
  those tiers can see. Both are frozen and identical across models — comparisons are
  fair; absolute values are lower bounds.
- **Statistical power**: per-category cells are small (n≈14–25); treat per-category
  winners as directional, not definitive.
- **Output-token budgets are not equalized**: most vLLM models cap generation at 4096
  tokens/page, but dots_ocr runs at 16000 and deepseek_ocr at 8192 (their cards' recipes).
  The 4096 cap demonstrably binds on dense newspaper pages (see
  findings/v1-interim-analysis.md §sanity-flags), so part of dots_ocr's OmniDocBench lead
  is budget headroom, not parse skill. More broadly, comparisons are *recipe-vs-recipe*
  (each model at its card-recommended resolution/prompt/token budget), not same-input.
- **Developer-affiliated benchmarks** (now marked on the scoreboard — a `⚠
  Developer-affiliated` footnote is rendered under the injected table, driven by
  `affiliated_models` in `configs/benchmarks.yaml`):

  | benchmark | affiliated model(s) | kind | verified |
  |---|---|---|---|
  | olmocr_bench (Allen AI) | olmocr2 | same lab | repo Attributions |
  | omnidocbench (opendatalab) | dots_ocr, paddleocr_vl | report SOTA on their model cards | live-fetched 2026-07-12 |

  Same-lab coupling (olmocr2 ↔ olmocr_bench) and train/select-toward-benchmark coupling
  (dots.ocr, PaddleOCR-VL ↔ OmniDocBench) are standard OCR-eval confounds. Cross-benchmark
  agreement mitigates but does not remove them: olmocr2 also leads the *unaffiliated*
  RealDoc B.1 group, so its standing isn't an artifact of its home bench. Interpret an
  affiliated model's score *on its own bench* with that caveat.
- **API readers are stamped, not frozen**: the gpt-5.4-mini / haiku B.2 reader rungs run
  temp=0 with identity + pricing stamped per record, but cannot be revision-pinned or
  seeded through OpenRouter — unlike the local instruments, byte-exact reproduction of
  those columns months later is not guaranteed.
- **Confidence intervals are computed on demand, not on the scoreboard face**: cells are
  means of ~15–100 samples. Paired bootstrap CIs (`gauntlet scoreboard --ci A,B`,
  `src/tbdoc/report/stats.py`) show that on RealDoc B.1 at n=90, **gaps below ~0.10 are
  within noise** — the entire B.1 top four ties, as does the B.2 leading trio (see
  [findings/statistical-significance.md](../findings/statistical-significance.md)). Coarse
  structure (leaders vs. mid-pack) is significant; fine adjacent-rank ordering is not. The
  scoreboard still prints point means; read close ranks as ties.
