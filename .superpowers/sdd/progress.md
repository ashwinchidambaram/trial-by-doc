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

## v1-baseline finalization (post-merge, 2026-07-08 continued)
- Tier A (olmocr_bench, omnidocbench): 8/8 models scored. omnidocbench 96/100 valid (4 uniform official-scorer exclusions, cdm/no-matched-element — not a bug).
- Tier C (merged_forms): FIXED — finalize used --no-llm-instruments which disabled boundary_judge → all-error rows. Re-scored 7 models WITH judge (Qwen2.5-7B pin), 15/15 valid each. granite N/A (skip records written 010-014). lightonocr 0.142 leads.
- Tier B (realdoc_qa) B.1/B.2: all-8 rescored with 1.5B reader. B.1 (primary) olmocr2 0.689 leads; B.2 ANLS qwen25vl 0.555 leads. scored=800 errors=0.
- tier-b-split merged to main (39 tests pass). granite skip records written.
- NEXT: Gemma-4 (E4B-it, Gemma4ForConditionalGeneration, vision, 4.5B eff — license needs precise verify) adapter #9 → throughput+Azure cost → README → owner verification.

## Batched throughput + Azure Foundry cost (task #11, done)
- Batched throughput measured (vLLM continuous batching, N=24, one process/model): deepseek 4947, dots 4753, paddleocr 3977, gemma4 3392, olmocr2 3074, lightonocr 2899, qwen25vl 2660 pages/hr. ~7-10x over single-stream. got2/granite (transformers backend) = single-stream only.
- Azure Foundry Managed Compute cost column added: SKU by param footprint (T4-16GB $0.53/hr <=3B; A100-80GB $3.67/hr 7-8B); $/1k pages single-stream + batched. CAVEAT documented: throughput is RTX 5090's, so figures are same-hardware relative floors (Azure GPU slower -> real cost higher).
- NOTE: batched script must run ONE model per process — in-process vLLM engine teardown leaks VRAM (RuntimeError on 2nd model).

## Roster expansion + reader upgrade + harness/UI (2026-07-09) — AUTONOMOUS
Plan: /home/ashwinc/.claude/plans/so-if-we-wanted-cozy-sloth.md (owner-approved). Reference: findings/candidate-models.md (425243f).
Mode: autonomous, subagent-driven, continuous. Heartbeat cron armed (~30min) for stall detection. Status pushed to owner at gates.
Sequencing: C1 (verify-env, early) → A1 Tesseract(all 4 tiers) → A2 RapidOCR/docTR/EasyOCR(CPU+GPU) → A3 SLM vision → A4 full run → B reader → C2 auto-inject → C3 UI.
Locked decisions: B.2 reader→Phi-4-mini(MIT); API=readers only via OpenRouter real-time (secret OPEN_ROUTER_API_KEY, no batch); WS2 vision=Florence-2/Kosmos-2.5/Phi-4-mm (SmolVLM/SmolDocling/TrOCR dropped).
Key facts: CPU engines subclass ModelAdapter directly (no torch, baselines.py template); 7B reader collides w/ frozen judge (VRAM+identity) → Phi-4-mini avoids it; NO system prompts today (all user-turn); "score once, two cost rows" is net-new.
Budget: ~$5-10 OpenRouter readers pre-authorized. STOP-and-push only for: reality≠plan, unrecoverable failure, spend>budget, destructive action.

