"""olmOCR-2-7B adapter (teacher base). vLLM, Qwen2.5-VL backbone.

Prompt verified verbatim from the olmocr repo (`build_no_anchoring_v4_yaml_prompt`,
allenai/olmocr) on 2026-06-11 — NOT reconstructed from memory. Image at longest-side 1288px
per the model card. Output = YAML front matter + markdown; we split the front matter into `raw`.
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter

# Verbatim from olmocr/prompts/prompts.py :: build_no_anchoring_v4_yaml_prompt
OLMOCR2_PROMPT = (
    "Attached is one page of a document that you must process. Just return the plain text "
    "representation of this document as if you were reading it naturally. Convert equations to "
    "LateX and tables to HTML.\n"
    "If there are any figures or charts, label them with the following markdown syntax "
    "![Alt text describing the contents of the figure](page_startx_starty_width_height.png)\n"
    "Return your output as markdown, with a front matter section on top specifying values for the "
    "primary_language, is_rotation_valid, rotation_correction, is_table, and is_diagram parameters."
)


@register_model("olmocr2")
class OlmOCR2Adapter(VLLMModelAdapter):
    prompt = OLMOCR2_PROMPT
    longest_side = 1288

    def parse_output(self, text: str) -> dict:
        s = text.lstrip()
        if s.startswith("---"):
            parts = s.split("---", 2)
            if len(parts) >= 3:
                return {"markdown": parts[2].lstrip("\n"), "raw": {"front_matter": parts[1].strip()}}
        return {"markdown": text}
