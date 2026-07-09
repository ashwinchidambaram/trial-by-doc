"""Florence-2-base adapter (transformers, trust_remote_code). Task-prompt VLM, NOT a chat model —
predict() sends the "<OCR>" task token and lets Florence-2's own post_process_generation clean the
raw decode into plain OCR text (per the model card's documented recipe).

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║ STATUS: BLOCKED on this stack (transformers 5.11) — 2026-07-09. NOT registered / not runnable. ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
Florence-2-base ships pre-transformers-v5 remote code (config `transformers_version` predates the
v5 Cache/generation rewrite). Loading it on the reference env's transformers 5.11 hits a *cascade*
of incompatibilities, the last of which is fatal and lives inside the model's own generation loop
(not shimmable from an adapter). In investigation order:
  1. `Florence2LanguageConfig` reads `self.forced_bos_token_id` which v5 no longer auto-sets
     (AttributeError) — patchable (set the class attr to None).
  2. `Florence2Processor.__init__` reads `tokenizer.additional_special_tokens`, renamed to
     `extra_special_tokens` in v5 — patchable (alias it).
  3. Model class lacks `_supports_sdpa`/`_supports_flash_attn*` attrs v5's attn dispatch expects
     (AttributeError) — patchable (set the class attrs False + attn_implementation="eager").
  4. The checkpoint stores only `language_model.model.shared.weight`; encoder/decoder embed_tokens
     and lm_head are meant to be *tied* to it, but v5's loader does NOT restore the tie → those
     weights are randomly initialized (garbage LM head) — patchable (manual weight tie after load).
  5. DaViT `_encode_image` asserts "only support square feature maps" — needs a forced 768x768
     square input (the processor's own resize didn't satisfy it) — patchable-ish.
  6. **FATAL:** `prepare_inputs_for_generation` indexes `past_key_values[0][0]` (legacy tuple-cache
     API), but v5 passes an `EncoderDecoderCache` object that is not subscriptable →
     `TypeError: 'EncoderDecoderCache' object is not subscriptable`. This is inside the remote
     model's BART-style generation code and would require rewriting its cache handling to match v5's
     Cache API — beyond a normal adapter and too fragile to ship.
Verdict per the task's "genuinely too hard to wire on transformers v5.11" clause: BLOCKED, continue
with the other two contenders (kosmos25, phi4mm). Revisit only if microsoft ports Florence-2 to
native v5 transformers, or if the roster pins an older transformers just for this model (rejected —
5.13 already breaks dots.ocr; a second pin is worse). The @register_model decorator and the
configs/models.yaml entry are intentionally left OUT so this never enters a run; code kept for
provenance + a future revival.

Verified live 2026-07-09 (HF API + model card): repo microsoft/Florence-2-base
@ 5ca5edf5bd017b9919c05d08aebef5e4c7ac3bac, license MIT (HF API tag `license:mit`), gated=false.
Params 0.23B. AutoModelForCausalLM + AutoProcessor, trust_remote_code=True — confirmed required:
config.json carries `auto_map: {AutoModelForCausalLM: modeling_florence2.Florence2ForConditionalGeneration}`
and no native transformers registration exists for "florence2". The text backbone is
encoder-decoder (text_config.is_encoder_decoder=true), so generate() output is the decoder
sequence only (no input-prompt echo to slice off) — matches the card's own recipe, which decodes
`generated_ids` directly with no length offset.

Doesn't fit TransformersModelAdapter (that base loads AutoModelForImageTextToText and assumes a
chat-style processor + causal-LM output slicing); subclasses LocalModelAdapter directly and
implements load()/predict() per the got2/_transformers_base idiom (track() for latency,
resize_longest cap for huge merged_forms pages).
"""
from __future__ import annotations

from tbdoc.core.model_adapter import LocalModelAdapter
from tbdoc.core.registry import register_model
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track
from tbdoc.models.local._vllm_base import load_image, resize_longest

OCR_TASK = "<OCR>"


# NOTE: intentionally NOT @register_model — Florence-2 is BLOCKED on transformers 5.11 (see module
# docstring). Registering it would let it be selected in a run and fail. Kept for provenance/revival.
class Florence2Adapter(LocalModelAdapter):
    max_new_tokens = 1024
    longest_side = 2048  # DaViT vision tower resizes internally either way; cap huge merged_forms pages

    def load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        rev = self.revision if (self.revision and not str(self.revision).startswith("TBD")) else None
        repo = self.entry["repo_id"]
        self.processor = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            repo, revision=rev, dtype=torch.bfloat16, trust_remote_code=True,
        ).to("cuda").eval()

    def predict(self, image) -> StructuredDoc:
        import torch
        img = resize_longest(load_image(image), self.longest_side)
        inputs = self.processor(text=OCR_TASK, images=img, return_tensors="pt").to("cuda", torch.bfloat16)
        input_len = int(inputs["input_ids"].shape[1])
        with track() as h:
            with torch.no_grad():
                gen_ids = self.model.generate(
                    input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                    max_new_tokens=self.max_new_tokens, do_sample=False, num_beams=3,
                )
        timing = h[0]
        # Encoder-decoder: generate() returns the decoder sequence only, no input-prompt prefix to slice.
        n_out = int(gen_ids.shape[-1])
        raw_text = self.processor.batch_decode(gen_ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(raw_text, task=OCR_TASK, image_size=(img.width, img.height))
        markdown = parsed.get(OCR_TASK, "") if isinstance(parsed, dict) else str(parsed)
        tel = Telemetry(
            latency_s=timing.latency_s,
            peak_vram_mb=timing.peak_vram_mb,
            input_tokens=input_len,
            output_tokens=n_out,
            tokens_per_s=round(n_out / timing.latency_s, 2) if timing.latency_s else None,
            backend="transformers",
        )
        return StructuredDoc(markdown=markdown, raw={"task": OCR_TASK}, telemetry=tel)

    def unload(self) -> None:
        for a in ("model", "processor"):
            if hasattr(self, a):
                try:
                    delattr(self, a)
                except Exception:
                    pass
        super().unload()
