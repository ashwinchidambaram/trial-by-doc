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
> ✅ **v1 baseline — all 9 local models scored across all four tiers** (deterministic
> scoring only; 0 scoring errors, 2694 scored samples). Numbers below are aggregated from the
> `v1-baseline` run's per-sample records in `results/runs/v1-baseline/raw/` (cross-checked with
> `gauntlet scoreboard --run-id v1-baseline`). The two scored API lanes (Mistral OCR, Gemini
> Flash-Lite) land next — see **Gaps**.

**How to read this:** every score is **higher-is-better, 0–1**, a mean over the valid
samples in that cell (n noted below). Each tier measures a different production capability;
no LLM-as-judge is used anywhere — the two LLM *instruments* (Tier-B reader, Tier-C boundary
judge) are frozen, pinned, temp-0, and identical for every model, so differences reflect the
**model under test**, not the instrument.

| Model | A · olmOCR-Bench | A · OmniDocBench | B.1 · extraction recall | B.2 · comprehension ANLS | C · segmentation |
|---|---|---|---|---|---|
| olmocr2 | **0.836** | 0.828 | **0.689** | 0.494 | 0.070 |
| dots_ocr | 0.734 | **0.897** | 0.549 | 0.484 | 0.006 |
| deepseek_ocr | 0.704 | 0.820 | 0.469 | 0.477 | 0.051 |
| qwen25vl | 0.702 | 0.736 | 0.637 | **0.555** | 0.018 |
| lightonocr | 0.675 | 0.726 | 0.658 | 0.522 | 0.142 |
| gemma4 | 0.414 | 0.706 | 0.564 | 0.380 | **0.157** |
| paddleocr_vl | 0.345 | 0.660 | 0.542 | 0.496 | 0.063 |
| got2 | 0.304 | 0.638 | 0.175 | 0.369 | 0.040 |
| granite_docling | 0.179 | 0.103 | 0.035 | 0.210 | _N/A_ |

_n per cell: olmOCR-Bench 100 · OmniDocBench 96 (4 pages have no scoreable elements under the
official pipeline, excluded uniformly for all models) · B.1 90 (the extractive-answer subset) ·
B.2 100 · segmentation 15 streams. **granite Tier-C is N/A** — its transformers backend OOMs on a
145-megapixel page; scoring only the streams it finished would flatter it, so we report N/A
([why](findings/granite-mergedforms-tierC-NA.md))._

**What each column means**
- **A · olmOCR-Bench** — official per-page unit-test pass rate (text/order/math/table). "Did you transcribe it correctly?"
- **A · OmniDocBench** — 1 − overall edit distance (text+formula+table+reading-order; formula-CDM excluded, needs a TeX toolchain). Full-page parse fidelity.
- **B.1 · extraction recall** — deterministic: does the *gold field value* appear, unmangled, in the model's markdown? **No LLM.** The production-critical "capture the value without corrupting it" signal.
- **B.2 · comprehension ANLS** — a frozen small reader (Qwen2.5-1.5B) answers each field question from the markdown; scored by ANLS. Secondary, and confounded by the reader.
- **C · segmentation** — boundary F1 on merged streams of look-alike NIST tax forms; boundaries composed from per-page OCR by the frozen 7B boundary judge.

