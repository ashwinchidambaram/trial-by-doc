"""Tier-B extractor interface — the frozen markdown->answer measuring instrument.

The concrete local deterministic model (Ministral-3-3B / Phi-4-mini, temp=0, seeded)
is implemented at S4. Here we define the contract so BenchAdapters and run_matrix can
depend on it now, plus a trivial FunctionExtractor for tests.
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    """Reads ONLY a model's markdown + a question, returns an answer string.

    Must be deterministic and identical across every OCR model so Tier-B differences
    reflect parse quality, not the answerer. `identity` is recorded with results.
    """
    identity: str

    def answer(self, markdown: str, question: str) -> str: ...


class FunctionExtractor:
    """Wrap a plain function as an Extractor (used in tests / wiring)."""

    def __init__(self, fn: Callable[[str, str], str], identity: str = "fn-extractor"):
        self._fn = fn
        self.identity = identity

    def answer(self, markdown: str, question: str) -> str:
        return self._fn(markdown, question)
