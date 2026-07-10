"""Deterministic scan/fax degradation pipeline (Part D, spec §4.1).

`degrade(img, level, seed) -> img` mimics a real scan/fax path:
  1. grayscale (fax is 1-bit/grayscale)
  2. resolution loss — downscale then upscale back (loses fine glyph detail)
  3. skew — small rotation (scanner misfeed), white fill
  4. Gaussian blur (optics / paper contact)
  5. Gaussian sensor noise
  6. JPEG recompression (transport artifacts)
  7. (heavy only) contrast push (toner/photocopy saturation)

Parameters are FROZEN (owner-approved comparison panel, 2026-07-09) and ported
VERBATIM from the validated reference implementation
(`faxify()` in the owner's scan-comparison script) — do not retune here.

Pure PIL/numpy — no torch import (keeps this bench CPU-safe for classic-OCR
contenders and importable without a GPU env).
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

Level = str  # "light" | "heavy"

# Frozen parameters (spec §4.1 table). Keyed by level; each entry is recorded
# on the fingerprint so a reviewer can regenerate the exact degraded page.
PARAMS: dict[str, dict[str, float]] = {
    "light": dict(scale=0.62, blur=0.6, noise=7, angle=0.6, jpeg=45),
    "heavy": dict(scale=0.42, blur=1.0, noise=15, angle=1.5, jpeg=27),
}


def degrade(img: Image.Image, level: Level, seed: int) -> Image.Image:
    """Degrade `img` to look like a `level` ("light" | "heavy") scan/fax.

    Deterministic: the same (img, level, seed) always produces byte-identical
    output (all randomness is drawn from `np.random.default_rng(seed)`).
    """
    if level not in PARAMS:
        raise ValueError(f"unknown degrade level {level!r}; expected one of {sorted(PARAMS)}")
    cfg = PARAMS[level]

    g = img.convert("L")
    w, h = g.size

    # 2. resolution loss: downscale then upscale back
    small = g.resize((max(1, int(w * cfg["scale"])), max(1, int(h * cfg["scale"]))), Image.BILINEAR)
    g2 = small.resize((w, h), Image.BILINEAR)

    # 3. skew: small rotation, white fill
    g2 = g2.rotate(cfg["angle"], expand=False, fillcolor=255, resample=Image.BILINEAR)

    # 4. Gaussian blur
    g2 = g2.filter(ImageFilter.GaussianBlur(cfg["blur"]))

    # 5. Gaussian sensor noise (seeded)
    arr = np.asarray(g2).astype(np.int16)
    rng = np.random.default_rng(seed)
    arr = np.clip(arr + rng.normal(0, cfg["noise"], arr.shape).astype(np.int16), 0, 255).astype(np.uint8)
    g2 = Image.fromarray(arr, "L")

    # 7. heavy-only contrast push
    if level == "heavy":
        a = np.asarray(g2).astype(np.float32)
        g2 = Image.fromarray(np.clip((a - 110) * 1.5 + 128, 0, 255).astype(np.uint8), "L")

    # 6. JPEG recompression (transport artifacts)
    buf = io.BytesIO()
    g2.convert("RGB").save(buf, format="JPEG", quality=cfg["jpeg"])
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def params_fingerprint(level: Level) -> dict:
    """The frozen params for `level`, for provenance stamping."""
    return dict(PARAMS[level])
