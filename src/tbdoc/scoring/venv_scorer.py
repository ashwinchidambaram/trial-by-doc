"""Invoke an official scorer living in its own isolated venv, in BATCH.

Contract (mirrors scoring/container_scorer.py): stdin = one JSON line per doc
{"pdf_id", "markdown"}; stdout = one JSON result line per doc, matched by pdf_id.
The scorer's deps (old transformers/torch pins) never touch the inference env.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class ScorerVenvError(RuntimeError):
    pass


def score_batch_venv(scorer_dir: str | Path, args: list[str], docs: list[dict[str, Any]],
                     timeout_s: int = 3600, env: dict[str, str] | None = None) -> dict[str, dict]:
    """Run `<scorer_dir>/.venv/bin/python <scorer_dir>/score.py *args` over docs."""
    if not docs:
        return {}
    d = Path(scorer_dir)
    py = d / ".venv" / "bin" / "python"
    script = d / "score.py"
    if not py.exists():
        raise ScorerVenvError(
            f"scorer venv missing: {py} — create it (see {d}/README.md), e.g. "
            f"`uv venv {d}/.venv && uv pip install -p {d}/.venv/bin/python -r {d}/requirements.txt`")
    import os
    full_env = {**os.environ, **(env or {})}
    stdin = "\n".join(json.dumps(x) for x in docs)
    try:
        proc = subprocess.run([str(py), str(script), *args], input=stdin, env=full_env,
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise ScorerVenvError(f"scorer timed out after {timeout_s}s") from e
    out: dict[str, dict] = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                r = json.loads(line)
                if "pdf_id" in r:
                    out[r["pdf_id"]] = r
            except json.JSONDecodeError:
                continue
    if not out:
        raise ScorerVenvError(f"scorer produced no results (rc={proc.returncode}); "
                              f"stderr tail: {(proc.stderr or '')[-300:]}")
    return out
