"""Run-directory discovery for the dashboard.

Deliberately independent of `cli.py`'s `_latest_run()`, which globs `run_*` — a naming
convention no run in this repo actually uses (`v1-baseline`, `gate1`, `smoke-a2`, ...; see
docs/superpowers/specs/2026-07-09-dashboard-ui-design.md §7). Here "latest" = most
recently modified directory under `results_dir` that looks like a scored run (has a
`raw/` subdirectory).
"""
from __future__ import annotations

from pathlib import Path


def _is_run_dir(p: Path) -> bool:
    return p.is_dir() and (p / "raw").is_dir()


def list_run_ids(results_dir: str | Path) -> list[str]:
    """Run ids under results_dir, newest-modified first."""
    root = Path(results_dir)
    if not root.exists():
        return []
    dirs = [p for p in root.iterdir() if _is_run_dir(p)]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in dirs]


def resolve_run(results_dir: str | Path, run_id: str | None) -> Path:
    """The run directory for `run_id`, or the latest scored run if `run_id` is None."""
    root = Path(results_dir)
    if run_id:
        run_dir = root / run_id
        if not _is_run_dir(run_dir):
            raise FileNotFoundError(f"no scored run '{run_id}' under {root} (no raw/ subdir)")
        return run_dir
    ids = list_run_ids(root)
    if not ids:
        raise FileNotFoundError(f"no scored runs under {root}")
    return root / ids[0]
