"""Official OmniDocBench end2end scorer — runs in THIS isolated venv, invoked via subprocess.

We wrap the OFFICIAL opendatalab/OmniDocBench evaluation pipeline (installed from GitHub at a
pinned commit as the `src` package, see requirements.txt) — never reimplement matching/metrics.

Contract (mirrors benchmarks/_scorers/olmocr_bench/score.py):
  argv[1] = path to the dataset's OmniDocBench.json (full ground truth, v1.6)
  stdin   = one JSON line per page {"pdf_id": "<GT image basename, e.g. xxx.png>", "markdown": ...}
  stdout  = one JSON result line per page, keyed by pdf_id, plus one {"pdf_id": "__aggregate__"}
            line carrying the OFFICIAL aggregate numbers for the scored subset.

How it works (per batch, ONE official pipeline run):
  1. Write each prediction to <tmp>/preds/<image_basename minus ext>.md — exactly the filename
     the official `End2EndDataset._resolve_prediction_path` expects.
  2. Subset the GT json to the pages present on stdin (page matching in the official pipeline is
     strictly per-page — `_match_single_page` — so subsetting is exact, it only changes which
     pages are averaged).
  3. chdir to a temp dir and call the official `src.core.pipeline.run_config` with the standard
     end2end config (quick_match), CDM REMOVED (formula CDM renders LaTeX via TeX Live +
     ImageMagick + Ghostscript — not installed here; formulas still get the official Edit_dist).
  4. Read the per-page dumps the official pipeline writes to ./result/:
       *_text_block_per_page_edit.json        (upper_len-weighted per-page edit dist — official)
       *_display_formula_per_page_edit.json
       *_table_per_page_edit.json
       *_table_per_table_TEDS.json            (keys "<img>_[i]" per table instance)
       *_reading_order_per_page_edit.json
     and *_metric_result.json for the official aggregates.

Per-page output fields (all edit distances LOWER=better in [0,1]; TEDS HIGHER=better in [0,1]):
  text_edit_dist, formula_edit_dist, table_edit_dist, order_edit_dist  (null if element absent),
  table_teds, table_teds_structure_only (mean over the page's tables), n_tables,
  overall_edit_dist = mean of the present per-element edit dists (v1.0-style overall),
  cdm_excluded: true (the v1.5+ leaderboard "Overall" needs CDM; see README.md).

Env knobs: SCORER_MATCH_WORKERS (default min(8, cpus)), SCORER_TEDS_WORKERS (same default).
"""
import contextlib
import json
import os
import sys
import tempfile


def _workers(env_key, default):
    try:
        return max(1, int(os.environ.get(env_key, "") or default))
    except ValueError:
        return default


def _build_config(gt_path, pred_dir, match_workers, teds_workers):
    # configs/end2end.yaml from the official repo, minus CDM (TeX toolchain not installed).
    return {
        "end2end_eval": {
            "metrics": {
                "text_block": {"metric": ["Edit_dist"]},
                "display_formula": {"metric": ["Edit_dist"]},
                "table": {"metric": ["TEDS", "Edit_dist"], "teds_workers": teds_workers},
                "reading_order": {"metric": ["Edit_dist"]},
            },
            "dataset": {
                "dataset_name": "end2end_dataset",
                "ground_truth": {"data_path": gt_path},
                "prediction": {"data_path": pred_dir},
                "match_method": "quick_match",
                "match_workers": match_workers,
                "quick_match_truncated_timeout_sec": 300,
                "match_timeout_sec": 420,
                "timeout_fallback_max_chunk_span": 10,
                "timeout_fallback_order_penalty": 0.10,
            },
        }
    }


