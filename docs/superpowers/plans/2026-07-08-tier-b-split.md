# Tier B Split (Plan 1: core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Tier B into B.1 (deterministic field-value extraction fidelity, the primary signal) and B.2 (comprehension via a single *selectable* reader instrument — local small model / Haiku 4.5 / GPT-5 mini), with a README explainer and roadmap deferrals.

**Architecture:** All changes are **scoring-phase + reporting + docs** — nothing touches inference. B.1 is a pure-python scorer over `prediction.markdown`, reusing the existing field-matching helpers; it becomes the cell `primary`. B.2 is the existing extractor path, relabeled and generalized so the "extractor" is any instrument satisfying the `Extractor` Protocol (local vLLM small model by default; Anthropic/OpenAI text readers when a key is set). Multi-reader comparison (both readers in one pass, sensitivity table, ladder curve) is deferred to Plan 2.

**Tech Stack:** Python 3.12, uv, pytest, vLLM 0.22.1, transformers 5.11, click CLI, `anthropic`/`openai` SDKs (text chat only).

## Global Constraints

- **Verify, never assume** — exact API model ids, pricing, and licenses are confirmed against the live source at wire-in and recorded in configs; never hardcode from memory. (CLAUDE.md prime directive.)
- **Pins are load-bearing:** `vllm>=0.22,<0.23`, `transformers>=5.11,<5.12`. Do not bump.
- **Do NOT disturb the in-flight `v1-baseline` run.** All rescoring/tests write to a scratch run-id (e.g. `tierb-dev`), never to `results/runs/v1-baseline/` until inference completes and the owner approves.
- **B.1 is fully deterministic** — no LLM anywhere in its path.
- **Secrets are never logged**; API readers declare `secrets:` and go through `core.secrets.require_secrets`.
- **The pinned Qwen2.5-7B `@a09a35458c70` stays the Tier C boundary judge, untouched.** B.2's local default is Qwen2.5-3B-Instruct.
- Reuse existing helpers in `src/tbdoc/scoring/scorers.py` (`_parse_fields`, `_values_match`, `_as_number`, `_canon_value`); do NOT touch `_norm`, `anls`, or `field_aware_exact_match`.

---

### Task 1: B.1 field-value-presence scorer + extractive-subset filter

**Files:**
- Modify: `src/tbdoc/scoring/scorers.py` (append new functions; touch nothing existing)
- Test: `tests/test_field_value_presence.py`

**Interfaces:**
- Consumes: `_parse_fields`, `_values_match`, `_as_number`, `_canon_value`, `anls` (existing, same file).
- Produces:
  - `is_extractive_gold(question: str, golds: list[str]) -> bool`
  - `field_value_presence(markdown: str, golds: list[str], anls_threshold: float = 0.8) -> float`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_field_value_presence.py
from tbdoc.scoring.scorers import is_extractive_gold, field_value_presence


def test_numeric_value_present_exact_and_formatted():
    md = "Total Due .......... $8,500.00 for services rendered"
    assert field_value_presence(md, ["nexus_tech_amount_paid=8500"]) == 1.0

def test_value_absent_scores_zero():
    md = "The quick brown fox jumps over the lazy dog."
    assert field_value_presence(md, ["nexus_tech_amount_paid=8500"]) == 0.0

def test_partial_multifield_recall():
    md = "Name: Jane Roe    Amount: 8500"
    # two gold fields; only the amount is present -> 0.5
    got = field_value_presence(md, ["amount=8500;name=John Doe"])
    assert abs(got - 0.5) < 1e-9

def test_string_value_slightly_garbled_within_threshold():
    md = "Applicant name: Jane Roee"  # one-char OCR slip
    assert field_value_presence(md, ["name=Jane Roe"], anls_threshold=0.8) == 1.0

def test_boolean_alias_present():
    md = "Checkbox for exemption: [X]"
    assert field_value_presence(md, ["exempt=true"]) == 1.0

def test_derived_answer_is_not_extractive():
    assert is_extractive_gold("How many line items are on the invoice?", ["count=7"]) is False

def test_surface_value_is_extractive():
    assert is_extractive_gold("What is the amount paid?", ["amount=8500"]) is True

def test_long_freetext_gold_not_extractive():
    long = "x" * 100
    assert is_extractive_gold("Summarize the letter", [f"summary={long}"]) is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/ashwinc/dev/projects/trial-by-doc && uv run pytest tests/test_field_value_presence.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_extractive_gold'`.

