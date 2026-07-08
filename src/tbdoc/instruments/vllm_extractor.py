"""The frozen Tier-B extractor — Qwen2.5-7B-Instruct via vLLM (text-only), held identical across every
OCR model so Tier-B differences reflect PARSE quality, not the answerer.

Design (see findings/S9):
  - Neutral instrument: a strict grounding prompt forces "answer ONLY from the provided text; say
    'not found' if absent" so the model reads the markdown faithfully instead of answering from world
    knowledge / repairing a broken parse (which would mask parse failures).
  - Deterministic: greedy (temperature=0), seed=0 — same markdown+question -> same answer, always.
  - Runs in PASS 2, after OCR inference has freed the GPU (a 7B extractor can't co-reside with a 7B
    OCR model on 32 GB). Load once, answer all Tier-B questions, unload.
"""
from __future__ import annotations

# Satisfies the structural `tbdoc.instruments.extractor.Extractor` Protocol (identity + answer()).

_SYSTEM = (
    "You extract answers from a document's parsed text. Use ONLY the text provided — do not use outside "
    "knowledge and do not guess. If the answer is not present in the text, reply exactly: not found. "
    "Reply with ONLY the answer value, as short as possible, no explanation, no punctuation around it."
)

_REPO = "Qwen/Qwen2.5-7B-Instruct"
_REVISION = "a09a35458c70"  # Apache-2.0; verified 2026-06-12


class VLLMExtractor:
    """Concrete Extractor (satisfies the Extractor Protocol). Lazy-loads vLLM on first use."""

    def __init__(self, repo: str = _REPO, revision: str | None = _REVISION,
                 max_markdown_chars: int = 48000, max_answer_tokens: int = 64):
        self.repo = repo
        self.revision = revision
        self.max_markdown_chars = max_markdown_chars
        self.max_answer_tokens = max_answer_tokens
        self.identity = f"{repo}@{revision or 'latest'}"
        self._llm = None
        self._sp = None

    @staticmethod
    def _assert_registry_pin() -> None:
        """#5: the registry mirrors this frozen pin for visibility — fail loud if they've drifted, so a
        registry edit can never silently change the Tier-B instrument. Registry unreadable => code stands."""
        try:
            from pathlib import Path
            import yaml
            reg = Path(__file__).resolve().parents[3] / "configs" / "model_registry.yaml"
            ex = (yaml.safe_load(reg.read_text()) or {}).get("extractor", {}) or {}
        except Exception:
            return
        chosen, rev = ex.get("chosen"), str(ex.get("revision") or "")
        if chosen and chosen != _REPO:
            raise RuntimeError(f"extractor registry/code drift: registry chosen={chosen!r} != code {_REPO!r}")
        if rev and _REVISION and not (_REVISION.startswith(rev) or rev.startswith(_REVISION)):
            raise RuntimeError(f"extractor registry/code revision drift: registry={rev!r} != code {_REVISION!r}")

    def load(self) -> None:
        import os
        self._assert_registry_pin()
        from tbdoc.core.cuda_env import ensure_cuda_home
        ensure_cuda_home()
        os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
        from vllm import LLM, SamplingParams
        # 32k context: dense OCR pages exceeded 8192 and crashed Tier-B (S10). Qwen2.5-7B supports 32k
        # natively. markdown is also char-capped as a backstop so a pathological page can't blow the window.
        self._llm = LLM(model=self.repo, revision=self.revision, dtype="bfloat16",
                        gpu_memory_utilization=0.90, max_model_len=32768, enforce_eager=True, seed=0)
        # greedy + tiny repetition guard; deterministic answer.
        self._sp = SamplingParams(temperature=0.0, max_tokens=self.max_answer_tokens,
                                  repetition_penalty=1.05)

    def answer(self, markdown: str, question: str) -> str:
        if self._llm is None:
            self.load()
        md = (markdown or "")[: self.max_markdown_chars]
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Document text:\n\n{md}\n\nQuestion: {question}\nAnswer:"},
        ]
        out = self._llm.chat(messages, sampling_params=self._sp, use_tqdm=False)
        return (out[0].outputs[0].text or "").strip()

    def unload(self) -> None:
        import contextlib
        import gc
        self._llm = self._sp = None
        gc.collect()
        with contextlib.suppress(Exception):
            import torch
            torch.cuda.empty_cache()

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, *exc):
        self.unload()
        return False