### === RESUME POINT (read FIRST after any compaction) ===
Branch: expansion/roster-reader-harness (6 commits: 5c14faf C1, 55b0e05 A1, 64b7f17 estimate-fix, 7c667a0/c4af560/7c000dc A2). NOT pushed. main untouched. Working via `uv run gauntlet` from repo root (cwd resets each bash — always cd first).
DONE: C1 verify-env, A1 Tesseract (all 4 tiers smoke), A2 four CPU engines (tesseract/rapidocr/doctr/easyocr) built+smoked+perf'd+findings.
A3 SUBAGENT DONE (aeac6e2c116a82107, 55min). 3 adapter files written (UNCOMMITTED). FLORENCE-2 BLOCKED on transformers v5 (its pre-v5 remote code hits `EncoderDecoderCache not subscriptable` in the generation loop) → adapter kept UNREGISTERED for revival, NO models.yaml entry (documented in file docstring + a yaml comment). kosmos25 + phi4mm registered w/ live-verified revisions (kosmos-2.5 @ec3c805, phi4mm @93f923e, both MIT). Subagent never ran its own smoke (stopped waiting on a download monitor). deps added: peft/backoff/timm (pyproject+uv.lock, synced OK). CONTROLLER now running validate-adapter on kosmos25+phi4mm myself (bg b51ls87xz). *** REALITY-VS-PLAN: Florence-2 dropped from WS2 → flag owner in Part-A gate digest. ***
NEXT ACTIONS (ordered):
  1. When A3 reports: verify florence2/kosmos25/phi4mm via validate-adapter + a clean smoke-a3 (olmocr_bench, 5 samples); confirm 0 errors; commit if not already. Watch for the same subagent footguns (orphaned bg run; check git for its commits).
  2. APPLY PENDING FIX: set easyocr `device: gpu` in configs/models.yaml (A2 subagent wrongly reverted it to cpu; cpu=84s/page impractical). Commit. ONLY after A3 done editing models.yaml.
  3. A4 full scored run: run infer for the whole expanded roster; SCORE Tier B and Tier C in SEPARATE invocations (reader 1.5B + judge 7B co-load OOMs — 2 vLLM engines @0.9 util). Use stratified sample cap like v1 (n~100), not all 1651. Write findings + refreshed scoreboard. → Part-A GATE: push digest to owner.
  4. Part B (reader upgrade): Phi-4-mini default via TRANSFORMERS backend (avoids vLLM co-load OOM) + OpenRouter readers (secret OPEN_ROUTER_API_KEY, real-time, models openai/gpt-5.4-mini + anthropic/claude-haiku-4.5). Code in src/tbdoc/instruments/reader.py. B.1 must stay unchanged.
  5. C2 (scoreboard --readme-inject perf/cost tables), C3 (dashboard UI). Then disarm crons + final summary.
