# CLAUDE.md — Standing rules for trial-by-doc

## Prime directive: verify, never assume
Never state a model repo ID, license, revision hash, API price, recommended setting, or
hardware capability from memory. Verify against the live source (HF model card, provider
pricing page, `nvidia-smi`/torch) and record it (configs/, findings/, configs/benchmarks.yaml).
If reality contradicts the plan, STOP and flag the owner.

## What this repo is
A model-agnostic OCR / doc-intelligence evaluation gauntlet. Any model = one adapter
subclass + one `configs/models.yaml` entry. Four tiers (A/B/C orthogonal capabilities;
D is a stress axis over B):
- **Tier A — parse fidelity** (grade OCR output directly; deterministic scorers)
- **Tier B — downstream extraction** (markdown → frozen extractor → exact-match/ANLS)
- **Tier C — document segmentation** (multi-doc PDFs → boundary F1 / PQ / STP)
- **Tier D — robustness** (Tier-B pages under deterministic scan/fax degradation;
  headline metric is reader-independent B.1, so a drop is the OCR degrading, not a
  reader confound)

## Hard rules
- **No LLM-as-judge.** All scoring functions are deterministic algorithms. LLMs appear
  only as *frozen instruments* (Tier B extractor, Tier C boundary_judge): pinned
  revision, temp=0, seeded, identical for every model. Scoreboard marks
  instrument-mediated columns. `--no-llm-instruments` runs strictly LLM-free.
- **Official scorers are wrapped, never reimplemented.** Each lives in its own isolated
  venv or Docker image (`benchmarks/_scorers/<name>/`), subprocess JSON-in/JSON-out.
- **Provenance is first-class.** `official` (third-party dataset + scorer) vs `custom`
  (we own ground truth + scorer). Custom benchmarks REQUIRE a VALIDATION.md; the
  registry refuses them without it.
- **Reproducibility is a deliverable.** Every result row: model fingerprint (revision
  or API version + called-on date), bench dataset revision, scorer identity, seeds,
  hardware fingerprint, run_id → results/runs/<id>/manifest.json.
- **API cost guard**: `gauntlet estimate-cost` before any paid run; per-model budget
  cap in matrix.yaml enforced before spend. Secrets in .env (gitignored); check
  presence only, NEVER print values.
- Smoke gate before any full run (hard stop for owner sign-off).

## Environment notes (reference host "Quantum", verified 2026-06-12 in the ocparse repo)
uv-managed, Python 3.12. RTX 5090 (Blackwell sm_120), driver 595.71.05, torch
2.11.0+cu130, vLLM 0.22.1 prebuilt, transformers 5.11. Never install xformers.
vLLM 0.22: `VLLM_ATTENTION_BACKEND` env is a NO-OP — pass `attention_backend=` to LLM()
(we read `TBDOC_ATTN_BACKEND`). FlashAttention 2 default; `enforce_eager=True` on this
host. CUDA 13.3 toolkit at ~/cuda-13.3 for JIT builds (core/cuda_env wiring, config-
gated — host-specific). vLLM runs models in a subprocess → measure VRAM via nvidia-smi.

## Lineage
Contracts evolved from the owner's ocparse project (of-course-i-can-parse-that);
scorer-isolation and provenance-stamping culture carried over.
