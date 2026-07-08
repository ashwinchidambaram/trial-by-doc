"""Qwen2.5-VL-7B-Instruct adapter (vLLM). General VLM with an explicit OCR->markdown prompt.

No trust_remote_code (native vLLM arch). Verified recipe 2026-06-11.
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter


@register_model("qwen25vl")
class Qwen25VLAdapter(VLLMModelAdapter):
    prompt = (
        "Convert this document page to clean GitHub-flavored Markdown. Transcribe all text in "
        "natural reading order. Render tables as Markdown tables, math as LaTeX ($...$ / $$...$$), "
        "and preserve headings and lists. Output only the Markdown, no commentary."
    )
    longest_side = 1540  # cap token blow-up on dense pages
