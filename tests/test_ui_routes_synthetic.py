"""UI route tests over a SYNTHETIC run — runs everywhere, including CI.

tests/test_ui_routes.py exercises the dashboard against the real v1-baseline data and
self-skips on checkouts without it (raw/ is gitignored), which left the routes — and the
path-traversal regression — with zero CI coverage. This module builds its own tiny run
in tmp_path so the security guard and the fresh-clone summary fallback are always tested.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import DummyModel
from fastapi.testclient import TestClient

from tbdoc.runner.matrix import run_matrix
from tbdoc.ui.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "configs"


@pytest.fixture(scope="module")
def run_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("ui-synth")
    from conftest import DummyBench
    run_matrix(models=["m1", "m2"], benches=["b1"],
               model_factory=lambda k: DummyModel(k), bench_factory=lambda k: DummyBench(k),
               results_dir=root, run_id="synth", log=lambda *_: None)
    return root


@pytest.fixture(scope="module")
def client(run_root):
    return TestClient(create_app(results_dir=run_root, config_dir=CONFIG_DIR))


def test_runs_lists_synthetic(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    rows = {row["run_id"]: row for row in r.json()}
    assert rows["synth"]["n_scored"] == 8


def test_scoreboard_payload(client):
    r = client.get("/api/scoreboard", params={"run_id": "synth"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["models"]) == {"m1", "m2"}
    assert body["source"] == "raw"
    assert body["cells"]["m1|b1"]["n"] == 4


def test_path_traversal_is_rejected(client):
    # regression guard: model/bench/run_id are joined into filesystem paths
    for params in ({"run_id": "synth", "model": "../../etc", "bench": "b1"},
                   {"run_id": "synth", "model": "m1", "bench": "..\\..\\etc"}):
        r = client.get("/api/samples", params=params)
        assert r.status_code == 400
    assert client.get("/api/scoreboard", params={"run_id": "../outside"}).status_code == 400


def test_unknown_run_is_404(client):
    assert client.get("/api/scoreboard", params={"run_id": "nope"}).status_code == 404


def test_fresh_clone_serves_from_summary(run_root):
    # simulate the published-run shape: tracked files only, raw/ + predictions/ absent
    clone = run_root / "clone-view"
    clone.mkdir()
    dst = clone / "synth"
    shutil.copytree(run_root / "synth", dst,
                    ignore=shutil.ignore_patterns("raw", "predictions"))
    c = TestClient(create_app(results_dir=clone, config_dir=CONFIG_DIR))
    runs = c.get("/api/runs").json()
    assert [r["run_id"] for r in runs] == ["synth"]          # summary.json qualifies the dir
    body = c.get("/api/scoreboard", params={"run_id": "synth"}).json()
    assert body["source"] == "summary"
    assert body["cells"]["m1|b1"]["n"] == 4                   # same numbers as raw-backed view
    # per-sample endpoints stay honestly empty (no records in a fresh clone)
    samples = c.get("/api/samples",
                    params={"run_id": "synth", "model": "m1", "bench": "b1"}).json()
    assert samples["sample_ids"] == []
