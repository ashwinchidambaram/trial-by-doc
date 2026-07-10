# WS1 — Classic / CPU-capable OCR engines (roster expansion Part A)

Four classic OCR engines added as contenders: **Tesseract, RapidOCR, docTR, EasyOCR**.
See the design in `docs/superpowers/specs/2026-07-09-roster-expansion-design.md`.

## Accuracy — smoke (olmocr_bench, 5 samples, 0 errors)

| engine | olmocr_bench | notes |
|---|---|---|
| tesseract | 0.280 | classic engine; also ran ALL 4 tiers (below) |
| rapidocr | 0.240 | ONNXRuntime, PP-OCR-derived |
| docTR | 0.323 | strongest classic engine on this smoke |
| easyocr | 0.267 | CRAFT+CRNN |

For reference the 7B VLM/OCR models score ~0.5+ on olmocr_bench — the classic engines sit
below them on parse fidelity (expected), which is the point: they anchor the cheap end of
the cost/quality spectrum.

**Tesseract, all 4 tiers (smoke, 5 samples/bench):** olmocr_bench 0.280 · omnidocbench 0.738
· realdoc_qa B.1 0.750 / B.2 0.600 · merged_forms PQ 0.329. 0 real errors.

> These are SMOKE numbers (5 samples/bench). The full-sample scored numbers for the whole
> expanded roster land in A4 (one stratified run after all adapters exist).

## Throughput — single-stream, CPU vs GPU (10 pages @ dpi 150, RTX 5090 / this box)

| engine | CPU pages/hr (s/page) | GPU pages/hr (s/page) | GPU speedup |
|---|---|---|---|
| tesseract | 3006 (1.20) | — (CPU-native, no GPU path) | — |
| rapidocr | 1214 (2.97) | — (no onnxruntime-gpu wheel for cu130/sm_120 Blackwell) | — |
| docTR | 983 (3.66) | 24328 (0.148) | ~25× |
| easyocr | 43 (84.4) | 2300 (1.57) | ~54× |

Key findings:
- **docTR is the throughput star**: on GPU ~24k pages/hr (0.15 s/page), ~25× its CPU rate.
- **easyocr is impractical on CPU** (~84 s/page on ordinary document pages; worse — minutes —
  on dense scans) → its accuracy pass runs on GPU (accuracy is device-invariant).
- **rapidocr / tesseract are the true CPU engines**: no GPU path used, ~1–3 s/page on CPU.
- Accuracy is identical across devices (same weights) → we **score once**, report **two cost
  rows** (CPU-VM vs GPU-VM) computed as `SKU $/hr ÷ pages/hr` (cost table lands in C2).

CAVEAT: throughput measured on an RTX 5090; these are same-hardware **relative floors** — a
cloud CPU-VM or a T4/A100 is slower, so real $/page is higher (same caveat as the Azure table).
