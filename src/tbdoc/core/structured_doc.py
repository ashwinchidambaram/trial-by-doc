"""The narrow data contracts every model adapter returns.

`StructuredDoc` is what a model emits for ONE page: the markdown parse plus any
structural extras (layout boxes, tables, formulas) and per-page `Telemetry`.
`Segmentation` is what `ModelAdapter.segment(pages)` emits for ONE multi-page
document in Tier C: the predicted partition into logical documents.

Telemetry convention: None = honestly unavailable from this backend (GPU fields are
None for API models; cost fields are None for local models).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Telemetry:
    """Per-call signals collected alongside generation."""
    latency_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_s: float | None = None
    mean_logprob: float | None = None      # mean log-prob of chosen tokens (confidence)
    min_logprob: float | None = None       # worst chosen-token log-prob
    mean_entropy: float | None = None      # mean per-token entropy over available top-k
    peak_vram_mb: float | None = None
    backend: str | None = None             # "vllm" | "transformers" | "api"
    # ---- API-backed models only ----
    cost_usd: float | None = None          # this call, from registry pricing
    api_provider: str | None = None
    api_model_version: str | None = None   # exact version string the API resolved to
    api_request_id: str | None = None
    retries: int | None = None
    rate_limit_waits_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredDoc:
    """One model's structured parse of one page image."""
    markdown: str
    layout_boxes: list[dict] | None = None   # [{"bbox": [x0,y0,x1,y1], "type": str, "text": str?}]
    tables_html: list[str] | None = None
    formulas_latex: list[str] | None = None
    telemetry: Telemetry = field(default_factory=Telemetry)
    raw: dict[str, Any] = field(default_factory=dict)  # model-specific extras (YAML meta, DocTags, ...)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["telemetry"] = self.telemetry.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StructuredDoc":
        tel = Telemetry(**(d.get("telemetry") or {}))
        return cls(markdown=d.get("markdown", ""), layout_boxes=d.get("layout_boxes"),
                   tables_html=d.get("tables_html"), formulas_latex=d.get("formulas_latex"),
                   telemetry=tel, raw=d.get("raw") or {})

    @property
    def has_layout(self) -> bool:
        return bool(self.layout_boxes)

    @property
    def has_tables(self) -> bool:
        return bool(self.tables_html)


@dataclass
class Segmentation:
    """One model's predicted partition of a multi-page document stream (Tier C).

    `boundaries` = 0-based page indices where a NEW logical document starts.
    Page 0 is always an implicit boundary and need not be listed.
    `method` = "native" (model has its own splitter) | "judge_composed"
    (per-page parse -> frozen boundary_judge instrument).
    """
    boundaries: list[int]
    method: str = "native"
    telemetry: Telemetry = field(default_factory=Telemetry)
    raw: dict[str, Any] = field(default_factory=dict)

    def groups(self, n_pages: int) -> list[list[int]]:
        """Materialize the partition as page-index groups."""
        cuts = sorted({0, *[b for b in self.boundaries if 0 < b < n_pages]})
        cuts.append(n_pages)
        return [list(range(cuts[i], cuts[i + 1])) for i in range(len(cuts) - 1)]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["telemetry"] = self.telemetry.to_dict()
        return d
