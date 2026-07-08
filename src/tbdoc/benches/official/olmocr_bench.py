"""olmOCR-Bench (allenai/olmOCR-bench, ODC-BY) — Tier A parse fidelity.

Gold = per-page unit tests (text present/absent, reading order, math, tables) run by
the OFFICIAL `olmocr.bench.tests` runner in an isolated venv (text/order natively;
math/table need the Playwright container — see benchmarks/_scorers/olmocr_bench/).
Primary metric: per-page unit-test pass rate.

Sampling is STRATIFIED round-robin across the 7 category subdirs (arxiv_math, tables,
old_scans, multi_column, headers_footers, long_tiny_text, old_scans_math) — 'first N
sorted' would be all arxiv_math (bias found in the ocparse S10 post-mortem).
"""
from __future__ import annotations

import io
from glob import glob
from pathlib import Path
from typing import Any, Iterable

from tbdoc.core.bench_adapter import BenchAdapter, Sample
from tbdoc.scoring.venv_scorer import score_batch_venv

_SCORER_DIR = Path(__file__).resolve().parents[4] / "benchmarks" / "_scorers" / "olmocr_bench"


def _render_pdf(path: str, page: int = 0, dpi: int = 150):
    import fitz
    from PIL import Image
    doc = fitz.open(path)
    pix = doc[min(page, len(doc) - 1)].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


class OlmOCRBench(BenchAdapter):
    tier = "A"
    unit = "page"
    provenance = "official"

    def load(self) -> Iterable[Sample]:
        pdf_root = Path(self.data_dir) / "bench_data" / "pdfs"
        cats = sorted([d for d in pdf_root.iterdir() if d.is_dir()]) if pdf_root.exists() else []
        per_cat = {c.name: sorted(glob(str(c / "*.pdf"))) for c in cats}
        ordered, i = [], 0
        while any(i < len(v) for v in per_cat.values()):
            for cat in per_cat:
                if i < len(per_cat[cat]):
                    ordered.append(per_cat[cat][i])
            i += 1
        for p in ordered:
            try:
                yield Sample(id=Path(p).name, gold=None, pages=[_render_pdf(p)],
                             category=Path(p).parent.name)
            except Exception:
                continue

    def evaluate(self, sample: Sample, prediction: Any, extractor: Any | None = None) -> dict:
        return self.evaluate_batch([sample], [prediction])[sample.id]

    def evaluate_batch(self, samples: list[Sample], predictions: list[Any],
                       extractor: Any | None = None) -> dict[str, dict]:
        bench_data = str(Path(self.data_dir) / "bench_data")
        docs = [{"pdf_id": s.id, "markdown": p.markdown} for s, p in zip(samples, predictions)]
        results = score_batch_venv(_SCORER_DIR, [bench_data], docs)
        out: dict[str, dict] = {}
        for s in samples:
            r = results.get(s.id)
            if r is None:
                out[s.id] = {"primary": None, "error": "no scorer result"}
                continue
            out[s.id] = {"primary": r.get("pass_rate"), "passed": r.get("passed"),
                         "total": r.get("total"), "by_type": r.get("by_type"),
                         "fails": r.get("fails"),
                         "render_tests_excluded": r.get("render_tests_excluded")}
        return out

    def categories(self) -> list[str]:
        return ["arxiv_math", "headers_footers", "long_tiny_text", "multi_column",
                "old_scans", "old_scans_math", "tables"]
