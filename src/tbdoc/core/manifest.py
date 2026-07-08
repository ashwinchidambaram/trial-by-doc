"""Run manifest — the provenance stamp for a whole run.

Written to results/runs/<run_id>/manifest.json at run start; every scoreboard row
traces back to it. A baseline you can't reproduce is not a baseline.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except Exception:
        return None


def build_manifest(*, run_id: str, models: list[str], benches: list[str],
                   model_fingerprints: dict[str, dict], bench_fingerprints: dict[str, dict],
                   instruments: dict[str, Any] | None = None,
                   hardware: dict | None = None, seeds: dict | None = None,
                   extra: dict | None = None, config_dir: str | Path = "configs") -> dict:
    cfg = Path(config_dir)
    m = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "harness": {
            "git_sha": _git(["rev-parse", "HEAD"]),
            "git_dirty": bool(_git(["status", "--porcelain"])),
            "python": sys.version.split()[0],
            "argv": sys.argv,
        },
        "configs": {p.name: _sha256(p) for p in sorted(cfg.glob("*.yaml"))},
        "models": model_fingerprints,
        "benchmarks": bench_fingerprints,
        "instruments": instruments or {},
        "hardware": hardware,
        "seeds": seeds or {"sampling_seed": 0, "temperature": 0},
    }
    if extra:
        m.update(extra)
    _ = models, benches  # fingerprint dicts carry the authoritative lists
    return m


def write_manifest(run_dir: str | Path, manifest: dict) -> Path:
    p = Path(run_dir) / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2))
    return p
