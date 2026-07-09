"""verify-env preflight: report formatting, PASS/WARN/FAIL/exit-code logic, secret presence-only.

Runs WITHOUT a GPU (CI has none) — GPU/dataset probes that shell out or import torch/vllm are
guarded or monkeypatched; nothing here requires CUDA, docker, or network access.
"""
from __future__ import annotations

from tbdoc.core.preflight import (
    FAIL,
    PASS,
    WARN,
    CheckResult,
    PreflightReport,
    check_datasets,
    check_scorers,
    check_secrets,
    check_versions,
)

# ---- CheckResult / report formatting ---------------------------------------------------------

def test_check_result_line_format():
    r = CheckResult("gpu.cuda_available", PASS, found=True, expected=True)
    assert r.line() == "[PASS] gpu.cuda_available: found=True expected=True"


def test_check_result_line_omits_absent_expected_and_detail():
    r = CheckResult("cpu.logical_cores", PASS, found=16)
    assert r.line() == "[PASS] cpu.logical_cores: found=16"


def test_check_result_line_includes_detail_when_present():
    r = CheckResult("dataset.foo", WARN, found="missing", expected="/data/foo",
                    detail="run: gauntlet download foo")
    line = r.line()
    assert line.startswith("[WARN] dataset.foo: found=missing expected=/data/foo")
    assert "run: gauntlet download foo" in line


# ---- PASS/WARN/FAIL classification + exit-code logic -----------------------------------------

def test_report_counts():
    report = PreflightReport()
    report.add(CheckResult("a", PASS, found=1))
    report.add(CheckResult("b", WARN, found=2))
    report.add(CheckResult("c", FAIL, found=3))
    report.add(CheckResult("d", PASS, found=4))
    assert report.counts() == {PASS: 2, WARN: 1, FAIL: 1}


def test_exit_code_zero_when_all_pass():
    report = PreflightReport()
    report.add(CheckResult("a", PASS, found=1))
    report.add(CheckResult("b", PASS, found=2))
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 0


def test_exit_code_nonzero_on_fail_regardless_of_strict():
    report = PreflightReport()
    report.add(CheckResult("a", PASS, found=1))
    report.add(CheckResult("b", FAIL, found=2))
    assert report.exit_code(strict=False) == 1
    assert report.exit_code(strict=True) == 1


def test_warn_alone_is_zero_exit_unless_strict():
    report = PreflightReport()
    report.add(CheckResult("a", PASS, found=1))
    report.add(CheckResult("b", WARN, found=2))
    assert report.exit_code(strict=False) == 0
    assert report.exit_code(strict=True) == 1


def test_lines_matches_results_order():
    report = PreflightReport()
    report.add(CheckResult("a", PASS, found=1))
    report.add(CheckResult("b", WARN, found=2))
    assert report.lines() == [
        "[PASS] a: found=1",
        "[WARN] b: found=2",
    ]


# ---- secret presence-only logic ---------------------------------------------------------------

def test_secret_reports_absent_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    results = check_secrets(names=("OPEN_ROUTER_API_KEY", "HF_TOKEN"), repo_root=tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["secret.OPEN_ROUTER_API_KEY"].status == WARN
    assert by_name["secret.OPEN_ROUTER_API_KEY"].found == "absent"
    assert by_name["secret.HF_TOKEN"].status == WARN


def test_secret_reports_present_when_set_in_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-super-secret-value-should-not-leak")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    results = check_secrets(names=("OPEN_ROUTER_API_KEY", "HF_TOKEN"), repo_root=tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["secret.OPEN_ROUTER_API_KEY"].status == PASS
    assert by_name["secret.OPEN_ROUTER_API_KEY"].found == "present"
    assert by_name["secret.HF_TOKEN"].status == WARN


def test_secret_reports_present_when_set_in_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPEN_ROUTER_API_KEY=sk-another-secret-value\n")
    results = check_secrets(names=("OPEN_ROUTER_API_KEY",), repo_root=tmp_path)
    assert results[0].status == PASS
    assert results[0].found == "present"


def test_secret_value_never_appears_anywhere_in_result(tmp_path, monkeypatch):
    """The whole point of presence-only: the secret value must not leak into found/expected/detail
    or the formatted report line, under any code path (env OR .env)."""
    secret_value = "sk-THIS-VALUE-MUST-NEVER-BE-PRINTED-abc123"
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", secret_value)
    (tmp_path / ".env").write_text(f"HF_TOKEN={secret_value}\n")
    results = check_secrets(names=("OPEN_ROUTER_API_KEY", "HF_TOKEN"), repo_root=tmp_path)
    for r in results:
        assert secret_value not in str(r.found)
        assert secret_value not in str(r.expected)
        assert secret_value not in str(r.detail)
        assert secret_value not in r.line()
    report = PreflightReport()
    report.extend(results)
    assert all(secret_value not in line for line in report.lines())


def test_dotenv_only_parses_key_names(tmp_path):
    from tbdoc.core.preflight import _dotenv_key_names
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "\n"
        "OPEN_ROUTER_API_KEY=sk-value-with-an-equals=sign-in-it\n"
        "HF_TOKEN=hf_anothervalue\n"
    )
    names = _dotenv_key_names(tmp_path / ".env")
    assert names == {"OPEN_ROUTER_API_KEY", "HF_TOKEN"}
    for n in names:
        assert "=" not in n


