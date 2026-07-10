"""Phi-4-multimodal-instruct adapter (transformers, trust_remote_code). Chat-template VLM:
"<|user|><|image_1|>{prompt}<|end|><|assistant|>" — reuses this repo's standard markdown-OCR
instruction (same wording as gemma4.py). The custom modeling code auto-activates its baked-in
vision LoRA adapter from the presence of image inputs (`forward()` reads `input_mode` off the
processor output and calls `set_lora_adapter('vision')` internally — see modeling_phi4mm.py), so
no manual LoRA wiring is needed here; the plain generate() call is enough.

*** BLOCKED on transformers 5.11 (this box's pinned stack) — NOT REGISTERED in configs/models.yaml,
kept for provenance/revival (2026-07-09). TWO independent v5 incompatibilities in the pre-v5 remote
code: (1) FIXED here — config.json pins `_attn_implementation: flash_attention_2`, which v5 rejects
(`Phi4MMForCausalLM does not support Flash Attention 2 yet`); load() below forces
`config._attn_implementation="sdpa"` before construction (the Siglip vision tower only gates on
`== flash_attention_2` and ships eager+FA2 only, so this makes it use EAGER — no flash-attn install,
respecting the house rule). (2) UNFIXED (the blocker) — the AUDIO ConformerEncoder
(speech_conformer_encoder.py:1435, NemoConvSubsampling) calls `int(out_length)` on a tensor during
`__init__`, which raises `RuntimeError: Tensor.item() cannot be called on meta tensors` under v5's
meta-device init. `low_cpu_mem_usage=False` does NOT lift the meta context for this remote-code path.
The audio encoder is built unconditionally even for image-only use, so there's no clean skip; the only
workaround is monkeypatching the model's remote code, which we won't ship. Revive if Microsoft ports
Phi-4-multimodal to native transformers v5, or pin a v5-compatible revision. ***

Verified live 2026-07-09 (HF API + model card): repo microsoft/Phi-4-multimodal-instruct
@ 93f923e1a7727d1c4f446756212d9d3e8fcc5d81, license MIT (HF API tag `license:mit`), gated=false.
Params 5.6B (per card: OCRBench 84.4, DocVQA 93.2). AutoModelForCausalLM + AutoProcessor,
trust_remote_code=True (config.json auto_map -> Phi4MMForCausalLM / Phi4MMConfig). The card's
recipe requests attn_implementation="flash_attention_2" on Ampere+, but this box has no flash-attn
wheel installed (CLAUDE.md: never install xformers; flash-attn is a separate, unverified build) —
the remote code ships its own `Phi4MMSdpaAttention` class (`_supports_sdpa = True` in
modeling_phi4mm.py), so "sdpa" is used instead, matching the fallback this stack already takes
elsewhere (e.g. _transformers_base's default).

Doesn't fit TransformersModelAdapter (needs AutoModelForCausalLM + a GenerationConfig + a
hand-built chat prompt with an image placeholder token, not the processor.apply_chat_template +
AutoModelForImageTextToText path); subclasses LocalModelAdapter directly.
"""
from __future__ import annotations

from tbdoc.core.model_adapter import LocalModelAdapter
from tbdoc.core.registry import register_model
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track
from tbdoc.models.local._vllm_base import load_image, resize_longest

PROMPT = (
    "Convert this document page to clean GitHub-flavored Markdown. Transcribe all text in "
    "natural reading order. Render tables as Markdown tables, math as LaTeX ($...$ / $$...$$), "
    "and preserve headings and lists. Output only the Markdown, no commentary."
)


@register_model("phi4mm")
class Phi4MultimodalAdapter(LocalModelAdapter):
    max_new_tokens = 4096
    longest_side = 2048  # dynamic-HD crop grid (max 12x448px crops) bounds tokens either way; cap anyway
    attn_implementation = "sdpa"  # no flash-attn wheel on this box; remote code implements Phi4MMSdpaAttention

    def load(self) -> None:
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor, GenerationConfig
        rev = self.revision if (self.revision and not str(self.revision).startswith("TBD")) else None
        repo = self.entry["repo_id"]
        self.processor = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=True)
        # v5 fix #1 (works): force sdpa in the config BEFORE construction so v5 doesn't reject the
        # config.json-pinned flash_attention_2, and the Siglip vision tower falls back to eager.
        cfg = AutoConfig.from_pretrained(repo, revision=rev, trust_remote_code=True)
        cfg._attn_implementation = self.attn_implementation
        # NOTE: model construction still raises on the v5 audio-encoder meta-init issue (see docstring
        # blocker #2) — this load() is revival-ready for issue #1 only; phi4mm stays UNREGISTERED.
        self.model = AutoModelForCausalLM.from_pretrained(
            repo, revision=rev, config=cfg, dtype=torch.bfloat16, trust_remote_code=True,
        ).to("cuda").eval()
        self.generation_config = GenerationConfig.from_pretrained(repo, revision=rev)

    def predict(self, image) -> StructuredDoc:
        import torch
        img = resize_longest(load_image(image), self.longest_side)
        prompt = f"<|user|><|image_1|>{PROMPT}<|end|><|assistant|>"
        inputs = self.processor(text=prompt, images=img, return_tensors="pt").to("cuda")
        input_len = int(inputs["input_ids"].shape[1])
        with track() as h:
            with torch.no_grad():
                out = self.model.generate(
                    **inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                    generation_config=self.generation_config,
                )
        timing = h[0]
        gen_ids = out[0, input_len:]
        n_out = int(gen_ids.shape[-1])
        text = self.processor.decode(gen_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False).strip()
        tel = Telemetry(
            latency_s=timing.latency_s,
            peak_vram_mb=timing.peak_vram_mb,
            input_tokens=input_len,
            output_tokens=n_out,
            tokens_per_s=round(n_out / timing.latency_s, 2) if timing.latency_s else None,
            backend="transformers",
        )
        return StructuredDoc(markdown=text, telemetry=tel)

    def unload(self) -> None:
        for a in ("model", "processor", "generation_config"):
            if hasattr(self, a):
                try:
                    delattr(self, a)
                except Exception:
                    pass
        super().unload()
