from types import SimpleNamespace

from tbdoc.benches.official.realdoc_qa import RealDocQA
from tbdoc.instruments.extractor import FunctionExtractor


def _sample(gold, question="What is the amount paid?", domain="finance"):
    from tbdoc.core.bench_adapter import Sample
    return Sample(id="q1", gold=[gold], question=question, category=domain)

def _pred(markdown):
    return SimpleNamespace(markdown=markdown, telemetry=SimpleNamespace(to_dict=lambda: {}))

def test_b1_is_primary_and_deterministic_without_reader():
    ba = RealDocQA("realdoc_qa")
    m = ba.evaluate(_sample("amount=8500"), _pred("Amount: 8500"), extractor=None)
    assert m["b1"] == 1.0
    assert m["primary"] == 1.0
    assert m["extractive"] is True
    assert m["b2"] is None      # no reader -> comprehension not computed

def test_derived_item_excluded_from_b1_primary():
    ba = RealDocQA("realdoc_qa")
    m = ba.evaluate(_sample("count=7", question="How many line items?"),
                    _pred("... a table ..."), extractor=None)
    assert m["extractive"] is False
    assert m["primary"] is None  # dropped from the B.1 mean

def test_b2_uses_reader_when_present():
    ba = RealDocQA("realdoc_qa")
    # the real reader answers in the gold's key=value format (response_format hint); mirror that
    reader = FunctionExtractor(lambda md, q: "amount=8500", identity="fake-reader")
    m = ba.evaluate(_sample("amount=8500"), _pred("Amount: 8500"), extractor=reader)
    assert m["b2"] == 1.0
    assert m["reader"] == "fake-reader"
