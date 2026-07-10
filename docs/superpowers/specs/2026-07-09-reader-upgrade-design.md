# Spec B — Tier-B B.2 comprehension-reader upgrade

**Date:** 2026-07-09
**Status:** implemented (code + free local verification); paid API ladder deferred to the
controller (no paid calls made in this pass).
**Scope:** the pluggable Tier-B B.2 reader instrument only. B.1 (deterministic field-value
presence, `docs/superpowers/specs/2026-07-08-tier-b-split-design.md`), the frozen Tier-C
Qwen2.5-7B judge/extractor pin, and every other frozen scorer are untouched.

## 1. Goal

The B.2 reader roster (`docs/superpowers/specs/2026-07-08-tier-b-split-design.md` §3) shipped
with a key-less local default (Qwen2.5-1.5B-Instruct) and two direct-provider API backends
(Anthropic Haiku, OpenAI GPT-5-mini). This spec:

1. Upgrades the key-less local default to a stronger, still-small, still-commercial-license
   model (**Phi-4-mini-instruct**) without losing the retained Qwen2.5-1.5B rung.
2. Adds a **named local-variant** mechanism so any local rung is selectable by `--reader <name>`,
   not just the single default.
3. Replaces the two API backends' transport with **OpenRouter** — one gateway key
   (`OPEN_ROUTER_API_KEY`) reaching both the Anthropic and OpenAI model families — because only
   that key is provisioned in this environment's `.env` (direct `ANTHROPIC_API_KEY` /
   `OPENAI_API_KEY` are not set), so the paid ladder the controller runs afterward needs the
   OpenRouter path to actually be reachable rather than silently falling back to local.

## 2. Reader roster (post-upgrade)

| Name | Kind | Model | License / key | Role |
|---|---|---|---|---|
| `local` (default) | local vLLM | `microsoft/Phi-4-mini-instruct` | MIT, key-less | key-less default — stronger small reader |
| `local_qwen15` | local vLLM | `Qwen/Qwen2.5-1.5B-Instruct` | Apache-2.0, key-less | retained ladder rung (previous default) |
| `haiku45` | OpenRouter | `anthropic/claude-haiku-4.5` | `OPEN_ROUTER_API_KEY` | recommended paid reader |
| `gpt5mini` | OpenRouter | `openai/gpt-5.4-mini` | `OPEN_ROUTER_API_KEY` | second paid reader |

`AnthropicReader`/`OpenAIReader` (direct-key transports) remain in `reader.py` unchanged — a
future environment with direct provider keys can still register a `backend: anthropic` /
`backend: openai` entry in `configs/models.yaml`; this upgrade did not remove that capability,
it just re-pointed the two named backends actually configured today at OpenRouter.

## 3. Local-default swap — Phi-4-mini-instruct

**Verified live 2026-07-09** via the unauthenticated HF models API
(`https://huggingface.co/api/models/microsoft/Phi-4-mini-instruct`):

- repo: `microsoft/Phi-4-mini-instruct`
- revision (sha): `cfbefacb99257ffa30c83adab238a50856ac3083`
- license tag: `license:mit`
- `pipeline_tag: text-generation`, `library_name: transformers`

Why this model clears the transformers-v5 remote-code trap that blocked Florence-2 / Phi-4-mm
(`findings/a4-expanded-roster.md`): Phi-4-mini-instruct is **natively integrated** in
`transformers` (4.49+; this stack runs 5.11) — it does not ship `trust_remote_code=True` custom
modeling code, so it is not exposed to the v5 remote-code registration breakage. It is
**text-only**, 3.8B params, and vLLM-supported (this stack runs vLLM 0.22.1), matching the
`VLLMExtractor`/reader machinery already in place for the frozen 7B extractor.

