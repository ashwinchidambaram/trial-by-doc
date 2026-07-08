"""`gauntlet validate-adapter` — smoke-test a model adapter before a full run.

Checks: registry entry resolves, secrets present (API), load() works, predict()
returns a well-formed StructuredDoc with telemetry on N sample pages, unload()
releases cleanly. Prints a pass/fail checklist; exit code 1 on any failure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "docs" / "samples"


def _synthetic_page(i: int) -> Image.Image:
    """Deterministic fallback page (no bundled samples yet): text on white."""
    img = Image.new("RGB", (800, 1000), "white")
    d = ImageDraw.Draw(img)
    lines = [f"trial-by-doc validation page {i}",
             "Invoice #2026-001", "Total: $123.45", "Date: 2026-07-07",
             "| item | qty | price |", "| widget | 2 | $10.00 |"]
    for j, t in enumerate(lines):
        d.text((40, 40 + 60 * j), t, fill="black")
    return img


def sample_pages(n: int = 3) -> list[Any]:
    files = sorted(SAMPLES_DIR.glob("*.png")) if SAMPLES_DIR.exists() else []
    if files:
        return [p for p in files[:n]]
    return [_synthetic_page(i) for i in range(n)]


def validate_adapter(registry, key: str, n_pages: int = 3) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))
        print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))

    try:
        adapter = registry.model(key)
        check("registry entry resolves", True, type(adapter).__name__)
    except Exception as e:
        check("registry entry resolves", False, str(e))
        return checks

    secrets = adapter.entry.get("secrets", [])
    if secrets:
        from tbdoc.core.secrets import missing_secrets
        miss = missing_secrets(secrets)
        check("secrets present", not miss, f"missing: {', '.join(miss)}" if miss else f"{len(secrets)} set")
        if miss:
            return checks

    try:
        with adapter:
            check("load()", True)
            for i, page in enumerate(sample_pages(n_pages)):
                doc = adapter.predict(page)
                ok = hasattr(doc, "markdown") and isinstance(doc.markdown, str)
                tel_ok = doc.telemetry.latency_s is not None and doc.telemetry.backend is not None
                check(f"predict(page {i}) -> StructuredDoc", ok,
                      f"{len(doc.markdown)} chars md")
                check(f"  telemetry populated (page {i})", tel_ok,
                      f"latency={doc.telemetry.latency_s}s backend={doc.telemetry.backend}"
                      + (f" cost=${doc.telemetry.cost_usd}" if doc.telemetry.cost_usd else ""))
        check("unload()", True)
    except Exception as e:
        check("predict/unload", False, f"{type(e).__name__}: {e}")
    return checks