def test_dotenv_missing_file_returns_empty_set(tmp_path):
    from tbdoc.core.preflight import _dotenv_key_names
    assert _dotenv_key_names(tmp_path / "nope.env") == set()


# ---- version pins -------------------------------------------------------------------------

def test_version_check_pass_on_exact_match(tmp_path, monkeypatch):
    (tmp_path / "requirements.lock").write_text("torch==9.9.9\nvllm==1.2.3\ntransformers==4.5.6\n")
    monkeypatch.setattr("tbdoc.core.preflight._installed_version",
                        lambda pkg: {"torch": "9.9.9", "vllm": "1.2.3", "transformers": "4.5.6"}[pkg])
    results = check_versions(tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["version.torch"].status == PASS
    assert by_name["version.vllm"].status == PASS
    assert by_name["version.transformers"].status == PASS
    assert by_name["version.pin_source"].found == "requirements.lock"


def test_version_check_ignores_local_version_segment(tmp_path, monkeypatch):
    """torch reports '2.11.0+cu130' locally; the lock pins the upstream '2.11.0' — that's a match."""
    (tmp_path / "requirements.lock").write_text("torch==2.11.0\nvllm==0.22.1\ntransformers==5.11.0\n")
    monkeypatch.setattr("tbdoc.core.preflight._installed_version",
                        lambda pkg: {"torch": "2.11.0+cu130", "vllm": "0.22.1",
                                     "transformers": "5.11.0"}[pkg])
    results = check_versions(tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["version.torch"].status == PASS
    assert by_name["version.torch"].found == "2.11.0+cu130"


def test_version_check_warn_on_mismatch(tmp_path, monkeypatch):
    (tmp_path / "requirements.lock").write_text("torch==2.11.0\nvllm==0.22.1\ntransformers==5.11.0\n")
    monkeypatch.setattr("tbdoc.core.preflight._installed_version",
                        lambda pkg: {"torch": "2.9.0", "vllm": "0.22.1", "transformers": "5.11.0"}[pkg])
    results = check_versions(tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["version.torch"].status == WARN


def test_version_check_fail_on_import_error(tmp_path, monkeypatch):
    (tmp_path / "requirements.lock").write_text("torch==2.11.0\n")

    def _boom(pkg):
        raise ImportError(f"no module named {pkg}")

    monkeypatch.setattr("tbdoc.core.preflight._installed_version", _boom)
    results = check_versions(tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["version.torch"].status == FAIL


def test_version_check_no_lock_file_warns_on_pin_source(tmp_path, monkeypatch):
    monkeypatch.setattr("tbdoc.core.preflight._installed_version", lambda pkg: "1.0.0")
    results = check_versions(tmp_path)
    by_name = {r.name: r for r in results}
    assert by_name["version.pin_source"].status == WARN
    assert by_name["version.torch"].status == WARN  # no pin to compare against


# ---- scorers --------------------------------------------------------------------------------

def test_scorer_native_always_pass():
    results = check_scorers({"foo": {"scorer": {"kind": "native"}}}, repo_root="/nonexistent")
    assert results[0].status == PASS


def test_scorer_venv_pass_when_present(tmp_path):
    venv_py = tmp_path / "benchmarks" / "_scorers" / "foo" / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("#!/bin/sh\n")
    results = check_scorers({"foo": {"scorer": {"kind": "venv"}}}, repo_root=tmp_path)
    assert results[0].status == PASS
    assert results[0].found == "present"


def test_scorer_venv_warn_when_missing(tmp_path):
    results = check_scorers({"foo": {"scorer": {"kind": "venv"}}}, repo_root=tmp_path)
    assert results[0].status == WARN
    assert results[0].found == "absent"
    assert "uv venv" in results[0].detail


def test_scorer_container_warn_when_docker_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("tbdoc.core.preflight._docker_image_present", lambda image: False)
    results = check_scorers({"foo": {"scorer": {"kind": "container", "image": "foo:v1"}}},
                             repo_root=tmp_path)
    assert results[0].status == WARN


def test_scorer_container_pass_when_image_present(tmp_path, monkeypatch):
    monkeypatch.setattr("tbdoc.core.preflight._docker_image_present", lambda image: True)
    results = check_scorers({"foo": {"scorer": {"kind": "container", "image": "foo:v1"}}},
                             repo_root=tmp_path)
    assert results[0].status == PASS


# ---- datasets (no network / no HF calls — pure filesystem probing) ---------------------------

def test_dataset_warn_when_missing(tmp_path):
    results = check_datasets({"foo": {"data_dir": str(tmp_path / "nope")}}, repo_root=tmp_path)
    assert results[0].status == WARN
    assert "gauntlet download foo" in results[0].detail


def test_dataset_pass_when_present_no_revision_metadata(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("x")
    results = check_datasets(
        {"foo": {"data_dir": str(data_dir), "source": {"revision": "abc123"}}}, repo_root=tmp_path)
    assert results[0].status == PASS
    assert results[0].found == "present"


def test_dataset_pass_when_revision_matches_metadata(tmp_path):
    data_dir = tmp_path / "data"
    meta_dir = data_dir / ".cache" / "huggingface" / "download"
    meta_dir.mkdir(parents=True)
    (meta_dir / "a.metadata").write_text("abc123def456\nsome-etag\n123.0\n")
    (data_dir / "file.txt").write_text("x")
    results = check_datasets(
        {"foo": {"data_dir": str(data_dir), "source": {"revision": "abc123"}}}, repo_root=tmp_path)
    assert results[0].status == PASS
    assert "abc123def456" in results[0].found


def test_dataset_warn_when_revision_mismatches_metadata(tmp_path):
    data_dir = tmp_path / "data"
    meta_dir = data_dir / ".cache" / "huggingface" / "download"
    meta_dir.mkdir(parents=True)
    (meta_dir / "a.metadata").write_text("000000000000\nsome-etag\n123.0\n")
    (data_dir / "file.txt").write_text("x")
    results = check_datasets(
        {"foo": {"data_dir": str(data_dir), "source": {"revision": "abc123"}}}, repo_root=tmp_path)
    assert results[0].status == WARN


# ---- CLI wiring (guard the heavy probes so this runs on CI with no GPU/docker) ----------------

def test_verify_env_cli_exits_nonzero_on_fail(monkeypatch):
    from click.testing import CliRunner

    from tbdoc.cli import main

    def fake_report():
        report = PreflightReport()
        report.add(CheckResult("gpu.cuda_available", FAIL, found=False, expected=True))
        return report

    monkeypatch.setattr("tbdoc.core.preflight.run_preflight", lambda *a, **kw: fake_report())
    runner = CliRunner()
    result = runner.invoke(main, ["verify-env"])
    assert result.exit_code != 0
    assert "[FAIL] gpu.cuda_available" in result.output


def test_verify_env_cli_strict_fails_on_warn_only(monkeypatch):
    from click.testing import CliRunner

    from tbdoc.cli import main

    def fake_report():
        report = PreflightReport()
        report.add(CheckResult("secret.HF_TOKEN", WARN, found="absent", expected="present"))
        return report

    monkeypatch.setattr("tbdoc.core.preflight.run_preflight", lambda *a, **kw: fake_report())
    runner = CliRunner()
    ok = runner.invoke(main, ["verify-env"])
    strict = runner.invoke(main, ["verify-env", "--strict"])
    assert ok.exit_code == 0
    assert strict.exit_code != 0