- [ ] **Step 3: Implement the scorer (append to scorers.py)**

```python
# ---- B.1 extraction fidelity (deterministic; no LLM) -------------------------------------------
# "Did the OCR reproduce the gold field VALUES on the page?" Reuses the field parsing + tolerant
# value matching from field_aware_exact_match, but searches the markdown instead of an answer.

import re as _re

_DERIVED_PAT = _re.compile(r"\b(how many|number of|count of|how much .*in total|total number)\b", _re.I)


def _surface_token(v: str) -> bool:
    """A value that could plausibly appear verbatim on a page: numeric, or a short string (<=64)."""
    if _as_number(v) is not None:
        return True
    return 0 < len(str(v).strip()) <= 64


def is_extractive_gold(question: str, golds: list[str]) -> bool:
    """True if this item's answer is a surface token on the page (vs derived/reasoned)."""
    if _DERIVED_PAT.search(question or ""):
        return False
    for g in golds:
        fields = _parse_fields(g)
        vals = list(fields.values()) if fields else [g]
        if vals and all(_surface_token(v) for v in vals):
            return True
    return False


def _value_in_markdown(value: str, markdown: str, anls_threshold: float) -> bool:
    """Is `value` present in `markdown`? Numeric: any numeric token matches (tolerant).
    Boolean (true/false): any markdown token canonicalizes to the same boolean (credits a
    correctly-transcribed checkbox glyph like [X]/[ ]). String: canonical substring, else best
    sliding-window ANLS >= threshold."""
    md = markdown or ""
    n = _as_number(value)
    if n is not None:
        for tok in _re.findall(r"-?\$?\d[\d,]*\.?\d*%?", md):
            if _values_match(tok, value):
                return True
        return False
    cv = _canon_value(value)
    if cv in ("true", "false"):
        # tokenize incl. checkbox glyphs, then canonicalize each token to its boolean (if any)
        for tok in _re.findall(r"\[[ xX✓✔]\]|\([ xX]\)|☑|☐|[^\s]+", md):
            if _canon_value(tok) == cv:
                return True
        return False
    if not cv:
        return True
    md_norm = " ".join(md.lower().split())
    if cv in md_norm:
        return True
    w = len(cv)
    for i in range(0, max(1, len(md_norm) - w + 1), max(1, w // 2)):
        if anls(md_norm[i:i + w], [cv], threshold=anls_threshold) >= anls_threshold:
            return True
    return False


def field_value_presence(markdown: str, golds: list[str], anls_threshold: float = 0.8) -> float:
    """Fraction of gold field VALUES found in the markdown (best over the gold variants)."""
    best = 0.0
    for g in golds:
        fields = _parse_fields(g)
        vals = list(fields.values()) if fields else [g]
        if not vals:
            continue
        hits = sum(1 for v in vals if _value_in_markdown(v, markdown, anls_threshold))
        best = max(best, hits / len(vals))
    return best
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_field_value_presence.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tbdoc/scoring/scorers.py tests/test_field_value_presence.py
git commit -m "feat(scoring): B.1 field-value-presence scorer + extractive-subset filter (deterministic)"
```

---

### Task 2: RealDoc-QA emits b1 (primary) + b2 + extractive flag

**Files:**
- Modify: `src/tbdoc/benches/official/realdoc_qa.py` (the `evaluate` method only)
- Test: `tests/test_realdoc_eval_split.py`

**Interfaces:**
- Consumes: `field_value_presence`, `is_extractive_gold` (Task 1); `field_aware_exact_match`, `anls` (existing); `Extractor` Protocol / `FunctionExtractor` (`tbdoc.instruments.extractor`).
- Produces: `RealDocQA.evaluate(sample, prediction, extractor=None)` returning metrics with keys:
  `primary` (=b1 when extractive else None), `b1`, `extractive` (bool), `b2`, `b2_anls`, `reader`, `answer`, `category`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_realdoc_eval_split.py
from types import SimpleNamespace
from tbdoc.benches.official.realdoc_qa import RealDocQA
from tbdoc.instruments.extractor import FunctionExtractor


def _sample(gold, question="What is the amount paid?", domain="finance"):
    from tbdoc.core.bench_adapter import Sample
    return Sample(id="q1", gold=[gold], question=question, category=domain)

