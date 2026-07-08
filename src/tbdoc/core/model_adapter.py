"""ModelAdapter — the single contract every model implements.

Hierarchy:
  ModelAdapter (ABC)          load / predict(image) -> StructuredDoc / unload / fingerprint
  ├── LocalModelAdapter       GPU lifecycle (free_gpu on unload); torch stays optional
  │     ├── VLLMModelAdapter        (models/local/_vllm_base.py)
  │     └── TransformersModelAdapter(models/local/_transformers_base.py)
  └── APIModelAdapter         rate-limit -> retry/backoff -> cost+telemetry stamping
        └── VisionChatAdapter       prompt-based image->markdown chat APIs

BYO model = subclass one of these + one configs/models.yaml entry.
"""
from __future__ import annotations

import gc
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tbdoc.core.structured_doc import Segmentation, StructuredDoc


def free_gpu() -> None:
    """Best-effort full GPU teardown between models (avoids OOM accumulation)."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


class ModelAdapter(ABC):
    """Load -> predict(page)/segment(pages) -> unload."""

    #: what this model can do; scoreboard + Tier C dispatch read this
    capabilities: frozenset[str] = frozenset({"page_markdown"})  # +"layout" +"segmentation"

    def __init__(self, key: str, entry: dict[str, Any] | None = None):
        self.key = key
        self.entry = entry or {}
        self.backend: str | None = self.entry.get("backend")
        self.revision: str | None = self.entry.get("revision")
        self._loaded = False

    @abstractmethod
    def load(self) -> None:
        """Acquire resources (GPU weights / API client). Idempotent-cheap for APIs."""

    @abstractmethod
    def predict(self, image: Any) -> "StructuredDoc":
        """Parse one page image into a StructuredDoc (with telemetry populated)."""

    def predict_document(self, pages: list[Any]) -> list["StructuredDoc"]:
        """Parse a multi-page document. Default: page-by-page."""
        return [self.predict(p) for p in pages]

    def segment(self, pages: list[Any], boundary_judge: Any | None = None) -> "Segmentation":
        """Tier C: partition a multi-page stream into logical documents.

        Default composition: predict() each page, then ask the frozen boundary_judge
        instrument "same document or new?" per consecutive pair. Models with a native
        splitter override this and declare "segmentation" in `capabilities`.
        """
        from tbdoc.core.structured_doc import Segmentation
        if boundary_judge is None:
            raise RuntimeError(
                f"{self.key} has no native segmentation and no boundary_judge instrument "
                "was provided (run without --no-llm-instruments, or use a native segmenter)")
        docs = self.predict_document(pages)
        boundaries = boundary_judge.boundaries([d.markdown for d in docs])
        return Segmentation(boundaries=boundaries, method="judge_composed",
                            raw={"judge": boundary_judge.identity()})

    def fingerprint(self) -> dict[str, Any]:
        """What to stamp on every result row (provenance)."""
        return {"key": self.key, "repo_id": self.entry.get("repo_id"),
                "revision": self.revision, "backend": self.backend}

    def unload(self) -> None:
        """Release resources. Subclasses drop handles then call super().unload()."""
        self._loaded = False

    # context-manager sugar so the runner can do `with adapter: ...`
    def __enter__(self) -> "ModelAdapter":
        if not self._loaded:
            self.load()
            self._loaded = True
        return self

    def __exit__(self, *exc) -> None:
        self.unload()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.key} backend={self.backend}>"


class LocalModelAdapter(ModelAdapter):
    """GPU-hosted open-weights model; frees the GPU on unload."""

    def unload(self) -> None:
        super().unload()
        free_gpu()


class APIModelAdapter(ModelAdapter):
    """API-backed model. predict() wraps subclass hooks with rate limiting,
    retry/backoff, and cost/telemetry stamping. No torch import anywhere.

    Subclass hooks:
      _client() -> Any                       construct the SDK client (called by load)
      _call_api(image) -> Any                one API call; raise RetryableError on 429/5xx
      _parse_response(raw) -> dict           StructuredDoc fields (markdown, layout_boxes, ...)
      _api_version(raw) -> str | None        exact model/version string the API resolved to
    """

    def __init__(self, key: str, entry: dict[str, Any] | None = None):
        super().__init__(key, entry)
        self.backend = "api"
        from tbdoc.core.ratelimit import TokenBucket
        rl = self.entry.get("rate_limit") or {}
        self._bucket = TokenBucket(rps=rl.get("rps", 1.0), burst=rl.get("burst", 1))
        self._retry = self.entry.get("retry") or {}

    def load(self) -> None:
        from tbdoc.core.secrets import require_secrets
        require_secrets(self.entry.get("secrets", []), context=self.key)
        self.client = self._client()

    def unload(self) -> None:
        if hasattr(self, "client"):
            try:
                close = getattr(self.client, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass
            del self.client
        super().unload()

    def cost_per_page(self) -> float | None:
        pricing = self.entry.get("pricing") or {}
        return pricing.get("per_page_usd")

    def fingerprint(self) -> dict[str, Any]:
        from datetime import date
        return {"key": self.key, "provider": self.entry.get("provider"),
                "api_model_id": self.entry.get("api_model_id"),
                "api_version": self.entry.get("api_version"),
                "called_on": date.today().isoformat(), "backend": "api"}

    def predict(self, image: Any) -> "StructuredDoc":
        from tbdoc.core.ratelimit import with_backoff
        from tbdoc.core.structured_doc import StructuredDoc, Telemetry
        waited = self._bucket.acquire()
        t0 = time.monotonic()
        raw, retries = with_backoff(
            lambda: self._call_api(image),
            max_attempts=self._retry.get("max_attempts", 5),
            base_s=self._retry.get("base_s", 1.0))
        latency = time.monotonic() - t0
        parsed = self._parse_response(raw)
        in_tok, out_tok = self._token_usage(raw)
        tel = Telemetry(
            latency_s=round(latency, 3), backend="api",
            input_tokens=in_tok, output_tokens=out_tok,
            tokens_per_s=round(out_tok / latency, 2) if (out_tok and latency) else None,
            cost_usd=self._cost(in_tok, out_tok),
            api_provider=self.entry.get("provider"),
            api_model_version=self._api_version(raw) or self.entry.get("api_model_id"),
            api_request_id=self._request_id(raw),
            retries=retries, rate_limit_waits_s=round(waited, 3) or None)
        return StructuredDoc(
            markdown=parsed.get("markdown", ""), layout_boxes=parsed.get("layout_boxes"),
            tables_html=parsed.get("tables_html"), formulas_latex=parsed.get("formulas_latex"),
            raw=parsed.get("raw", {}), telemetry=tel)

    # ---- hooks --------------------------------------------------------------
    @abstractmethod
    def _client(self) -> Any: ...

    @abstractmethod
    def _call_api(self, image: Any) -> Any: ...

    @abstractmethod
    def _parse_response(self, raw: Any) -> dict: ...

    def _api_version(self, raw: Any) -> str | None:
        return None

    def _request_id(self, raw: Any) -> str | None:
        return None

    def _token_usage(self, raw: Any) -> tuple[int | None, int | None]:
        return None, None

    def _cost(self, in_tok: int | None, out_tok: int | None) -> float | None:
        """Per-page price if declared; else token pricing if declared; else None."""
        pricing = self.entry.get("pricing") or {}
        if "per_page_usd" in pricing:
            return pricing["per_page_usd"]
        if in_tok is not None and out_tok is not None and "per_mtok_in_usd" in pricing:
            return round(in_tok * pricing["per_mtok_in_usd"] / 1e6
                         + out_tok * pricing.get("per_mtok_out_usd", 0) / 1e6, 6)
        return None
