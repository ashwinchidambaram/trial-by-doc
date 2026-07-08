"""LightOnOCR-1B adapter (vLLM). IMAGE-ONLY: the OCR instruction is baked in — send no text prompt.

Verified recipe 2026-06-11. longest-side 1540px. Output is markdown directly.
(Card recommends temp 0.2; we use temp 0 for deterministic baseline.)
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter


@register_model("lightonocr")
class LightOnOCRAdapter(VLLMModelAdapter):
    longest_side = 1540

    def build_messages(self, data_url: str) -> list[dict]:
        # image only — no text turn (adding a prompt degrades it)
        return [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}]
