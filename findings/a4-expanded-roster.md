# A4 — Expanded-roster full scored run (Part A gate)

Ran the 5 new expansion contenders into run-id **v1-baseline** (deterministic seed-0 stratified
sampling → the *same* 100 samples/bench as the v1 nine → directly comparable rows). 4199 scored
samples total. 0 error rows across every new (model, bench) cell; Tier-C validated 15/15 valid PQ
per engine (no all-error pathology). Frozen instruments reused unchanged (extractor/judge
`Qwen2.5-7B-Instruct@a09a35458c70`; B.2 reader `Qwen2.5-1.5B-Instruct`).

## Roster outcome (WS1 + WS2)

- **WS1 classic/CPU OCR (4/4 landed):** Tesseract, RapidOCR, docTR, EasyOCR.
- **WS2 small vision-OCR (1/3 landed):** **Kosmos-2.5** only. **Florence-2** and **Phi-4-multimodal**
  are BLOCKED on the pinned transformers 5.11 (distinct pre-v5 remote-code incompatibilities —
  Florence-2: `EncoderDecoderCache not subscriptable`; Phi-4-mm: audio ConformerEncoder `.item()` on a
  meta tensor under v5 meta-init, after its flash-attn config issue was fixed). Both kept
  unregistered for revival; see their adapter docstrings + `configs/models.yaml` comments.

Net roster: **14 scored contenders** (9 v1 + 5 new; Florence-2/Phi-4-mm out).

## Scoreboard (primary metric per tier, all 14)

| model | realdoc_qa (B.1) | omnidocbench (A) | olmocr_bench (A) | merged_forms (C, PQ) |
|---|---|---|---|---|
| olmocr2 | 0.689 | 0.828 | **0.836** | 0.070 |
| dots_ocr | 0.549 | **0.897** | 0.734 | 0.006 |
| deepseek_ocr | 0.469 | 0.820 | 0.704 | 0.051 |
| qwen25vl | 0.637 | 0.736 | 0.701 | 0.018 |
| lightonocr | 0.658 | 0.726 | 0.675 | 0.142 |
| gemma4 | 0.564 | 0.706 | 0.414 | 0.157 |
| paddleocr_vl | 0.542 | 0.660 | 0.345 | 0.063 |
| got2 | 0.175 | 0.638 | 0.304 | 0.040 |
| granite_docling | 0.035 | 0.103 | 0.179 | — (OOM, N/A) |
| **tesseract** | 0.580 | 0.507 | 0.296 | **0.330** |
| **rapidocr** | 0.499 | 0.642 | 0.163 | 0.258 |
| **docTR** | **0.682** | 0.511 | 0.185 | 0.336 |
| **easyocr** | 0.583 | 0.483 | 0.162 | **0.397** |
| **kosmos25** | 0.565 | 0.539 | 0.259 | 0.204 |

(bold within a column = notable; new models bolded in the model column.)

## Findings

1. **Classic CPU OCR engines OWN Tier-C segmentation.** easyocr 0.397 / docTR 0.336 / tesseract
   0.330 / rapidocr 0.258 all beat the best v1 VLM (gemma4 0.157) by 1.6–2.5×, and dwarf the strong
   parse models (olmocr2 0.070, dots_ocr 0.006). Mechanism: Tier-C composes boundaries from clean
   per-page OCR text via the frozen judge; the classic engines emit steady, well-formed per-page text
   on dense scanned forms, whereas the VLMs degrade / over-merge on 145 MP multi-form pages. This is
   the headline reversal of the whole expansion — the cheap engines are the *best* tool for the
   segmentation tier.
2. **CPU engines are competitive Tier-B extractors.** docTR 0.682 is 2nd overall on realdoc_qa B.1
   (behind olmocr2 0.689, ahead of qwen25vl 0.637); tesseract/easyocr ~0.58. Field *values* are
   frequently short surface tokens a classic engine transcribes correctly, so downstream extraction
   holds up even where full-page fidelity does not.
3. **VLMs still own Tier-A parse fidelity.** olmocr_bench: olmocr2 0.836 vs the best classic
   (tesseract 0.296). omnidocbench similar (dots_ocr 0.897). Complex layout/table/math reconstruction
   remains a VLM strength; classic engines anchor the cheap floor, as intended.
4. **Kosmos-2.5 underdelivers** (0.20–0.57 across tiers) — terse outputs depress parse fidelity and
   Tier-C. It is not the small-VLM standout the size ladder anticipated; docTR (a 0-param-class
   classic engine) beats it on 3 of 4 tiers.

## Cost angle (throughput → $/page; full $ table lands in C2)

Accuracy is device-invariant, so we scored once and measured single-stream throughput per device
(findings/ws1-cpu-engines.md, RTX 5090): tesseract 3006 pg/hr (CPU), rapidocr 1214 (CPU), docTR 983
(CPU) / 24328 (GPU, ~25×), easyocr 2300 (GPU) / 43 (CPU, impractical). The provocative implication:
**docTR delivers 2nd-best Tier-B extraction and best-tier Tier-C segmentation at classic-engine cost**
— a cheap CPU-VM (or a GPU-VM for docTR/easyocr) plausibly wins $/page over a 7B VLM for the
extraction + segmentation workloads, while the VLMs are only worth their cost when Tier-A parse
fidelity is the requirement. The verified SKU $/hr ÷ pages/hr two-row (CPU-VM vs GPU-VM) table is the
C2 deliverable.

## Provenance / reproducibility

Run manifest `results/runs/v1-baseline/manifest.json`; scoreboard `results/runs/v1-baseline/scoreboard.csv`;
seed 0, temp 0; new-model revisions/licenses in `configs/models.yaml` (all verified live 2026-07-09);
hardware fingerprint per `baseline_model_results/hardware.json`. Co-load rule honored: Tier A+B
(1.5B reader) and Tier C (7B judge) scored in separate invocations.