def _pred(markdown):
    return SimpleNamespace(markdown=markdown, telemetry=SimpleNamespace(to_dict=lambda: {}))

def test_b1_is_primary_and_deterministic_without_reader():
    ba = RealDocQA("realdoc_qa")
    m = ba.evaluate(_sample("amount=8500"), _pred("Amount: 8500"), extractor=None)
    assert m["b1"] == 1.0
    assert m["primary"] == 1.0
    assert m["extractive"] is True
    assert m["b2"] is None      # no reader -> comprehension not computed

def test_derived_item_excluded_from_b1_primary():
    ba = RealDocQA("realdoc_qa")
    m = ba.evaluate(_sample("count=7", question="How many line items?"),
                    _pred("... a table ..."), extractor=None)
    assert m["extractive"] is False
    assert m["primary"] is None  # dropped from the B.1 mean

def test_b2_uses_reader_when_present():
    ba = RealDocQA("realdoc_qa")
    reader = FunctionExtractor(lambda md, q: "8500", identity="fake-reader")
    m = ba.evaluate(_sample("amount=8500"), _pred("Amount: 8500"), extractor=reader)
    assert m["b2"] == 1.0
    assert m["reader"] == "fake-reader"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_realdoc_eval_split.py -v`
Expected: FAIL (`KeyError: 'b1'` or assertion on old `primary` semantics).

- [ ] **Step 3: Replace the `evaluate` method**

```python
# in src/tbdoc/benches/official/realdoc_qa.py — replace the whole evaluate() method
    def evaluate(self, sample: Any, prediction: Any, extractor: Any | None = None) -> dict:
        from tbdoc.scoring.scorers import field_value_presence, is_extractive_gold
        golds = sample.gold or [""]
        md = getattr(prediction, "markdown", "") or ""
        extractive = is_extractive_gold(sample.question or "", golds)
        b1 = field_value_presence(md, golds) if extractive else None
        # B.2 comprehension — only when a reader instrument is supplied (secondary signal)
        b2 = b2_anls = answer = reader_id = None
        if extractor is not None:
            answer = extractor.answer(md, sample.question or "")
            b2 = field_aware_exact_match(answer, golds)
            b2_anls = anls(answer, golds)
            reader_id = getattr(extractor, "identity", "?")
        return {"primary": b1,            # B.1 is the headline; None -> excluded from the mean
                "b1": b1, "extractive": extractive,
                "b2": b2, "b2_anls": b2_anls, "reader": reader_id,
                "answer": (answer[:200] if answer else None),
                "category": sample.category}
```

Keep `requires_extractor = True` (so the score phase still offers a reader for B.2), and keep `load()` unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_realdoc_eval_split.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tbdoc/benches/official/realdoc_qa.py tests/test_realdoc_eval_split.py
git commit -m "feat(realdoc): emit b1 (primary, deterministic) + b2 (reader) + extractive flag"
```

---

### Task 3: Pluggable reader instrument (local small default + Anthropic + OpenAI)

**Files:**
- Create: `src/tbdoc/instruments/reader.py`
- Modify: `configs/models.yaml` (add a `reader` block under `instruments:`)
- Test: `tests/test_reader_instrument.py`

**Interfaces:**
- Consumes: `VLLMExtractor` (existing — already takes `repo`/`revision`); `core.secrets.require_secrets`; `core.ratelimit.RetryableError`.
- Produces:
  - `AnthropicReader(model_id, secrets, pricing) .answer(md,q)->str`, `.identity`
  - `OpenAIReader(model_id, secrets, pricing) .answer(md,q)->str`, `.identity`
  - `build_reader(name: str, cfg: dict) -> Extractor` — factory selecting backend; falls back to the local default when the named API reader's key is missing.

- [ ] **Step 1: Write the failing tests** (no network — construct + fallback + identity only)

