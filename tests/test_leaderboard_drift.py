"""docs/leaderboard.md must equal what `gauntlet leaderboard` generates.

Same guard pattern as test_readme_drift: the committed file is a build artifact of
`tbdoc.report.leaderboard`; any hand-edit (or any run/summary change without a regen)
fails here. Regenerate with `uv run gauntlet leaderboard`.
"""
from pathlib import Path

import pytest

from tbdoc.core.registry import Registry
from tbdoc.report.leaderboard import leaderboard_data, render_md

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def generated() -> str:
    reg = Registry(str(ROOT / "configs"))
    return render_md(leaderboard_data(ROOT / "results/runs", reg))


def test_leaderboard_md_matches_generator(generated: str):
    committed = (ROOT / "docs/leaderboard.md").read_text()
    assert committed == generated, (
        "docs/leaderboard.md is stale or hand-edited — regenerate with "
        "`uv run gauntlet leaderboard`")


def test_leaderboard_names_all_four_tiers(generated: str):
    for t in ("**A**", "**B**", "**C**", "**D**"):
        assert t in generated


def test_leaderboard_cells_are_explicit(generated: str):
    # gaps must be labeled, never silently blank: pending frontier rows,
    # deferred Tier-C cells, and the legend explaining them
    assert "pending" in generated
    assert "deferred" in generated
    assert "`—` = not run yet" in generated