def _load(result_dir, name):
    p = os.path.join(result_dir, name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    gt_path = os.path.abspath(sys.argv[1])
    with open(gt_path, encoding="utf-8") as f:
        gt_all = json.load(f)
    by_img = {os.path.basename(p["page_info"]["image_path"]): p for p in gt_all}

    reqs = [json.loads(l) for l in sys.stdin.read().splitlines() if l.strip().startswith("{")]
    docs, errors = {}, []
    for r in reqs:
        pid = r["pdf_id"]
        if pid in by_img:
            docs[pid] = r.get("markdown", "") or ""
        else:
            errors.append({"pdf_id": pid, "error": "pdf_id not found in OmniDocBench.json "
                                                   "(expected a GT image basename)"})
    if not docs and errors:
        for e in errors:
            print(json.dumps(e), flush=True)
        return

    match_workers = _workers("SCORER_MATCH_WORKERS", min(8, os.cpu_count() or 4))
    teds_workers = _workers("SCORER_TEDS_WORKERS", min(8, os.cpu_count() or 4))

    with tempfile.TemporaryDirectory(prefix="odb_score_") as tmp:
        pred_dir = os.path.join(tmp, "preds")
        os.makedirs(pred_dir)
        for img_name, md in docs.items():
            stem = os.path.splitext(img_name)[0]  # official loader tries <img[:-4]>.md first
            with open(os.path.join(pred_dir, stem + ".md"), "w", encoding="utf-8") as f:
                f.write(md)
        gt_sub_path = os.path.join(tmp, "OmniDocBench_subset.json")
        with open(gt_sub_path, "w", encoding="utf-8") as f:
            json.dump([by_img[i] for i in docs], f, ensure_ascii=False)

        cfg = _build_config(gt_sub_path, pred_dir, match_workers, teds_workers)
        cwd = os.getcwd()
        os.chdir(tmp)  # official pipeline writes to ./result relative to cwd
        try:
            # Keep OUR stdout clean (JSONL protocol): official prints go to stderr.
            with contextlib.redirect_stdout(sys.stderr):
                from src.core.pipeline import build_save_name, run_config
                run_config(cfg)
                save_name = build_save_name(cfg["end2end_eval"])  # "preds_quick_match"
        finally:
            os.chdir(cwd)

        rdir = os.path.join(tmp, "result")
        text_pp = _load(rdir, f"{save_name}_text_block_per_page_edit.json")
        formula_pp = _load(rdir, f"{save_name}_display_formula_per_page_edit.json")
        table_pp = _load(rdir, f"{save_name}_table_per_page_edit.json")
        order_pp = _load(rdir, f"{save_name}_reading_order_per_page_edit.json")
        per_table = _load(rdir, f"{save_name}_per_table_TEDS.json") or \
            _load(rdir, f"{save_name}_table_per_table_TEDS.json")
        metric_all = _load(rdir, f"{save_name}_metric_result.json")

        teds_by_page = {}
        for key, v in (per_table or {}).items():
            img = key.rsplit("_[", 1)[0]
            teds_by_page.setdefault(img, []).append(v)

        for pid in docs:
            eds = {"text_edit_dist": text_pp.get(pid),
                   "formula_edit_dist": formula_pp.get(pid),
                   "table_edit_dist": table_pp.get(pid),
                   "order_edit_dist": order_pp.get(pid)}
            present = [v for v in eds.values() if v is not None]
            tt = teds_by_page.get(pid, [])
            out = {"pdf_id": pid, **eds,
                   "table_teds": (sum(x["TEDS"] for x in tt) / len(tt)) if tt else None,
                   "table_teds_structure_only":
                       (sum(x["TEDS_structure_only"] for x in tt) / len(tt)) if tt else None,
                   "n_tables": len(tt),
                   "overall_edit_dist": (sum(present) / len(present)) if present else None,
                   "cdm_excluded": True}
            print(json.dumps(out), flush=True)
        for e in errors:
            print(json.dumps(e), flush=True)

        # Official aggregates over THIS subset (compare against the leaderboard when the subset
        # is the full 1651 pages): metric_result[element]["all"] and ["page"]["ALL"].
        agg = {"pdf_id": "__aggregate__", "save_name": save_name, "official": {}}
        for el in ("text_block", "display_formula", "table", "reading_order"):
            blk = (metric_all or {}).get(el) or {}
            agg["official"][el] = {"all": blk.get("all"),
                                   "page_ALL": {m: v.get("ALL") for m, v in
                                                (blk.get("page") or {}).items()
                                                if isinstance(v, dict)}}
        print(json.dumps(agg), flush=True)


if __name__ == "__main__":
    main()
