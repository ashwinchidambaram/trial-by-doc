"""BenchAdapter — the single contract every benchmark implements.

`load()` yields `Sample`s; `evaluate()`/`evaluate_batch()` wraps the benchmark's
OFFICIAL scorer for official benchmarks (never reimplemented) or our validated
custom scorer (VALIDATION.md required, enforced by the registry).

Tiers: A = parse fidelity, B = downstream extraction (needs the frozen extractor),
C = segmentation (unit="document"; runner calls model.segment(), not predict()),
D = robustness (Tier-B extraction under deterministic scan/fax degradation — a
stress axis over B, not a fourth orthogonal capability; same extractor contract).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class Sample:
    """One gradable unit: a page (unit='page') or a multi-page stream (unit='document')."""
    id: str
    gold: Any                       # benchmark-native ground truth
    pages: list[Any] = field(default_factory=list)  # PIL.Image | path; len 1 for page-unit
    category: str | None = None     # doc type for per-category breakdowns
    question: str | None = None     # Tier-B QA
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def image(self) -> Any:         # back-compat convenience for page-unit benches
        return self.pages[0] if self.pages else None


class BenchAdapter(ABC):
    """A benchmark: a stream of samples + a scorer-backed evaluate()."""

    tier: str = "A"                          # "A" | "B" | "C" | "D"
    unit: str = "page"                       # "page" | "document"
    provenance: str = "official"             # "official" | "custom"
    validation_doc: str | None = None        # REQUIRED for custom (registry enforces)
    requires_extractor: bool = False         # Tier-B: markdown -> answer instrument
    requires_boundary_judge: bool = False    # Tier-C composed path

    def __init__(self, key: str, data_dir: str | None = None, entry: dict | None = None):
        self.key = key
        self.data_dir = data_dir
        self.entry = entry or {}

    @abstractmethod
    def load(self) -> Iterable[Sample]:
        """Yield Samples."""

    @abstractmethod
    def evaluate(self, sample: Sample, prediction: Any,
                 extractor: Any | None = None) -> dict[str, Any]:
        """Score one prediction (StructuredDoc / list[StructuredDoc] / Segmentation).

        Returns metrics dict with a "primary" float (headline metric) plus components.
        May include "category" to override sample.category.
        """

    def evaluate_batch(self, samples: list[Sample], predictions: list[Any],
                       extractor: Any | None = None) -> dict[str, dict[str, Any]]:
        """Score a whole (model, bench) cell; returns {sample_id: metrics}.

        Default loops evaluate() with PER-SAMPLE fault isolation: one raising sample
        (e.g. a transient reader/API failure that survived its own retries) becomes one
        error-marked row instead of aborting the whole cell — same {"primary": None,
        "error": ...} marker convention the subprocess-scored benches use.
        Container/venv-scored benches override to score in ONE subprocess/container
        run (see scoring/container_scorer.py).
        """
        out: dict[str, dict[str, Any]] = {}
        for s, p in zip(samples, predictions):
            try:
                out[s.id] = self.evaluate(s, p, extractor=extractor)
            except Exception as e:
                out[s.id] = {"primary": None, "error": f"scorer: {type(e).__name__}: {e}"}
        return out

    def categories(self) -> list[str] | None:
        """Doc-type categories this benchmark distinguishes (per-category breakdowns)."""
        return None

    def fingerprint(self) -> dict[str, Any]:
        """Provenance stamped on the scoreboard."""
        src = self.entry.get("source") or {}
        return {"key": self.key, "tier": self.tier, "unit": self.unit,
                "provenance": self.provenance, "revision": src.get("revision"),
                "license": src.get("license"),
                "scorer": (self.entry.get("scorer") or {}).get("kind", "native")}

    def __repr__(self) -> str:
        return f"<BenchAdapter {self.key} tier={self.tier} {self.provenance}>"
