# INTERIM Tier-A scores — v1-baseline (DRAFT, not for publication until verified)

Run `v1-baseline` (2026-07-08, harness `2abae49` *dirty*). 3 of 8 models, 2 of N benchmarks, 100 pages per model×bench.
Scoring: **olmocr_bench** primary = official unit-test pass rate (uncapped; `render_tests_excluded=0` on all pages).
**omnidocbench** primary = 1 − overall edit distance (higher better); 4 pages/model have `primary=null` (no scoreable elements — same 4 pages for all models: 2 colorful_textbook, 1 academic_literature, 1 magazine) and are excluded from means.
All records `error=null` (0 errors across 600 records). Greedy decoding, seed 0.

## Scoreboard (mean primary, macro over pages)

| Model | olmocr_bench | omnidocbench |
|---|---|---|
| olmocr2 (allenai/olmOCR-2-7B-1025 @ `e52d6f0`) | **0.836** (n=100) | **0.828** (n=96) |
| qwen25vl (Qwen/Qwen2.5-VL-7B-Instruct @ `cc59489`) | 0.702 (n=100) | 0.736 (n=96) |
| got2 (stepfun-ai/GOT-OCR-2.0-hf @ `d3017ef`) | 0.304 (n=100) | 0.638 (n=96) |

Micro pass rates on olmocr_bench (sum passed / sum tests, 636 tests total): olmocr2 522/636 = 0.821, qwen25vl 461/636 = 0.725, got2 152/636 = 0.239.

Consistency vs the prior ocparse n=100 baseline (capped render-test config): olmocr2 0.814 → 0.836, qwen25vl 0.694 → 0.702, got2 0.319 → 0.304. Deltas of ±0.02 are expected from the uncapped render-test config plus a different page sample; ranking is unchanged.

## olmocr_bench by category (mean primary)

| Category | n | olmocr2 | qwen25vl | got2 |
|---|---|---|---|---|
| arxiv_math | 15 | 0.894 | 0.716 | 0.163 |
| headers_footers | 15 | 0.893 | 0.590 | 0.906 |
| long_tiny_text | 14 | 0.925 | 0.855 | 0.443 |
| multi_column | 14 | 0.918 | 0.564 | 0.179 |
| old_scans | 14 | 0.476 | 0.477 | 0.296 |
| old_scans_math | 14 | 0.799 | 0.776 | 0.111 |
| tables | 14 | 0.941 | 0.941 | **0.000** |

## olmocr_bench by test type (Σpassed / Σtotal across pages)

| Type | olmocr2 | qwen25vl | got2 |
|---|---|---|---|
| absent | 60/66 = 0.909 | 42/66 = 0.636 | 60/66 = 0.909 |
| math | 213/258 = 0.826 | 196/258 = 0.760 | 34/258 = 0.132 |
| order | 56/78 = 0.718 | 39/78 = 0.500 | 13/78 = 0.167 |
| present | 97/131 = 0.740 | 90/131 = 0.687 | 45/131 = 0.344 |
| table | 96/103 = 0.932 | 94/103 = 0.913 | **0/103 = 0.000** |

## omnidocbench by category (mean primary; n excludes nulls)

| Category | n (null) | olmocr2 | qwen25vl | got2 |
|---|---|---|---|---|
| PPT2PDF | 11 | 1.000 | 0.980 | 0.996 |
| academic_literature | 10 (1) | 0.887 | 0.679 | 0.671 |
| book | 11 | 0.986 | 0.977 | 0.644 |
| colorful_textbook | 9 (2) | 0.896 | 0.769 | 0.679 |
| exam_paper | 11 | 0.882 | 0.886 | 0.747 |
| historical_document | 5 | 0.716 | **0.039** | 0.480 |
| magazine | 9 (1) | 0.992 | 0.966 | 0.865 |
| newspaper | 10 | **0.167** | **0.250** | **0.089** |
| note | 10 | 0.921 | 0.909 | 0.747 |
| research_report | 10 | 0.764 | 0.518 | 0.364 |

omnidocbench element-level means (edit dist, lower better; TEDS higher better): table_edit_dist (n=24): olmocr2 0.217, qwen25vl 0.628, got2 1.000; table_TEDS: 0.761 / 0.689 / 0.000. formula_edit_dist (n=11): 0.050 / 0.052 / 0.413.

## Per-model interpretation

