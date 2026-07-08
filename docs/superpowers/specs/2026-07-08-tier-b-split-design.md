# Tier B split — B.1 extraction fidelity + B.2 pluggable comprehension

**Date:** 2026-07-08
**Status:** approved (design), pending implementation plan
**Scope:** scoring-phase + reporting change to Tier B. No inference change. Live v1 run untouched.

## 1. Motivation

Today's Tier B (RealDoc-QA) conflates two capabilities into one number:

```
page image → [OCR model] → markdown → [frozen Qwen-7B extractor] → answer → field_aware_exact_match + ANLS
             \___ extraction quality ___/   \___ comprehension mixed in ___/
```

The owner's production priority is **extraction quality** — "does the OCR capture the field
values without mangling them?" Comprehension is **secondary**, because in production a
separate, swappable model does the reasoning over the extracted text. The single score can't
tell you which half failed: a perfect transcription scores zero if the extractor misreads, and
a strong extractor can paper over OCR errors.

**Goal:** split Tier B so extraction fidelity (B.1) is an isolated, deterministic, primary
signal, and comprehension (B.2) is an explicitly secondary signal produced by a *pluggable*
reader model that is not the model under test.

## 2. B.1 — Extraction fidelity (new, primary, deterministic)

**Question answered:** did the OCR faithfully reproduce the specific gold field values on the page?

**Metric — field-value presence recall.** RealDoc gold is `key=value`, often multi-field
(`k1=v1;k2=v2`). For a QA item, B.1 checks how many of the gold *values* appear in the OCR
markdown, using the SAME tolerant matcher already used by `field_aware_exact_match`
(`scorers._values_match`: canonical-string equality with boolean aliasing + numeric closeness).

- For each gold value `v`: search the OCR markdown for a matching surface token.
  - Numeric/currency/percent `v`: extract numeric tokens from the markdown and match with
    `_as_number` + `math.isclose` (so `8,500` / `8500` / `8500.00` all match).
  - String/boolean `v`: canonical substring containment, else best-window ANLS ≥ 0.8
    (localized — a value garbled beyond recognition counts as absent).
