"""Kosmos-2.5 adapter (transformers, native — no trust_remote_code). Markdown-mode dense-document
OCR: task token "<md>" (the card also has a coordinate-heavy "<ocr>" mode; markdown is what our
scorers want, per the roster-expansion design doc). Card explicitly warns of hallucination risk on
some pages — that's a signal we measure, not something to work around.

Verified live 2026-07-09 (HF API + model card): repo microsoft/kosmos-2.5
@ ec3c8051b697166514a31d646cfa36d6ef4c93d7, license MIT (HF API tag `license:mit`), gated=false.
Params ~1.3B. Native transformers>=4.56 support (confirmed two ways: config.json has NO auto_map,
and this env's transformers 5.11 imports `Kosmos2_5ForConditionalGeneration` / resolves
`Kosmos2_5Processor` via AutoProcessor with no trust_remote_code). Uses a Pix2Struct-style
flattened-patch image representation: the processor returns extra scalar `height`/`width` fields
that are NOT model kwargs (must be popped before generate()), and `flattened_patches` is emitted
float32 and needs an explicit cast to the model's compute dtype (verified empirically: processor
output keys are flattened_patches/attention_mask/width/height/input_ids/image_embeds_position_mask).
It IS decoder-only (despite `is_decoder`/`is_encoder_decoder` both reading false in the raw
text_config JSON) — the card's own post-processing strips the echoed prompt from generate()'s
output, confirming the prompt is NOT excluded automatically.

Fits TransformersModelAdapter's build_inputs/decode hooks, but load() is overridden for the exact
model/processor classes and dtype handling the card specifies (rather than the base's generic
AutoModelForImageTextToText path).
"""
from __future__ import annotations

from tbdoc.core.registry import register_model
from tbdoc.models.local._transformers_base import TransformersModelAdapter

MD_PROMPT = "<md>"


@register_model("kosmos25")
class Kosmos25Adapter(TransformersModelAdapter):
    max_new_tokens = 2048
    longest_side = 2048  # cap huge merged_forms pages before the patch-flattening image processor

    def load(self) -> None:
        import torch
        from transformers import AutoProcessor, Kosmos2_5ForConditionalGeneration
        rev = self.revision if (self.revision and not str(self.revision).startswith("TBD")) else None
        repo = self.entry["repo_id"]
        self.processor = AutoProcessor.from_pretrained(repo, revision=rev)
        self.model = Kosmos2_5ForConditionalGeneration.from_pretrained(
            repo, revision=rev, dtype=torch.bfloat16, attn_implementation=self.attn_implementation,
        ).to("cuda").eval()

    def build_inputs(self, image):
        import torch
        inputs = self.processor(text=MD_PROMPT, images=image, return_tensors="pt")
        inputs.pop("height", None)  # scale-factor scalars, not model kwargs (only needed for <ocr> bbox mode)
        inputs.pop("width", None)
        inputs = {k: (v.to("cuda") if hasattr(v, "to") else v) for k, v in inputs.items()}
        inputs["flattened_patches"] = inputs["flattened_patches"].to(torch.bfloat16)
        return inputs

    def decode(self, gen_ids, image) -> dict:
        # base predict() already sliced gen_ids to just the newly-generated tokens (input_len:) —
        # no need to strip the "<md>" prompt echo the card's own post-process does for the unsliced case.
        text = self.processor.decode(gen_ids, skip_special_tokens=True).strip()
        return {"markdown": text}