Qwen2.5-1.5B-Instruct (Apache-2.0, revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, verified
2026-07-08) is **kept**, not deleted — it becomes the `local_qwen15` named rung, preserving it as
a comprehension-floor ladder point (`2026-07-08-tier-b-split-design.md` §3 "comprehension-floor
study") below the new stronger default.

## 4. Named local variants

`configs/models.yaml` `instruments.reader` gains a `local_variants` map alongside
`default_local`:

```yaml
reader:
  default_local: { repo: microsoft/Phi-4-mini-instruct, revision: cfbefacb..., license: mit }
  local_variants:
    local_qwen15: { repo: Qwen/Qwen2.5-1.5B-Instruct, revision: 989aa798..., license: apache-2.0 }
  backends: { haiku45: {...}, gpt5mini: {...} }
```

`build_reader(name, cfg)` resolution order (unchanged behavior for existing names, additive for
new ones):

1. `name in ("local", "default", None)` → `default_local` (Phi-4-mini).
2. `name in local_variants` → that named local rung (`_build_local(cfg, variant)`).
3. `name in backends` → the API reader if its `secrets` are present, else fallback to
   `default_local` (key-less clones still run — this fallback behavior is unchanged).
4. Unknown name → fallback to `default_local`.

Any local rung's `.identity` is `f"{repo}@{revision}"` (from `VLLMExtractor`), which by
construction differs from every other repo/revision pair — including the frozen Tier-C judge
identity `Qwen/Qwen2.5-7B-Instruct@a09a35458c70`. Verified by
`test_reader_identity_distinct_from_frozen_judge` (`tests/test_reader_instrument.py`).

## 5. OpenRouter backend

New `OpenRouterReader` class in `src/tbdoc/instruments/reader.py`: an `openai` SDK client
(already a project dependency) pointed at `base_url="https://openrouter.ai/api/v1"` with
`api_key=os.environ["OPEN_ROUTER_API_KEY"]`. Satisfies the Extractor Protocol
(`.identity`/`.answer(md, q)`), reuses the same `_SYSTEM`/`_user` prompt builders,
`temperature=0`, `max_tokens=64`, and the same `RetryableError` mapping
(`openai.RateLimitError`/`openai.APITimeoutError`) as `OpenAIReader`. `.identity` is
`f"openrouter:{api_model_id}"` (e.g. `openrouter:anthropic/claude-haiku-4.5`) — distinguishable
from a direct-key reader's `f"anthropic:{...}"` identity in the scoreboard's provenance stamp,
so a rescored row can be told apart from a same-model direct-key run.

**Model slugs + pricing — verified live 2026-07-09** via an unauthenticated
`GET https://openrouter.ai/api/v1/models` (346 models returned; no completion call made, no
spend):

| Backend name | OpenRouter slug | prompt $/token | completion $/token | ⇒ $/MTok in / out |
|---|---|---|---|---|
| `haiku45` | `anthropic/claude-haiku-4.5` | 0.000001 | 0.000005 | 1.00 / 5.00 |
| `gpt5mini` | `openai/gpt-5.4-mini` | 0.00000075 | 0.0000045 | 0.75 / 4.50 |

Both slugs matched the brief's given values exactly (no correction needed) and the OpenRouter
per-MTok pricing is numerically identical to what the direct-provider entries already recorded
on 2026-07-08, so re-pointing the transport does not change the budget-guard math in
`configs/matrix.yaml`'s `max_usd_per_model`.

`build_reader` dispatches `backend: openrouter` entries to `OpenRouterReader`; missing
`OPEN_ROUTER_API_KEY` falls back to the local default, same as the other API backends.

## 6. Co-load / identity analysis

- The local reader (`VLLMExtractor` wrapping either Phi-4-mini or Qwen2.5-1.5B) is a vLLM engine
  at `gpu_memory_utilization≈0.9`. It **must never co-reside** with the Tier-C judge's own
  pinned-7B vLLM engine (also ≈0.9) or with a Tier-C `merged_forms` scoring pass in the same
  process — two ≈0.9 engines on one GPU OOM. `cli.py`'s `run` command already sequences these:
  the reader is built only when Tier-B benches need an `extractor`-instrument scorer, the judge
  only when a Tier-C bench is selected, and both are `unload()`-ed in the `finally` block. This
  spec does not change that sequencing; it only changes which repo/revision the local reader
  loads and how the API rungs authenticate.
- API readers (`AnthropicReader`/`OpenAIReader`/`OpenRouterReader`) hold no GPU state and have no
  `unload()` — `cli.py` already guards that (`hasattr(extractor, "unload")`).
- Identity: reader `.identity` values are always distinct from the frozen judge/extractor
  identity by construction (different repo string in the local case; `openrouter:`/`anthropic:`/
  `openai:` prefixes vs the bare `repo@revision` judge identity in the API case) — a scoreboard
  row can never confuse "who answered the B.2 question" with "who judged Tier-C boundaries."

## 7. Ladder-study design (unchanged from Spec A, restated for this upgrade)

The comprehension-floor ladder described in `2026-07-08-tier-b-split-design.md` §3 stays a
bounded, opt-in study: sequential local loads over the **same on-disk predictions**, re-scoring
B.2 only (no re-inference). With this upgrade, the size axis becomes **Qwen2.5-1.5B → Phi-4-mini
(3.8B)** at minimum, with the two OpenRouter-backed API readers (Haiku 4.5, GPT-5.4-mini) as the
strong-reader anchors the ladder is measured against. Running the ladder (which rungs, how many
samples) remains the owner's call — this spec only wires the rungs up as selectable
`--reader` names; it does not launch the study.

## 8. Scope boundaries

- **Untouched:** B.1 scoring path, `field_aware_exact_match`/`_norm`/`anls`, the frozen Tier-C
  `VLLMExtractor`/`BoundaryJudge` pin (`Qwen/Qwen2.5-7B-Instruct@a09a35458c70`), every other
  benchmark scorer/adapter, `configs/matrix.yaml` budget guard logic.
- **Changed:** `instruments.reader` in `configs/models.yaml` (`default_local` now Phi-4-mini;
  new `local_variants.local_qwen15`; `haiku45`/`gpt5mini` backends now `backend: openrouter`
  against `OPEN_ROUTER_API_KEY` instead of direct provider keys); `build_reader` in
  `src/tbdoc/instruments/reader.py` gains `local_variants` resolution and a new
  `OpenRouterReader` class/dispatch branch; `cli.py`'s `--reader` help text and an inline comment
  updated to match.
- **Verification performed this pass (free, local only):** HF model-card GET for Phi-4-mini;
  unauthenticated OpenRouter `/models` GET for both slugs + pricing; unit tests for
  construction/fallback/identity-distinctness (no network); a foreground Tier-B-only local smoke
  run (`--reader local`, 5 realdoc_qa samples) confirming the local engine loads, produces B.2
  answers, and B.1 stays unaffected — see `findings/` for the smoke run's result row.
- **Deferred to the controller:** the actual paid OpenRouter completion calls (haiku45/gpt5mini
  ladder rungs) and any reader-sensitivity / comprehension-floor study runs.
