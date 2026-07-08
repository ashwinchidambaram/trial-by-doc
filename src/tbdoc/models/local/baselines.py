"""Trivial Tier-C baselines — scoreboard FLOOR rows (no GPU, no API, no LLM).

The PSS literature warns that degenerate strategies score deceptively well on
boundary F1 (OpenPSS: 'every page a doc' hits F1 0.77 on singleton-heavy data).
Publishing these rows makes the floor visible: a real model must beat all three.

- every_page_boundary: predicts a new document at every page.
- no_boundary: predicts one single document.
- pixel_diff: boundary where consecutive pages differ most (mean abs pixel delta
  above the stream's own mean + 1 std). Also the seam-artifact canary: if THIS
  beats content-based models on merged_forms, the merge seams leak (VALIDATION.md).
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.model_adapter import ModelAdapter
from tbdoc.core.structured_doc import Segmentation, StructuredDoc, Telemetry


class _BaselineAdapter(ModelAdapter):
    capabilities = frozenset({"segmentation"})

    def load(self) -> None:
        pass

    def predict(self, image: Any) -> StructuredDoc:
        return StructuredDoc(markdown="", telemetry=Telemetry(latency_s=0.0, backend="baseline"))

    def fingerprint(self) -> dict:
        return {"key": self.key, "backend": "baseline", "revision": "n/a"}


class EveryPageBoundary(_BaselineAdapter):
    def segment(self, pages: list[Any], boundary_judge: Any | None = None) -> Segmentation:
        return Segmentation(boundaries=list(range(1, len(pages))), method="native",
                            telemetry=Telemetry(latency_s=0.0, backend="baseline"))


class NoBoundary(_BaselineAdapter):
    def segment(self, pages: list[Any], boundary_judge: Any | None = None) -> Segmentation:
        return Segmentation(boundaries=[], method="native",
                            telemetry=Telemetry(latency_s=0.0, backend="baseline"))


class PixelDiff(_BaselineAdapter):
    def segment(self, pages: list[Any], boundary_judge: Any | None = None) -> Segmentation:
        import numpy as np
        from PIL import Image
        arrs = []
        for p in pages:
            img = p if isinstance(p, Image.Image) else Image.open(p)
            arrs.append(np.asarray(img.convert("L").resize((128, 160)), dtype=float))
        diffs = [float(abs(arrs[i] - arrs[i - 1]).mean()) for i in range(1, len(arrs))]
        if not diffs:
            return Segmentation(boundaries=[], method="native")
        mean = sum(diffs) / len(diffs)
        std = (sum((d - mean) ** 2 for d in diffs) / len(diffs)) ** 0.5
        thresh = mean + std
        return Segmentation(boundaries=[i + 1 for i, d in enumerate(diffs) if d > thresh],
                            method="native",
                            telemetry=Telemetry(latency_s=0.0, backend="baseline"),
                            raw={"diffs": [round(d, 2) for d in diffs], "thresh": round(thresh, 2)})
