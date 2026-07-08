# M1 — Walking skeleton (GATE 1 PASSED, 2026-07-07)

2 models × olmocr_bench × 5 pages, end-to-end on real infra:
- **qwen25vl** (vLLM 0.22.1, RTX 5090): 5 real predictions → official olmocr scorer
  (isolated venv) → per-page pass rates [—(math-only page), 0.50, 0.42, 1.00, 0.20],
  cell mean 0.529 (n=4 scoreable; plausible vs the ocparse n=100 value 0.694).
- **anthropic_vision**: no ANTHROPIC_API_KEY on host → clean fail-fast at load,
  all 5 cells recorded as error rows (no crash, no silent gap).
- **Resume verified**: rerunning the same run-id → 0 predictions, 0 scores, 0 model loads.
- **Provenance**: manifest.json carries git SHA, config hashes, model revision
  (cc594898137f), bench revision (54a96a6f), GPU fingerprint. Every result row stamps
  model_revision + telemetry (VRAM ~29.5 GB during vLLM serve).
- 13 unit tests green (two-phase runner, resume, error rows, registry refusal,
  ratelimit/backoff, secrets, Segmentation).

Notes:
- vLLM resolved to 0.24.0 initially — pinned back to the verified 0.22.x
  (pyproject) until a deliberate re-verification.
- arxiv_math pages can be 100% math-type tests → primary=None on host (render tests
  excluded); the math/table container scorer lands in M2. Scoreboard means skip None.
- MuPDF color-profile warnings on old_scans PDFs are benign stderr noise.
