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
