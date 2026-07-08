"""dots.ocr adapter (vLLM, trust_remote_code). Emits a single JSON array of layout elements.

Verified recipe 2026-06-11 (prompt_layout_all_en). NOTE: dots.ocr's vLLM path historically needed a
plugin registration step; on vLLM 0.22.1 trust_remote_code may or may not auto-register — if load
fails, the matrix records the error (no silent gap) and we revisit.
"""
from __future__ import annotations

import json
import re

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter

DOTS_PROMPT = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object."""


@register_model("dots_ocr")
class DotsOCRAdapter(VLLMModelAdapter):
    prompt = DOTS_PROMPT
    trust_remote_code = True
    max_tokens = 16000  # dense pages need headroom
    # dots.ocr is Qwen2-VL-based (32k ctx). The base's 8192 (a deepseek/lighton floor) is too small here:
    # large DocVQA images tokenize to >8192 vision tokens AND output is up to 16000 -> widen the window.
    max_model_len = 32768

    def parse_output(self, text: str) -> dict:
        s = text.strip()
        s = re.sub(r"^```(?:json)?", "", s).strip()
        s = re.sub(r"```$", "", s).strip()
        try:
            arr = json.loads(s)
            assert isinstance(arr, list)
        except Exception:
            return {"markdown": text, "raw": {"parse_error": "non-JSON output"}}
        md, boxes, tables, formulas = [], [], [], []
        for el in arr:
            if not isinstance(el, dict):
                continue
            cat, txt = el.get("category"), el.get("text")
            boxes.append({"bbox": el.get("bbox"), "type": cat, "text": txt})
            if cat == "Picture":
                continue
            if cat == "Table" and txt:
                tables.append(txt)
            elif cat == "Formula" and txt:
                formulas.append(txt)
            if txt:
                md.append(txt)
        return {
            "markdown": "\n\n".join(md),
            "layout_boxes": boxes or None,
            "tables_html": tables or None,
            "formulas_latex": formulas or None,
        }
