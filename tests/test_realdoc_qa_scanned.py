"""realdoc_qa_scanned — reuses RealDocQA's gold/qa_bank verbatim, only degrades pixels.

Uses the real benchmarks/official/realdoc_qa/data corpus (present in this repo) but
only pulls the first few samples via itertools.islice so it stays fast (avoids
rendering every PDF in the bank).
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest

from tbdoc.benches.official.realdoc_qa import RealDocQA
from tbdoc.benches.official.realdoc_qa_scanned import RealDocQAScanned

DATA_DIR = "benchmarks/official/realdoc_qa/data"
N = 3

pytestmark = pytest.mark.skipif(
    not Path(DATA_DIR, "qa_bank.json").exists(),
    reason="realdoc_qa data not present in this checkout",
)


def _first_n(bench, n=N):
    return list(itertools.islice(bench.load(), n))


def test_sample_ids_match_clean():
    clean = _first_n(RealDocQA("realdoc_qa", data_dir=DATA_DIR))
    light = _first_n(RealDocQAScanned("realdoc_qa_scanned_light", data_dir=DATA_DIR,
                                       entry={"level": "light"}))
    assert [s.id for s in clean] == [s.id for s in light]


def test_light_and_heavy_images_differ_from_clean_and_each_other():
    clean = _first_n(RealDocQA("realdoc_qa", data_dir=DATA_DIR))
    light = _first_n(RealDocQAScanned("realdoc_qa_scanned_light", data_dir=DATA_DIR,
                                       entry={"level": "light"}))
    heavy = _first_n(RealDocQAScanned("realdoc_qa_scanned_heavy", data_dir=DATA_DIR,
                                       entry={"level": "heavy"}))
    for c, lt, h in zip(clean, light, heavy):
        assert c.id == lt.id == h.id
        ac, al, ah = np.asarray(c.image), np.asarray(lt.image), np.asarray(h.image)
        assert not np.array_equal(ac, al)
        assert not np.array_equal(ac, ah)
        assert not np.array_equal(al, ah)
        assert lt.meta["severity"] == "light"
        assert h.meta["severity"] == "heavy"


def test_same_doc_reuses_identical_degraded_image():
    # Two questions on the same source_file must share byte-identical degraded pixels
    # (RealDocQA shares one render per doc across its questions; this subclass mirrors it).
    light = _first_n(RealDocQAScanned("realdoc_qa_scanned_light", data_dir=DATA_DIR,
                                       entry={"level": "light"}), n=20)
    by_doc: dict[str, list] = {}
    for s in light:
        by_doc.setdefault(s.meta["source_file"], []).append(s)
    reused = [v for v in by_doc.values() if len(v) > 1]
    assert reused, "expected at least one doc with >1 question in the first 20 samples"
    for group in reused:
        first = np.asarray(group[0].image)
        for s in group[1:]:
            assert np.array_equal(first, np.asarray(s.image))


def test_invalid_level_rejected():
    with pytest.raises(ValueError):
        RealDocQAScanned("realdoc_qa_scanned_bogus", data_dir=DATA_DIR, entry={"level": "bogus"})
