# Add your model to the gauntlet

Any model gets in with **one adapter subclass + one YAML entry**. No harness edits.

## 1. Pick your adapter base

| Your model is... | Subclass | Working example |
|---|---|---|
| Open-weights VLM on your GPU (vLLM-servable) | `VLLMModelAdapter` | `src/tbdoc/models/local/qwen25vl.py` (18 lines) |
| Open-weights needing raw transformers | `TransformersModelAdapter` | `src/tbdoc/models/local/got2.py` |
| A chat-vision API you prompt for markdown | `VisionChatAdapter` | `src/tbdoc/models/api/anthropic_vision.py` |
| A dedicated document/OCR API | `APIModelAdapter` | `src/tbdoc/models/api/mistral_ocr.py` |

Copy `src/tbdoc/models/template/my_model.py` and fill in the blanks. The contract is
tiny: `predict(page_image) -> StructuredDoc(markdown, ...)`. API bases give you rate
limiting, retry/backoff, cost + telemetry stamping, and secrets checking for free.

## 2. Register it

Add to `configs/models.yaml` (verify repo id / revision / license on the LIVE model
card — this repo's rule is verify-never-assume):

```yaml
  my_model:
    kind: local                        # local | api | baseline
    adapter: "my_pkg.my_model:MyModelAdapter"   # any importable dotted path
    repo_id: your-org/your-model
    revision: <commit hash>            # pin it — reproducibility is a deliverable
    backend: vllm
    license: apache-2.0
    commercial_use: true
    # api models add: provider, api_model_id, secrets: [MY_KEY], rate_limit, retry, pricing
```

Secrets go in `.env` (gitignored); the harness checks presence and never logs values.

## 3. Validate, then run

```bash
uv run gauntlet validate-adapter my_model            # shape/telemetry/secrets smoke, 3 pages
uv run gauntlet run -m my_model -b olmocr_bench --max-samples 5 --run-id mine   # tiny real slice
uv run gauntlet run -m my_model -p v1 --run-id mine  # your model over the full published bench set
uv run gauntlet scoreboard --run-id mine             # your scores, provenance-stamped
```

**Compare against the published baselines without re-running them**: keep the `v1`
profile's per-bench sample caps (the stratified loaders then select the identical
samples) and read your rows against `uv run gauntlet scoreboard --run-id v1-baseline`
— which renders from the tracked `summary.json` even on a fresh clone — or the README
table. The dashboard's run picker (`uv run gauntlet ui`) shows both runs side by side.

Runs are resumable (`--run-id`), scoring is decoupled from inference
(`--phase score --rescore` re-scores without re-running your model), and API spend
is estimated and budget-capped before any call — including Tier-B API reader spend.

## Tier C (document segmentation)

If your model/service natively splits multi-document streams, override
`segment(pages) -> Segmentation` and declare the `"segmentation"` capability —
the scoreboard marks yours `native`. Otherwise every model is automatically
evaluable via the frozen boundary-judge instrument (`judge_composed`).

## Ground rules

- The **prompt and output normalization live in your adapter** and are part of the
  measured system — keep them stable, document them in the adapter docstring.
- Official benchmark scorers are wrapped, never reimplemented; don't touch them.
- Scoring is deterministic — no LLM-as-judge. LLM instruments (Tier B extractor,
  Tier C boundary judge) are frozen: pinned revision, temp=0, seeded.
