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


def _invocation_stanza(manifest: dict) -> dict:
    """The per-invocation slice of a manifest (what varies between reruns of a run-id)."""
    return {
        "created_at": manifest.get("created_at"),
        "harness": manifest.get("harness"),
        "models": sorted(manifest.get("models") or {}),
        "benchmarks": sorted(manifest.get("benchmarks") or {}),
    }


def write_manifest(run_dir: str | Path, manifest: dict) -> Path:
    """Write manifest.json, MERGING with any existing one — a rescore/resume into the
    same run-id must never clobber the original run's provenance (this bug destroyed
    v1-baseline's core-bench fingerprints once). Union the fingerprint maps, keep the
    first invocation's created_at, and log every invocation under "invocations".
    Top-level "harness" reflects the LATEST invocation; per-invocation history has the rest.
    """
    p = Path(run_dir) / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if p.exists():
        try:
            old = json.loads(p.read_text())
        except Exception:
            old = None
    merged = dict(manifest)
    if old:
        invocations = list(old.get("invocations") or [_invocation_stanza(old)])
        merged["created_at"] = old.get("created_at") or manifest.get("created_at")
        for k in ("models", "benchmarks", "instruments", "configs"):
            merged[k] = {**(old.get(k) or {}), **(manifest.get(k) or {})}
        # preserve keys the new manifest doesn't know about (e.g. a reconstruction note)
        for k, v in old.items():
            merged.setdefault(k, v)
    else:
        invocations = []
    merged["invocations"] = invocations + [_invocation_stanza(manifest)]
    p.write_text(json.dumps(merged, indent=2))
    return p
