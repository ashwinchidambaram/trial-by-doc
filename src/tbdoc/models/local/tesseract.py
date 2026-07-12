"""Tesseract adapter — classic CPU OCR engine (Apache-2.0). No torch import.

First WS1 contender (see docs/superpowers/specs/2026-07-09-roster-expansion-design.md).
Subclasses `ModelAdapter` directly, not `LocalModelAdapter`/`TransformersModelAdapter` —
there is no GPU state to tear down and no HF repo/revision to pin (see `fingerprint()`).

Runs the system `tesseract` binary via `pytesseract`. Requires the binary on PATH (or
`tesseract_cmd` set in the models.yaml entry) — `load()` fails loudly if it's missing
rather than silently degrading to an empty parse.
"""
from __future__ import annotations

import shutil
from typing import Any

from tbdoc.core.model_adapter import ModelAdapter
from tbdoc.core.registry import register_model
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track


@register_model("tesseract")
class TesseractAdapter(ModelAdapter):
    """Plain-text OCR via the classic Tesseract engine. CPU-only; no GPU path exists."""

    lang = "eng"
    # Downscale huge scans before OCR. Tesseract's layout analysis degrades to
    # minutes/page on full-res images (a 145 MP merged_forms page hangs for minutes);
    # CPU adapters do NOT inherit the vLLM resize path, so we cap here. ~2600 px longest
    # side ≈ 300 DPI on a letter page — Tesseract's sweet spot. Normal rendered pages
    # (~1600–2200 px) are untouched; only oversized scans are downscaled. Configurable
    # via the models.yaml entry (`longest_side`). Documented preprocessing (Spec A §4).
    longest_side = 2600
    # Word-level bboxes require a SECOND full Tesseract pass (image_to_data); off by
    # default so predict() = one OCR pass (fair throughput). Enable via entry `emit_boxes`.
    emit_boxes = False

    def load(self) -> None:
        import pytesseract

        cmd = self.entry.get("tesseract_cmd")
        if cmd:
            # a configured path may be host-specific (e.g. the reference host's
            # micromamba env) — fall back to PATH before failing on other machines
            if shutil.which(cmd) is None and shutil.which("tesseract") is not None:
                cmd = "tesseract"
            pytesseract.pytesseract.tesseract_cmd = cmd
        resolved = pytesseract.pytesseract.tesseract_cmd
        if shutil.which(resolved) is None:
            raise RuntimeError(
                f"tesseract binary not found (looked for '{resolved}') — install "
                "tesseract-ocr (e.g. `apt install tesseract-ocr` or a conda-forge/"
                "micromamba env with the `tesseract` package) and/or set "
                "configs/models.yaml tesseract.tesseract_cmd to the binary's path")
        # get_tesseract_version() itself shells out; a readiness check, not just a
        # PATH lookup, so a broken/unreadable binary fails at load() not predict().
        self._version = str(pytesseract.get_tesseract_version())
        # Per-model overrides from the registry entry (fall back to class defaults).
        self.lang = self.entry.get("lang", self.lang)
        self.longest_side = int(self.entry.get("longest_side") or self.longest_side)
        self.emit_boxes = bool(self.entry.get("emit_boxes", self.emit_boxes))

    def _prepare(self, image: Any) -> Any:
        """Open + downscale the page so Tesseract doesn't choke on oversized scans."""
        from PIL import Image

        img = image if isinstance(image, Image.Image) else Image.open(image)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if self.longest_side:
            w, h = img.size
            m = max(w, h)
            if m > self.longest_side:
                scale = self.longest_side / m
                img = img.resize(
                    (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        return img

    def predict(self, image: Any) -> StructuredDoc:
        import pytesseract

        img = self._prepare(image)
        with track() as timing:
            text = pytesseract.image_to_string(img, lang=self.lang)
            layout_boxes = self._word_boxes(img) if self.emit_boxes else None
        t = timing[0]
        return StructuredDoc(
            markdown=text,
            layout_boxes=layout_boxes,
            telemetry=Telemetry(latency_s=t.latency_s, backend="tesseract"),
        )

    def _word_boxes(self, img: Any) -> list[dict] | None:
        """Word-level bboxes from image_to_data. Best-effort — None on any failure
        (honestly-unavailable convention; predict() never blocks on this)."""
        try:
            import pytesseract
            from pytesseract import Output

            data = pytesseract.image_to_data(img, lang=self.lang, output_type=Output.DICT)
        except Exception:
            return None
        boxes = []
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                continue
            x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            boxes.append({"bbox": [x, y, x + w, y + h], "type": "word", "text": text})
        return boxes or None

    def fingerprint(self) -> dict:
        return {"key": self.key, "backend": "tesseract", "engine": "tesseract",
                "engine_version": getattr(self, "_version", "n/a"), "revision": "n/a"}