**What the numbers say**
- **olmocr2 is the parser to beat** — top olmOCR-Bench (0.836) and top extraction recall (0.689). If the job is "read the page and don't lose the field values," it leads.
- **dots_ocr wins full-page fidelity** (OmniDocBench 0.897) — its layout+table strength shows on the edit-distance metric even though it trails olmocr2 on the unit-test bench.
- **B.1 vs B.2 disagree, on purpose.** olmocr2 tops raw extraction (B.1) but **qwen25vl** tops comprehension (B.2) — a capable reader can "understand around" slightly worse OCR. Watch B.1 for extraction reliability, B.2 for QA usability.
- **Segmentation is hard for everyone** (all ≤ 0.16). Splitting merged look-alike forms by content change barely works with page-OCR→judge composition; **gemma4** edges ahead (0.157) with lightonocr close behind (0.142), but the absolute ceiling is low — a genuine open problem, not a scorer artifact.
- **gemma4 (Google's general multimodal model) is a jack-of-all-trades** — mid-pack on raw parse fidelity (below the OCR specialists) but it **tops segmentation** and holds respectable extraction recall (0.564). A generalist that trades peak OCR accuracy for broad capability; also the slowest local model (see below).
- **granite_docling trails across the board** here; it's a DocTags-specialist whose strengths aren't what these general parse/extract metrics reward.

**Performance — time per page** (local models; from per-sample telemetry on olmOCR-Bench, n=100):

| model | median s/page | mean s/page | p90 s/page | peak VRAM* |
|---|---|---|---|---|
| paddleocr_vl (0.9B) | 3.5 | 4.9 | 9.0 | 30.0 GB |
| lightonocr (1B) | 4.3 | 5.0 | 8.8 | 29.6 GB |
| got2 (580M) | 5.3 | 6.1 | 12.5 | 3.6 GB |
| granite_docling (258M) | 5.5 | 40.7 | 145.3 | 1.0 GB |
| dots_ocr (1.7B) | 5.9 | 7.9 | 11.3 | 31.8 GB |
| deepseek_ocr (3B) | 6.6 | 9.7 | 19.4 | 30.6 GB |
| qwen25vl (7B) | 7.7 | 9.3 | 18.0 | 29.5 GB |
| olmocr2 (7B) | 8.5 | 10.2 | 18.0 | 29.5 GB |
| gemma4 (8B) | 10.4 | 11.6 | 20.3 | 30.5 GB |

\*peak VRAM = whole-GPU (nvidia-smi) during the vLLM serve — for the vLLM models this is
dominated by the KV-cache pool (gpu_memory_utilization=0.9 on a 32 GB card), **not** the model's
own weights. got2 and granite run on the transformers backend (no big KV pool), so their VRAM is
the true model footprint; granite's mean/p90 blow-up is that backend not resizing oversized pages.
**Pending:** batched-throughput numbers, per-page $/page for the scored API lane, and the
Azure Foundry Managed-Compute self-host cost column (see **Gaps**). `gauntlet scoreboard --perf`
regenerates this.
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
  instrument, never the model under test** — it defaults to a small local model (Qwen2.5-1.5B,
  Apache-2.0) and can be set to Claude Haiku 4.5 or GPT-5.4-mini. Because a capable reader can paper over OCR slips,
  **B.2 is confounded by the reader by design** — trust B.1 for extraction quality; read B.2 as a
  directional "does this feed a downstream QA step" signal. Each B.2 number is stamped with which
  reader produced it.

Run `gauntlet scoreboard --tier-b` for the B.1/coverage/B.2 breakdown.

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
| [Gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) | 4.5B-eff | vLLM (local) | Apache-2.0† | ✅ | general multimodal; OCR, doc/PDF parsing, handwriting, charts |
| Mistral OCR | API | Mistral API | API terms | ✅ | purpose-built OCR API, native markdown ($0.004/page, verified 2026-07-07) |
| Gemini Flash-Lite | API | Google API | API terms | ✅ | cheapest credible VLM baseline (~$0.0005/page est.) |
| Claude / GPT vision | API | Anthropic / OpenAI | API terms | ✅ | adapters built; scored runs deferred |

† Gemma-4 ships under **Apache-2.0** per its HF model card and API metadata (verified live
2026-07-08, `google/gemma-4-E4B-it` @ `fee6332`) — a departure from the custom *Gemma Terms of
Use* that governed earlier Gemma releases. Confirm against the model card before you rely on it.

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

- **Landing next (not yet in the table above)**: the two scored API lanes (Mistral OCR,
  Gemini Flash-Lite); batched-throughput numbers and per-page $/page; and the Azure Foundry
  Managed-Compute self-host cost column. The 9-model, 4-tier local scoreboard above is complete
  and stable; these are additive.
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
