"""Deterministic segmentation metrics (Tier C) — pure python, no LLM anywhere.

Definitions from the PSS literature:
- boundary F1: per-page binary "starts a new document" P/R/F1 (page 0 excluded — it's
  always a boundary). Standard but inflated by singleton-heavy data; report with PQ.
- document-level Panoptic Quality (OpenPSS, van Heusden et al., TPDL 2024,
  doi 10.1007/978-3-031-72437-4_24): docs are page SETS; a (gold, pred) pair matches
  iff page-set IoU > 0.5 (guarantees 1-to-1). RQ = F1 over matches, SQ = mean IoU of
  matches, PQ = RQ * SQ.
- STP (straight-through processing, TABME++ arXiv 2408.11981): fraction of streams
  segmented perfectly — the operations-facing headline.
"""
from __future__ import annotations


def _groups(boundaries: list[int], n_pages: int) -> list[frozenset[int]]:
    cuts = sorted({0, *[b for b in boundaries if 0 < b < n_pages]})
    cuts.append(n_pages)
    return [frozenset(range(cuts[i], cuts[i + 1])) for i in range(len(cuts) - 1)]


def boundary_f1(pred: list[int], gold: list[int], n_pages: int) -> dict[str, float]:
    p = {b for b in pred if 0 < b < n_pages}
    g = {b for b in gold if 0 < b < n_pages}
    tp = len(p & g)
    prec = tp / len(p) if p else 1.0   # no predictions -> vacuously no false positives
    rec = tp / len(g) if g else 1.0    # no gold boundaries -> vacuously all recalled
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}


def panoptic_quality(pred: list[int], gold: list[int], n_pages: int) -> dict[str, float]:
    P, G = _groups(pred, n_pages), _groups(gold, n_pages)
    matches: list[float] = []
    used: set[int] = set()
    for gset in G:
        for j, pset in enumerate(P):
            if j in used:
                continue
            iou = len(gset & pset) / len(gset | pset)
            if iou > 0.5:               # IoU>0.5 guarantees 1-to-1 matching
                matches.append(iou)
                used.add(j)
                break
    tp = len(matches)
    fp, fn = len(P) - tp, len(G) - tp
    rq = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    sq = sum(matches) / tp if tp else 0.0
    return {"rq": round(rq, 4), "sq": round(sq, 4), "pq": round(rq * sq, 4)}


def segmentation_metrics(pred: list[int], gold: list[int], n_pages: int) -> dict[str, float]:
    """Full Tier-C metric set for one stream. primary = PQ."""
    bf = boundary_f1(pred, gold, n_pages)
    pq = panoptic_quality(pred, gold, n_pages)
    perfect = _groups(pred, n_pages) == _groups(gold, n_pages)
    return {"primary": pq["pq"], **pq,
            "boundary_precision": bf["precision"], "boundary_recall": bf["recall"],
            "boundary_f1": bf["f1"], "perfect": 1.0 if perfect else 0.0}
