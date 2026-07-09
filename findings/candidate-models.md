# Candidate models & scope expansion (owner-review — NOT yet wired)

Status: **draft scope for owner review.** Nothing implemented. Licenses/prices verified live
2026-07-09 (HF model cards + provider pricing + OpenRouter API); **re-verify exact revision +
license at wire-in** per the verify-never-assume rule.

Three workstreams have emerged. They're separable → proposed as **two specs** (roster expansion,
and the reader upgrade). Distillation/custom-model is parked.

---

## Workstream 1 — Classic / CPU-capable OCR engines (contenders)

**Sequencing (owner): run Tesseract through all 4 tiers FIRST, before the other engines.**

| Engine | Sel | License | Compute | Notes |
|---|---|---|---|---|
| **Tesseract 5** | ✅ **first** | Apache-2.0 | CPU-native (no GPU benefit) | classic floor; plain text/hOCR; weak on tables/math/multi-column |
| **RapidOCR (PP-OCRv5, ONNX)** | ✅ | Apache-2.0 | CPU (ONNXRuntime) **or GPU** (onnxruntime-gpu/OpenVINO/TensorRT) | modern "Tesseract"; distinct from our `PaddleOCR-VL` (that's the new VLM) |
| **docTR** (Mindee) | ✅ | Apache-2.0 | CPU **or GPU** (PyTorch/TF; GPU Docker on CUDA 12.2) | layout-aware (bounding boxes); Python ≥3.10 |
| **EasyOCR** (JaidedAI) | ✅ | Apache-2.0 | CPU **or GPU** (PyTorch, `gpu=True`) | 80+ langs; CPU throughput weakest of the three |

CPU-vs-GPU: accuracy is **identical** across hardware (same weights → same output → same Tier-A/B/C
scores). So **score once per engine, report two latency + $/page rows** (CPU-VM vs GPU-VM). Cost
angle: CPU VM is much cheaper $/hr, so CPU may win on $/page despite being slower — that's the point.

## Workstream 2 — New SLM vision-OCR contenders (license-verified 2026-07-09)

| Contender | HF repo | Params | License | Commercial | OCR capability | Runtime | Verdict |
|---|---|---|---|---|---|---|---|
| **Florence-2-base** | `microsoft/Florence-2-base` | 0.23B | MIT | ✅ | OCR + "OCR with Region" (bbox) | transformers, **trust_remote_code** | **include** |
| **Kosmos-2.5** | `microsoft/kosmos-2.5` | ~1.3B | MIT | ✅ | dense doc OCR → markdown + coords | native transformers/vLLM (no trust_remote_code) | **include** (hallucination caveat on card) |
| **Phi-4-multimodal** | `microsoft/Phi-4-multimodal-instruct` | 5.6B | MIT | ✅ | strong (OCRBench 84.4, DocVQA 93.2) | transformers, **trust_remote_code** | **include** (largest, strongest) |
| ~~SmolDocling-256M~~ | `docling-project/SmolDocling-256M-preview` | 0.256B | CDLA-Permissive-2.0 | ✅ | full-page DocTags OCR | vLLM (Idefics3) | **drop** — redundant with granite-docling (same DocTags family + size); CDLA needs legal glance; Idefics3 runtime |
| ~~SmolVLM-256M~~ | `HuggingFaceTB/SmolVLM-256M-Instruct` | 0.256B | Apache-2.0 | ✅ | general VLM, modest doc scores | vLLM (Idefics3) | **drop** — not OCR-specialized; general VLMs already covered |
| ~~TrOCR~~ | `microsoft/trocr-base-printed` | 0.33B | **none listed** ⚠️ | **unverified** | line-level only (pre-cropped) | transformers | **drop** — no license + page mismatch |

**Final WS2 set (owner-confirmed 2026-07-09): Florence-2-base, Kosmos-2.5, Phi-4-multimodal** — a
clean all-MIT size ladder (0.23B → 1.3B → 5.6B).

## Workstream 3 — B.2 reader upgrade + ladder (measuring instrument, not a contender)

B.2 reader = reads OCR **markdown** and answers the field question (pure comprehension; no OCR/vision
needed). B.1 (deterministic field-value presence) stays the **primary, reader-independent** Tier-B
signal regardless of reader choice.

- **Default (local, reproducible, free): `Qwen2.5-7B-Instruct`** (Apache-2.0) — strongest ≤7B permissive
  option, already loaded as the judge/extractor → zero new infra. Alt: **Phi-4-mini (~3.8B, MIT)**.
- **Ladder rungs (optional, to measure reader sensitivity):** gemma4-E4B (Apache-2.0; note E4B is the
  largest gemma4 ≤7B — next is 26B), plus API readers below.
- **Published B.2 → API batch (owner lean):** GPT-5.4-mini and/or Claude Haiku 4.5.

Reader pricing (verified 2026-07-09; OpenRouter = same price as direct, just one key):

| Reader | $/1M in·out | Cost / full B.2 pass¹ | Batch (−50%) |
|---|---|---|---|
| GPT-5.4-mini | $0.75 / $4.50 | ~$1.51 | ~$0.76 |
| Claude Haiku 4.5 | $1.00 / $5.00 | ~$1.96 | ~$0.98 |
| both (ladder) | — | ~$3.47 | ~$1.74 |

¹ 100 questions × ~14 contenders × ~1,200 input + ~40 output tok/call (input measured from real
realdoc markdown: olmocr2 ~1,125, gemma4 ~1,423, got2 ~465 tok/call). Per-pass; scales ~$0.11–0.14
per added contender. Cost is negligible — reproducibility + capability drive the choice, not price.

## Parked
- Distillation / domain-specialist custom model (separate future effort; ties to the sibling
  `of-course-i-can-parse-that` project — measure here, build there).

## Proposed spec split
- **Spec A — Roster expansion:** WS1 (Tesseract-first) + WS2, with the CPU-vs-GPU comparison.
- **Spec B — B.2 reader upgrade + ladder:** WS3.
