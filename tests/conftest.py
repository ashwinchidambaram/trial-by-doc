"""Shared dummy adapters — the harness is dependency-injected so no GPU/API needed."""
from __future__ import annotations

import pytest

from tbdoc.core.bench_adapter import BenchAdapter, Sample
from tbdoc.core.model_adapter import ModelAdapter
from tbdoc.core.structured_doc import StructuredDoc, Telemetry


class DummyModel(ModelAdapter):
    def __init__(self, key="dummy", entry=None, fail_on=None):
        super().__init__(key, entry or {"revision": "r0", "backend": "dummy"})
        self.fail_on = fail_on or set()
        self.load_count = 0

    def load(self):
        self.load_count += 1

    def predict(self, image):
        if image in self.fail_on:
            raise ValueError(f"boom on {image}")
        return StructuredDoc(markdown=f"# parsed {image}",
                             telemetry=Telemetry(latency_s=0.01, backend="dummy"))


class DummyBench(BenchAdapter):
    tier = "A"
    unit = "page"
    provenance = "official"

    def __init__(self, key="dummy_bench", n=4, **kw):
        super().__init__(key, **kw)
        self.n = n

    def load(self):
        for i in range(self.n):
            yield Sample(id=f"s{i}", gold=f"gold{i}", pages=[f"page{i}"], category="cat_a")

    def evaluate(self, sample, prediction, extractor=None):
        ok = sample.id.lstrip("s") in prediction.markdown
        return {"primary": 1.0 if ok else 0.0}


@pytest.fixture
def dummy_factories():
    return (lambda k: DummyModel(k), lambda k: DummyBench(k))
