"""EasyOCR adapter — JaidedAI's modern classic OCR engine (PyTorch). Apache-2.0.

Second wave of WS1 CPU-capable OCR engines (see `tesseract.py` for the template this
follows). Subclasses `LocalModelAdapter` (not `ModelAdapter` directly, unlike Tesseract/
RapidOCR) because EasyOCR runs on torch and has real GPU state — `LocalModelAdapter.
unload()` calls `free_gpu()` for us.

Module is named `easyocr_engine.py` (not `easyocr.py`) so `import easyocr` inside this
file unambiguously resolves to the PyPI package, not this module, if this package's
directory is ever prepended to sys.path.

`device` is read from the registry entry (`"cpu"` | `"gpu"`) so the perf harness can
measure the same accuracy on both devices later; accuracy is device-invariant, only
latency (and `peak_vram_mb` on GPU) differs.
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.model_adapter import LocalModelAdapter
from tbdoc.core.registry import register_model
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track


@register_model("easyocr")
class EasyOCRAdapter(LocalModelAdapter):
    """EasyOCR two-stage OCR (CRAFT detector + CRNN recognizer), pretrained weights."""

    # Same rationale as Tesseract's cap: full-res merged_forms pages (~145 MP) make
    # even the numpy conversion/preprocessing before EasyOCR's own internal resize slow
    # enough to hang. Configurable via the models.yaml entry (`longest_side`).
    longest_side = 2600
    lang = "en"

    def load(self) -> None:
        import importlib.metadata as im

        import easyocr

        self.longest_side = int(self.entry.get("longest_side") or self.longest_side)
        self.lang = self.entry.get("lang", self.lang)
        self.device = self.entry.get("device", "cpu")
        if self.device == "gpu":
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("easyocr: device='gpu' requested but torch.cuda.is_available() "
                                    "is False on this box")
        elif self.device != "cpu":
            raise RuntimeError(f"easyocr: unknown device '{self.device}' (expected cpu|gpu)")
        self._reader = easyocr.Reader([self.lang], gpu=(self.device == "gpu"))
        self._version = im.version("easyocr")

    def _prepare(self, image: Any) -> Any:
        """Open + downscale the page so preprocessing doesn't choke on oversized scans."""
        from PIL import Image

        img = image if isinstance(image, Image.Image) else Image.open(image)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if self.longest_side:
            w, h = img.size
            longest = max(w, h)
            if longest > self.longest_side:
                scale = self.longest_side / longest
                img = img.resize(
                    (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        return img

    def predict(self, image: Any) -> StructuredDoc:
        import numpy as np

        img = self._prepare(image)
        with track() as timing:
            result = self._reader.readtext(np.array(img))
            lines: list[str] = []
            boxes: list[dict] = []
            for box, text, _conf in result:
                text = (text or "").strip()
                if not text:
                    continue
                lines.append(text)
                # EasyOCR returns np.int32 coords — cast to float so the row is JSON-serializable.
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                boxes.append({
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "type": "line",  # EasyOCR's readtext groups words into text-line regions
                    "text": text,
                })
        t = timing[0]
        return StructuredDoc(
            markdown="\n".join(lines),
            layout_boxes=boxes or None,
            telemetry=Telemetry(latency_s=t.latency_s, backend="easyocr",
                                 peak_vram_mb=t.peak_vram_mb),
        )

    def fingerprint(self) -> dict:
        return {"key": self.key, "backend": "easyocr", "engine": "easyocr",
                "engine_version": getattr(self, "_version", "n/a"), "lang": self.lang,
                "device": getattr(self, "device", "n/a"), "revision": "n/a"}