```python
# tests/test_reader_instrument.py
import pytest
from tbdoc.instruments.reader import build_reader, AnthropicReader, OpenAIReader


READER_CFG = {
    "default_local": {"repo": "Qwen/Qwen2.5-3B-Instruct", "revision": "main"},
    "backends": {
        "haiku45": {"backend": "anthropic", "api_model_id": "claude-haiku-4-5-20251001",
                    "secrets": ["ANTHROPIC_API_KEY"]},
        "gpt5mini": {"backend": "openai", "api_model_id": "gpt-5-mini",
                     "secrets": ["OPENAI_API_KEY"]},
    },
}

def test_local_default_selected_and_is_small_model():
    r = build_reader("local", READER_CFG)
    assert "Qwen2.5-3B" in r.identity   # NOT the 7B

def test_api_reader_falls_back_to_local_when_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = build_reader("haiku45", READER_CFG)
    assert "Qwen2.5-3B" in r.identity   # graceful fallback, key-less clones still run

def test_api_reader_built_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    r = build_reader("haiku45", READER_CFG)
    assert isinstance(r, AnthropicReader)
    assert r.identity == "anthropic:claude-haiku-4-5-20251001"

def test_openai_reader_identity(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    r = build_reader("gpt5mini", READER_CFG)
    assert isinstance(r, OpenAIReader)
    assert r.identity == "openai:gpt-5-mini"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_reader_instrument.py -v`
Expected: FAIL (`ModuleNotFoundError: tbdoc.instruments.reader`).

- [ ] **Step 3: Implement `reader.py`**

```python
# src/tbdoc/instruments/reader.py
"""Pluggable Tier-B B.2 comprehension reader: markdown+question -> answer.

Satisfies the Extractor Protocol (.identity + .answer). Backends: local vLLM small model
(default Qwen2.5-3B — never the 7B, which stays the Tier C judge), Anthropic, OpenAI. API
readers are text-only and fall back to the local default when their key is absent, so
key-less clones still run. Deterministic where the backend allows (temperature=0)."""
from __future__ import annotations

from typing import Any

from tbdoc.core.ratelimit import RetryableError

_SYSTEM = (
    "You extract answers from a document's parsed text. Use ONLY the text provided — do not use "
    "outside knowledge and do not guess. If the answer is not present, reply exactly: not found. "
    "Reply with ONLY the answer value, as short as possible, no punctuation around it.")

_MAX_MD = 48000


def _user(md: str, q: str) -> str:
    return f"Document text:\n\n{(md or '')[:_MAX_MD]}\n\nQuestion: {q}\nAnswer:"


class AnthropicReader:
    def __init__(self, api_model_id: str, secrets: list[str] | None = None, pricing: dict | None = None):
        self.api_model_id = api_model_id
        self.identity = f"anthropic:{api_model_id}"
        self._pricing = pricing or {}
        self._client = None

    def _c(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def answer(self, markdown: str, question: str) -> str:
        import anthropic
        try:
            r = self._c().messages.create(
                model=self.api_model_id, max_tokens=64, temperature=0, system=_SYSTEM,
                messages=[{"role": "user", "content": _user(markdown, question)}])
        except (anthropic.RateLimitError, anthropic.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()


class OpenAIReader:
    def __init__(self, api_model_id: str, secrets: list[str] | None = None, pricing: dict | None = None):
        self.api_model_id = api_model_id
        self.identity = f"openai:{api_model_id}"
        self._pricing = pricing or {}
        self._client = None

    def _c(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def answer(self, markdown: str, question: str) -> str:
        import openai
        try:
            r = self._c().chat.completions.create(
                model=self.api_model_id, temperature=0, max_tokens=64,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": _user(markdown, question)}])
        except (openai.RateLimitError, openai.APITimeoutError) as e:
            raise RetryableError(str(e)) from e
        return (r.choices[0].message.content or "").strip()


def _build_local(cfg: dict) -> Any:
    from tbdoc.instruments.vllm_extractor import VLLMExtractor
    loc = (cfg or {}).get("default_local") or {}
    repo = loc.get("repo", "Qwen/Qwen2.5-3B-Instruct")
    return VLLMExtractor(repo=repo, revision=loc.get("revision"))


def build_reader(name: str, cfg: dict) -> Any:
    """Select a reader by name. 'local' -> the small default. An API backend name ->
    the API reader if its key is present, else a graceful fallback to the local default."""
    from tbdoc.core.secrets import missing_secrets
    if name in ("local", "default", None):
        return _build_local(cfg)
    b = ((cfg or {}).get("backends") or {}).get(name)
    if not b:
        return _build_local(cfg)
    if missing_secrets(b.get("secrets", [])):
        return _build_local(cfg)          # key-less fallback
    kind = b.get("backend")
    if kind == "anthropic":
        return AnthropicReader(b["api_model_id"], b.get("secrets"), b.get("pricing"))
    if kind == "openai":
        return OpenAIReader(b["api_model_id"], b.get("secrets"), b.get("pricing"))
    return _build_local(cfg)
```

