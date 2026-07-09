"""Gemma-4-E4B-it adapter (vLLM). Google's multimodal Gemma 4 (text + image), a native vLLM
architecture (`Gemma4ForConditionalGeneration`, registered in vLLM 0.22.1; transformers 5.11
ships `gemma4`). Vision is confirmed by the model config's `vision_config` (`gemma4_vision`),
so no trust_remote_code is needed — we serve the HF weights straight through vLLM's chat API.

Verified live 2026-07-08 (HF model card + API): repo `google/gemma-4-E4B-it`
@ fee6332c1abaafb77f6f9624236c63aa2f1d0187, license apache-2.0 (commercial OK — note this is a
departure from prior Gemma custom terms), gated=false. Params: 4.5B effective (8B with embeddings).
Declared capabilities include OCR (multilingual), document/PDF parsing, handwriting, and charts.
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter


@register_model("gemma4")
class Gemma4Adapter(VLLMModelAdapter):
    prompt = (
        "Convert this document page to clean GitHub-flavored Markdown. Transcribe all text in "
        "natural reading order. Render tables as Markdown tables, math as LaTeX ($...$ / $$...$$), "
        "and preserve headings and lists. Output only the Markdown, no commentary."
    )
    longest_side = 1536  # cap token blow-up on dense pages (Gemma-4 vision is variable-resolution)
