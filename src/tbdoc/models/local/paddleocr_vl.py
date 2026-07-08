"""PaddleOCR-VL adapter (vLLM, trust_remote_code).

IMPORTANT LIMITATION (verified 2026-06-11): the PaddleOCR-VL *VLM* only does element-level recognition;
full-page layout + reading order require the separate PP-DocLayoutV2 detector (heavy Paddle dep, Blackwell-
risky), which we do NOT wire. For smoke we send the "OCR:" prompt on the whole page to get text output —
this WON'T have layout boxes and under-represents the model's true page-parse ability. Flagged for the
full run (either adopt the paddle pipeline or pair with our own layout detector).
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._vllm_base import VLLMModelAdapter


@register_model("paddleocr_vl")
class PaddleOCRVLAdapter(VLLMModelAdapter):
    prompt = "OCR:"
    trust_remote_code = True
    longest_side = 1540
    # S11 #2: paddle degenerates into repetition loops on ~53% of pages (88% of realdoc) — running to
    # max_tokens with one line repeated ≥50×. The class default repetition_penalty=1.05 is too weak to
    # break them. Bumped PADDLE-ONLY so teacher candidates (olmocr2/qwen) stay on 1.05 and byte-comparable.
    # Verified on a known-degenerate page in the S11 smoke; escalate to no_repeat_ngram_size if insufficient.
    repetition_penalty = 1.2
