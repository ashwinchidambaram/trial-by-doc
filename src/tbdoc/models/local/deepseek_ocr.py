"""DeepSeek-OCR adapter (vLLM). Grounding-markdown prompt; strips <|ref|>/<|det|> tags to markdown.

Verified recipe 2026-06-11. Needs skip_special_tokens=False to keep grounding tags. NOTE: the official
recipe also uses a custom NGram logits processor (anti-repetition) we don't wire for smoke — dense
tables may repeat; acceptable for smoke, revisit for the full run.
"""
from __future__ import annotations

import re

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter

_GROUND = re.compile(r"<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>", re.DOTALL)


@register_model("deepseek_ocr")
class DeepSeekOCRAdapter(VLLMModelAdapter):
    prompt = "<|grounding|>Convert the document to markdown. "
    trust_remote_code = True
    max_tokens = 8192
    skip_special_tokens = False  # keep grounding tags so we can parse them

    def parse_output(self, text: str) -> dict:
        boxes = []

        def repl(m):
            label, coords = m.group(1), m.group(2)
            boxes.append({"type": label, "bbox": coords})
            return label

        md = _GROUND.sub(repl, text).replace("<|grounding|>", "").strip()
        return {"markdown": md, "layout_boxes": boxes or None}
