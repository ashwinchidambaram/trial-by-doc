# Tier B Split — SDD progress

Branch: tier-b-split (worktree ../trial-by-doc-tierb)
Plan: docs/superpowers/plans/2026-07-08-tier-b-split.md

Task 1: complete (commits 668521e..75f7793, review clean after 1 fix loop) — B.1 scorer + extractive filter, 8 tests
  Minor (defer to final review): scorers.py import-re placement (E402-style); empty-cv leniency could use a comment
Task 2: complete (commits 75f7793..d9f3747, review clean after 1 constraint-revert loop) — realdoc evaluate emits b1(primary)/b2/extractive; frozen field_aware_exact_match confirmed byte-identical (net-zero)
  Minor (defer to final review): realdoc_qa.py:33 sample:Any loosened from Sample; :53 empty-string answer -> None conflation
  Resolved WARN: scoreboard _collect excludes primary=None (isinstance guard); no downstream relied on old inline error key
Task 3: complete (commit d9f3747..d61fabe, review clean, no fixes) — pluggable reader (local 3B / Anthropic / OpenAI) + key-less fallback; lazy imports verified; VERIFY_AT_WIRE_IN kept
  Minor (defer): reader __init__ secrets param unused; test unused pytest import (both plan-verbatim)
Task 4: complete (commit d61fabe..903e34f, review clean, no fixes) — --reader CLI option; judge/reader engine independence fix verified line-by-line (a-d hold)
  Minor/gap (defer): judge-engine-independence fix is GPU-dependent, no automated test (verified by inspection); test unused monkeypatch fixture
Task 5: complete (commit 903e34f..67ab891, review clean, no fixes) — --tier-b scoreboard view; coverage/B.1/B.2 None-exclusion correct; last-record-wins dedup reuses proven idiom
  Minor (defer): test fixture could assert exact mean + a b2=None record to make aggregation load-bearing
  Resolved WARN: realcoc_qa-only filter correct (only Tier B bench emitting b1/b2 today)
Task 6: complete (commit 67ab891..4f7f733, review clean, no fixes) — README Tier-B explainer + 3 roadmap deferrals; claims verified accurate to implementation
Task 7: complete (commit 4f7f733..6250b37, review clean, no fixes) — end-to-end score-phase integration test; real (unmocked) PredictionStore->run_score->scorers->CheckpointStore chain; 36/36 suite
  Minor (harmless): report attributed reader-answer adaptation to brief; actually came from controller dispatch

ALL 7 TASKS COMPLETE. Full suite: 36 passed. Next: final whole-branch review.

FINAL WHOLE-BRANCH REVIEW (opus): Ready to merge = YES. No Critical/Important blockers.
  Verified: frozen field_aware_exact_match/_norm/anls byte-unchanged; reader/judge engine independence (3B reader, 7B judge); primary=None excluded from all means; no heavy top-level imports; docs accurate.
  1 conscious sign-off: Tier B + Tier C in one score run now co-loads 3B+7B (intended; ~unmeasured VRAM — check on first combined run).
  4 Minors: all defer-safe (import placement; sample:Any + empty-answer display; unused secrets param/pytest import; thin fixtures + no GPU test for judge-independence).
MERGE GATE (not code): hold until v1 inference completes (resume must not pick up changed evaluate code) + wire-in (Qwen2.5-3B revision hash, exact API ids/pricing).

WIRE-IN (commit after 6250b37): default reader 3B->1.5B (3B is qwen-research/non-commercial; 1.5B Apache-2.0 SHA 989aa79); OpenAI id gpt-5-mini->gpt-5.4-mini ($0.75/$4.50). Haiku id unchanged. 36 pass. Branch now fully runnable (no VERIFY_AT_WIRE_IN left in reader path).
