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
