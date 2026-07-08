"""Google Gemini vision as an OCR baseline (google-genai SDK).

Normalization owned by this adapter: page -> PNG bytes -> DEFAULT_OCR_PROMPT ->
markdown, fences stripped. temperature=0. Token-based pricing from configs
(verified 2026-07-07); usage_metadata supplies real token counts per call.

NOTE: validated by `gauntlet validate-adapter gemini_flash_lite` (paid cents)
before any scored run.
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.ratelimit import RetryableError
from tbdoc.models.api._vision_chat import VisionChatAdapter, encode_png_b64


class GeminiVisionAdapter(VisionChatAdapter):

    def _client(self) -> Any:
        import os

        from google import genai
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _call_api(self, image: Any) -> Any:
        import base64

        from google.genai import errors, types
        png = base64.b64decode(encode_png_b64(image, self.longest_side))
        try:
            return self.client.models.generate_content(
                model=self.entry["api_model_id"],
                contents=[types.Part.from_bytes(data=png, mime_type="image/png"),
                          self.prompt],
                config=types.GenerateContentConfig(temperature=0,
                                                   max_output_tokens=self.max_tokens))
        except errors.APIError as e:
            if e.code in (429, 500, 502, 503, 504):
                raise RetryableError(str(e)) from e
            raise

    def _response_text(self, raw: Any) -> str:
        return getattr(raw, "text", "") or ""

    def _api_version(self, raw: Any) -> str | None:
        return getattr(raw, "model_version", None)

    def _token_usage(self, raw: Any):
        u = getattr(raw, "usage_metadata", None)
        return (getattr(u, "prompt_token_count", None),
                getattr(u, "candidates_token_count", None))
