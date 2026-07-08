"""OmniDocBench v1.6 (opendatalab/OmniDocBench, HF rev d386947f) — Tier A parse fidelity.

Gold = the dataset's `OmniDocBench.json` page annotations; scoring = the OFFICIAL
opendatalab/OmniDocBench end2end pipeline (quick_match + Edit_dist/TEDS) running in an
isolated venv (benchmarks/_scorers/omnidocbench/ — official pins need Python <3.12).
CDM (formula render) is excluded there (TeX toolchain); results carry `cdm_excluded`.

Primary metric: 1 - overall_edit_dist (mean of the page's per-element official edit
distances over text/formula/table/reading-order; higher = better). Components (incl.
table TEDS) are reported alongside.

Sampling is STRATIFIED round-robin across the 10 `data_source` page attributes ('first N
sorted' would over-represent one source — same bias fixed for olmocr_bench).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from tbdoc.core.bench_adapter import BenchAdapter, Sample
from tbdoc.scoring.venv_scorer import score_batch_venv

_SCORER_DIR = Path(__file__).resolve().parents[4] / "benchmarks" / "_scorers" / "omnidocbench"


class OmniDocBench(BenchAdapter):
    tier = "A"
    unit = "page"
    provenance = "official"

    def _gt_path(self) -> Path:
        return Path(self.data_dir) / "OmniDocBench.json"

    def load(self) -> Iterable[Sample]:
        pages = json.loads(self._gt_path().read_text(encoding="utf-8"))
        img_dir = Path(self.data_dir) / "images"
        per_cat: dict[str, list[dict]] = {}
        for p in pages:
            per_cat.setdefault(p["page_info"]["page_attribute"]["data_source"], []).append(p)
        for cat in per_cat:
            per_cat[cat].sort(key=lambda p: p["page_info"]["image_path"])
        ordered, i = [], 0
        while any(i < len(v) for v in per_cat.values()):
            for cat in sorted(per_cat):
                if i < len(per_cat[cat]):
                    ordered.append(per_cat[cat][i])
            i += 1
        from PIL import Image
        for p in ordered:
            name = Path(p["page_info"]["image_path"]).name
            attr = p["page_info"]["page_attribute"]
            try:
                img = Image.open(img_dir / name).convert("RGB")
            except Exception:
                continue
            yield Sample(id=name, gold=None, pages=[img], category=attr["data_source"],
                         meta={"language": attr.get("language"), "layout": attr.get("layout")})

    def evaluate(self, sample: Sample, prediction: Any, extractor: Any | None = None) -> dict:
        return self.evaluate_batch([sample], [prediction])[sample.id]

    def evaluate_batch(self, samples: list[Sample], predictions: list[Any],
                       extractor: Any | None = None) -> dict[str, dict]:
        docs = [{"pdf_id": s.id, "markdown": p.markdown} for s, p in zip(samples, predictions)]
        results = score_batch_venv(_SCORER_DIR, [str(self._gt_path())], docs, timeout_s=7200)
        aggregate = results.pop("__aggregate__", None)
        if aggregate is not None:
            print(f"[omnidocbench] official batch aggregate: "
                  f"{json.dumps(aggregate.get('official'))[:600]}")
        out: dict[str, dict] = {}
        for s in samples:
            r = results.get(s.id)
            if r is None or r.get("error"):
                out[s.id] = {"primary": None, "error": (r or {}).get("error", "no scorer result")}
                continue
            oed = r.get("overall_edit_dist")
            out[s.id] = {"primary": (1.0 - oed) if oed is not None else None,
                         "overall_edit_dist": oed,
                         "text_edit_dist": r.get("text_edit_dist"),
                         "formula_edit_dist": r.get("formula_edit_dist"),
                         "table_edit_dist": r.get("table_edit_dist"),
                         "order_edit_dist": r.get("order_edit_dist"),
                         "table_teds": r.get("table_teds"),
                         "table_teds_structure_only": r.get("table_teds_structure_only"),
                         "n_tables": r.get("n_tables"),
                         "cdm_excluded": r.get("cdm_excluded", True)}
        return out

    def categories(self) -> list[str]:
        return ["PPT2PDF", "academic_literature", "book", "colorful_textbook", "exam_paper",
                "historical_document", "magazine", "newspaper", "note", "research_report"]
