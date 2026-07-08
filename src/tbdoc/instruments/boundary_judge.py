"""The frozen Tier-C boundary judge — decides "same document or new?" for consecutive
page pairs, identically for every model, so judge-composed segmentation is comparable.

An INSTRUMENT, not a judge-of-quality: it reads two page parses and emits a binary
structural decision, which is then scored deterministically (boundary F1 / PQ / STP).
Pinned model + versioned prompt (both stamped in the run manifest); temp=0, seed=0.
Reuses the SAME pinned model as the Tier-B extractor so one instrument download serves
both. Loads on GPU in the score/infer pass AFTER OCR models have unloaded.
"""
from __future__ import annotations

PROMPT_VERSION = "v1"
_REPO = "Qwen/Qwen2.5-7B-Instruct"
_REVISION = "a09a35458c70"  # same frozen pin as the extractor (Apache-2.0)

_SYSTEM = (
    "You are deciding whether two consecutive scanned pages belong to the SAME logical "
    "document or whether the second page STARTS A NEW document (e.g. a new form "
    "submission, a new invoice, a new letter). Same form template with different "
    "filled-in data (different names, dates, amounts, IDs) means a NEW document. "
    "A continuation (same names/IDs, continued tables, page numbers advancing, "
    "'continued' markers) means SAME document. Reply with exactly one word: "
    "SAME or NEW."
)

_TAIL, _HEAD = 2400, 2400  # chars of context from page i's end and page i+1's start


class BoundaryJudge:
    def __init__(self, entry: dict | None = None):
        e = entry or {}
        self.repo = e.get("chosen") or _REPO
        self.revision = e.get("revision") or _REVISION
        self.prompt_version = e.get("prompt_version") or PROMPT_VERSION
        self._llm = None
        self._sp = None

    def identity(self) -> dict:
        return {"model": f"{self.repo}@{self.revision}",
                "prompt_version": self.prompt_version}

    def load(self) -> None:
        from tbdoc.core.cuda_env import ensure_cuda_home
        ensure_cuda_home()
        from vllm import LLM, SamplingParams
        self._llm = LLM(model=self.repo, revision=self.revision, dtype="bfloat16",
                        gpu_memory_utilization=0.90, max_model_len=8192,
                        enforce_eager=True, seed=0)
        self._sp = SamplingParams(temperature=0.0, max_tokens=4)

    def _decide(self, prev_md: str, next_md: str) -> bool:
        """True = next page starts a NEW document."""
        if self._llm is None:
            self.load()
        user = (f"--- END OF PAGE A ---\n{(prev_md or '')[-_TAIL:]}\n\n"
                f"--- START OF PAGE B ---\n{(next_md or '')[:_HEAD]}\n\n"
                "Does PAGE B start a NEW document, or is it the SAME document as PAGE A?")
        out = self._llm.chat([{"role": "system", "content": _SYSTEM},
                              {"role": "user", "content": user}],
                             sampling_params=self._sp, use_tqdm=False)
        return "NEW" in (out[0].outputs[0].text or "").strip().upper()

    def boundaries(self, page_markdowns: list[str]) -> list[int]:
        """0-based indices where a new logical document starts (page 0 implicit)."""
        return [i for i in range(1, len(page_markdowns))
                if self._decide(page_markdowns[i - 1], page_markdowns[i])]

    def unload(self) -> None:
        import contextlib
        import gc
        self._llm = self._sp = None
        gc.collect()
        with contextlib.suppress(Exception):
            import torch
            torch.cuda.empty_cache()
