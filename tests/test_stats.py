"""Paired bootstrap CI helper — determinism, tie vs. real-gap discrimination, pairing."""
from __future__ import annotations

from tbdoc.report.stats import paired_bootstrap_diff


def test_identical_scores_are_a_tie():
    a = {f"s{i}": float(i % 2) for i in range(100)}
    r = paired_bootstrap_diff(a, dict(a))
    assert r["diff"] == 0.0
    assert r["ci_low"] <= 0 <= r["ci_high"]
    assert r["p_two_sided"] == 1.0


def test_large_consistent_gap_is_significant():
    # a beats b on every item -> paired CI must exclude 0
    a = {f"s{i}": 1.0 for i in range(100)}
    b = {f"s{i}": 0.0 for i in range(100)}
    r = paired_bootstrap_diff(a, b)
    assert r["diff"] == 1.0
    assert r["ci_low"] > 0
    assert r["p_two_sided"] < 0.05


def test_small_noisy_gap_spans_zero():
    # the B.2 leading-trio situation: each model wins a few items the other loses,
    # net a tiny edge -> the paired CI spans 0 (a statistical tie)
    a = {f"s{i}": 0.0 for i in range(100)}
    b = {f"s{i}": 0.0 for i in range(100)}
    for i in range(5):        # a wins 5 items
        a[f"s{i}"] = 1.0
    for i in range(5, 8):     # b wins 3 items -> net +0.02 for a
        b[f"s{i}"] = 1.0
    r = paired_bootstrap_diff(a, b)
    assert abs(r["diff"] - 0.02) < 1e-9
    assert r["ci_low"] < 0 < r["ci_high"]  # tie: CI spans 0


def test_seed_is_deterministic():
    a = {f"s{i}": float((i * 7) % 3 == 0) for i in range(80)}
    b = {f"s{i}": float((i * 5) % 3 == 0) for i in range(80)}
    r1 = paired_bootstrap_diff(a, b, seed=0)
    r2 = paired_bootstrap_diff(a, b, seed=0)
    assert (r1["ci_low"], r1["ci_high"]) == (r2["ci_low"], r2["ci_high"])


def test_only_shared_numeric_items_are_paired():
    a = {"s0": 1.0, "s1": 0.0, "s2": None, "s3": 1.0}
    b = {"s0": 0.0, "s1": 0.0, "s2": 1.0, "s4": 1.0}  # s2 None in a, s3/s4 unshared
    r = paired_bootstrap_diff(a, b)
    assert r["n"] == 2  # only s0, s1


def test_empty_overlap_is_safe():
    r = paired_bootstrap_diff({"s0": 1.0}, {"s9": 1.0})
    assert r["n"] == 0 and r["diff"] is None
