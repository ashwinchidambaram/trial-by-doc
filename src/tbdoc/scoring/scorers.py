"""Pure-Python scoring primitives that need no isolated env or browser.

ANLS (DocVQA) and normalized exact-match (RealDoc-QA) are simple string metrics — we keep them in the
main env. Rendering/structure scorers (olmOCR math+tables, OmniDocBench TEDS/CDM) live in isolated
venvs / Docker scorer containers instead (see benchmarks/_scorers/).
"""
from __future__ import annotations

import math


def levenshtein(a: str, b: str) -> int:
    """Edit distance (iterative, O(len(a)*len(b)) time, O(len(b)) space)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(s: str) -> str:
    return " ".join(str(s).strip().lower().split())


def anls(prediction: str, golds: list[str], threshold: float = 0.5) -> float:
    """Average Normalized Levenshtein Similarity for ONE question (official DocVQA metric).

    NLS = 1 - edit_distance/max(len) against each gold (case-insensitive, whitespace-normalized);
    take the best gold; values below `threshold` are floored to 0 (the standard DocVQA rule).
    Returns the per-question score in [0, 1]; the dataset ANLS is the mean over questions.
    """
    p = _norm(prediction)
    best = 0.0
    for g in golds:
        gg = _norm(g)
        if not p and not gg:
            best = max(best, 1.0)
            continue
        m = max(len(p), len(gg)) or 1
        nls = 1.0 - levenshtein(p, gg) / m
        best = max(best, nls)
    return best if best >= threshold else 0.0


def normalized_exact_match(prediction: str, golds: list[str]) -> float:
    """RealDoc-QA per-field check: 1.0 if the (normalized) prediction equals any gold, else 0.0.

    Kept for reference/back-compat; the live RealDoc-QA metric is field_aware_exact_match (#3)."""
    p = _norm(prediction)
    return 1.0 if any(p == _norm(g) for g in golds) else 0.0


# ---- Field-aware exact match (RealDoc-QA, S11 #3) ----------------------------------------------
# The RealDoc gold is `key=value`, often multi-field joined by ';' (e.g. "check_if_none=false;
# nexus_tech_amount_paid=8500"). Plain string-equality (normalized_exact_match) scored demonstrably
# correct parses as wrong — e.g. a checkbox read as "X" vs gold "true", or "151000.0" vs "151000".
# field_aware_exact_match parses both sides into per-field dicts and compares each value with boolean
# aliasing + numeric tolerance, order-insensitively. _norm/anls above are deliberately NOT touched.

_BOOL_TRUE = {"x", "✓", "✔", "☑", "yes", "checked", "true", "[x]", "(x)", "marked"}
_BOOL_FALSE = {"☐", "[ ]", "( )", "no", "unchecked", "false", "not marked", "unmarked"}


def _canon_value(v: str) -> str:
    """Canonicalize a single field value: whitespace/case-normalize, then alias common boolean tokens."""
    t = " ".join(str(v).strip().lower().split())
    if t in _BOOL_TRUE:
        return "true"
    if t in _BOOL_FALSE:
        return "false"
    return t


def _as_number(v: str):
    """Parse a value as a number after stripping currency/grouping/percent; None if it isn't numeric."""
    t = str(v).strip().lower().replace("$", "").replace(",", "").replace("%", "").strip()
    if t in ("", "-", "."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _values_match(a: str, b: str) -> bool:
    """One value vs one value: canonical-string equal, or numerically close (24500.00 == 24500.0)."""
    if _canon_value(a) == _canon_value(b):
        return True
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        return math.isclose(na, nb, rel_tol=1e-6, abs_tol=1e-9)
    return False


def _parse_fields(s: str) -> dict[str, str] | None:
    """Parse 'k1=v1; k2=v2' -> {k1:v1, k2:v2} (first '=' splits; key lowercased). None if not key=value."""
    s = str(s).strip()
    if "=" not in s:
        return None
    out: dict[str, str] = {}
    for part in s.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        out[k.strip().lower()] = v.strip()
    return out or None


def field_aware_exact_match(prediction: str, golds: list[str]) -> float:
    """RealDoc-QA match tolerant of benign formatting (#3). 1.0 if the prediction matches any gold.

    Structured gold (key=value): every gold field must be present in the prediction and match by
    boolean-aliased / numerically-tolerant value compare (order-insensitive; extra prediction fields
    are ignored). Non-structured gold: fall back to a whole-string canonical/numeric compare.
    """
    p_fields = _parse_fields(prediction)
    for g in golds:
        g_fields = _parse_fields(g)
        if g_fields and p_fields:
            if all(k in p_fields and _values_match(p_fields[k], g_fields[k]) for k in g_fields):
                return 1.0
        elif _values_match(prediction, g):  # gold (or prediction) not key=value -> whole-string compare
            return 1.0
    return 0.0
