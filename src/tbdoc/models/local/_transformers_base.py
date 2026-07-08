"""Shared transformers ModelAdapter base — for models we don't run on vLLM (GOT, granite).

Loads via AutoModelForImageTextToText + AutoProcessor with SDPA attention (sm_120, no flash-attn).
Telemetry: latency, in-process peak VRAM, token counts. (Per-token logprobs are skipped here —
`output_scores` over long generations is memory-heavy; vLLM models carry the logprob signal.)
"""
from __future__ import annotations

from typing import Any

from tbdoc.models.local._vllm_base import load_image, resize_longest
from tbdoc.core.model_adapter import ModelAdapter
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import track


class TransformersModelAdapter(ModelAdapter):
    max_new_tokens: int = 4096
    attn_implementation: str = "sdpa"  # sm_120 + no flash-attn
    trust_remote_code: bool = False
    longest_side: int | None = None    # processor usually handles resize
    # Anti-degeneration (transformers has no vLLM repetition_penalty path): granite looped to the token
    # cap on hard pages (~700s/page, S10). repetition_penalty mirrors the vLLM side; no_repeat_ngram_size
    # is the hard stop against repeated n-grams. Greedy (do_sample=False) stays deterministic.
    repetition_penalty: float = 1.05
    no_repeat_ngram_size: int = 3

    def load(self) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        rev = self.revision if (self.revision and not str(self.revision).startswith("TBD")) else None
        repo = self.entry["repo_id"]
        self.processor = AutoProcessor.from_pretrained(repo, revision=rev, trust_remote_code=self.trust_remote_code)
        self.model = AutoModelForImageTextToText.from_pretrained(
            repo, revision=rev, dtype=torch.bfloat16,
            attn_implementation=self.attn_implementation, trust_remote_code=self.trust_remote_code,
        ).to("cuda").eval()

    # --- subclass hooks ---
    def build_inputs(self, image) -> dict:
        raise NotImplementedError

    def gen_kwargs(self) -> dict:
        return {}

    def decode(self, gen_ids, image) -> dict:
        """gen_ids = generated token ids (after the prompt). Return StructuredDoc fields."""
        raise NotImplementedError

    def predict(self, image: Any) -> StructuredDoc:
        import torch
        img = load_image(image)
        if self.longest_side:
            img = resize_longest(img, self.longest_side)
        inputs = self.build_inputs(img)
        input_len = int(inputs["input_ids"].shape[1])
        with track() as h:
            with torch.no_grad():
                gen = dict(do_sample=False, max_new_tokens=self.max_new_tokens,
                           repetition_penalty=self.repetition_penalty)
                if self.no_repeat_ngram_size:
                    gen["no_repeat_ngram_size"] = self.no_repeat_ngram_size
                gen.update(self.gen_kwargs())  # subclass can override
                out = self.model.generate(**inputs, **gen)
        timing = h[0]
        gen_ids = out[0, input_len:]
        n_out = int(gen_ids.shape[-1])
        parsed = self.decode(gen_ids, img)
        tel = Telemetry(
            latency_s=timing.latency_s,
            peak_vram_mb=timing.peak_vram_mb,
            input_tokens=input_len,
            output_tokens=n_out,
            tokens_per_s=round(n_out / timing.latency_s, 2) if timing.latency_s else None,
            backend="transformers",
        )
        return StructuredDoc(
            markdown=parsed.get("markdown", ""),
            layout_boxes=parsed.get("layout_boxes"),
            tables_html=parsed.get("tables_html"),
            formulas_latex=parsed.get("formulas_latex"),
            raw=parsed.get("raw", {}),
            telemetry=tel,
        )

    def unload(self) -> None:
        for a in ("model", "processor"):
            if hasattr(self, a):
                try:
                    delattr(self, a)
                except Exception:
                    pass
        super().unload()
