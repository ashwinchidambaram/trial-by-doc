"""Route tests for `gauntlet ui` (C3a) against the real, already-scored v1-baseline run.

Read-only: exercises the FastAPI app in-process via TestClient (no network bind, no
uvicorn), over this repo's real results/runs/v1-baseline + configs/ — nothing here writes
to either. Kept intentionally light on the slow full-catalog path (§ see
test_bench_catalog_function below) since /api/benchmarks decodes preview images for every
registered bench.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tbdoc.core.registry import Registry
from tbdoc.ui import data as uidata
from tbdoc.ui import runs as uiruns
from tbdoc.ui.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results" / "runs"
CONFIG_DIR = REPO_ROOT / "configs"

pytestmark = pytest.mark.skipif(
    not (RESULTS_DIR / "v1-baseline" / "raw").is_dir(),
    reason="v1-baseline run not present in this checkout",
)


@pytest.fixture(scope="module")
def client():
    app = create_app(results_dir=RESULTS_DIR, config_dir=CONFIG_DIR)
    return TestClient(app)


def test_index_shell_is_no_store(client):
    # The app shell inlines all JS/CSS; it must not be browser-cached or an updated dashboard
    # serves stale UI (regression: a cached shell hid a workbench fix during live testing).
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


def test_runs_lists_v1_baseline(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    ids = {row["run_id"] for row in r.json()}
    assert "v1-baseline" in ids


def test_scoreboard_has_14_models(client):
    r = client.get("/api/scoreboard", params={"run_id": "v1-baseline"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["models"]) == 14
    assert "realdoc_qa" in body["benches"]
    assert body["n_scored"] > 0
    # every bench column carries provenance/license metadata (leaderboard header badges)
    for b in body["benches"]:
        assert "tier" in body["bench_meta"][b]


def test_example_join_realdoc_qa_markdown_and_gold(client):
    r = client.get("/api/example", params={
        "run_id": "v1-baseline", "model": "qwen25vl", "bench": "realdoc_qa",
        "sample_id": "finance_q1",
    })
    assert r.status_code == 200
    body = r.json()
    md = body["prediction"]["prediction"]["markdown"]
    assert isinstance(md, str) and len(md) > 50
    assert body["gold"]["kind"] == "qa"
    assert body["gold"]["answers"]
    assert body["metrics"]["b1"] in (0.0, 1.0)
    assert body["image_url"].startswith("/api/page-image")


def test_example_gold_match_agrees_with_b1(client):
    # The workbench "missing" chip must not contradict the b1 score. finance_q1 is a passing
    # extractive QA item (b1==1.0): every gold VALUE is present, so gold_match.missing is empty
    # and the value list is offered for highlight (regression: naive whole "key=value" matching
    # always reported missing even when the scorer credited the value).
    r = client.get("/api/example", params={
        "run_id": "v1-baseline", "model": "olmocr2", "bench": "realdoc_qa",
        "sample_id": "finance_q1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["b1"] == 1.0
    gm = body["gold_match"]
    assert gm is not None
    assert gm["missing"] == []                 # nothing chipped on a passing sample
    assert gm["values"] and gm["present"] == gm["values"]


def test_example_gold_match_reports_missing_on_failure(client):
    # A b1==0 extractive item must chip every gold value as missing (present split empty).
    r = client.get("/api/example", params={
        "run_id": "v1-baseline", "model": "tesseract", "bench": "realdoc_qa",
        "sample_id": "medical_healthcare_q2",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["b1"] == 0.0
    gm = body["gold_match"]
    assert gm and gm["missing"] and gm["present"] == []


def test_example_join_unknown_sample_404s(client):
    r = client.get("/api/example", params={
        "run_id": "v1-baseline", "model": "qwen25vl", "bench": "realdoc_qa",
        "sample_id": "not-a-real-sample-id",
    })
    assert r.status_code == 404


def test_page_image_returns_real_png(client):
    r = client.get("/api/page-image", params={
        "run_id": "v1-baseline", "bench": "realdoc_qa", "sample_id": "finance_q1",
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(r.content) > 1000


def test_olmocr_bench_gold_is_unit_tests_with_pass_fail(client):
    ids = client.get("/api/samples", params={
        "run_id": "v1-baseline", "model": "qwen25vl", "bench": "olmocr_bench",
    }).json()["sample_ids"]
    assert ids
    r = client.get("/api/example", params={
        "run_id": "v1-baseline", "model": "qwen25vl", "bench": "olmocr_bench",
        "sample_id": ids[0],
    })
    assert r.status_code == 200
    gold = r.json()["gold"]
    assert gold["kind"] == "unit_tests"
    assert isinstance(gold["tests"], list)


def test_samples_and_example_reject_path_traversal(client):
    # model/bench are joined into predictions/<model>/<bench>.jsonl — a traversal
    # payload must be refused (400), not walked outside the results dir (review Critical #1).
    traversal = "../../../../etc"
    for route, params in [
        ("/api/samples", {"run_id": "v1-baseline", "model": traversal, "bench": "x"}),
        ("/api/samples", {"run_id": "v1-baseline", "model": "qwen25vl", "bench": traversal}),
        ("/api/example", {"run_id": "v1-baseline", "model": traversal, "bench": "x",
                          "sample_id": "s"}),
        ("/api/example", {"run_id": "v1-baseline", "model": "qwen25vl", "bench": "..",
                          "sample_id": "s"}),
    ]:
        r = client.get(route, params=params)
        assert r.status_code == 400, f"{route} {params} → {r.status_code}"


def test_perf_endpoint_matches_report(client):
    body = client.get("/api/perf", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "olmocr2")
    assert row["median_s"] == 13.69 and row["peak_vram_gb"] == 28.8


def test_tier_b_endpoint_has_reader_and_coverage(client):
    body = client.get("/api/tier-b", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "olmocr2")
    assert row["b1"] == 0.689 and row["coverage"]["extractive"] == 90
    assert "1.5B" in (row["reader"] or "") or row["reader"]


def test_robustness_endpoint_curve(client):
    body = client.get("/api/robustness", params={"run_id": "v1-baseline"}).json()
    row = next(r for r in body if r["model"] == "tesseract")
    assert row["clean"] > row["light"] > row["heavy"]      # monotone degradation
    assert 0 <= row["retained_pct"] <= 100


def test_cost_endpoint_has_classic_and_self_host(client):
    body = client.get("/api/cost").json()
    assert any(r["engine"] == "tesseract" for r in body["classic"])
    assert any(r["model"] == "olmocr2" for r in body["self_host"])


def test_provenance_endpoint(client):
    body = client.get("/api/provenance", params={"run_id": "v1-baseline"}).json()
    assert "hardware" in body and "git_sha" in body
    assert body["models"]  # per-model revisions present


def test_samples_scored_sorts_worst_first(client):
    body = client.get("/api/samples", params={
        "run_id": "v1-baseline", "model": "tesseract", "bench": "realdoc_qa"}).json()
    prims = [s["primary"] for s in body["scored"] if s["primary"] is not None]
    assert prims == sorted(prims)   # ascending == worst first


def test_gallery_gated_for_unspecified_license(client):
    # omnidocbench's license is "unspecified" (verified — no tag on the HF dataset card),
    # so the explorer gallery must refuse to serve thumbnails for it (spec §4.2/§4.3).
    r = client.get("/api/benchmarks/omnidocbench/gallery", params={"run_id": "v1-baseline"})
    assert r.status_code == 403


def test_gallery_allowed_for_odc_by_license(client):
    r = client.get("/api/benchmarks/olmocr_bench/gallery",
                   params={"run_id": "v1-baseline", "n": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["license"] == "odc-by"
    assert len(body["items"]) <= 2
    for item in body["items"]:
        assert item["thumbnail_url"].startswith("/api/page-image")


def test_localhost_only_refuses_wildcard_bind():
    from click.testing import CliRunner

    from tbdoc.cli import main
    result = CliRunner().invoke(main, ["ui", "--host", "0.0.0.0", "--no-browser"])
    assert result.exit_code != 0
    assert "localhost" in result.output.lower() or "refusing" in result.output.lower()


# ---- lower-level unit coverage (fast — bounded preview_cap, no HTTP layer) --------------

def test_resolve_run_picks_v1_baseline_or_newer(tmp_path):
    (tmp_path / "a" / "raw").mkdir(parents=True)
    (tmp_path / "b" / "raw").mkdir(parents=True)
    import os
    os.utime(tmp_path / "a", (1, 1))
    os.utime(tmp_path / "b", (2, 2))
    assert uiruns.resolve_run(tmp_path, None).name == "b"
    assert uiruns.resolve_run(tmp_path, "a").name == "a"
    with pytest.raises(FileNotFoundError):
        uiruns.resolve_run(tmp_path, "does-not-exist")


def test_bench_catalog_function_small_cap():
    registry = Registry(str(CONFIG_DIR))
    catalog = uidata.bench_catalog(registry, preview_cap=3)
    keys = {c["key"] for c in catalog}
    assert {"omnidocbench", "olmocr_bench", "realdoc_qa", "merged_forms"} <= keys
    omni = next(c for c in catalog if c["key"] == "omnidocbench")
    assert omni["gallery_allowed"] is False   # license: unspecified
    olm = next(c for c in catalog if c["key"] == "olmocr_bench")
    assert olm["gallery_allowed"] is True     # license: odc-by
