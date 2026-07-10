"""docTR adapter — Mindee's modern classic OCR engine (PyTorch). Apache-2.0.

Second wave of WS1 CPU-capable OCR engines (see `tesseract.py` for the template this
follows: downscale-before-OCR, `load()`/`predict()`/`fingerprint()`, no `build_messages`).
Subclasses `LocalModelAdapter` (not `ModelAdapter` directly, unlike Tesseract/RapidOCR)
because docTR runs on torch and has real GPU state — `LocalModelAdapter.unload()` calls
`free_gpu()` for us.

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

_DEVICE_MAP = {"cpu": "cpu", "gpu": "cuda"}


@register_model("doctr")
class DocTRAdapter(LocalModelAdapter):
    """docTR two-stage OCR (text detection + recognition), pretrained weights."""

    # Same rationale as Tesseract's cap: full-res merged_forms pages (~145 MP) make
    # even the numpy conversion/preprocessing before docTR's own internal resize slow
    # enough to hang. Configurable via the models.yaml entry (`longest_side`).
    longest_side = 2600
    det_arch = "fast_base"
    reco_arch = "crnn_vgg16_bn"

    def load(self) -> None:
        import doctr
        from doctr.models import ocr_predictor

        self.longest_side = int(self.entry.get("longest_side") or self.longest_side)
        self.device = self.entry.get("device", "cpu")
        torch_device = _DEVICE_MAP.get(self.device)
        if torch_device is None:
            raise RuntimeError(f"doctr: unknown device '{self.device}' (expected cpu|gpu)")
        if torch_device == "cuda":
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("doctr: device='gpu' requested but torch.cuda.is_available() "
                                    "is False on this box")
        self.det_arch = self.entry.get("det_arch", self.det_arch)
        self.reco_arch = self.entry.get("reco_arch", self.reco_arch)
        self._predictor = ocr_predictor(
            det_arch=self.det_arch, reco_arch=self.reco_arch, pretrained=True,
        ).to(torch_device)
        self._version = getattr(doctr, "__version__", "n/a")

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
        arr = np.array(img)
        with track() as timing:
            result = self._predictor([arr])
            doc = result.export()
        t = timing[0]

        page = doc["pages"][0]
        h, w = page["dimensions"]
        lines: list[str] = []
        boxes: list[dict] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [wd["value"] for wd in line.get("words", []) if wd.get("value")]
                if words:
                    lines.append(" ".join(words))
                for wd in line.get("words", []):
                    text = (wd.get("value") or "").strip()
                    if not text:
                        continue
                    (x0, y0), (x1, y1) = wd["geometry"]
                    # geometry is normalized np.float64 — cast to plain float (JSON-serializable).
                    boxes.append({
                        "bbox": [float(x0 * w), float(y0 * h), float(x1 * w), float(y1 * h)],
                        "type": "word",
                        "text": text,
                    })
            lines.append("")  # blank line between blocks
        markdown = "\n".join(lines).strip("\n")
        return StructuredDoc(
            markdown=markdown,
            layout_boxes=boxes or None,
            telemetry=Telemetry(latency_s=t.latency_s, backend="doctr",
                                 peak_vram_mb=t.peak_vram_mb),
        )

    def fingerprint(self) -> dict:
        return {"key": self.key, "backend": "doctr", "engine": "doctr",
                "engine_version": getattr(self, "_version", "n/a"),
                "det_arch": self.det_arch, "reco_arch": self.reco_arch,
                "device": getattr(self, "device", "n/a"), "revision": "n/a"}
