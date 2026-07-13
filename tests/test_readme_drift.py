"""Drift guard: the README's HAND-AUTHORED numbers must still match the run data.

The scoreboard block between the ``SCOREBOARD:BEGIN/END`` markers is auto-injected and
always fresh. But the analysis prose around it — the Bottom line, Recommendations, the
scanned-robustness table, the B.2 re-score table, the Tier-C floor table — is typed by
hand. If a published run is ever re-scored, those numbers can silently go stale with
nothing to catch it. This test re-derives each load-bearing figure from the TRACKED
``summary.json`` aggregates and asserts the README still displays it (at 3-dp display
precision), so re-scoring a run without updating the prose fails CI instead of shipping a
lie. It exercises exactly the artifacts a fresh clone has (summary.json), so it runs
anywhere — no raw/ records needed.

If this test fails after an intentional re-score: update the README table it names, then
update the expected number here only if the *source* (run_id/bench/metric) changed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text()


def _summary(run_id: str) -> dict:
    return json.loads((REPO / "results" / "runs" / run_id / "summary.json").read_text())


def _cell_mean(run_id: str, model: str, bench: str) -> float | None:
    s = _summary(run_id)["cells"].get(f"{model}|{bench}")
    return s["mean"] if s and s.get("mean") is not None else None


def _parse_table(header_contains: list[str]) -> list[dict[str, str]]:
    """Rows (as {column: cell}) of the first README markdown table whose header row
    contains every string in ``header_contains``."""
    lines = README.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and all(h in line for h in header_contains):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:                      # +2 skips the |---|---| separator
                if not row.lstrip().startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append(dict(zip(header, cells)))
            return rows
    raise AssertionError(f"README table not found (header contains {header_contains})")


def _nums(cell: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+\.\d+|-?\d+", cell.replace("*", "").replace("`", ""))]


def _one(cell: str) -> float | None:
    n = _nums(cell)
    return n[0] if n else None


def _at3(x: float) -> str:
    return f"{x:.3f}"


# --- Scanned-and-faxed robustness table -------------------------------------------------

def test_scanned_robustness_table_matches_run_data():
    rows = _parse_table(["clean", "light", "heavy", "retained"])
    assert len(rows) >= 13, f"expected the full robustness roster, got {len(rows)} rows"
    cols = list(rows[0])
    clean_c, light_c, heavy_c = cols[1], cols[2], cols[3]
    retained_c = cols[4]
    for r in rows:
        model = r[cols[0]].replace("*", "").strip()
        for col, bench in ((clean_c, "realdoc_qa"),
                           (light_c, "realdoc_qa_scanned_light"),
                           (heavy_c, "realdoc_qa_scanned_heavy")):
            data = _cell_mean("v1-baseline", model, bench)
            assert data is not None, f"{model}|{bench} missing from v1-baseline summary"
            assert _at3(data) == _at3(_one(r[col])), (
                f"scanned table drift: {model} {col} README={r[col]} data={_at3(data)}")
        # retained = heavy / clean (%), derived from the table's own DISPLAYED 3-dp scores
        # (so a reader can verify it), when the README states a number (granite = noise floor)
        ret = _one(r[retained_c])
        if ret is not None:
            clean = round(_cell_mean("v1-baseline", model, "realdoc_qa"), 3)
            heavy = round(_cell_mean("v1-baseline", model, "realdoc_qa_scanned_heavy"), 3)
            assert round(heavy / clean * 100) == round(ret), (
                f"retained% drift: {model} README={ret} data={round(heavy/clean*100)}")


# --- Recommendations "Mixed B.1" = mean(clean, light, heavy) ----------------------------

def test_recommendations_mixed_b1_is_mean_of_conditions():
    rows = _parse_table(["Your constraint", "Mixed B.1"])
    checked = 0
    for r in rows:
        picks = [p.strip().lower() for p in r["Pick"].replace("*", "").split("/")]
        mixed = _nums(r["Mixed B.1"])
        if not mixed:                                      # the full-page row lists "—"
            continue
        assert len(picks) == len(mixed), f"pick/number count mismatch in row: {r}"
        for model, stated in zip(picks, mixed):
            conds = [_cell_mean("v1-baseline", model, b) for b in
                     ("realdoc_qa", "realdoc_qa_scanned_light", "realdoc_qa_scanned_heavy")]
            assert all(c is not None for c in conds), f"{model} missing a condition cell"
            assert _at3(sum(conds) / 3) == _at3(stated), (
                f"Mixed B.1 drift: {model} README={stated} mean(clean,light,heavy)={_at3(sum(conds)/3)}")
            checked += 1
    assert checked >= 6, f"expected to check ~6 recommendation picks, checked {checked}"


# --- B.2 re-score table (B.1 + gpt-5.4-mini reader) --------------------------------------

def test_b2_rescore_table_matches_run_data():
    rows = _parse_table(["B.1 extract", "gpt-5.4-mini"])
    tb_new = _summary("v1-b2-gpt5mini")["tier_b"]
    tb_hist = _summary("v1-baseline")["tier_b"]
    cols = list(rows[0])
    b1_c = next(c for c in cols if "B.1" in c)
    hist_c = next(c for c in cols if "historical" in c)
    new_c = next(c for c in cols if "gpt-5.4-mini" in c)
    assert len(rows) >= 13
    for r in rows:
        model = r[cols[0]].replace("*", "").strip()
        assert _at3(tb_new[model]["b1"]) == _at3(_one(r[b1_c])), f"B.1 drift: {model}"
        assert _at3(tb_new[model]["b2"]) == _at3(_one(r[new_c])), f"B.2 gpt-5.4-mini drift: {model}"
        assert _at3(tb_hist[model]["b2"]) == _at3(_one(r[hist_c])), f"B.2 historical drift: {model}"


# --- Tier-C floor baselines -------------------------------------------------------------

def test_tierc_floor_table_matches_run_data():
    rows = _parse_table(["baseline", "what it does", "PQ"])
    assert {r["baseline"].replace("`", "").strip() for r in rows} == {
        "baseline_pixel_diff", "baseline_every_page", "baseline_no_boundary"}
    for r in rows:
        name = r["baseline"].replace("`", "").strip()
        data = _cell_mean("tierc-floor-15", name, "merged_forms")
        assert data is not None, f"{name} missing from tierc-floor-15 summary"
        assert _at3(data) == _at3(_one(r["PQ"])), (
            f"Tier-C floor drift: {name} README={r['PQ']} data={_at3(data)}")


# --- meta: the guard is anchored to real, tracked runs ----------------------------------

@pytest.mark.parametrize("run_id", ["v1-baseline", "v1-b2-gpt5mini", "tierc-floor-15"])
def test_guarded_runs_have_tracked_summaries(run_id):
    assert (REPO / "results" / "runs" / run_id / "summary.json").exists()
