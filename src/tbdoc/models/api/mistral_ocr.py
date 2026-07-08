"""Mistral OCR API — purpose-built document OCR; returns markdown natively.

Normalization owned by this adapter: page image -> PNG data-URL -> OCR endpoint ->
per-page markdown taken verbatim from the response (no prompt — dedicated OCR model).
Pricing: flat per page (configs). The API resolves `mistral-ocr-latest` to a dated
version — stamped per call via _api_version.

NOTE: written against the mistralai SDK docs (2026-07); exact response shape gets
validated by `gauntlet validate-adapter mistral_ocr` (2-3 paid calls) before any run.
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.model_adapter import APIModelAdapter
from tbdoc.core.ratelimit import RetryableError
from tbdoc.models.api._vision_chat import encode_png_b64


class MistralOCRAdapter(APIModelAdapter):
    longest_side: int | None = None   # dedicated OCR API handles resolution itself

    def _client(self) -> Any:
        import os

        from mistralai import Mistral
        return Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    def _call_api(self, image: Any) -> Any:
        b64 = encode_png_b64(image, self.longest_side)
        try:
            return self.client.ocr.process(
                model=self.entry["api_model_id"],
                document={"type": "image_url",
                          "image_url": f"data:image/png;base64,{b64}"})
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status in (429,) or (status is not None and status >= 500):
                raise RetryableError(str(e)) from e
            raise

    def _parse_response(self, raw: Any) -> dict:
        pages = getattr(raw, "pages", None) or []
        md = "\n\n".join(getattr(p, "markdown", "") or "" for p in pages)
        return {"markdown": md}

    def _api_version(self, raw: Any) -> str | None:
        return getattr(raw, "model", None)
