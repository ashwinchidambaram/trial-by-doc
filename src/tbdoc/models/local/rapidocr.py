"""RapidOCR adapter — modern classic OCR engine (ONNXRuntime, no torch). Apache-2.0.

Second wave of WS1 CPU-capable OCR engines (Tesseract was the first — see
`tesseract.py`, this file's template). Subclasses `ModelAdapter` directly, not
`LocalModelAdapter` — RapidOCR runs on onnxruntime, not torch, so there is no GPU
state to tear down and no HF repo/revision to pin (see `fingerprint()`).

CPU-only by design: onnxruntime-gpu was checked 2026-07-09 — `onnxruntime.get_available_
providers()` on this box returns only `CPUExecutionProvider`/`AzureExecutionProvider`, and
onnxruntime-gpu's prebuilt wheels target CUDA 11/12 runtimes, not this box's cu130/sm_120
(Blackwell) stack — GPU support would need a source build. Per the "never fight a GPU wheel
mismatch" guidance, this adapter stays CPU-only; `device: gpu` raises loudly at load()
rather than silently running on CPU anyway.
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.model_adapter import ModelAdapter
from tbdoc.core.registry import register_model
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track


@register_model("rapidocr")
class RapidOCRAdapter(ModelAdapter):
    """RapidOCR (PP-OCR-derived detector+recognizer exported to ONNX). CPU-only."""

    # Same rationale as Tesseract's cap: CPU/classic OCR chokes (multi-minute hangs)
    # on full-resolution scans (merged_forms has ~145 MP pages). Configurable via the
    # models.yaml entry (`longest_side`).
    longest_side = 2600

    def load(self) -> None:
        import importlib.metadata as im

        from rapidocr_onnxruntime import RapidOCR

        self.longest_side = int(self.entry.get("longest_side") or self.longest_side)
        self.device = self.entry.get("device", "cpu")
        if self.device != "cpu":
            raise RuntimeError(
                "rapidocr: device='gpu' requested but this adapter is CPU-only — "
                "onnxruntime-gpu (checked 2026-07-09) has no prebuilt wheel for this "
                "box's cu130/sm_120 (Blackwell) stack. Set configs/models.yaml "
                "rapidocr.device to 'cpu'.")
        self._engine = RapidOCR()
        self._version = im.version("rapidocr-onnxruntime")

    def _prepare(self, image: Any) -> Any:
        """Open + downscale the page so RapidOCR doesn't choke on oversized scans."""
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
            result, _elapse = self._engine(np.array(img))
            lines: list[str] = []
            boxes: list[dict] = []
            for box, text, score in result or []:
                text = (text or "").strip()
                if not text:
                    continue
                lines.append(text)
                # Cast to plain float so the row is always JSON-serializable (numpy scalars are not).
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                boxes.append({
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "type": "line",  # RapidOCR's detector groups words into text-line regions
                    "text": text,
                })
        t = timing[0]
        return StructuredDoc(
            markdown="\n".join(lines),
            layout_boxes=boxes or None,
            telemetry=Telemetry(latency_s=t.latency_s, backend="rapidocr"),
        )

    def fingerprint(self) -> dict:
        return {"key": self.key, "backend": "rapidocr", "engine": "rapidocr-onnxruntime",
                "engine_version": getattr(self, "_version", "n/a"), "revision": "n/a"}
