"""Invoke a Dockerized scorer in BATCH — the pattern for rendering scorers (olmOCR math/tables,
OmniDocBench TEDS/CDM) that can't run natively on this host (Playwright has no Ubuntu 26.04 build).

Why batch: a scorer container cold-starts heavy deps (olmocr+torch ~30s) and a Playwright browser per
run, so per-page `docker run` is hopeless. We score a whole (model, benchmark) in ONE container run:
each input doc is a JSON line {pdf_id, markdown}; the container emits one JSON result line per doc.

Inference (GPU, this env) and scoring (CPU, container) are decoupled: the harness saves predicted
markdown, then this scores it. Exit code is treated leniently — we parse stdout result lines (the
container hard-exits to skip a Playwright cleanup hang, so the code can be non-zero even on success).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class ScorerContainerError(RuntimeError):
    pass


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def score_batch(image: str, mounts: dict[str, str], docs: list[dict[str, Any]],
                timeout_s: int = 3600, env: dict[str, str] | None = None) -> dict[str, dict]:
    """Run `image` once over `docs` (each {pdf_id, markdown}); return {pdf_id: result_dict}.

    `mounts` maps host_path -> container_path (read-only); `env` -> docker `-e` vars (e.g. sampling cap).
    Results are matched back by pdf_id.
    """
    if not docs:
        return {}
    if not docker_available():
        raise ScorerContainerError("docker not available — cannot run containerized scorer")
    args = ["docker", "run", "--rm", "-i"]
    for host, cont in mounts.items():
        args += ["-v", f"{host}:{cont}:ro"]
    for k, v in (env or {}).items():
        args += ["-e", f"{k}={v}"]
    args.append(image)
    stdin = "\n".join(json.dumps(d) for d in docs)
    try:
        proc = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise ScorerContainerError(f"scorer container timed out after {timeout_s}s") from e
    out: dict[str, dict] = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "pdf_id" in r:
            out[r["pdf_id"]] = r
    if not out:
        raise ScorerContainerError(
            f"scorer container produced no results (rc={proc.returncode}); "
            f"stderr tail: {(proc.stderr or '')[-300:]}"
        )
    return out