SCOPE ADDITION REQUESTED (owner, 2026-07-09): evaluate ALL models on SCANNED/FAXED document robustness for OCR+EXTRACTION (not just Tier-C segmentation). Production need: clean uploads (like Tier B) vs faxed/scanned copies (degraded look like Tier C). Current gap: scanned OCR only partially in olmocr_bench old_scans (28 samples, buried); NIST SD2 scans used only for segmentation; Tier B extraction is clean-only.
  *** OWNER DECIDED 2026-07-09: BOTH/STAGED · LIGHT+HEAVY severities · TIER-B EXTRACTION ONLY. → becomes PART D (own spec). ***
  Design: new bench `realdoc_qa_scanned` reusing realdoc_qa qa_bank.json + gold, but degrade the rendered page image (light + heavy, FIXED SEED) before OCR. Per model, per severity: clean B.1 → light B.1 → heavy B.1 = robustness curve. Reader-INDEPENDENT (B.1 primary), so every roster model gets a row on B.1 alone; B.2 reader ladder is a stricter bonus. Validate synthetic ranking against REAL scans (olmocr old_scans breakdown [free] + optionally NIST SD2 if field GT exists).
  CONTENT-CORRECTNESS CONFIRMED (owner's critical Q): Tier-B primary = field_value_presence (scorers.py:206) scores fraction of gold field VALUES surviving in OCR'd md — content, not field-location. Type-aware: numeric tolerant-token match, boolean/checkbox canonicalization, string canonical-substring OR sliding-window ANLS>=0.8 (fuzzy by design). Paired design → gold identical clean vs degraded → drop attributable purely to scan. If STRICT exact-match wanted, field_aware_exact_match (scorers.py:118, drives B.2) is available as an added rung.
  SEQUENCING: Part D after Part A roster exists (so every contender gets a scan row). Does NOT block roster. Write short Part-D spec before building.
*** CAP-SEMANTICS FINDING (for A4) ***: `--profile smoke` benchmarks dict = {olmocr_bench: 5} ONLY. bench cap is per-bench: cli.py sets max_samples=bench_caps dict, runner does `cap=max_samples.get(bench)` → a bench NOT in the dict is UNCAPPED (runs full). So `--profile smoke -b olmocr_bench,realdoc_qa` ran realdoc_qa FULL (~1356). For A4: use `--profile full` (its benchmarks dict caps ALL 4: olmocr 100/omnidoc 100/realdoc 100/merged_forms 15) with explicit `-m <new models>` — caps apply correctly since they come from the profile bench dict. OR pass scalar `--max-samples N` to cap every bench uniformly. NEVER add a bench via -b to a profile whose bench dict lacks it (uncapped).
CRONS: 8e04eb47 (stall watch :13,:43) + 67be2f84 (hourly health :23). Disarm both at completion.
RULE: strictly SEQUENTIAL subagents; confirm prior fully dead before next; don't edit models.yaml while a subagent is live.

### Progress
- [x] C1 verify-env — COMPLETE (commit 5c14faf; 27 PASS/1 WARN[avx512]/0 FAIL on this box; tests 30/30, suite 69/69). NOTE: repo pins via uv.lock, NOT requirements.lock (CLAUDE.md stale — flag owner). Datasets: 3/4 revisions unverifiable (no local HF metadata) — reported honestly.
- [x] A1 Tesseract + Spec A doc — COMPLETE (commits 55b0e05 adapter, 64b7f17 estimate-fix). Full 4-tier smoke VALID: olmocr 0.280, omnidoc 0.738, realdoc B.1 0.750/B.2 0.600, merged_forms PQ 0.329 (metrics.primary nested — not top-level). 0 real errors. Spec A written (docs/superpowers/specs/2026-07-09-roster-expansion-design.md). Tesseract adapter committed 55b0e05. tesseract 5.5.2 via micromamba env (no sudo). validate-adapter 9/9.
      STALL CAUGHT+FIXED: 1st subagent left smoke run orphaned; Tesseract fed full-res 145MP pages → multi-min hang. Fix: downscale <=2600px + opt-in box 2nd-pass. Lesson for A2/A3: CPU/vision adapters MUST cap image size; never let a subagent leave a run orphaned — controller owns background runs.
      Smoke results (run-id smoke-tess): olmocr_bench 0.280, omnidocbench 0.738, realdoc_qa B.1 0.750 (cov 4/5) B.2 0.600 (1.5B reader), 0 error-kind preds all benches. merged_forms scoring separately (bg blgq0kdel).
      Watchers: 30-min stall cron 8e04eb47 + hourly health cron 67be2f84 (:23).
      Also fixed (commit 64b7f17): budget _estimate walked ENTIRE dataset (1651 omnidoc pages) even for local-only runs → looked like a hang. Now short-circuits $0 for local-only + caps count.
      *** KEY FINDING — reader+judge VRAM co-load OOM ***
      Running Tier B (loads 1.5B reader) + Tier C (loads 7B judge) in ONE invocation OOMs: two vLLM engines each want gpu_memory_utilization=0.9 → 2nd fails "Free memory 1.24/31.36 GiB < desired 28.22". v1 never hit this (scored B and C in separate passes). This is the exact collision the plan flagged.
      → OPERATIONAL RULE for A4 full run: score Tier B and Tier C in SEPARATE score invocations (infer can be combined). Never co-invoke a Tier-B and Tier-C bench in one score pass while the reader is vLLM.
      → REINFORCES Part B: make Phi-4-mini reader use the TRANSFORMERS backend (not vLLM) so it doesn't grab a 0.9 vLLM pool → then B+C can co-run. Design accordingly.
- [~] A2 RapidOCR/docTR/EasyOCR — adapters COMMITTED (7c667a0) + perf script (c4af560). Smoke olmocr_bench (0 err): rapidocr 0.240, doctr 0.323, easyocr 0.267.
      easyocr_engine.py (renamed to avoid pkg shadow). All: resize<=2600, float coords (JSON-safe). rapidocr CPU-only (no Blackwell onnxruntime wheel). easyocr device→GPU for accuracy (CPU=12min/page, impractical). doctr cpu default.
      PERF (single-stream, 10 pg @dpi150, RTX5090): tesseract cpu 3006 pg/hr (1.20s); rapidocr cpu 1214 (2.97s); doctr cpu 983 (3.66s) / gpu 24328 (0.148s, 25x); easyocr gpu 2300 (1.57s) / cpu 43 (84.4s, 54x, impractical). Findings: findings/ws1-cpu-engines.md.
- [x] A2 COMPLETE — commits 7c667a0 (adapters), c4af560 (perf script), findings note. All 4 WS1 engines built+validated+smoked+perf'd.
  *** PENDING FIX (do AFTER A3 finishes editing models.yaml) ***: A2 subagent (ran 57min concurrently, resuming) REVERTED my easyocr device:gpu → cpu; that cpu version got committed at 7c667a0. MUST re-set easyocr device:gpu (cpu=84s/page impractical) else A4 full run crawls. Do NOT edit models.yaml while A3 subagent is live.
  *** CONCURRENCY LESSON ***: two subagents sharing one worktree + me editing the same files = races (easyocr revert, slowed smokes). ROOT CAUSE: A2 subagent "paused waiting for bg run" and kept resuming, so it was still alive when A3 dispatched. RULE GOING FORWARD: strictly sequential subagents; confirm a subagent is FULLY dead before dispatching the next or editing shared files (models.yaml). Consider isolation:worktree for config-editing subagents.
- [~] A3 SLM vision — IN RECONCILIATION (controller, post-subagent).
  - kosmos25: ✅ validate-adapter 9/9 (loads, predicts sub-sec/page, telemetry, clean unload). Registered, live-verified rev.
  - phi4mm: ⚠️ BLOCKED on transformers 5.11 → UNREGISTERED (adapter kept for revival). TWO v5 issues: (1) FIXED — config.json:220 pins flash_attention_2 (v5 rejects); adapter now forces `cfg._attn_implementation="sdpa"` pre-construction → Siglip vision tower uses eager (no flash-attn, house-rule-safe). (2) BLOCKER (unfixed) — audio ConformerEncoder (speech_conformer_encoder.py:1435) calls `int(out_length)` in __init__ → `Tensor.item() cannot be called on meta tensors` under v5 meta-init; low_cpu_mem_usage=False does NOT lift it; built unconditionally even for image-only; only fix = monkeypatch remote code (won't ship). Verified via 2 bounded tests (b7gdc5vnt fixed #1→revealed #2; b3197xxm2 confirmed #2 persists). models.yaml entry removed + explanatory comment; adapter docstring documents both.
  - florence2: ⚠️ BLOCKED on transformers v5 (EncoderDecoderCache not subscriptable). Unregistered, kept for revival. Dropped from scored roster.
  - NET WS2 vision so far: kosmos25 (works) + phi4mm (fix pending) — Florence-2 out. FLAG to owner at Part-A gate.
- [x] A3 SLM vision — COMPLETE (commits 220ea56 Part-D spec, c5fe901 A3). kosmos25 registered+validated 9/9+scored-pipeline-confirmed (823 valid preds, 0 err). florence2+phi4mm BLOCKED on transformers v5 (unregistered, documented, revival-ready). easyocr device→gpu fixed. Net roster: 9 v1 + tesseract/rapidocr/doctr/easyocr + kosmos25 = 14 (Florence-2/Phi-4-mm out).
- [~] A4 full run — LAUNCHED (bg, nohup; script scratchpad/run_a4.sh; log scratchpad/a4_run.log). Into run-id **v1-baseline** (seed-0 stratified = same 100 samples/bench as v1's 9 → comparable; additive, existing 9 untouched via done_ids). Models: tesseract,rapidocr,doctr,easyocr,kosmos25. TWO invocations for co-load rule: G1 `-b olmocr_bench,omnidocbench,realdoc_qa` (reader only), G2 `-b merged_forms` (judge only), then `scoreboard --run-id v1-baseline` → scratchpad/a4_scoreboard.txt. Est $0 (local-only). Expect multi-hour (merged_forms Tier-C for CPU engines slow). MONITOR: results/runs/v1-baseline advancing + GPU; resume via same command (done_ids). ⚠️ MEMORY WATCH: Group-1 process observed at ~49GB RSS / 61GB (~85% used, 8GB avail) ~26min in (likely accumulated large decoded page images across sequential CPU engines). Not OOM yet; two-invocation split means Group 2 starts fresh (memory released when G1 exits). If G1 process RSS climbs toward ~58GB before finishing → intervene (kill+resume; done_ids preserve work). Check `free -g` + process %MEM each beat.
  A4 ✅ COMPLETE (GROUP1_EXIT=0, GROUP2_EXIT=0, SCOREBOARD_EXIT=0). 4199 scored samples, 0 error rows anywhere; Tier-C 15/15 valid PQ per engine (no all-error). Findings: findings/a4-expanded-roster.md. HEADLINE: classic CPU engines OWN Tier-C (easyocr 0.397/doctr 0.336/tesseract 0.330/rapidocr 0.258 >> best VLM gemma4 0.157); docTR 2nd on Tier-B (0.682); VLMs own Tier-A (olmocr2 0.836); kosmos25 middling (0.20-0.57). 14-model scoreboard in results/runs/v1-baseline/scoreboard.csv. → PART-A GATE digest pushed to owner. NEXT: Part B reader upgrade. On done → findings note + Part-A GATE digest to owner (Florence-2/Phi-4-mm v5 blocks + CPU-vs-GPU cost + expanded scoreboard).
- [pending] B reader upgrade
- [pending] C2 auto-inject
- [pending] C3 dashboard UI
