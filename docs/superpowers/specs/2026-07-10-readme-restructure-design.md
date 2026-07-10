# README restructure — design

_2026-07-10. Owner-approved in conversation; written for the record per the
brainstorming skill._

## Problem

The README mixed three kinds of content (results, concepts, how-to-run) in one long
scroll, in an order that shows jargon (Tier A/B/C, B.1/B.2, ANLS, TEDS, PQ/STP, CDM,
`judge_composed`/`native`, "frozen instrument") before it's ever defined — worst case,
the `## Scores` section (with a full B.1/B.2 breakdown table) appears *before*
`## Benchmarks` explains what Tier A/B/C or B.1/B2 even mean. There is no glossary.
The owner also suspected some content had gone stale.

## Audience decision

Primary reader: a new visitor deciding whether to trust/use a model. Optimize for
concepts before numbers, setup near the end.

## New section order

1. Title + intro (trimmed, jargon-free)
2. Contents (TOC), anchors updated to match new order
3. **Benchmarks** (moved up, before Scores)
   - Summary table: Tier A/B/C × benchmark × provenance × what/why (existing table,
     relocated verbatim)
   - New subsection **"Tier B in detail: B.1 vs B.2"** — existing explanation, reworded
     so the B.2 local-default reader (Phi-4-mini) reads as a deliberate
     reproducibility/no-API-key choice, backed by `findings/partb-reader-ladder.md`'s
     finding that reader choice moves B.2 by ~2.8x — not "the best available reader."
     Notes that each scoreboard row's `reader` column stamps which reader produced it,
     and that `v1-baseline`'s B.2 column predates the Phi-4-mini switch (scored with
     Qwen2.5-1.5B-Instruct).
   - Tier C floor-rows paragraph (existing, unchanged)
4. **Scores** — short pointer line ("tier definitions are above; jargon is in the
   Glossary"), then the untouched `<!-- SCOREBOARD:BEGIN/END -->` auto-injected block
5. **Dashboard** (existing, unchanged)
6. **Scanned & faxed robustness** (existing, unchanged)
7. **Example documents** (existing, unchanged)
8. **Models** — roster + self-host cost tables (existing, unchanged)
9. **How the harness actually works** — infer/score mechanics (existing, unchanged)
10. **Setup**
11. **Hardware**
12. **Gaps** — content audit fixes (see below)
13. **Glossary** (new, at the end — reference appendix, not a linear read)
14. **Attributions & credits**

## Hard constraint (verified in code)

`src/tbdoc/report/scoreboard.py::inject_readme` regex-replaces everything between
`<!-- SCOREBOARD:BEGIN -->` and `<!-- SCOREBOARD:END -->` with a fixed shape every time
`gauntlet scoreboard --readme-inject` runs: main table → `### Tier-B — extraction (B.1)
vs comprehension (B.2)` heading+table → `### Performance...` heading+table → `### Cost...`
heading+table. Nothing inside that span may depend on hand-written prose — it will be
silently overwritten on next inject. All conceptual explanation of B.1/B.2 lives in
`## Benchmarks`, outside the markers.

## Content fixes folded in (not just reorg)

- **Gaps**: add that Florence-2 and Phi-4-multimodal adapters are built but
  unregistered (blocked on pinned transformers 5.11 remote-code incompatibilities,
  distinct per model) — currently missing from Gaps entirely.
- **Gaps**: add that `granite_docling` OOMs on Tier C (`merged_forms`), hence the `—`
  in that scoreboard column — currently unexplained.
- **Benchmarks/Tier B**: reword B.2 reader framing (see above) — the one specific
  inconsistency the owner flagged.

## Glossary content (new section)

Grouped, not alphabetical soup:
- **Metrics**: ANLS, TEDS, edit distance, PQ, STP, CDM
- **Harness concepts**: frozen instrument, official vs custom provenance, extractive,
  coverage, `judge_composed` vs `native`, boundary judge, `gold_match` (verified against
  `src/tbdoc/ui/app.py` — Diagnose-view highlight, gated on extractive items)
- **Repro concepts**: run_id, manifest.json, revision pin
- **Licensing shorthand**: ODC-BY

## Explicitly out of scope

Re-scoring `v1-baseline`'s B.2 column with API readers (Anthropic/OpenAI, not
Phi-4-mini) is a separate, owner-approved follow-up — a paid API run requiring its own
`gauntlet estimate-cost` + sign-off per the CLAUDE.md cost-guard rule. Tracked outside
this doc (agent memory: `project_b2_rescore_followup`). This README pass only fixes the
*wording*, not the underlying data.

## Verification plan

Before pushing: run `inject_readme` against the rewritten README (via a throwaway copy)
to confirm the marker-replace regex still finds exactly one `BEGIN...END` span and
produces byte-identical injected content to what's live now — i.e., the restructure
doesn't corrupt the automation.
