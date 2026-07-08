"""Official olmOCR-Bench scorer — runs in THIS isolated venv (olmocr[bench]), invoked via subprocess.

Contract (JSON in on stdin, JSON out on stdout):
  argv[1] = bench_data dir (has *.jsonl test files)
  stdin   = JSON {"pdf_id": "<basename.pdf>", "markdown": "<predicted md>"}
  stdout  = JSON {"pdf_id","passed","total","pass_rate","by_type","fails","tables_excluded"}

We wrap the official `olmocr.bench.tests` runner — never reimplement the rules. A page's score is the
fraction of its unit tests that pass against the predicted markdown.

KNOWN LIMITATION (this host): olmOCR's TableTest renders tables via Playwright/Chromium, which has no
build for Ubuntu 26.04 (`playwright install` fails). So `table_tests.jsonl` is EXCLUDED here and the
output flags `tables_excluded: true`. All other test types (text presence, math, reading order,
headers/footers, multi-column, scans) run normally — no browser needed. Revisit tables in a container
on a Playwright-supported OS. See findings/S9.
"""
import contextlib
import glob
import io
import json
import os
import sys
from collections import defaultdict
from functools import lru_cache

from olmocr.bench.tests import load_tests

# Test types that render via Playwright/Chromium (katex math, HTML tables). Excluded on hosts without
# a Playwright browser (Ubuntu 26.04) and reported separately; scored normally inside the scorer
# container (SCORER_RENDER=1, MS Playwright base image). Pure text/order tests always run.
RENDER_TYPES = set() if os.environ.get("SCORER_RENDER") == "1" else {"math", "table"}


@lru_cache(maxsize=1)
def _index(bench_dir):
    idx, skipped = defaultdict(list), defaultdict(int)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for jf in sorted(glob.glob(os.path.join(bench_dir, "*.jsonl"))):
            try:
                for t in load_tests(jf):
                    key = os.path.basename(t.pdf)
                    if t.type in RENDER_TYPES:
                        skipped[key] += 1
                    else:
                        idx[key].append(t)
            except Exception:
                continue
    return idx, skipped


# Sampling: cap how many slow Playwright-rendered tests (math/table) we actually run PER DOC, to bound
# the ~23s/test cost on a full run. Deterministic (sorted by test id) so every model is scored on the
# SAME sampled tests -> fair comparison. 0 = no cap. Native text/order tests always run (they're fast).
_RENDER_CAP = int(os.environ.get("SCORER_RENDER_CAP", "0"))
_RENDER = {"math", "table"}


def _score_one(idx, skipped, pdf_id, md):
    tests = idx.get(pdf_id, [])
    if _RENDER_CAP:
        kept, seen_render = [], 0
        for t in sorted(tests, key=lambda x: x.id):
            if t.type in _RENDER:
                if seen_render >= _RENDER_CAP:
                    skipped[pdf_id] = skipped.get(pdf_id, 0) + 1
                    continue
                seen_render += 1
            kept.append(t)
        tests = kept
    passed, by_pass, by_tot, fails = 0, defaultdict(int), defaultdict(int), []
    for t in tests:
        by_tot[t.type] += 1
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                ok, reason = t.run(md)
            except Exception as e:
                ok, reason = False, f"runner-error: {type(e).__name__}: {e}"
        if ok:
            passed += 1
            by_pass[t.type] += 1
        else:
            fails.append({"id": t.id, "type": t.type, "reason": str(reason)[:160]})
    total = len(tests)
    return {
        "pdf_id": pdf_id, "passed": passed, "total": total,
        "pass_rate": (passed / total) if total else None,
        "by_type": {k: [by_pass[k], by_tot[k]] for k in by_tot},
        "fails": fails[:8], "render_tests_excluded": skipped.get(pdf_id, 0),
    }


def main():
    bench_dir = sys.argv[1]
    idx, skipped = _index(bench_dir)
    # BATCH contract: each stdin line is a JSON {pdf_id, markdown}; emit one JSON result per line.
    # (One container run scores a whole model's benchmark — the cold start + warm browser amortize.)
    # A single non-JSONL object on stdin is also accepted (one result).
    raw = sys.stdin.read().strip()
    reqs = []
    if raw.startswith("[") :
        reqs = json.loads(raw)
    elif "\n" in raw and raw.lstrip().startswith("{"):
        reqs = [json.loads(l) for l in raw.splitlines() if l.strip()]
    elif raw:
        reqs = [json.loads(raw)]
    for req in reqs:
        out = _score_one(idx, skipped, req["pdf_id"], req.get("markdown", "") or "")
        print(json.dumps(out), flush=True)
    # olmocr's katex Playwright browsers don't reap cleanly and hang the process on exit; results are
    # already emitted, so hard-exit to skip that hang.
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
