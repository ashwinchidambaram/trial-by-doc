"""RealDoc-Bench QA under synthetic scan/fax degradation (Tier D, spec §4.2).

Thin subclass of `RealDocQA` — reuses its `qa_bank.json` + gold + stratified
sampling VERBATIM (calls `super().load()`, never re-derives the bank) and only
interposes `degrade()` (`tbdoc.benches.degrade`) on the rendered page image
before each Sample is yielded. Scoring is completely unchanged (inherited
`evaluate()` / `categories()`); this file adds no scorer code.

Sample ids are IDENTICAL to clean `realdoc_qa` (same `question_id`) so the
scoreboard can join clean <-> light <-> heavy per (model, question) — only
`meta["severity"]` and the degraded pixels differ.

Seeding: `RealDocQA.load()` renders each source PDF page ONCE and shares that
image across every question for that document (`by_doc[src]`), matching how a
real reader would see one scanned page and answer several questions about it.
This subclass mirrors that sharing: the page is degraded ONCE per (source_file,
level) and the same degraded image is reused for every question sample drawn
from it (rather than re-degrading per question, which would make the "same
page" look subtly different per question — not representative of a real scan).
The seed is derived deterministically from (source_file, level), so it is a
seed "per (sample, level)" at the page granularity that RealDocQA already
treats as one physical scanned artifact.

tier="D" (set in configs/benchmarks.yaml; promoted from "B" when the scanned
study became an official tier, 2026-07-22), unit="page", requires_extractor=True
(unchanged from RealDocQA).
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from tbdoc.benches.degrade import degrade, params_fingerprint
from tbdoc.benches.official.realdoc_qa import RealDocQA
from tbdoc.core.bench_adapter import Sample

VALID_LEVELS = ("light", "heavy")


def _doc_seed(source_file: str, level: str) -> int:
    """Deterministic seed for (source_file, level) — stable across processes/runs."""
    h = hashlib.sha256(f"{source_file}|{level}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


class RealDocQAScanned(RealDocQA):
    """RealDocQA with the rendered page degraded to a scan/fax before yielding.

    `level` ("light" | "heavy") comes from the benchmarks.yaml entry
    (`entry["level"]`), defaulting to "light" if unset — so one class serves
    both registered variants (`realdoc_qa_scanned_light`,
    `realdoc_qa_scanned_heavy`).
    """

    def __init__(self, key: str, data_dir: str | None = None, entry: dict | None = None):
        super().__init__(key, data_dir=data_dir, entry=entry)
        self.level = (entry or {}).get("level", "light")
        if self.level not in VALID_LEVELS:
            raise ValueError(f"realdoc_qa_scanned level must be one of {VALID_LEVELS}, "
                              f"got {self.level!r}")

    def load(self) -> Iterable[Sample]:
        degraded_by_doc: dict[str, object] = {}
        for sample in super().load():
            src = sample.meta.get("source_file")
            if src not in degraded_by_doc:
                seed = _doc_seed(src, self.level)
                degraded_by_doc[src] = degrade(sample.image, self.level, seed)
            degraded_img = degraded_by_doc[src]
            meta = dict(sample.meta)
            meta["severity"] = self.level
            meta["degrade_params"] = params_fingerprint(self.level)
            meta["degrade_seed"] = _doc_seed(src, self.level)
            yield Sample(id=sample.id, gold=sample.gold, pages=[degraded_img],
                         question=sample.question, category=sample.category, meta=meta)

    def fingerprint(self) -> dict:
        fp = super().fingerprint()
        fp["severity"] = self.level
        fp["degrade_params"] = params_fingerprint(self.level)
        return fp