- Item score = (# gold values found) / (# gold values). Dataset B.1 = mean over scored items.

**No LLM anywhere in the B.1 path.** Fully deterministic, reproducible, no API key, no GPU.

**Extractive subset (the honest scope guard).** Some RealDoc answers are *derived* (e.g. "how
many line items?") and are not surface tokens on the page; scoring OCR against them would
penalize faithful transcription. B.1 therefore scores only the **extractive subset**:

- A gold value is *extractive* if it is a surface token type — number, currency, percent, date,
  boolean, or short string (≤ 64 chars) — AND the item's question does not match derived-answer
  patterns (`how many`, `total number of`, `count of`, `how much …in total` where no literal
  total is printed).
- Non-extractive items are **excluded from B.1** (they belong to B.2), never counted as failures.
- The scorer emits `coverage = n_scored / n_total`; the scoreboard and README show it, so the
  subset is transparent, not hidden.

**Build-time validation (before publishing B.1 numbers):**
1. Measure the extractive-subset size per domain; report it.
2. Spot-check a sample of *excluded* items to confirm they are genuinely derived (not mis-filtered).
3. Sanity floor: a deliberately garbled transcription must score ≈ 0; a copy of the gold-bearing
   text must score ≈ 1.

**Data flow:** the RealDoc-QA bench's `evaluate()` emits BOTH sub-scores per item — `b1`
(field-value presence, computed here with no LLM) and `b2` (the existing extractor/reader answer
score) — reading `prediction.markdown` and the item's gold from **the predictions already on
disk**. One bench, two sub-metrics; no new bench, no re-inference. → Produces B.1 for the finished
models (olmocr2, qwen25vl, got2, dots_ocr) immediately, with no GPU. When no reader key is set,
`b2` is null and `b1` still computes (extraction is never blocked on comprehension).

## 3. B.2 — Comprehension (existing path, secondary, pluggable reader)

**Question answered:** given the OCR markdown, can a capable reader answer the field question?

**The reader becomes a configurable instrument** with three interchangeable backends behind one
interface (`answer(markdown, question) -> str`), selected in config:

| Backend | Model | Key | Role |
|---|---|---|---|
| API (Anthropic) | Claude Haiku 4.5 | `ANTHROPIC_API_KEY` | recommended default |
| API (OpenAI) | GPT-5 mini | `OPENAI_API_KEY` | second reader (owner will provide key) |
| Local (vLLM) | **any small instruction-tuned model** (default: Qwen2.5-3B-Instruct) | none | fallback when no key |

**B.2 uses only small local models — never the 7B** (owner decision 2026-07-08). The 7B is the
"known-capable" reference; the interesting question is where comprehension breaks *below* it, so
B.2's readers stay in the small regime. The default key-less fallback is therefore
**Qwen2.5-3B-Instruct** (same stack as our existing Qwen2.5-7B ⇒ known to serve on vLLM 0.22.1 /
sm_120; safer default than Gemma 4, whose serving support is unverified). The pinned Qwen2.5-7B
`@a09a35458c70` **remains in the harness for the Tier C boundary judge — untouched there**; it is
simply no longer used for B.2.

The local reader is **not fixed to one model** — the interface is `answer(markdown, question) -> str`,
so any vLLM-servable instruction model qualifies (config takes model id + revision). Comprehension
is text-only, so multimodal readers (e.g. Gemma 4) are served via their text path.

*Note:* with B.2 on a 3B and Tier C on the 7B, a key-less full run loads two local instruments in
separate scoring passes (not simultaneously — the two-phase design sequences them). Accepted cost
of honoring "B.2 = small models only." If the study finds 3B sits below the comprehension floor,
that is reported as a caveat; **B.1 is deterministic and unaffected either way.**

- Exact API model IDs and pricing are **verified live at wire-in** (house rule — not from memory):
  Haiku `claude-haiku-4-5-*`, GPT-5-mini id confirmed against the OpenAI models list. Local reader
  model ids/revisions/licenses and **vLLM 0.22.1 + sm_120 support** are likewise verified at
  wire-in (Gemma 4 is new — do not assume it serves on the pinned stack until confirmed).
- Each B.2 result row is stamped with `reader_identity`, `api_model_version`, and `called_on`
  date (APIs roll → non-reproducibility is stamped honestly, not hidden).
- Cost is negligible (text-only: ~2k in + ~60 out tokens/call; ~$0.50–$1.80 per full 8-model run).
  The existing `estimate-cost` + `budget.max_usd_per_model` guard applies before any spend.
- New OpenAI text-reader instrument gets a `validate-adapter` smoke call (cents) before real use.

**Reader-sensitivity check (a feature of having multiple readers).** The v1 findings run B.2 under
BOTH Haiku 4.5 and GPT-5 mini. If the OCR-model ranking is stable across readers, B.2 is
reader-agnostic (trustworthy). If it flips, B.2 is reader-sensitive → flagged as a caveat. This
diagnostic falls out for free and is reported in the findings.

**Comprehension-floor study (optional, opt-in — finds the minimum viable reader).** Because the
local reader is now a configurable list, we can measure *at what point a reader is too weak to be
a fair instrument* — i.e. where a low B.2 score reflects the reader's failure, not the OCR's. Clean
two-axis design (vary one thing at a time):

- **Size axis (family held constant):** Qwen2.5-Instruct `0.5B → 1.5B → 3B` (**no 7B** — owner
  decision; the floor is expected below 7B). Isolates the parameter count at which comprehension
  breaks down. Same family ⇒ a score drop is attributable to size, not architecture.
- **Family axis (size held ≈ small):** Gemma-4-E4B-it and/or a Llama-3.x small (~1–4B) vs Qwen at
  a comparable small size. Isolates whether family matters, staying in the small regime.

Mechanics: each ladder rung is one extra B.2 scoring pass over the **predictions already on disk**
(no re-inference) — load reader → answer 100 questions × N OCR models → score. Sequential local
loads reuse the existing `LocalModelAdapter` GPU-teardown path. Output: a B.2-vs-reader curve in
the findings, and a recommended *minimum local reader* (the smallest rung whose B.2 tracks the
strong API readers). This is a **bounded study, not core v1 B.2** — core ships with the three
readers above; the ladder runs when the GPU is free and its scope (which rungs) is the owner's call.

## 4. README — "How Tier B works" explainer (owner-required)

A dedicated subsection so no reader is caught off guard:
- The split diagram (extraction vs comprehension).
- Plain-language "what B.1 / B.2 mean and do NOT mean."
- The load-bearing caveat up front: **B.1 is the extraction signal to trust; B.2 is
  reader-confounded by design** — which is why B.2 is secondary, shown under two readers, and
  B.1 leads. The reader is a swappable instrument, never the model under test.

## 5. Deferred to roadmap (LEARNINGS-AND-ROADMAP.md, one line each)

- **Old-B — full-page transcription fidelity:** already delivered by Tier A (olmocr_bench
  edit-distance + omnidocbench TEDS against real gold markdown). Not rebuilt.
- **C — structured KV extraction:** the most production-shaped lane, but needs a KIE dataset
  (CORD CC BY 4.0 + our existing NIST forms) and a structure-native-only scoring path to avoid
  reintroducing an extractor. A proper v2 `tierB_kie` lane, not a v1 blocker.

## 6. Scope boundaries

- **Untouched:** the live v1 run (scoring-phase change only), Tier A, Tier C, `_norm`/`anls`
  (the existing DocVQA metric stays byte-identical), `field_aware_exact_match`.
- **Changed:** RealDoc-QA bench gains a B.1 evaluate path; the extractor instrument generalizes
  into a pluggable reader (Anthropic / OpenAI / local); configs gain reader selection; scoreboard
  + README gain B.1/B.2 columns and the explainer.
- **Reproducibility:** B.1 is fully deterministic. B.2 rows are provenance-stamped with reader
  identity + API version + date; the local small-model backend (default Qwen2.5-3B, pinned
  revision) remains the reproducible, key-less default path. Tier C's pinned Qwen2.5-7B judge is
  unchanged.

## 7. Testing / validation plan

- Unit: B.1 field-presence scorer against hand-built fixtures (value present / mangled / numeric
  variants / boolean aliases / derived-answer exclusion). Garbled→0, gold-copy→1 floors.
- Unit: reader-instrument interface — each backend selectable; local fallback engages with no key;
  provenance stamping present.
- Integration: rescore the on-disk v1 predictions → B.1 numbers for the 4 finished models;
  coverage reported per domain.
- `validate-adapter` green for the OpenAI text reader (paid smoke, cents) before any run.
- Cross-check: B.1 on a faithful transcription vs a known-bad model matches intuition (olmocr2 ≫ got2).

## 8. Deliverable framing

- Primary: B.1 extraction-fidelity scoreboard column (with coverage), the signal the owner cares about.
- Secondary: B.2 comprehension under two readers + the reader-sensitivity note.
- Docs: README Tier-B explainer; roadmap lines for deferred B and C.
