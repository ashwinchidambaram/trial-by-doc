# Session Handover — trial-by-doc

_Written 2026-07-10. Snapshot for picking up a fresh session. If this contradicts
`git log` or `findings/`, trust git — this file goes stale._

> **Staleness update (2026-07-12):** main has moved well past `696efd3` — since this
> was written: README restructure + density fix (PRs #1–3), CI ui-extra fix (#4), the
> gpt-5.4-mini B.2 rescore tracked + folded in (#5–6, `findings/b2-gpt5mini-rescore.md`),
> pipeline hardening — reader retry/cost-guard, merge-on-write run artifacts (#7),
> fresh-clone replicability via tracked `summary.json` (#8), and the results-integrity
> pass (Tier C floors on all 15 streams: run `tierc-floor-15`; Spearman correction;
> v1-baseline manifest reconstruction). The section below stays as the Phase-1 record.
> Known deferred: haiku-4.5 B.2 rung (owner-paused). Closed in the 2026-07-12 followups
> pass: got2 table-zero (format mismatch — findings/got2-table-zero.md), paired bootstrap
> CIs (findings/statistical-significance.md + `gauntlet scoreboard --ci`), Docker
> lockfile pinning (Dockerfile.cpu now `--frozen`), developer-affiliation disclosure.
> Still open: Dockerfile.gpu not yet `--frozen`, token-cap equalization (disclosed only),
> the API fleet, and merged_forms' owner spot-check.

## TL;DR

**Phase 1 is complete and merged to `main` (pushed to origin at `696efd3`).** The
document-OCR evaluation harness now has a 14-model baseline across 4 tiers, a pluggable
Tier-B reader with a sensitivity ladder, a fresh-clone `verify-env` preflight, code-generated
report tables, a scanned-robustness study, and a full results dashboard (`gauntlet ui`).

Per `CLAUDE.md`, Phase 1 ends with a **hard STOP before Phase 2** (data pipeline /
fine-tuning / distillation). Do not start Phase 2 without owner sign-off.

## How to work in this repo (read first)

- **The shell cwd resets to `of-course-i-can-parse-that` on every Bash call.** Always
  `cd /home/ashwinc/dev/projects/trial-by-doc &&  ...` in each command.
- Python is **uv-managed**: run everything via `uv run <cmd>` (e.g. `uv run pytest -q`,
  `uv run gauntlet ...`).
- CLI entrypoint is `gauntlet`: `run` (infer/score), `scoreboard`, `ui`, `verify-env`,
  `validate-adapter`.
- **Verify, never assume** (CLAUDE.md prime directive): re-pin any model repo/revision/
  license/price against the live source at wire-in; record it in `configs/` or `findings/`.
  If reality contradicts the plan, STOP and flag the owner.
- **Never modify the frozen instruments/scorers.** Extractor + boundary judge =
  `Qwen2.5-7B-Instruct@a09a35458c70`; scorers `field_aware_exact_match`,
  `field_value_presence`/`_norm`, `anls`. Never print secret values
  (`OPEN_ROUTER_API_KEY`, `HF_TOKEN` in `.env`). Never install xformers.
- Design specs live in `docs/superpowers/specs/`. Environment facts (Blackwell/sm_120,
  torch 2.11+cu130, vLLM 0.22, transformers 5.11): see `CLAUDE.md` "Environment notes".

## What's on main (all done, all merged)

| Part | Deliverable | Key commits |
|---|---|---|
| A | +5 contenders (tesseract, rapidocr, docTR, easyocr, kosmos25) scored on every applicable tier | `55b0e05`, `7c667a0`, `c5fe901`, merge `215d573` |
| B | B.2 reader upgraded to Phi-4-mini (local default) + OpenRouter ladder (gpt-5.4-mini, claude-haiku-4.5); reader-sensitivity study | `e5eea22` |
| C1 | `gauntlet verify-env` preflight (GPU + CPU + scorers + datasets + secrets-presence) | `src/tbdoc/core/preflight.py` |
| C2 | `gauntlet scoreboard --readme-inject` regenerates report tables into README | `scoreboard.py:inject_readme` |
| C3 | Dashboard rebuild (decide cockpit / diagnose workbench / verify explorer, AC brand) | merge `696efd3` |
| D | Scanned-degradation robustness study (clean/light/heavy) | `580ae7b`, `findings/partd-*` |

## The 14-model scoreboard (`results/runs/v1-baseline/scoreboard.csv`)

Primary metric per tier — realdoc_qa = Tier-B extraction (b1), omnidocbench/olmocr_bench =
Tier-A parse fidelity, merged_forms = Tier-C segmentation (boundary-judge PQ). Higher = better;
bold = column best.

| model | realdoc_qa (B) | omnidocbench (A) | olmocr_bench (A) | merged_forms (C) |
|---|---|---|---|---|
| olmocr2 | 0.689 | 0.828 | **0.836** | 0.070 |
| dots_ocr | 0.549 | **0.897** | 0.734 | 0.006 |
| deepseek_ocr | 0.469 | 0.820 | 0.704 | 0.051 |
| qwen25vl | 0.637 | 0.736 | 0.701 | 0.018 |
| lightonocr | 0.658 | 0.726 | 0.675 | 0.142 |
| gemma4 | 0.564 | 0.706 | 0.414 | 0.157 |
| paddleocr_vl | 0.542 | 0.660 | 0.345 | 0.063 |
| got2 | 0.175 | 0.638 | 0.304 | 0.040 |
| kosmos25 | 0.565 | 0.539 | 0.259 | 0.204 |
| **tesseract** | 0.580 | 0.507 | 0.296 | 0.330 |
| **docTR** | **0.682** | 0.511 | 0.185 | 0.336 |
| **easyocr** | 0.583 | 0.483 | 0.162 | **0.397** |
| **rapidocr** | 0.499 | 0.642 | 0.163 | 0.258 |
| granite_docling | 0.035 | 0.103 | 0.179 | — (OOM) |

Headline findings (`findings/a4-expanded-roster.md`):
1. **Classic CPU engines OWN Tier-C segmentation** — easyocr 0.397 / docTR 0.336 /
   tesseract 0.330 / rapidocr 0.258 all beat the best VLM (gemma4 0.157) by 1.6–2.5×.
   Mechanism: Tier-C composes boundaries from clean per-page OCR text; classic engines emit
   steady per-page text where VLMs over-merge on huge multi-form pages.
2. **CPU engines are competitive Tier-B extractors** — docTR 0.682 is 2nd overall on b1.
3. **VLMs still own Tier-A parse fidelity** — olmocr2 0.836 (olmocr_bench), dots_ocr 0.897
   (omnidocbench); best classic (tesseract) only ~0.30–0.51 there.
4. **Kosmos-2.5 underdelivers** (0.20–0.57); docTR beats it on 3 of 4 tiers.

## Known blockers (flagged, revival-ready — NOT bugs to fix blindly)

- **Florence-2** and **Phi-4-multimodal** are BLOCKED on the pinned **transformers 5.11**
  (distinct pre-v5 remote-code incompatibilities). Adapters kept but **unregistered** in
  `configs/models.yaml` (see the commented block ~line 128 + each adapter's docstring).
  Dropped from the scored roster. Revisit only if upstream ports them to native v5.
- **granite_docling** OOMs on merged_forms (Tier-C) — deferred, shown as N/A.

## Operational rule you WILL hit (co-load / OOM)

The Phi-4-mini B.2 reader is **vLLM-backed** (`instruments/reader.py:_build_local` →
`VLLMExtractor`). Running a Tier-B bench (loads the reader) and a Tier-C bench (loads the 7B
judge) in **one** `gauntlet run --phase score` invocation OOMs — two vLLM engines each grab
`gpu_memory_utilization=0.9` on a 32GB card. **Score Tier B and Tier C in separate score
invocations** (inference can be combined). This is why v1-baseline was scored in two passes.

## Repo cleanliness / scratch state

- `main` is clean and pushed to origin (`696efd3`). No crons armed (disarmed at `6323f63`).
- Untracked scratch runs under `results/runs/`: `smoke-*`, `partb-localsmoke`,
  `partd-validate-{light,heavy}` are regenerable plumbing smokes; `rl-{gpt5,haiku,phi4}`
  are the reader-ladder runs (findings already in `findings/partb-reader-ladder.md`; two cost
  API budget). Disposition pending owner decision — safe to delete the smokes, keep rl-*
  gitignored if you want the paid evidence.
- Tracked baseline runs (do NOT delete): `v1-baseline`, `gate1`, `tierb-smoke`,
  `tierc-floor`, `all-models-smoke`.

## Dashboard

`cd /home/ashwinc/dev/projects/trial-by-doc && uv run gauntlet ui --no-browser --port 8765`
→ http://127.0.0.1:8765 (localhost-only, read-only, no network). Three surfaces: Decide
(leaderboard + value frontier + accuracy-vs-cost tradeoff), Diagnose (per-example workbench:
page image / model markdown / ground truth with scorer-aligned gold highlight), Explore
(benchmark ledger, license-gated thumbnails). Screenshots in `docs/ui/`, README `## Dashboard`.

## Suggested next steps (await owner sign-off before Phase 2)

- **Parked roadmap items** (from the plan, explicitly out of Phase 1): granite Tier-C revisit,
  merged_forms human spot-check (owner action), API vision-contender scored runs (mistral/
  gemini/Claude/GPT vision — wired but deferred), tierB_kie, RealDoc-Layout, quantized
  variants, OmniDocBench CDM headline, distillation / custom CPU model.
- **Phase 2** (STOP gate): data pipeline → teacher-routing → distillation. Needs owner
  go-ahead; Phase 1 produced only the baseline scoreboard + draft routing table.
