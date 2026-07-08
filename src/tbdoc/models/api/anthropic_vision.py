"""Anthropic Claude vision as an OCR baseline.

Normalization owned by this adapter (part of the measured system): page ->
PNG b64 (longest side capped) -> DEFAULT_OCR_PROMPT -> markdown, fences stripped.
temperature=0. Pricing from configs (per-Mtok, verified 2026-07-07).
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.ratelimit import RetryableError
from tbdoc.models.api._vision_chat import VisionChatAdapter, encode_png_b64


class AnthropicVisionAdapter(VisionChatAdapter):

    def _client(self) -> Any:
        import anthropic
        return anthropic.Anthropic()

    def _call_api(self, image: Any) -> Any:
        import anthropic
        b64 = encode_png_b64(image, self.longest_side)
        try:
            return self.client.messages.create(
                model=self.entry["api_model_id"],
                max_tokens=self.max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": self.prompt},
                ]}])
        except anthropic.RateLimitError as e:
            raise RetryableError(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise RetryableError(str(e)) from e
            raise
        except anthropic.APITimeoutError as e:
            raise RetryableError(str(e)) from e

    def _response_text(self, raw: Any) -> str:
        return "".join(b.text for b in raw.content if getattr(b, "type", "") == "text")

    def _api_version(self, raw: Any) -> str | None:
        return getattr(raw, "model", None)

    def _request_id(self, raw: Any) -> str | None:
        return getattr(raw, "id", None)

    def _token_usage(self, raw: Any):
        u = getattr(raw, "usage", None)
        return (getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