- [ ] **Step 4: Add the `reader` config block** to `configs/models.yaml` under `instruments:` (values verified at wire-in — see Global Constraints):

```yaml
  reader:                       # Tier-B B.2 comprehension (pluggable; B.1 needs none)
    default_local:              # small model — NEVER the 7B (that's the Tier C judge)
      repo: Qwen/Qwen2.5-3B-Instruct
      revision: VERIFY_AT_WIRE_IN     # resolve + pin the HF revision hash at download
    backends:
      haiku45:
        backend: anthropic
        api_model_id: claude-haiku-4-5-20251001   # verify live at wire-in
        secrets: [ANTHROPIC_API_KEY]
        pricing: { per_mtok_in_usd: 1.0, per_mtok_out_usd: 5.0, as_of: "2026-07-08",
                   source: "https://platform.claude.com/docs/en/about-claude/pricing" }
      gpt5mini:
        backend: openai
        api_model_id: gpt-5-mini                   # verify live at wire-in
        secrets: [OPENAI_API_KEY]
        pricing: { per_mtok_in_usd: 0.25, per_mtok_out_usd: 2.0, as_of: "2026-07-08",
                   source: "https://developers.openai.com/api/docs/pricing" }
```

> Replace `VERIFY_AT_WIRE_IN` with the resolved Qwen2.5-3B-Instruct revision hash during download (do not leave the literal in a committed run).

- [ ] **Step 5: Run to verify pass + commit**

Run: `uv run pytest tests/test_reader_instrument.py -v`
Expected: PASS (4 passed).

```bash
git add src/tbdoc/instruments/reader.py configs/models.yaml tests/test_reader_instrument.py
git commit -m "feat(instruments): pluggable B.2 reader (local Qwen-3B default / Anthropic / OpenAI) w/ key-less fallback"
```

---

### Task 4: CLI `--reader` selection wired into the score phase

**Files:**
- Modify: `src/tbdoc/cli.py` (the `run` command: replace the hardcoded `VLLMExtractor()` extractor construction with reader selection)
- Test: `tests/test_cli_reader_selection.py`

**Interfaces:**
- Consumes: `build_reader` (Task 3); `reg.instruments["reader"]`.
- Produces: `gauntlet run ... --reader {local|haiku45|gpt5mini}` (default `local`). The selected reader is passed as `extractor=` to `run_matrix`/`run_score` (it satisfies the Extractor Protocol, so downstream is unchanged).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_reader_selection.py
from tbdoc.instruments.reader import build_reader

def test_default_reader_is_local_small(monkeypatch):
    cfg = {"default_local": {"repo": "Qwen/Qwen2.5-3B-Instruct", "revision": "main"}, "backends": {}}
    r = build_reader("local", cfg)
    assert "3B" in r.identity and "7B" not in r.identity
```
(The CLI option itself is exercised by the integration test in Task 7; this locks the default.)

- [ ] **Step 2: Run to verify it passes trivially, then edit the CLI.** In `src/tbdoc/cli.py`, add the option to the `run` command decorator block (next to `--no-llm-instruments`):

```python
@click.option("--reader", default="local", show_default=True,
              help="Tier-B B.2 comprehension reader: local | haiku45 | gpt5mini")
```

Add `reader` to the `run(...)` function signature, and replace the extractor-construction block (currently lines ~89-96) with:

```python
    # Tier-B B.2 reader — pluggable; may be a small LOCAL model (Qwen-3B) or an API reader.
    extractor = None
    if "score" in phases and not no_llm_instruments:
        needs = [b for b in bench_keys
                 if (reg.benchmarks.get(b, {}).get("scorer") or {}).get("instrument") == "extractor"]
        if needs:
            from tbdoc.instruments.reader import build_reader
            extractor = build_reader(reader, (reg.instruments or {}).get("reader") or {})
            click.echo(f"[instruments] B.2 reader {extractor.identity} for: {', '.join(needs)}")
