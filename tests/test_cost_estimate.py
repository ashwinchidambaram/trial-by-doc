"""The API cost guard must count what it BILLS for — page inferences — not samples.

Two benches diverge from a naive per-sample count in opposite directions:
  - unit="document" (merged_forms): 1 sample == N page calls (~17 for a stream)
  - unit="page"     (realdoc_qa):   M question-samples share ONE rendered page object,
                                    and infer.py memoizes on id(s.image) -> 1 page call
Under-counting the first leaks the matrix.yaml budget cap, which is the one thing
standing between a typo and real money.
"""
from __future__ import annotations

from tbdoc.cli import _count_samples
from tbdoc.core.bench_adapter import BenchAdapter, Sample


class _FakeBench(BenchAdapter):
    provenance = "official"

    def __init__(self, key, samples, unit="page"):
        super().__init__(key)
        self.unit = unit
        self._samples = samples

    def load(self):
        yield from self._samples

    def evaluate(self, sample, prediction, extractor=None):
        return {"primary": 1.0}


class _FakeRegistry:
    def __init__(self, benches):
        self._benches = benches

    def bench(self, key):
        return self._benches[key]


def _doc_bench(key="merged_forms", n_streams=2, pages_per=3):
    samples = [Sample(id=f"st{i}", gold=[], pages=[object() for _ in range(pages_per)])
               for i in range(n_streams)]
    return _FakeBench(key, samples, unit="document")


def _shared_page_bench(key="realdoc_qa", n_docs=2, questions_per=4):
    """Mirrors realdoc_qa: one rendered image object shared across a doc's questions."""
    samples = []
    for d in range(n_docs):
        img = object()                     # rendered ONCE per doc (realdoc_qa.py:63)
        for q in range(questions_per):
            samples.append(Sample(id=f"d{d}q{q}", gold="g", pages=[img], question="?"))
    return _FakeBench(key, samples, unit="page")


def test_document_unit_bench_counts_every_page_not_the_stream():
    """merged_forms: 2 streams x 3 pages = 6 billable page calls, not 2 samples."""
    reg = _FakeRegistry({"merged_forms": _doc_bench(n_streams=2, pages_per=3)})
    assert _count_samples(reg, ["merged_forms"], None) == 6


def test_shared_page_objects_are_counted_once():
    """realdoc_qa: 8 questions over 2 docs -> infer.py OCRs 2 pages, so bill 2."""
    reg = _FakeRegistry({"realdoc_qa": _shared_page_bench(n_docs=2, questions_per=4)})
    assert _count_samples(reg, ["realdoc_qa"], None) == 2


def test_cap_applies_to_samples_then_pages_are_counted():
    """A cap of 2 streams selects 2 samples -> 2 x 3 = 6 pages (cap is not a page cap)."""
    reg = _FakeRegistry({"merged_forms": _doc_bench(n_streams=5, pages_per=3)})
    assert _count_samples(reg, ["merged_forms"], {"merged_forms": 2}) == 6


def test_plain_page_bench_is_unchanged():
    """Regression guard: 1 sample == 1 distinct page == 1 call."""
    samples = [Sample(id=f"s{i}", gold="g", pages=[object()]) for i in range(4)]
    reg = _FakeRegistry({"olmocr_bench": _FakeBench("olmocr_bench", samples)})
    assert _count_samples(reg, ["olmocr_bench"], None) == 4
