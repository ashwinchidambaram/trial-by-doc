# Goal

Expand the trial-by-doc model roster with **Part A: classic/CPU OCR engines (WS1) and small
MIT-licensed vision-OCR models (WS2)**, so the scoreboard covers the cheap-CPU floor through the
small-VLM middle, not just the current 7B-class local models and frontier APIs. This is the
durable design for all of Part A — Tesseract is the first WS1 engine built against it, but the
adapter approach, tier applicability, and CPU-vs-GPU cost methodology below apply to every
contender in this doc, present and future.

**Date:** 2026-07-09
**Status:** approved (design) — Tesseract wired in as the first contender; RapidOCR/docTR/EasyOCR
and the WS2 vision models are scoped here but not yet implemented.
**Source of truth for facts:** `findings/candidate-models.md` (verified live 2026-07-09 against
HF model cards + provider pricing; **re-verify exact revision + license at wire-in** for every
model not yet implemented — the verify-never-assume house rule applies per-contender, not once
for the whole doc).

## 1. Scope

**WS1 — classic/CPU-capable OCR engines.** Sequencing (owner decision): **Tesseract runs through
all 4 tiers first**, before the other three engines are wired in. Order after that is RapidOCR,
docTR, EasyOCR.

| Engine | Status | License | Compute |
|---|---|---|---|
| **Tesseract 5** | **built (this doc's Part 2)** | Apache-2.0 | CPU-native only (no GPU path exists) |
| RapidOCR (PP-OCRv5, ONNX) | scoped, not built | Apache-2.0 | CPU (ONNXRuntime) *or* GPU (onnxruntime-gpu / OpenVINO / TensorRT) |
| docTR (Mindee) | scoped, not built | Apache-2.0 | CPU *or* GPU (PyTorch/TF; GPU Docker on CUDA 12.2) |
| EasyOCR (JaidedAI) | scoped, not built | Apache-2.0 | CPU *or* GPU (PyTorch, `gpu=True`) |

**WS2 — small vision-OCR models (all MIT, all scoped, none built yet).** A clean size ladder,
0.23B → 1.3B → 5.6B:

| Contender | HF repo | Params | License | OCR capability | Runtime |
|---|---|---|---|---|---|
| Florence-2-base | `microsoft/Florence-2-base` | 0.23B | MIT | OCR + "OCR with Region" (bbox) | transformers, `trust_remote_code=True` |
| Kosmos-2.5 | `microsoft/kosmos-2.5` | ~1.3B | MIT | dense doc OCR → markdown + coords | native transformers/vLLM (no `trust_remote_code`) |
| Phi-4-multimodal | `microsoft/Phi-4-multimodal-instruct` | 5.6B | MIT | strong (OCRBench 84.4, DocVQA 93.2 per card) | transformers, `trust_remote_code=True` |

WS3 (B.2 reader upgrade + ladder) is a separate spec (Spec B) and out of scope here — it's a
measuring-instrument change, not a roster contender.

## 2. Model table — adapter base class + tier applicability

| Engine/model | Repo or binary | Params | License | Commercial | Compute | Adapter base | Tiers |
|---|---|---|---|---|---|---|---|
| Tesseract 5 | `tesseract` binary (system/conda-forge) + `pytesseract` | n/a (classic CV, not a param-counted model) | Apache-2.0 | yes | CPU only | `ModelAdapter` (direct) | A, B (B.1 primary), C (judge-composed) |
| RapidOCR | PP-OCRv5 ONNX, pip package | ~few M–10M (ONNX det+rec) | Apache-2.0 | yes | CPU (ONNXRuntime) or GPU (onnxruntime-gpu/OpenVINO/TensorRT) | `ModelAdapter` (direct; ONNXRuntime, no torch) | A, B (B.1), C (judge-composed) |
| docTR | `python-doctr` pip package | varies by det/rec backbone (~10-25M each) | Apache-2.0 | yes | CPU or GPU (PyTorch/TF) | `ModelAdapter` (direct); **not** `TransformersModelAdapter` — docTR is its own PyTorch/TF stack, not an HF `transformers` model | A, B (B.1), C (judge-composed; docTR's own layout boxes are richer telemetry, not a native segmenter) |
| EasyOCR | `easyocr` pip package | ~few M (CRAFT det + CRNN rec) | Apache-2.0 | yes | CPU or GPU (`gpu=True`) | `ModelAdapter` (direct) | A, B (B.1), C (judge-composed) |
| Florence-2-base | `microsoft/Florence-2-base` | 0.23B | MIT | yes | GPU (works CPU-slow) | `TransformersModelAdapter` (`trust_remote_code=True`) | A, B (B.1+B.2), C (judge-composed) |
| Kosmos-2.5 | `microsoft/kosmos-2.5` | ~1.3B | MIT | yes | GPU | `TransformersModelAdapter` (native, no `trust_remote_code`) — or `VLLMModelAdapter` if the vLLM model card path is confirmed at wire-in | A, B (B.1+B.2), C (judge-composed) |
| Phi-4-multimodal | `microsoft/Phi-4-multimodal-instruct` | 5.6B | MIT | yes | GPU | `TransformersModelAdapter` (`trust_remote_code=True`) | A, B (B.1+B.2), C (judge-composed) |

**Revision pins:** none of the WS1/WS2 entries above carry a commit-hash revision in this doc
because none is wired in yet except Tesseract (which has no HF repo/revision concept — see §3).
Every future entry follows `configs/models.yaml` convention: `repo_id` + a pinned commit-hash
`revision`, **re-verified against the live HF card at wire-in time**, not copied from this doc or
from `findings/candidate-models.md` without a fresh check.

## 3. Adapter approach per class

**CPU engines (Tesseract, RapidOCR, docTR, EasyOCR) subclass `ModelAdapter` directly** — see
`src/tbdoc/models/local/baselines.py` for the pattern (the Tier-C floor baselines already do this:
`load()`/`predict()`/`fingerprint()` overridden, no `LocalModelAdapter` GPU teardown needed because
there's no GPU state to tear down). Concretely:

- **No torch import anywhere in the adapter file.** These engines don't need it (Tesseract: none;
  RapidOCR: ONNXRuntime; docTR: its own PyTorch/TF *runtime*, imported lazily inside the adapter
  module, not at trial-by-doc's top level — it doesn't participate in `free_gpu()`/CUDA-context
  bookkeeping the way `LocalModelAdapter` subclasses do; EasyOCR: PyTorch internally but again a
  private runtime, not the shared vLLM/transformers stack).
- `load()` does a cheap readiness check (binary on PATH, or a package import) rather than loading
  multi-GB weights.
- `predict(image)` calls the engine's OCR call, wraps it in `tbdoc.core.telemetry.track()` for
  latency, and returns a `StructuredDoc` with `backend` set to the engine name (e.g.
  `"tesseract"`) — never `None`, so scoreboard/report code can group by real backend rather than
  the "honestly unavailable" `None` used when a signal genuinely can't be produced.
- `fingerprint()` is overridden (there's no `repo_id`/HF `revision`) to stamp the engine name +
  installed engine version (e.g. tesseract's `--version` output) with `revision: "n/a"`, following
  `_BaselineAdapter.fingerprint()`'s shape in `baselines.py`.
- None of these engines has a native multi-document segmenter, so none declares `"segmentation"`
  in `capabilities` — Tier C falls through to `ModelAdapter.segment()`'s default judge-composed
  path (§5).

**The WS2 vision models (Florence-2-base, Kosmos-2.5, Phi-4-multimodal) subclass
`TransformersModelAdapter`** (`src/tbdoc/models/local/_transformers_base.py`), following the
`got2.py` idiom: `build_inputs()`, optional `gen_kwargs()`, `decode()`. Two of the three
(Florence-2, Phi-4-multimodal) need `trust_remote_code=True` per their model cards — verify this
is still required at wire-in (cards do sometimes migrate to native `transformers` code). If
Kosmos-2.5 turns out to have a working vLLM serving path at wire-in, `VLLMModelAdapter` is
preferred (matches the roster's existing GPU-model pattern, e.g. `qwen25vl.py`) — decide per the
live vLLM model-support matrix, not from this doc.

## 4. CPU-vs-GPU cost methodology

**Core claim: OCR accuracy is device-independent.** Same model weights + same input image → same
output text → identical Tier A/B/C scores, regardless of whether inference ran on CPU or GPU
(floating-point non-determinism across hardware is a rounding-noise concern, not a scoring
concern, at the tolerances these scorers use). So the roster does **not** run each dual-capable
engine (RapidOCR, docTR, EasyOCR) twice through the full scoring pipeline. Instead:

1. **Score once** — run the engine on whichever device is convenient (CPU is the natural default
   for engines whose whole selling point is "doesn't need a GPU"; Tesseract only has a CPU path,
   so there's no ambiguity for it). This produces the one, canonical Tier A/B/C score row.
2. **Measure latency on both devices** for engines that support both — a short, separate timing
   pass (no scoring, `--phase infer` only, discard the predictions or reuse them, whichever is
   cheaper) captures `latency_s` on CPU and again on GPU.
3. **Report two cost rows per engine**, derived from measured throughput:

   ```
   $/page = (SKU $/hr) / (pages/hr)
          = (SKU $/hr) / (3600 / latency_s_per_page)
   ```

   e.g. a CPU VM SKU at $X/hr and a GPU VM SKU at $Y/hr each get their own `$/page`, using that
   device's measured `latency_s`. The point of the exercise (owner framing, `candidate-models.md`
   §WS1): CPU is much cheaper per hour but slower per page, so the two rows let a reader see
   whether CPU wins on $/page despite losing on raw speed — that's the interesting number, not
   "GPU is faster" (already known).
4. Both single-stream and batched throughput are worth capturing if the engine supports batching
   (mirrors the existing Azure hosting-cost methodology already used elsewhere in this project's
   sibling docs: per-GPU-hr ÷ pages/hr, both single-stream and batched) — batched throughput is
   the honest number for a production deployment, single-stream is the honest number for
   interactive/low-volume use; report both rather than picking one.
5. Tesseract has no GPU row — only the CPU cost line applies, and that's reported as-is (not "N/A
   padding" — a CPU-only engine's CPU number is its whole cost story).

## 5. Tier applicability

All WS1/WS2 engines run all three implemented tiers the same way every other roster model does:

- **Tier A** (`olmocr_bench`, `omnidocbench`) — page-level markdown/edit-distance/TEDS scoring.
  No special handling; `predict(image)` per page is the whole contract.
- **Tier B** (`realdoc_qa`) — **B.1 (field-value presence, deterministic, primary) is the signal
  that matters for these engines**: it scores the OCR markdown directly against gold field values
  with no LLM in the loop, so it's the fair, reproducible way to compare a classic CV engine
  against a 7B VLM without conflating OCR quality with a comprehension model's reasoning. **B.2**
  (LLM-reader comprehension) also runs by default (it's driven by the frozen/pluggable reader
  instrument, not by the model under test) but is secondary per the Tier-B split design
  (`docs/superpowers/specs/2026-07-08-tier-b-split-design.md`) — expect classic engines to do
  relatively better on B.1 than B.2 if their raw transcription is decent but noisy in ways a
  downstream LLM reader tolerates less well than the tolerant B.1 matcher does, or vice versa if
  layout loss (no reading-order awareness) scrambles the text enough to confuse the reader.
- **Tier C** (`merged_forms`) — **none of these engines is a native multi-document segmenter**, so
  every one of them runs Tier C via `ModelAdapter.segment()`'s default: per-page `predict()` then
  the frozen `boundary_judge` instrument decides same-document-or-new per consecutive page pair
  (`method="judge_composed"`). This requires the run to include the boundary_judge instrument —
  i.e. **do not pass `--no-llm-instruments`** for these engines' Tier C runs, or every Tier C row
  silently becomes an all-error row (see `findings/` note: `--no-llm-instruments` silently breaks
  `merged_forms` scoring for any non-native segmenter — audit row validity, not just row counts).

## 6. What's NOT in this doc

- Exact revision hashes / license re-verification for RapidOCR, docTR, EasyOCR, Florence-2-base,
  Kosmos-2.5, Phi-4-multimodal — **verify live at each one's wire-in**, per the verify-never-assume
  house rule; nothing here should be copied into `configs/models.yaml` without a fresh check.
  Tesseract's actually-installed version is recorded in `findings/` at wire-in time (this doc only
  fixes the *architecture*, not the number).
- Spec B (B.2 reader upgrade + ladder, WS3) — separate doc, not roster expansion.
- Distillation / custom domain model — parked, tracked in the sibling
  `of-course-i-can-parse-that` project, not built here.
