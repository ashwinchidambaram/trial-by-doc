"""RealDoc-Bench QA (Extend-AI/RealDoc-Bench, CC BY 4.0) — Tier B downstream extraction.

The production-shaped signal: OCR the page -> frozen extractor answers field questions
from the markdown -> DETERMINISTIC scoring (field-aware exact match primary + ANLS).
The extractor is an instrument, not a judge (pinned, temp=0, seeded, identical for
every model) — Tier-B differences reflect parse quality.

Sampling is STRATIFIED by DOCUMENT across the 4 domains (finance, medical_healthcare,
mortgage, supply_chain) via round-robin; every question of a selected doc is emitted
and the page image is shared across them (ocparse S10 fixes carried over).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Iterable

from tbdoc.core.bench_adapter import BenchAdapter, Sample
from tbdoc.scoring.scorers import anls, field_aware_exact_match


def _render_pdf(path: str, page: int = 0, dpi: int = 150):
    import fitz
    from PIL import Image
    doc = fitz.open(path)
    pix = doc[min(page, len(doc) - 1)].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


class RealDocQA(BenchAdapter):
    tier = "B"
    unit = "page"
    provenance = "official"
    requires_extractor = True

    def load(self) -> Iterable[Sample]:
        root = Path(self.data_dir)
        bank = json.loads((root / "qa_bank.json").read_text())
        docs_dir = root / "docs"
        by_doc: dict[str, list] = {}
        doc_domain: dict[str, str] = {}
        for it in bank.get("items", []):
            src = it.get("source_file")
            if src is None:
                continue
            by_doc.setdefault(src, []).append(it)
            doc_domain.setdefault(src, it.get("domain"))
        per_dom: dict[str, list] = {}
        for src in sorted(by_doc):
            per_dom.setdefault(doc_domain[src], []).append(src)
        ordered_docs, i = [], 0
        while any(i < len(v) for v in per_dom.values()):
            for dom in sorted(per_dom):
                if i < len(per_dom[dom]):
                    ordered_docs.append(per_dom[dom][i])
            i += 1
        for src in ordered_docs:
            pdf = docs_dir / f"{src}.pdf"
            if not pdf.exists():
                continue
            try:
                img = _render_pdf(str(pdf))  # rendered ONCE, shared across the doc's questions
            except Exception:
                continue
            for it in by_doc[src]:
                q = it.get("question", "")
                fmt = it.get("response_format")
                yield Sample(id=it.get("question_id", src),
                             gold=[str(it.get("gold_answer", ""))],
                             pages=[img], question=(f"{q}\n{fmt}" if fmt else q),
                             category=doc_domain[src], meta={"source_file": src})

    def evaluate(self, sample: Sample, prediction: Any, extractor: Any | None = None) -> dict:
        if extractor is None:
            return {"primary": None, "error": "Tier B requires the frozen extractor "
                    "(run without --no-llm-instruments)"}
        answer = extractor.answer(prediction.markdown, sample.question or "")
        golds = sample.gold or [""]
        em = field_aware_exact_match(answer, golds)
        a = anls(answer, golds)
        return {"primary": em, "anls": a, "answer": answer[:200],
                "extractor": getattr(extractor, "identity", "?")}

    def categories(self) -> list[str]:
        return ["finance", "medical_healthcare", "mortgage", "supply_chain"]