**olmocr2** — Strongest across the board (0.836 / 0.828), leading every olmocr_bench category except old_scans (0.476, tied with qwen25vl — degraded historical scans are the shared weak spot) and every test type (tables 0.932, math 0.826). On omnidocbench its only bad category is newspaper (0.167), where all models collapse. Slightly above the prior capped baseline (0.814), as expected from including render tests.

**qwen25vl** — Solid generalist (0.702 / 0.736): matches olmocr2 on tables (0.941) and near-parity on math categories, but loses badly on layout-sensitive work — multi_column 0.564, order tests 0.500, absent tests 0.636 (hallucinates/leaks content that shouldn't be there, e.g. headers_footers 0.590). Its 0.039 on omnidocbench historical_document (3 of 5 pages at exactly 0.00 with output pinned at the 4096-token cap and very low entropy) looks like repetition-loop degeneration on hard scans, not merely weak OCR.

**got2** — Bimodal (0.304 / 0.638): competitive on plain running text (headers_footers 0.906, absent 0.909, book/PPT decent on omnidocbench) but effectively fails structured output — **0/103 table tests and table_TEDS = 0.000 / table_edit_dist = 1.000 on all 24 table pages**, math 0.132, multi_column 0.179. The clean zero on both benchmarks' table metrics suggests an output-format mismatch (GOT-2 emits tables/formulas in its own markup that the scorers don't credit) at least as much as raw capability — worth a manual look at 2-3 raw outputs before publishing. Consistent with the prior 0.319 baseline.

## Telemetry (per page)

| Model | Bench | Mean latency | Median | Max | Peak VRAM |
|---|---|---|---|---|---|
| olmocr2 | olmocr_bench | 10.2 s | 8.5 s | 27 s | 29.5 GB |
| olmocr2 | omnidocbench | 9.7 s | 5.3 s | 41 s | 29.5 GB |
| qwen25vl | olmocr_bench | 9.3 s | 7.7 s | 41 s | 29.5 GB |
| qwen25vl | omnidocbench | 11.3 s | 5.4 s | 41 s | 29.5 GB |
| got2 | olmocr_bench | 6.1 s | 5.3 s | 17 s | 3.6 GB |
| got2 | omnidocbench | 3.5 s | 2.9 s | 14 s | 3.6 GB |

(vLLM peak VRAM ≈ 29.5 GB reflects the configured gpu_memory_utilization pool, not model footprint; got2 runs via transformers at 3.6 GB.)

## Sanity flags (resolve before publishing)

_Status audit 2026-07-12: flags 1, 2, 5 all addressed. Flag 2 disclosed (README Gaps +
docs/REFERENCE.md#gaps); flag 5 covered by v1-baseline's manifest reconstruction note;
flag 1 (got2 table zero) explained below._

1. **got2 table zero is suspiciously clean** — 0/103 olmocr_bench table tests AND TEDS 0.000 on all 24 omnidocbench table pages. **RESOLVED 2026-07-12** ([got2-table-zero.md](got2-table-zero.md)): a **format mismatch** — got2 is the only model emitting LaTeX `\begin{tabular}` (29 pages), and the olmOCR/omnidocbench table scorers parse only markdown-pipe + HTML tables, so they report "No tables found" and auto-fail before grading content. Caveat: got2's LaTeX is itself malformed, so it wouldn't score well even with a LaTeX-aware scorer — but the categorical zero is the format gap. Don't cite got2's table sub-scores as a quality claim.
2. **4096-token output cap is binding on dense pages** — the worst newspaper pages (all models) and qwen25vl's 0.00 historical_document pages all hit exactly 4096 output tokens. Newspaper truncation depresses scores mechanically; consider noting the cap in the README or re-running dense categories with a higher cap. qwen25vl's low-entropy 4096-token outputs match the known repetition-loop failure mode. **Disclosed in README Gaps + REFERENCE.md (2026-07-12); caps not yet equalized.**
3. **Newspaper collapse is universal** (0.089–0.250) — consistent with the cap issue above plus known difficulty; don't read it as a model ranking signal.
4. **olmocr_bench category n is 14–15, omnidocbench 5–11 per category** — historical_document has only n=5; per-category numbers are noisy, label as indicative.
5. **manifest says `git_dirty: true`** — the harness tree was dirty at run time; note in provenance or re-stamp before publishing.
6. No errors, no missing records (600/600), model revisions pinned in manifest; same 4 null omnidocbench pages across all models (expected: no scoreable elements).
