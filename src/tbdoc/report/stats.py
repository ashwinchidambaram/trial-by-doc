"""Paired bootstrap confidence intervals for model comparisons.

Every model is scored on the SAME items (identical samples, deterministic scorers), so a
model-vs-model comparison is *paired*: resample item indices once per bootstrap round and
read both models' per-item scores at those indices. Paired resampling cancels
item-difficulty variance, so it's far more powerful than comparing two independent
means — the right tool for "is a 0.030 gap real or noise?".

Seeded (default seed=0) so the CIs are reproducible, per the repo's determinism rule.
Pure stdlib — no numpy/scipy dependency.
"""
from __future__ import annotations

import random
from collections.abc import Mapping


def _paired_items(a: Mapping[str, float | None], b: Mapping[str, float | None]) -> tuple[list[float], list[float]]:
    """Per-item score vectors over the items BOTH models scored numerically."""
    va, vb = [], []
    for k in a:
        x, y = a[k], b.get(k)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            va.append(float(x))
            vb.append(float(y))
    return va, vb


def paired_bootstrap_diff(a: Mapping[str, float | None], b: Mapping[str, float | None],
                          *, n_boot: int = 10000, seed: int = 0,
                          alpha: float = 0.05) -> dict:
    """Paired bootstrap of mean(a) - mean(b) over shared items.

    Returns {diff, ci_low, ci_high, p_two_sided, n} where the CI is the
    (1-alpha) percentile interval and p_two_sided is the fraction of resampled
    differences on the far side of 0 (a tie shows a CI spanning 0 and p near 1).
    """
    va, vb = _paired_items(a, b)
    n = len(va)
    if n == 0:
        return {"diff": None, "ci_low": None, "ci_high": None, "p_two_sided": None, "n": 0}
    diff = sum(va) / n - sum(vb) / n
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        boots.append(sum(va[j] for j in idx) / n - sum(vb[j] for j in idx) / n)
    boots.sort()
    lo = boots[int((alpha / 2) * n_boot)]
    hi = boots[min(int((1 - alpha / 2) * n_boot), n_boot - 1)]
    p = 2 * min(sum(1 for x in boots if x <= 0), sum(1 for x in boots if x >= 0)) / n_boot
    return {"diff": diff, "ci_low": lo, "ci_high": hi, "p_two_sided": min(p, 1.0), "n": n}


def per_sample_metric(run_dir, model: str, bench: str, key: str) -> dict[str, float | None]:
    """{sample_id: metric[key]} for one cell, last-record-per-sample (rescore-safe)."""
    import json
    from pathlib import Path
    path = Path(run_dir) / "raw" / model / f"{bench}.jsonl"
    out: dict[str, float | None] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        m = r.get("metrics") or {}
        out[str(r.get("sample_id"))] = m.get(key) if r.get("error") is None else None
    return out
