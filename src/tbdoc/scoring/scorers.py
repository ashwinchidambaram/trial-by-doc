"""Pure-Python scoring primitives that need no isolated env or browser.

ANLS (DocVQA) and normalized exact-match (RealDoc-QA) are simple string metrics — we keep them in the
main env. Rendering/structure scorers (olmOCR math+tables, OmniDocBench TEDS/CDM) live in isolated
venvs / Docker scorer containers instead (see benchmarks/_scorers/).
"""
from __future__ import annotations

import math
import re as _re


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


# ---- B.1 extraction fidelity (deterministic; no LLM) -------------------------------------------
# "Did the OCR reproduce the gold field VALUES on the page?" Reuses the field parsing + tolerant
# value matching from field_aware_exact_match, but searches the markdown instead of an answer.

_DERIVED_PAT = _re.compile(r"\b(how many|number of|count of|how much .*in total|total number)\b", _re.I)
# Anonymization / template placeholders in the GOLD (e.g. RealDoc's «ID», «ApproveDate», <name>,
# {{field}}) are NOT reliable extraction targets — no OCR model can reproduce a redaction token, so
# they'd unfairly floor B.1 for every model. Items whose gold carries one are excluded from B.1.
_PLACEHOLDER_PAT = _re.compile(r"«[^»]*»|‹[^›]*›|<[^>]{0,40}>|\{\{.*?\}\}")


def _surface_token(v: str) -> bool:
    """A value that could plausibly appear verbatim on a page: numeric, or a short string (<=64),
    and NOT an anonymization/template placeholder token."""
    t = str(v).strip()
    if _PLACEHOLDER_PAT.search(t):
        return False
    if _as_number(t) is not None:
        return True
    return 0 < len(t) <= 64


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
    step = max(1, w // 2)
    starts = set(range(0, max(1, len(md_norm) - w + 1), step))
    starts.add(max(0, len(md_norm) - w))
    for i in sorted(starts):
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
