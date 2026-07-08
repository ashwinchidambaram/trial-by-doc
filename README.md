# trial-by-doc ⚖️

**An OCR / document-intelligence model gauntlet.** Wire in any model — local
open-weights, commercial doc-AI APIs, or frontier VLMs — and run it through a
three-tier benchmark gauntlet with **deterministic, automatic scoring**. Built to
answer one question honestly: *which model should you trust to parse your documents?*

- **Tier A — parse fidelity**: is the OCR output actually correct? (unit tests, edit distance, TEDS)
- **Tier B — downstream extraction**: is it good enough to extract fields from? (exact match, ANLS)
- **Tier C — document segmentation**: can it split a PDF that is really 3–4 merged documents? (boundary F1, PQ, STP)

No LLM-as-judge anywhere. Every score is a deterministic algorithm; the only LLMs in
the measurement path are **frozen instruments** (pinned revision, temp=0, seeded,
identical for every model) and the scoreboard marks where they're used.

## Scores

> 🚧 **v1 baseline run in progress.** This section is auto-generated from
> `results/runs/<id>/` by `gauntlet scoreboard --format md` when the run completes.
> Interim engineering-run numbers live in `findings/`.

<!-- SCOREBOARD:BEGIN -->
> ⏳ **INTERIM — v1 run in progress** (3 of 8 models scored; Tier A only. Tier B/C
> and the remaining 5 models land as the run completes.)

**Tier A — parse fidelity** (higher is better; mean over stratified pages, n per cell):

| Model | olmOCR-Bench | OmniDocBench |
|---|---|---|
| olmocr2 | **0.836** (n=100) | **0.828** (n=96) |
| qwen25vl | 0.702 (n=100) | 0.736 (n=96) |
| got2 | 0.304 (n=100) | 0.638 (n=96) |
| _dots_ocr, paddleocr_vl, deepseek_ocr, granite_docling, lightonocr_ | _inferring…_ | _inferring…_ |

olmocr_bench = official unit-test pass rate (uncapped render tests). OmniDocBench =
1 − overall edit distance (CDM excluded); 4 pages/model have no scoreable elements
(excluded, hence n=96). 0 scoring errors across 600 records.

**Early read**: olmocr2 leads every olmOCR-Bench category (except old_scans, tied)
and every test type — the purpose-built OCR model is the parser to beat. qwen25vl
matches it on tables (0.94) but trails on layout/reading-order and shows
repetition-loop degeneration on a few dense historical pages. got2 (580M) handles
plain text but emits **no table structure** (0/103 table unit tests) — a
capability/format limit of the small specialist, not a scorer artifact. Ranking
tracks the prior baseline; per-model detail in `findings/`.
<!-- SCOREBOARD:END -->

## Benchmarks

| Benchmark | Tier | Provenance | What it tests | Why we test it |
|---|---|---|---|---|
| [olmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench) | A | official | Per-page **unit tests**: text present/absent, reading order, math (KaTeX render), tables — across 7 doc categories incl. old scans | The broadest "did you transcribe this correctly" signal; scans + multi-column are production reality |
| [OmniDocBench](https://github.com/opendatalab/OmniDocBench) | A | official | Full-page parse quality: text/formula/table **edit distance**, **TEDS** table structure, over 10 document sources | The industry-standard parse-fidelity metric set |
| [RealDoc-Bench QA](https://huggingface.co/datasets/Extend-AI/RealDoc-Bench) | B | official | **Field extraction** from business docs (finance, medical, mortgage, supply-chain): markdown → frozen extractor → exact-match/ANLS | The closest proxy for "extract data from PDFs without mistakes" — the production task itself |
| [merged_forms](benchmarks/custom/merged_forms/VALIDATION.md) | C | **custom** | **Document segmentation**: streams of 3–4 concatenated NIST SD2 tax submissions — same form faces, different filled data; boundaries only detectable by content | The hard production case: splitting merged PDFs of look-alike forms. No public benchmark covers it (we verified) |

Tier C publishes three **trivial-baseline floor rows** (every-page-boundary,
no-boundary, pixel-diff) — a real model must beat all three; pixel-diff doubles as
the seam-artifact canary for the synthesized data.

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
| Mistral OCR | API | Mistral API | API terms | ✅ | purpose-built OCR API, native markdown ($0.004/page, verified 2026-07-07) |
| Gemini Flash-Lite | API | Google API | API terms | ✅ | cheapest credible VLM baseline (~$0.0005/page est.) |
| Claude / GPT vision | API | Anthropic / OpenAI | API terms | ✅ | adapters built; scored runs deferred |

**Self-host cost** (measured VRAM + $/page from measured throughput) is stamped per
row in the results and summarized here after the v1 run. API rows carry the exact
resolved model version + called-on date (remote models drift; we stamp it honestly).

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

- **DocVQA / DocBench not included**: DocVQA's visual-spatial questions measure the
  extractor, not the OCR (deferred with cause); DocBench requires an LLM judge —
  excluded by the no-judge rule.
- **OmniDocBench CDM excluded** (formula render metric needs TeX Live in a container);
  we report the official edit-distance + TEDS set and flag `cdm_excluded` per row.
- **RealDoc-Layout not wired** (box-emitting models only; optional lane).
- **API fleet partially scored**: Mistral OCR + Gemini Flash-Lite in v1 (cheapest
  worth testing, verified pricing); Textract/Azure/Google Doc AI/Claude/GPT adapters
  ship validated but unscored. Azure DI's self-host container lane is designed, not wired.
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
