"""Shared vLLM ModelAdapter base — most roster VLMs run through this.

A concrete model = a thin subclass setting `prompt`, `longest_side`, and (optionally)
`parse_output`. Loads via vLLM, runs the chat API with one image, captures full telemetry
(latency, peak VRAM, token counts, logprob/entropy), and frees the GPU on unload.

Determinism: temperature=0 (greedy). We DON'T install model-specific toolkits into the
inference env — we serve the HF weights directly through vLLM.
"""
from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

from tbdoc.core.model_adapter import LocalModelAdapter
from tbdoc.core.structured_doc import StructuredDoc, Telemetry
from tbdoc.core.telemetry import gpu_used_mb_smi, summarize_entropy, summarize_logprobs, track


def load_image(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    return Image.open(image).convert("RGB")


def resize_longest(img: Image.Image, longest: int | None) -> Image.Image:
    if not longest:
        return img
    w, h = img.size
    m = max(w, h)
    if m <= longest:
        return img
    s = longest / m
    return img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)


def to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class VLLMModelAdapter(LocalModelAdapter):
    # ---- per-model knobs (override in subclass; verify against the model card) ----
    prompt: str = "Convert this document page to markdown."
    longest_side: int | None = None
    max_tokens: int = 4096
    trust_remote_code: bool = False
    max_model_len: int | None = 8192  # <= every roster model's max_position_embeddings; ample for 1 page
    gpu_mem_util: float = 0.90
    skip_special_tokens: bool = True  # some models (DeepSeek-OCR) need False to keep grounding tags
    # Anti-degeneration: a mild repetition penalty stops the empty-table-cell / repeated-line loops that
    # otherwise run to max_tokens (seen on qwen25vl, S8). Greedy (temp=0) stays deterministic; >1.0
    # multiplicatively down-weights already-seen tokens. Kept mild so legitimate tables aren't harmed.
    repetition_penalty: float = 1.05

    #: Attention backend override. None => let vLLM auto-select (FLASH_ATTN on sm120). Set to a vLLM
    #: AttentionBackendEnum name ("FLASHINFER", "FLASH_ATTN", "TRITON_ATTN"). Verified mechanism: in
    #: vLLM 0.22 the legacy VLLM_ATTENTION_BACKEND env var is GONE — the backend is an LLM() kwarg.
    #: Read from TBDOC_ATTN_BACKEND so subprocess workers can A/B it without code changes.
    attention_backend: str | None = None

    def load(self) -> None:
        import os

        from tbdoc.core.cuda_env import ensure_cuda_home
        # The cu13 wheels bundle a full nvcc toolchain (verified 2026-06-12). Wire CUDA_HOME so any
        # runtime JIT can find it: DeepSeek-OCR's custom ops compile through this; vLLM's FlashInfer
        # can too. Inherited by vLLM's worker subprocess since we set it before LLM().
        ensure_cuda_home()
        from vllm import LLM, SamplingParams
        self._SamplingParams = SamplingParams
        # placeholder/None revision -> use cached/latest rather than 404 on "TBD-at-download"
        rev = self.revision if (self.revision and not str(self.revision).startswith("TBD")) else None
        kwargs: dict[str, Any] = dict(
            model=self.entry["repo_id"],
            revision=rev,
            trust_remote_code=self.trust_remote_code,
            dtype="bfloat16",
            gpu_memory_utilization=self.gpu_mem_util,
            limit_mm_per_prompt={"image": 1},
            max_model_len=self.max_model_len,
            enforce_eager=True,  # Blackwell: avoid cudagraph capture issues on bleeding-edge
        )
        # Default decoder attention is FlashAttention 2 (prebuilt, no nvcc). FlashInfer is opt-in and
        # must be passed as an LLM() kwarg — the old VLLM_ATTENTION_BACKEND env var is a no-op in 0.22.
        backend = os.environ.get("TBDOC_ATTN_BACKEND") or self.attention_backend
        if backend:
            kwargs["attention_backend"] = backend
        self.llm = LLM(**kwargs)

    def build_messages(self, data_url: str) -> list[dict]:
        return [{"role": "user", "content": [
            {"type": "text", "text": self.prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}]

    def parse_output(self, text: str) -> dict:
        """Map raw model text -> StructuredDoc fields. Override per model."""
        return {"markdown": text}

    def predict(self, image: Any) -> StructuredDoc:
        img = resize_longest(load_image(image), self.longest_side)
        messages = self.build_messages(to_data_url(img))
        # seed=0: pin the sampler RNG so greedy decoding is reproducible (tie-breaks deterministic).
        # NB: this alone does NOT fully remove run-to-run drift — vLLM's attention/matmul reductions
        # aren't bit-deterministic across separate .chat() calls (issue #4). The structural fix is the
        # OCR-once memoization in baseline_infer.py (each unique page decoded once, reused). Residual
        # cross-run nondeterminism is documented in findings/S11.
        sp = self._SamplingParams(temperature=0.0, seed=0, max_tokens=self.max_tokens, logprobs=5,
                                  repetition_penalty=self.repetition_penalty,
                                  skip_special_tokens=self.skip_special_tokens)
        with track() as h:
            outs = self.llm.chat(messages, sampling_params=sp, use_tqdm=False)
        timing = h[0]
        comp = outs[0].outputs[0]

        chosen, topk = [], []
        if comp.logprobs:
            for tok_id, lp in zip(comp.token_ids, comp.logprobs):
                if not lp:
                    continue
                if tok_id in lp:
                    chosen.append(lp[tok_id].logprob)
                topk.append([v.logprob for v in lp.values()])
        lp_stats = summarize_logprobs(chosen)
        out_tokens = len(comp.token_ids)
        in_tokens = len(outs[0].prompt_token_ids or [])
        tel = Telemetry(
            latency_s=timing.latency_s,
            # vLLM runs in an engine subprocess; whole-GPU used (nvidia-smi) is the right proxy
            peak_vram_mb=gpu_used_mb_smi() or timing.peak_vram_mb,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            tokens_per_s=round(out_tokens / timing.latency_s, 2) if timing.latency_s else None,
            mean_logprob=lp_stats["mean_logprob"],
            min_logprob=lp_stats["min_logprob"],
            mean_entropy=summarize_entropy(topk),
            backend="vllm",
        )
        parsed = self.parse_output(comp.text)
        return StructuredDoc(
            markdown=parsed.get("markdown", ""),
            layout_boxes=parsed.get("layout_boxes"),
            tables_html=parsed.get("tables_html"),
            formulas_latex=parsed.get("formulas_latex"),
            raw=parsed.get("raw", {}),
            telemetry=tel,
        )

    def unload(self) -> None:
        for attr in ("llm", "_SamplingParams"):
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception:
                    pass
        super().unload()
