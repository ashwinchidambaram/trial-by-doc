# trial-by-doc ⚖️

**An OCR / document-intelligence model gauntlet.** Wire in any model — a classic
CPU OCR engine, a local open-weights VLM, a commercial doc-AI API, or a frontier
VLM — and run it through a three-tier benchmark gauntlet with **deterministic,
automatic scoring**. Built to answer one question honestly: *which model should you
trust to parse your documents?* The roster spans the full cost/quality spectrum, from
a CPU engine that costs cents per thousand pages to a 7B VLM on an A100.

- **Tier A — parse fidelity**: is the OCR output actually correct? (unit tests, edit distance, TEDS)
- **Tier B — downstream extraction**: is it good enough to extract fields from? (exact match, ANLS)
- **Tier C — document segmentation**: can it split a PDF that is really 3–4 merged documents? (boundary F1, PQ, STP)

No LLM-as-judge anywhere. Every score is a deterministic algorithm; the only LLMs in
the measurement path are **frozen instruments** (pinned revision, temp=0, seeded,
identical for every model) and the scoreboard marks where they're used.

**Contents:** [Scores](#scores) · [Benchmarks](#benchmarks) · [Scanned/faxed robustness](#scanned-and-faxed-robustness-tier-b-under-degradation) · [Example documents](#example-documents) · [Models](#models) · [What the harness is](#what-the-harness-actually-is) · [Setup](#setup) · [Hardware](#hardware) · [Gaps](#gaps) · [Credits](#attributions--credits)

## Scores

> These numbers come from the `v1-baseline` run and are reproducible from its per-sample
> records; regenerate the table any time with `gauntlet scoreboard --run-id v1-baseline`.
>
> **New here?** The columns below are per-tier primary scores — skim
> [Benchmarks](#benchmarks) first for what Tier A / B / C actually measure, then the numbers
> read straight. Higher is better everywhere; `—` means not applicable to that model.

<!-- SCOREBOARD:BEGIN -->
| model | realdoc_qa | omnidocbench | olmocr_bench | merged_forms |
|---|---|---|---|---|
| deepseek_ocr | 0.469 | 0.820 | 0.704 | 0.051 |
| easyocr | 0.583 | 0.483 | 0.162 | 0.397 |
| tesseract | 0.580 | 0.507 | 0.296 | 0.330 |
| lightonocr | 0.658 | 0.726 | 0.675 | 0.142 |
| paddleocr_vl | 0.542 | 0.660 | 0.345 | 0.063 |
| rapidocr | 0.499 | 0.642 | 0.163 | 0.258 |
| doctr | 0.682 | 0.511 | 0.185 | 0.336 |
| qwen25vl | 0.637 | 0.736 | 0.701 | 0.018 |
| granite_docling | 0.035 | 0.103 | 0.179 | — |
| gemma4 | 0.564 | 0.706 | 0.414 | 0.157 |
| olmocr2 | 0.689 | 0.828 | 0.836 | 0.070 |
| dots_ocr | 0.549 | 0.897 | 0.734 | 0.006 |
| got2 | 0.175 | 0.638 | 0.304 | 0.040 |
| kosmos25 | 0.565 | 0.539 | 0.259 | 0.204 |

_4199 scored samples · run: v1-baseline_

### Tier-B — extraction (B.1) vs comprehension (B.2)

| model | B.1 extract | coverage | B.2 comp | reader |
|---|---|---|---|---|
| deepseek_ocr | 0.469 | 90/100 | 0.080 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| easyocr | 0.583 | 90/100 | 0.090 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| tesseract | 0.580 | 90/100 | 0.110 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| lightonocr | 0.658 | 90/100 | 0.130 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| paddleocr_vl | 0.542 | 90/100 | 0.090 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| rapidocr | 0.499 | 90/100 | 0.060 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| doctr | 0.682 | 90/100 | 0.100 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| qwen25vl | 0.637 | 90/100 | 0.140 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| granite_docling | 0.035 | 90/100 | 0.000 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| gemma4 | 0.564 | 90/100 | 0.050 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| olmocr2 | 0.689 | 90/100 | 0.130 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| dots_ocr | 0.549 | 90/100 | 0.130 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| got2 | 0.175 | 90/100 | 0.010 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |
| kosmos25 | 0.565 | 90/100 | 0.070 | Qwen/Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306 |

### Performance — time per page, VRAM, $/page (per-sample telemetry)

| model | median s/page | mean s/page | p90 s/page | peak VRAM | $/page |
|---|---|---|---|---|---|
| deepseek_ocr | 10.13 | 18.96 | 47.9 | 29.9 GB | — |
| easyocr | 2.2 | 2.17 | 3.32 | 5.7 GB | — |
| tesseract | 1.93 | 1.93 | 2.73 | — (API) | — |
| lightonocr | 5.57 | 6.42 | 10.07 | 29.0 GB | — |
| paddleocr_vl | 6.15 | 9.49 | 17.79 | 29.3 GB | — |
| rapidocr | 2.21 | 2.19 | 2.73 | — (API) | — |
| doctr | 1.82 | 1.72 | 2.61 | — (API) | — |
| qwen25vl | 10.78 | 14.19 | 41.26 | 28.8 GB | — |
| granite_docling | 5.14 | 36.01 | 96.78 | 1.0 GB | — |
| gemma4 | 14.03 | 15.6 | 22.73 | 29.8 GB | — |
| olmocr2 | 13.69 | 15.8 | 40.95 | 28.8 GB | — |
| dots_ocr | 7.91 | 20.77 | 78.51 | 31.1 GB | — |
| got2 | 3.39 | 4.14 | 9.09 | 3.5 GB | — |
| kosmos25 | 4.71 | 4.95 | 8.92 | 6.8 GB | — |

### Cost — classic OCR engines, CPU-VM vs GPU-VM

| engine | device | SKU | pages/hr | $/1k pages |
|---|---|---|---|---|
| tesseract | CPU-VM | AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU) | 3006 | $0.057 |
| rapidocr | CPU-VM | AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU) | 1214 | $0.140 |
| doctr | CPU-VM | AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU) | 983 | $0.173 |
| doctr | GPU-VM | AWS EC2 g5.xlarge (1x NVIDIA A10G, 24 GiB) | 24328 | $0.041 |
| easyocr | CPU-VM | AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU) | 43 | $3.953 |
| easyocr | GPU-VM | AWS EC2 g5.xlarge (1x NVIDIA A10G, 24 GiB) | 2300 | $0.437 |

