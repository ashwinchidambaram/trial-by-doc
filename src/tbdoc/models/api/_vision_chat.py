"""VisionChatAdapter — base for prompt-based chat-vision APIs (Claude, GPT, Gemini).

The model is prompted to transcribe a page image to markdown. NOTE: the prompt and
our response cleanup are part of the measured system — keep them in the adapter
header and stable across runs.
"""
from __future__ import annotations

import base64
import io
from typing import Any

from tbdoc.core.model_adapter import APIModelAdapter

DEFAULT_OCR_PROMPT = (
    "Transcribe this document page to GitHub-flavored markdown. Preserve reading "
    "order, headings, lists, and tables (as markdown tables). Transcribe all visible "
    "text exactly; do not add commentary, descriptions, or code fences around the output."
)


def encode_png_b64(image: Any, longest_side: int | None = None) -> str:
    from PIL import Image
    img = image if isinstance(image, Image.Image) else Image.open(image)
    img = img.convert("RGB")
    if longest_side:
        w, h = img.size
        m = max(w, h)
        if m > longest_side:
            s = longest_side / m
            img = img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def strip_md_fence(text: str) -> str:
    """Models often wrap output in ```markdown fences despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1 and t.endswith("```"):
            t = t[first_nl + 1:-3].strip()
    return t


class VisionChatAdapter(APIModelAdapter):
    prompt: str = DEFAULT_OCR_PROMPT
    longest_side: int | None = 1540
    max_tokens: int = 4096

    def _parse_response(self, raw: Any) -> dict:
        return {"markdown": strip_md_fence(self._response_text(raw))}

    def _response_text(self, raw: Any) -> str:  # override per provider
        raise NotImplementedError
