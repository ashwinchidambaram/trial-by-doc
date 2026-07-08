"""GOT-OCR-2.0 adapter (transformers). format=True -> markdown/LaTeX. Verified recipe 2026-06-11.

Native HF port (no trust_remote_code). SDPA attention for sm_120. stop_strings needs the tokenizer.
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._transformers_base import TransformersModelAdapter


@register_model("got2")
class GotOcr2Adapter(TransformersModelAdapter):
    attn_implementation = "eager"  # GOT-OCR-2.0 doesn't support SDPA in transformers 5.11
    # S11 #7 (best-effort, MED): got2 emits immediate-EOS (1 token, empty markdown) on specific finance/
    # map images but is fine on olmocr_bench. Pre-resize to the card's recommended 1024px before the GOT
    # processor's own format=True crop/pad. May not fully fix (trigger is likely aspect-ratio/tiling) —
    # got2 isn't a teacher candidate, so we ship the one-liner and don't block the sweep on it.
    longest_side = 1024

    def build_inputs(self, image):
        return self.processor(image, return_tensors="pt", format=True).to("cuda")

    def gen_kwargs(self) -> dict:
        # GOT uses stop_strings, which requires the tokenizer be passed to generate()
        return {"tokenizer": self.processor.tokenizer, "stop_strings": "<|im_end|>"}

    def decode(self, gen_ids, image) -> dict:
        text = self.processor.decode(gen_ids, skip_special_tokens=True)
        return {"markdown": text}
