"""Secrets handling: .env loading + presence checks. NEVER log values.

Registry entries name their required env vars (`secrets: [MISTRAL_API_KEY]`);
we verify presence at run start — fail fast, before any GPU load or API spend.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    try:
        from dotenv import load_dotenv as _ld
        _ld(p, override=False)
    except ImportError:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def missing_secrets(names: list[str]) -> list[str]:
    """Return the subset of env var names that are unset/empty (names only, no values)."""
    return [n for n in names if not os.environ.get(n)]


def require_secrets(names: list[str], *, context: str = "") -> None:
    miss = missing_secrets(names)
    if miss:
        raise RuntimeError(
            f"missing required secrets{f' for {context}' if context else ''}: "
            f"{', '.join(miss)} (set them in .env — values are never logged)")
