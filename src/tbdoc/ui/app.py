"""FastAPI app factory for `gauntlet ui` — the C3a read-only results dashboard.

Localhost-only, read-only: never writes under results/, configs/, or touches scorer/
instrument/model code; never makes a network call. See
docs/superpowers/specs/2026-07-09-dashboard-ui-design.md.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

from tbdoc.core.registry import Registry
from tbdoc.ui import data as uidata
from tbdoc.ui import gold as uigold
from tbdoc.ui import runs as uiruns

_STATIC_DIR = Path(__file__).parent / "static"


def _safe_seg(value: str, label: str) -> str:
    """Reject path traversal in a single path component (model/bench/run_id).

    These strings are joined into filesystem paths (predictions/<model>/<bench>.jsonl,
    raw/<model>/<bench>.jsonl). Without this guard a query like model="../../etc" walks
    outside the results dir and reads arbitrary *.jsonl files (confirmed in review)."""
    if not value or "/" in value or "\\" in value or value in (".", ".."):
        raise HTTPException(400, f"invalid {label} {value!r}")
    return value


def _safe_run_dir(results_dir: Path, run_id: str | None) -> Path:
    if run_id:
        _safe_seg(run_id, "run_id")
    try:
        return uiruns.resolve_run(results_dir, run_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


def create_app(results_dir: str | Path = "results/runs",
               config_dir: str | Path = "configs") -> FastAPI:
    results_dir = Path(results_dir)
    registry = Registry(str(config_dir))
    app = FastAPI(title="trial-by-doc dashboard", docs_url="/api/docs")

    @app.middleware("http")
    async def _no_store_api(request, call_next):
        # A results dashboard must never serve stale data after a re-run/re-score.
        resp = await call_next(request)
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---- pages ---------------------------------------------------------------
    @app.get("/")
    def index():
        # The app shell carries all the inlined JS/CSS; never let a browser serve a stale shell
        # after the dashboard is updated (the vendored assets below stay cacheable by filename).
        return FileResponse(_STATIC_DIR / "index.html",
                            headers={"Cache-Control": "no-store"})

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(_STATIC_DIR / "ac-monogram-dark.svg", media_type="image/svg+xml")

    # ---- API ------------------------------------------------------------------
    @app.get("/api/runs")
    def api_runs():
        out = []
        for rid in uiruns.list_run_ids(results_dir):
            run_dir = results_dir / rid
            cells = uidata.list_cells(run_dir)
            out.append({
                "run_id": rid,
                "mtime": run_dir.stat().st_mtime,
                "models": sorted({c["model"] for c in cells}),
                "benches": sorted({c["bench"] for c in cells}),
                "n_scored": sum(c["n"] for c in cells),
            })
        return out

    @app.get("/api/scoreboard")
    def api_scoreboard(run_id: str | None = None):
        run_dir = _safe_run_dir(results_dir, run_id)
        return uidata.scoreboard_payload(run_dir, registry)

    @app.get("/api/benchmarks")
    def api_benchmarks():
        # Small preview cap — this route decodes preview page images per bench (via the
        # bench's own load()) just to produce a sample count; the exact size of a
        # 1000+-page bench isn't the point of an explorer card, so keep it snappy.
        return uidata.bench_catalog(registry, preview_cap=20)

    @app.get("/api/benchmarks/{bench}/gallery")
    def api_bench_gallery(bench: str, n: int = 6, run_id: str | None = None):
        meta = registry.benchmarks.get(bench)
        if meta is None:
            raise HTTPException(404, f"unknown benchmark {bench!r}")
        src = meta.get("source") or {}
        license_ = (src.get("license") or "").lower()
        if license_ not in uidata.GALLERY_LICENSE_ALLOWLIST:
            raise HTTPException(
                403, f"license {src.get('license')!r} for {bench!r} is not on the "
                     "redistribution allowlist — metadata only (see spec §4.2)")
        run_dir = _safe_run_dir(results_dir, run_id)
        sample_model = _any_model_for(run_dir, bench)
        ids = uidata.sample_ids(run_dir, sample_model, bench, limit=n) if sample_model else []
        out = []
        for sid in ids[:n]:
            out.append({"sample_id": sid,
                        "thumbnail_url": f"/api/page-image?run_id={run_dir.name}&bench={bench}"
                                         f"&sample_id={sid}"})
        return {"bench": bench, "license": src.get("license"), "items": out}

    @app.get("/api/perf")
    def api_perf(run_id: str | None = None):
        return uidata.perf_payload(_safe_run_dir(results_dir, run_id))

    @app.get("/api/tier-b")
    def api_tier_b(run_id: str | None = None):
        return uidata.tier_b_payload(_safe_run_dir(results_dir, run_id))

    @app.get("/api/cost")
    def api_cost():
        return uidata.cost_payload()

    @app.get("/api/robustness")
    def api_robustness(run_id: str | None = None):
        return uidata.robustness_payload(_safe_run_dir(results_dir, run_id))

    @app.get("/api/provenance")
    def api_provenance(run_id: str | None = None):
        return uidata.provenance_payload(_safe_run_dir(results_dir, run_id))

    @app.get("/api/samples")
    def api_samples(run_id: str | None, model: str, bench: str, limit: int = 200):
        run_dir = _safe_run_dir(results_dir, run_id)
        model = _safe_seg(model, "model")
        bench = _safe_seg(bench, "bench")
        return {"model": model, "bench": bench,
                "sample_ids": uidata.sample_ids(run_dir, model, bench, limit=limit),
                "scored": uidata.scored_sample_ids(run_dir, model, bench, limit=limit)}

    @app.get("/api/example")
    def api_example(run_id: str | None, model: str, bench: str, sample_id: str):
        run_dir = _safe_run_dir(results_dir, run_id)
        model = _safe_seg(model, "model")
        bench = _safe_seg(bench, "bench")
        pred = uidata.prediction_record(run_dir, model, bench, sample_id)
        raw = uidata.raw_record(run_dir, model, bench, sample_id)
        if pred is None and raw is None:
            raise HTTPException(404, f"no record for model={model!r} bench={bench!r} "
                                      f"sample_id={sample_id!r} in run {run_dir.name!r}")
        pred_md = ((pred or {}).get("prediction") or {})
        pred_md = pred_md.get("markdown") if isinstance(pred_md, dict) else None
        meta = registry.benchmarks.get(bench, {})
        src = meta.get("source") or {}
        gold: dict[str, Any] = {"kind": "unknown", "note": "bench not found in registry"}
        if bench in registry.benchmarks:
            try:
                ba = registry.bench(bench)
                sample = uigold.find_sample(ba, sample_id)
                if sample is not None:
                    gold = uigold.gold_view(bench, ba, sample, (raw or {}).get("metrics"))
                else:
                    gold = {"kind": "unknown",
                            "note": f"sample_id {sample_id!r} not found in bench.load()"}
            except Exception as e:
                gold = {"kind": "unknown", "note": f"gold lookup failed: {e}"}
        # Scorer-aligned value presence for the QA workbench: highlight the field VALUES the
        # b1 scorer credits and chip only the ones it counts missing (never the raw key=value
        # string, which the scorer never looks for). Keeps chip/highlight consistent with b1.
        gold_match = (uidata.qa_value_presence(pred_md, gold.get("answers") or [])
                      if gold.get("kind") == "qa" and isinstance(pred_md, str) else None)
        return {
            "run_id": run_dir.name, "model": model, "bench": bench, "sample_id": sample_id,
            "category": (raw or {}).get("category"),
            "tier": meta.get("tier"), "provenance": meta.get("provenance"),
            "license": src.get("license"),
            "image_url": f"/api/page-image?run_id={run_dir.name}&bench={bench}"
                          f"&sample_id={sample_id}",
            "prediction": pred,
            "gold": gold,
            "gold_match": gold_match,
            "metrics": (raw or {}).get("metrics"),
            "telemetry": (raw or {}).get("telemetry"),
            "error": (raw or {}).get("error") or (pred or {}).get("error"),
            "model_revision": (raw or {}).get("model_revision"),
        }

    @app.get("/api/page-image")
    def api_page_image(run_id: str | None, bench: str, sample_id: str, page: int = 0):
        _safe_run_dir(results_dir, run_id)  # 404s on an unknown/invalid run_id
        if bench not in registry.benchmarks:
            raise HTTPException(404, f"unknown benchmark {bench!r}")
        ba = registry.bench(bench)
        sample = uigold.find_sample(ba, sample_id)
        if sample is None or not sample.pages:
            raise HTTPException(404, f"no page image for sample_id={sample_id!r} in {bench!r}")
        page = max(0, min(page, len(sample.pages) - 1))
        img = sample.pages[page]
        if not hasattr(img, "save"):  # some adapters may yield a path string
            raise HTTPException(500, f"sample page is not a PIL image ({type(img)!r})")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")

    return app


def _any_model_for(run_dir: Path, bench: str) -> str | None:
    for c in uidata.list_cells(run_dir):
        if c["bench"] == bench:
            return c["model"]
    return None
