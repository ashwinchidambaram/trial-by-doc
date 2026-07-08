"""OpenAI GPT vision as an OCR baseline (deferred from v1 scored runs).

Normalization owned by this adapter: page -> PNG data-URL -> DEFAULT_OCR_PROMPT ->
markdown, fences stripped. temperature=0.
"""
from __future__ import annotations

from typing import Any

from tbdoc.core.ratelimit import RetryableError
from tbdoc.models.api._vision_chat import VisionChatAdapter, encode_png_b64


class OpenAIVisionAdapter(VisionChatAdapter):

    def _client(self) -> Any:
        from openai import OpenAI
        return OpenAI()

    def _call_api(self, image: Any) -> Any:
        import openai
        b64 = encode_png_b64(image, self.longest_side)
        try:
            return self.client.chat.completions.create(
                model=self.entry["api_model_id"],
                temperature=0,
                max_completion_tokens=self.max_tokens,
                messages=[{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": self.prompt},
                ]}])
        except openai.RateLimitError as e:
            raise RetryableError(str(e)) from e
        except openai.APIStatusError as e:
            if e.status_code >= 500:
                raise RetryableError(str(e)) from e
            raise
        except openai.APITimeoutError as e:
            raise RetryableError(str(e)) from e

    def _response_text(self, raw: Any) -> str:
        return (raw.choices[0].message.content or "") if raw.choices else ""

    def _api_version(self, raw: Any) -> str | None:
        return getattr(raw, "model", None)

    def _request_id(self, raw: Any) -> str | None:
        return getattr(raw, "id", None)

    def _token_usage(self, raw: Any):
        u = getattr(raw, "usage", None)
        return (getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None))