```

**CRITICAL — also change the boundary-judge block (currently lines ~99-106).** It previously
reused `extractor` as the judge's shared vLLM engine. That is now wrong: `extractor` is the B.2
reader (a 3B, or an API reader with no `.repo`/`._llm`) and sharing it would raise a pin-mismatch
`RuntimeError`. The Tier C judge must get its OWN pinned 7B engine, independent of the B.2 reader:

```python
    judge = None
    judge_engine = None
    if not no_llm_instruments and any(
            reg.benchmarks.get(b, {}).get("tier") == "C" for b in bench_keys):
        from tbdoc.instruments.boundary_judge import BoundaryJudge
        from tbdoc.instruments.vllm_extractor import VLLMExtractor
        judge_engine = VLLMExtractor()   # pinned 7B — the Tier C judge's own engine
        judge = BoundaryJudge((reg.instruments or {}).get("boundary_judge") or {},
                              shared_extractor=judge_engine)
        click.echo(f"[instruments] boundary_judge {judge.identity()} (own pinned 7B engine)")
```

And in the `finally:` block, unload the judge's engine too (add alongside the existing unloads):

```python
    finally:
        if judge is not None:
            judge.unload()
        if judge_engine is not None:
            judge_engine.unload()
        if extractor is not None and hasattr(extractor, "unload"):
            extractor.unload()   # API readers have no unload(); guard it
```

VRAM note: a local-3B reader (~6 GB) + the 7B judge (~15 GB) co-reside fine on 32 GB; an API
reader uses no GPU. So no sequencing change is needed for Plan 1.

- [ ] **Step 3: Verify nothing else references the removed import**

Run: `cd /home/ashwinc/dev/projects/trial-by-doc && uv run gauntlet run --help | grep -A1 reader`
Expected: the `--reader` option appears with its help text.

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all prior tests + the new ones).

- [ ] **Step 5: Commit**

```bash
git add src/tbdoc/cli.py tests/test_cli_reader_selection.py
git commit -m "feat(cli): --reader selects the B.2 comprehension instrument (default local Qwen-3B)"
```

---

### Task 5: Scoreboard Tier-B view (b1 primary + b2 + coverage)

**Files:**
- Modify: `src/tbdoc/report/scoreboard.py` (add a `render_tier_b` function + `_collect_tier_b` helper; reuse `CheckpointStore`)
- Modify: `src/tbdoc/cli.py` (`scoreboard` command: add `--tier-b` flag, mirror of the existing `--perf`)
- Test: `tests/test_scoreboard_tier_b.py`

**Interfaces:**
- Consumes: `CheckpointStore.iter_records()` (records carry `metrics` with `b1`/`b2`/`extractive`).
- Produces: `render_tier_b(run_dir, models=None) -> str` — a markdown table with columns: model, B.1 (mean over extractive), coverage (n_extractive/n_total), B.2 (mean, when present), reader.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scoreboard_tier_b.py
from pathlib import Path
from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import render_tier_b


def test_tier_b_view_reports_b1_and_coverage(tmp_path: Path):
    store = CheckpointStore(tmp_path)
    store.record("m1", "realdoc_qa", "q1", metrics={"primary": 1.0, "b1": 1.0, "extractive": True,
                 "b2": 1.0, "reader": "anthropic:claude-haiku-4-5-20251001", "category": "finance"})
    store.record("m1", "realdoc_qa", "q2", metrics={"primary": None, "b1": None, "extractive": False,
                 "b2": 0.0, "reader": "anthropic:claude-haiku-4-5-20251001", "category": "finance"})
    out = render_tier_b(tmp_path)
    assert "B.1" in out and "coverage" in out.lower()
    assert "1/2" in out or "0.50" in out   # 1 of 2 items extractive
    assert "haiku" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_scoreboard_tier_b.py -v`
Expected: FAIL (`ImportError: cannot import name 'render_tier_b'`).

- [ ] **Step 3: Implement `render_tier_b` (append to scoreboard.py)**