> ⚠️ **Read as a same-hardware relative comparison, not a cloud invoice** (same caveat as the Azure Foundry table above). Throughput is single-stream on our **RTX 5090** ([findings/ws1-cpu-engines.md](findings/ws1-cpu-engines.md)); a real cloud CPU-VM or GPU-VM is slower, so actual $/page will be **higher** — these are optimistic floors. Batched throughput would lower $/page further (not measured for classic engines). SKU prices verified **2026-07-09** via Vantage (on-demand, us-east-1, Linux): [AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU)](https://instances.vantage.sh/aws/ec2/c6i.xlarge) $0.17/hr · [AWS EC2 g5.xlarge (1x NVIDIA A10G, 24 GiB)](https://instances.vantage.sh/aws/ec2/g5.xlarge) $1.006/hr. Re-pin SKU prices + region before quoting.

<!-- SCOREBOARD:END -->

## Benchmarks

| Benchmark | Tier | Provenance | What it tests | Why we test it |
|---|---|---|---|---|
| [olmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench) | A | official | Per-page **unit tests**: text present/absent, reading order, math (KaTeX render), tables — across 7 doc categories incl. old scans | The broadest "did you transcribe this correctly" signal; scans + multi-column are production reality |
| [OmniDocBench](https://github.com/opendatalab/OmniDocBench) | A | official | Full-page parse quality: text/formula/table **edit distance**, **TEDS** table structure, over 10 document sources | The industry-standard parse-fidelity metric set |
| [RealDoc-Bench QA](https://huggingface.co/datasets/Extend-AI/RealDoc-Bench) | B | official | **Field extraction** from business docs (finance, medical, mortgage, supply-chain): markdown → frozen extractor → exact-match/ANLS | The closest proxy for "extract data from PDFs without mistakes" — the production task itself |
| [merged_forms](benchmarks/custom/merged_forms/VALIDATION.md) | C | **custom** | **Document segmentation**: streams of 3–4 concatenated NIST SD2 tax submissions — same form faces, different filled data; boundaries only detectable by content | The hard production case: splitting merged PDFs of look-alike forms. No public benchmark covers it (we verified) |

#### How Tier B works — extraction (B.1) vs comprehension (B.2)

Tier B is split so the signal you care about is isolated:

- **B.1 — extraction fidelity (primary, deterministic).** For each field question we check
  whether the *gold value* appears, unmangled, in the model's OCR markdown — with **no LLM in
  the loop**. This is the "does it capture the values without messing them up?" signal. It is
  scored only on the *extractive* subset (answers that are literally on the page); the
  `coverage` column shows how many items that is. Reproducible; needs no API key.
- **B.2 — comprehension (secondary).** A separate *reader* model answers the question from the
  markdown, scored deterministically (field-aware exact-match + ANLS). **The reader is a swappable
  instrument, never the model under test** — it defaults to a small local model (**Phi-4-mini**,
  `microsoft/Phi-4-mini-instruct`, MIT), with the older Qwen2.5-1.5B kept as a labeled ladder rung,
  and can be swapped for Claude Haiku 4.5 or GPT-5.4-mini via OpenRouter. Because a capable reader can
  paper over OCR slips, **B.2 is confounded by the reader by design** — trust B.1 for extraction
  quality; read B.2 as a directional "does this feed a downstream QA step" signal. Each B.2 number is
  stamped with which reader produced it — the `v1-baseline` column above was scored with Qwen2.5-1.5B.

Run `gauntlet scoreboard --tier-b` for the B.1/coverage/B.2 breakdown.

Tier C publishes three **trivial-baseline floor rows** (every-page-boundary,
no-boundary, pixel-diff) — a real model must beat all three; pixel-diff doubles as
the seam-artifact canary for the synthesized data.

### Scanned and faxed robustness (Tier B under degradation)

Clean uploads and faxed/scanned copies are different production realities. We re-run the Tier-B
extraction set through a **seeded scan-degradation pipeline** (benches `realdoc_qa_scanned_light`
/ `_heavy`) and score **B.1** (deterministic, reader-independent) on each — so a drop reflects the
*OCR* degrading, not a reader confound. The per-model robustness curve (full write-up:
[findings/partd-scanned-robustness.md](findings/partd-scanned-robustness.md)):

| model | clean | light | heavy | heavy retained |
|---|---|---|---|---|
| olmocr2 | 0.689 | 0.657 | 0.514 | 75% |
| gemma4 | 0.564 | 0.586 | 0.451 | **80%** |
| qwen25vl | 0.637 | 0.676 | 0.436 | 68% |
| doctr | 0.682 | 0.660 | 0.398 | 58% |
| dots_ocr | 0.549 | 0.585 | 0.386 | 70% |
| kosmos25 | 0.565 | 0.517 | 0.390 | 69% |
| lightonocr | 0.658 | 0.602 | 0.408 | 62% |
| paddleocr_vl | 0.542 | 0.497 | 0.305 | 56% |
| deepseek_ocr | 0.469 | 0.451 | 0.261 | 56% |
| rapidocr | 0.499 | 0.495 | 0.261 | 52% |
| tesseract | 0.580 | 0.395 | 0.171 | **29%** |
| easyocr | 0.583 | 0.405 | 0.126 | **22%** |
| got2 | 0.175 | 0.149 | 0.107 | 61% |
| granite_docling | 0.035 | 0.067 | 0.015 | — (noise floor) |

**Takeaway:** VLMs are markedly more scan-robust than classic OCR engines. Under heavy degradation
olmocr2 and gemma4 keep 75–80% of clean extraction, while **tesseract and easyocr collapse to
22–29%** — the classic engines that look competitive on clean digital text are brittle on
scanned/faxed input. docTR is the exception (58% retained), so the split is really tesseract/easyocr,
not "classic engines" as a class. Light degradation is largely absorbed; the cliff is at heavy.
Each cell is n=100 — treat sub-0.03 gaps and the granite noise-floor row as directional.

### Example documents

What the gauntlet actually feeds the models (thumbnails in [`docs/examples/`](docs/examples/);
sources permit redistribution with attribution — OmniDocBench pages are
[browsable upstream](https://huggingface.co/datasets/opendatalab/OmniDocBench) instead,
its card carries no license tag):

**olmOCR-Bench** — seven categories, including the scanned-document cases:

| old scans | scanned math | tables | multi-column |
|---|---|---|---|
| ![old scan](docs/examples/olmocr_old_scans.jpg) | ![old scan math](docs/examples/olmocr_old_scans_math.jpg) | ![tables](docs/examples/olmocr_tables.jpg) | ![multi-column](docs/examples/olmocr_multi_column.jpg) |

(also: `arxiv_math`, `headers_footers`, `long_tiny_text` in the same folder)

**RealDoc-Bench QA** — the business documents Tier B extracts fields from:

| finance | medical | mortgage | supply chain |
|---|---|---|---|
| ![finance](docs/examples/realdoc_finance.jpg) | ![medical](docs/examples/realdoc_medical_healthcare.jpg) | ![mortgage](docs/examples/realdoc_mortgage.jpg) | ![supply chain](docs/examples/realdoc_supply_chain.jpg) |

**merged_forms (Tier C)** — four consecutive stream pages spanning a document
boundary; note the form faces look alike and only the filled content changes:

| page 6 | page 7 | **page 8 — new document starts** | page 9 |
|---|---|---|---|
| ![p6](docs/examples/mergedforms_p06.jpg) | ![p7](docs/examples/mergedforms_p07.jpg) | ![p8 boundary](docs/examples/mergedforms_p08_BOUNDARY.jpg) | ![p9](docs/examples/mergedforms_p09.jpg) |

> A page-image → parsed-markdown side-by-side per tier lands with the v1 scores.

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
| Mistral OCR | API | Mistral API | API terms | ✅ | purpose-built OCR API, native markdown ($0.004/page, verified 2026-07-07) |
| Gemini Flash-Lite | API | Google API | API terms | ✅ | cheapest credible VLM baseline (~$0.0005/page est.) |
| Claude / GPT vision | API | Anthropic / OpenAI | API terms | ✅ | adapters built; scored runs deferred |

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

## What the harness actually is

A **two-phase, resumable evaluation matrix** (`gauntlet run` = infer → score):

1. **Infer**: one model in VRAM at a time (API models need no GPU), every benchmark
   page → `predictions/<model>/<bench>.jsonl` with full telemetry (latency, VRAM,
   tokens/s, logprobs; API: cost, version, retries). Multi-question pages are OCR'd
   once and reused.
2. **Score**: per (model, benchmark) batch through the **official scorer wrapped in
   its own isolated venv/container** — never reimplemented, never sharing deps with
   the inference env. Scorer bugfix? `--phase score --rescore` re-scores without
   re-running a single model.

Contracts an adapter implements: `predict(page image) → StructuredDoc(markdown, …)`
(+ optional `segment(pages) → Segmentation` for native splitters). Benchmarks
implement `load() → Samples` and `evaluate() → {"primary": float, …}`.

**What a score means — and doesn't**: Tier A grades the OCR text directly. Tier B
passes it through the frozen extractor, so it measures *parse quality as seen by a
fixed reader* — extractor limitations are shared equally by all models but are in
the loop. Tier C `judge_composed` rows measure per-page parses + the frozen boundary
judge; `native` rows measure the model's own splitter. Every row carries provenance:
model revision (or API version + date), benchmark revision, scorer identity, run id
→ `results/runs/<id>/manifest.json`.

## Setup

```bash
git clone https://github.com/ashwinchidambaram/trial-by-doc
cd trial-by-doc
uv sync --extra local          # GPU/open-weights lane (torch + vLLM)
# uv sync --extra api          # API-only lane (no GPU needed)

cp .env.example .env           # add API keys if scoring API models
gauntlet download all          # benchmark data at pinned revisions
gauntlet list models           # see what's wired

gauntlet run --profile smoke   # tiny end-to-end sanity run
gauntlet run --profile full    # the whole gauntlet (resumable; --run-id to resume)
gauntlet scoreboard            # provenance-stamped results
```

Docker (same CLI, zero env setup): `docker/Dockerfile.gpu` (needs
nvidia-container-toolkit; mount your HF cache) and `docker/Dockerfile.cpu` (API
models + scoring). See `docker/compose.yaml`. Scorer containers (e.g. the olmOCR
math/table renderer) run as siblings — mount `/var/run/docker.sock`, or score on
the host with `--phase score`.

**Bring your own model** → [ADD_A_MODEL.md](ADD_A_MODEL.md) (one subclass + one YAML
entry + `gauntlet validate-adapter my_model`). Add a benchmark →
[ADD_A_BENCHMARK.md](ADD_A_BENCHMARK.md).

API spend is estimated up front (`gauntlet estimate-cost`) and hard-capped per model
(`configs/matrix.yaml: budget`) before any call is made.

## Hardware

v1 numbers were produced on a single **RTX 5090 (Blackwell, sm_120)** — driver
595.71.05, CUDA 13.0 runtime, torch 2.11.0+cu130, vLLM 0.22.1, transformers 5.11,
Ubuntu 26.04. The exact fingerprint ships in each run's `manifest.json`. Other GPUs
change throughput/VRAM (and the `enforce_eager` Blackwell workaround may be
unnecessary); scores should reproduce given the pinned revisions and seeds, with the
usual caveat that cross-hardware kernel differences can shift greedy decoding on
rare token ties.

## Gaps

Honest limitations, current as of the v1 baseline:

- **Landing next**: the two scored API lanes (Mistral OCR, Gemini Flash-Lite) and their
  per-page $/page. The 14-model, 4-tier local scoreboard, the Tier-B/latency/CPU-vs-GPU-cost
  tables, and the Azure self-host cost column above are complete and stable; the API lanes are additive.
- **DocVQA / DocBench not included**: DocVQA's visual-spatial questions measure the
  extractor, not the OCR (deferred with cause); DocBench requires an LLM judge —
  excluded by the no-judge rule.
- **OmniDocBench CDM excluded** (formula render metric needs TeX Live in a container);
  we report the official edit-distance + TEDS set and flag `cdm_excluded` per row.
- **RealDoc-Layout not wired** (box-emitting models only; optional lane).
- **API fleet not yet scored**: adapters for Mistral OCR, Gemini Flash-Lite, and
  Textract/Azure/Google Doc AI/Claude/GPT ship validated but unscored — no API rows are in
  the v1-baseline scoreboard. Mistral OCR + Gemini Flash-Lite are the cheapest worth testing
  (pricing verified) and land next. Azure DI's self-host container lane is designed, not wired.
- **merged_forms is synthesized** (no public dataset covers the similar-forms case —
  verified against the PSS literature and HF). Mitigations: public-domain source
  data, seeded determinism, published floor rows, seam canary, VALIDATION.md. Its
  `custom` provenance is labeled on every scoreboard.
- **Tier B/C instrument coupling**: extractor and boundary-judge quality bound what
  those tiers can see. Both are frozen and identical across models — comparisons are
  fair; absolute values are lower bounds.
- **Statistical power**: per-category cells are small (n≈14–25); treat per-category
  winners as directional, not definitive.

## Attributions & credits

This harness stands on other people's careful work:

**Benchmarks & datasets**
- [olmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench) — Allen Institute for AI, **ODC-BY 1.0** (attribution required — thank you AI2). Scored by the official [`olmocr[bench]`](https://github.com/allenai/olmocr) runner.
- [OmniDocBench](https://github.com/opendatalab/OmniDocBench) — OpenDataLab / Shanghai AI Lab (CVPR 2025). Scored via the official repo pipeline (Apache-2.0 code); dataset card carries no license tag (verified 2026-07-07) — evaluation use only, not redistributed.
- [RealDoc-Bench](https://huggingface.co/datasets/Extend-AI/RealDoc-Bench) — Extend-AI, **CC BY 4.0**.
- [NIST Special Database 2](https://www.nist.gov/srd/nist-special-database-2) (SFRS) — U.S. National Institute of Standards and Technology; U.S. Government work. Raw material for `merged_forms`.
- Segmentation metrics: **Panoptic Quality for PSS** from van Heusden, Kamps & Marx, *OpenPSS* (TPDL 2024, doi:10.1007/978-3-031-72437-4_24); **STP** from *LLMs for Page Stream Segmentation* (arXiv:2408.11981, TABME++).

**Models** — Allen Institute for AI (olmOCR-2), Alibaba Qwen (Qwen2.5-VL; Qwen2.5-7B-Instruct is also our frozen instrument), StepFun (GOT-OCR 2.0), rednote-hilab (dots.ocr), PaddlePaddle (PaddleOCR-VL), DeepSeek (DeepSeek-OCR), IBM (granite-docling), LightOn (LightOnOCR), Mistral AI, Google, Anthropic, OpenAI.

**Lineage** — harness contracts (adapter/benchmark seams, scorer isolation,
provenance stamping) evolved from the author's `of-course-i-can-parse-that`
distillation project.

Harness code: MIT. Benchmark data keeps its own licenses (links above);
nothing restrictive is redistributed here.