```python
def _collect_tier_b(run_dir):
    store = CheckpointStore(run_dir)
    per = {}   # model -> {b1: [...], n_total, n_extractive, b2: [...], reader}
    latest = {}
    for r in store.iter_records():
        if r.get("bench") != "realdoc_qa":
            continue
        latest[(r["model"], str(r.get("sample_id")))] = r
    for (m, _sid), r in latest.items():
        d = per.setdefault(m, {"b1": [], "n_total": 0, "n_extractive": 0, "b2": [], "reader": None})
        mt = r.get("metrics") or {}
        d["n_total"] += 1
        if mt.get("extractive"):
            d["n_extractive"] += 1
            if isinstance(mt.get("b1"), (int, float)):
                d["b1"].append(mt["b1"])
        if isinstance(mt.get("b2"), (int, float)):
            d["b2"].append(mt["b2"])
        d["reader"] = d["reader"] or mt.get("reader")
    return per


def render_tier_b(run_dir, models=None):
    per = _collect_tier_b(run_dir)
    order = [m for m in (models or per) if m in per]
    if not order:
        return "_no Tier-B records_"
    out = ["| model | B.1 extract | coverage | B.2 comp | reader |", "|---|---|---|---|---|"]
    for m in order:
        d = per[m]
        b1 = f"{sum(d['b1'])/len(d['b1']):.3f}" if d["b1"] else "—"
        cov = f"{d['n_extractive']}/{d['n_total']}"
        b2 = f"{sum(d['b2'])/len(d['b2']):.3f}" if d["b2"] else "—"
        out.append(f"| {m} | {b1} | {cov} | {b2} | {d['reader'] or '—'} |")
    return "\n".join(out)
```

- [ ] **Step 4: Wire the `--tier-b` flag** in `cli.py`'s `scoreboard` command (mirror `--perf`): add `@click.option("--tier-b", is_flag=True, ...)`, param `tier_b`, and near the top of the function `if tier_b: click.echo(render_tier_b(_latest_run(run_id))); return` (import `render_tier_b`).

- [ ] **Step 5: Run tests + commit**

Run: `uv run pytest tests/test_scoreboard_tier_b.py -v && uv run gauntlet scoreboard --help | grep tier-b`
Expected: PASS; the `--tier-b` flag listed.

```bash
git add src/tbdoc/report/scoreboard.py src/tbdoc/cli.py tests/test_scoreboard_tier_b.py
git commit -m "feat(report): --tier-b scoreboard view (B.1 primary + coverage + B.2 + reader)"
```

---

### Task 6: README Tier-B explainer + roadmap deferrals

**Files:**
- Modify: `README.md` (add a "How Tier B works" subsection near the Benchmarks/Tier section)
- Modify: `findings/LEARNINGS-AND-ROADMAP.md` (two deferral lines)

- [ ] **Step 1: Add the README explainer.** Insert this block under the Tier B benchmark description:

```markdown
#### How Tier B works — extraction (B.1) vs comprehension (B.2)

Tier B is split so the signal you care about is isolated:

- **B.1 — extraction fidelity (primary, deterministic).** For each field question we check
  whether the *gold value* appears, unmangled, in the model's OCR markdown — with **no LLM in
  the loop**. This is the "does it capture the values without messing them up?" signal. It is
  scored only on the *extractive* subset (answers that are literally on the page); the
  `coverage` column shows how many items that is. Reproducible; needs no API key.
- **B.2 — comprehension (secondary).** A separate *reader* model answers the question from the
  markdown, scored deterministically (field-aware exact-match + ANLS). **The reader is a swappable
  instrument, never the model under test** — it defaults to a small local model (Qwen2.5-3B) and
  can be set to Claude Haiku 4.5 or GPT-5 mini. Because a capable reader can paper over OCR slips,
  **B.2 is confounded by the reader by design** — trust B.1 for extraction quality; read B.2 as a
  directional "does this feed a downstream QA step" signal. Each B.2 number is stamped with which
  reader produced it.

Run `gauntlet scoreboard --tier-b` for the B.1/coverage/B.2 breakdown.
```

- [ ] **Step 2: Add the roadmap deferrals** to `findings/LEARNINGS-AND-ROADMAP.md` under "Benchmarks":

```markdown
- **Tier B full-page fidelity (old "B"):** already delivered by Tier A (olmocr_bench edit-distance
  + omnidocbench TEDS against real gold markdown); not rebuilt on the RealDoc corpus (no gold
  transcriptions there).
- **Tier B structured KV extraction (`tierB_kie`, v2):** the most production-shaped lane — key→value
  field extraction scored by field F1. Needs a KIE dataset (CORD CC BY 4.0 + our existing NIST
  forms) and a structure-native scoring path (to avoid reintroducing an extractor LLM). Deferred
  from v1.
- **Multi-reader B.2 (Plan 2):** run Haiku + GPT-5 mini in one pass with reader-tagged columns, an
  auto reader-sensitivity table, and the comprehension-floor ladder (Qwen2.5 0.5/1.5/3B + Gemma-4-E4B).
```

- [ ] **Step 3: Commit**

```bash
git add README.md findings/LEARNINGS-AND-ROADMAP.md
git commit -m "docs: Tier B B.1/B.2 explainer in README; defer old-B, C (KIE), multi-reader to roadmap"
```

---

### Task 7: Integration — rescore on-disk predictions into a scratch run-id

**Files:**
- Test: `tests/test_tier_b_integration.py` (uses a tiny synthetic prediction cell; no GPU, no key)

**Interfaces:**
- Consumes: `run_score` (existing), `RealDocQA`, `FunctionExtractor`, `CheckpointStore`, `PredictionStore`.

- [ ] **Step 1: Write the integration test** (drives the score phase end-to-end with a fake reader; asserts B.1 primary + coverage land in records)

```python
# tests/test_tier_b_integration.py
from pathlib import Path
from tbdoc.core.bench_adapter import Sample
from tbdoc.instruments.extractor import FunctionExtractor


def test_score_phase_records_b1_primary(tmp_path: Path):
    from tbdoc.runner.infer import PredictionStore
    from tbdoc.core.checkpoint import CheckpointStore
    from tbdoc.runner.score import run_score
    from tbdoc.benches.official.realdoc_qa import RealDocQA

    preds = PredictionStore(tmp_path)
    preds.append("m1", "realdoc_qa", "q1", kind="structured_doc",
                 prediction={"markdown": "Amount: 8500", "layout_boxes": [], "telemetry": {}})
    samples = [Sample(id="q1", gold=["amount=8500"], question="What is the amount paid?",
                      category="finance")]
    store = CheckpointStore(tmp_path)
    reader = FunctionExtractor(lambda md, q: "8500", identity="fake-reader")
    run_score(models=["m1"], benches=["realdoc_qa"],
              bench_factory=lambda k: RealDocQA(k), preds=preds, store=store,
              bench_samples={"realdoc_qa": samples}, extractor=reader)
    rec = next(r for r in store.iter_records() if r["model"] == "m1")
    assert rec["metrics"]["b1"] == 1.0
    assert rec["metrics"]["primary"] == 1.0
    assert rec["metrics"]["b2"] == 1.0
```

> Verify the `PredictionStore.append(...)` signature against `src/tbdoc/runner/infer.py` before running; adapt kwarg names if they differ (the store is the source of truth).

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/test_tier_b_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Manual rescore against real on-disk predictions (scratch run-id — does NOT touch v1-baseline).** Once the v1 inference has produced `realdoc_qa` predictions for the finished models, dry-run the new scoring on a COPY:

```bash
cp -r results/runs/v1-baseline results/runs/tierb-dev
uv run gauntlet run -m olmocr2,qwen25vl,got2,dots_ocr -b realdoc_qa \
    --run-id tierb-dev --phase score --reader local
uv run gauntlet scoreboard --run-id tierb-dev --tier-b
```
Expected: a B.1/coverage/B.2 table; sanity — olmocr2's B.1 ≫ got2's B.1 (got2 mangles structure). Report coverage per the spec's build-time validation.

- [ ] **Step 4: Full suite green**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_tier_b_integration.py
git commit -m "test(tier-b): end-to-end score-phase integration (B.1 primary + reader B.2)"
```

---

## Post-plan validation (owner-facing, not a code task)

- **Extractive-subset audit** (spec §2 build-time validation): report the extractive fraction per
  domain from the `tierb-dev` rescore; spot-check a sample of *excluded* items to confirm they are
  genuinely derived (not mis-filtered). If coverage is surprisingly low, revisit `is_extractive_gold`.
- **API reader smoke** (when a key lands): `gauntlet run -m got2 -b realdoc_qa --run-id tierb-dev
  --phase score --reader haiku45` on a handful of items (cents); confirm provenance stamping
  (reader id, api version) on the records.
- **Wire-in verifications** (Global Constraints): resolve + pin the Qwen2.5-3B revision hash;
  confirm the exact Haiku/GPT-5-mini api ids + current pricing; confirm `gpt-5-mini` chat params.
