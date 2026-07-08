"""gauntlet — the trial-by-doc CLI. Every command is resumable and provenance-stamped."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from tbdoc.core.registry import Registry, load_yaml
from tbdoc.core.secrets import load_dotenv


def _registry() -> Registry:
    return Registry("configs")


def _matrix_cfg() -> dict:
    return load_yaml("configs/matrix.yaml")


def _profile(name: str) -> dict:
    prof = (_matrix_cfg().get("profiles") or {}).get(name)
    if not prof:
        raise click.ClickException(f"unknown profile '{name}' (configs/matrix.yaml)")
    return prof


@click.group()
def main():
    """trial-by-doc: run OCR/doc-intelligence models through the benchmark gauntlet."""
    load_dotenv()


@main.command()
@click.option("--models", "-m", help="comma-separated model keys (default: profile)")
@click.option("--benches", "-b", help="comma-separated benchmark keys (default: profile)")
@click.option("--profile", "-p", default="smoke", show_default=True)
@click.option("--max-samples", type=int, default=None, help="cap samples per cell")
@click.option("--run-id", default=None, help="resume an existing run")
@click.option("--phase", type=click.Choice(["all", "infer", "score"]), default="all")
@click.option("--rescore", is_flag=True, help="re-score even already-scored samples")
@click.option("--no-llm-instruments", is_flag=True,
              help="strictly LLM-free measurement path (Tier A + native segmenters only)")
def run(models, benches, profile, max_samples, run_id, phase, rescore, no_llm_instruments):
    """Run the matrix (infer -> score), resumable."""
    from tbdoc.core.hardware import fingerprint as hw_fingerprint
    from tbdoc.runner.matrix import run_matrix
    prof = _profile(profile)
    model_keys = [m.strip() for m in models.split(",")] if models else prof["models"]
    bench_keys = [b.strip() for b in benches.split(",")] if benches else prof["benchmarks"]
    if max_samples is None:
        max_samples = prof.get("max_samples")
    reg = _registry()
    benches_meta = {b: reg.benchmarks.get(b, {}) for b in bench_keys}
    if no_llm_instruments:
        drop = [b for b, meta in benches_meta.items() if meta.get("tier") == "B"]
        if drop:
            click.echo(f"[no-llm-instruments] dropping Tier B benches: {', '.join(drop)}")
        bench_keys = [b for b in bench_keys if b not in drop]
    phases = ("infer", "score") if phase == "all" else (phase,)
    try:
        hw = hw_fingerprint()
    except Exception:
        hw = None
    summary = run_matrix(
        models=model_keys, benches=bench_keys,
        model_factory=reg.model, bench_factory=reg.bench,
        results_dir=(_matrix_cfg().get("run") or {}).get("results_dir", "results/runs"),
        run_id=run_id, max_samples=max_samples, phases=phases, rescore=rescore,
        boundary_judge=None if no_llm_instruments else _boundary_judge(reg),
        hardware=hw, instruments_meta=reg.instruments)
    click.echo(json.dumps(summary, indent=2))


def _boundary_judge(reg: Registry):
    bj = (reg.instruments or {}).get("boundary_judge") or {}
    if not bj.get("chosen"):
        return None
    from tbdoc.instruments.boundary_judge import BoundaryJudge  # M3
    return BoundaryJudge(bj)


@main.command("validate-adapter")
@click.argument("model_key")
@click.option("--pages", type=int, default=3, show_default=True)
def validate_adapter(model_key, pages):
    """Smoke-test a model adapter (shape, telemetry, secrets, clean unload)."""
    from tbdoc.runner.validate import validate_adapter as _va
    click.echo(f"validating adapter '{model_key}' on {pages} sample pages:")
    checks = _va(_registry(), model_key, n_pages=pages)
    failed = [c for c in checks if not c[1]]
    click.echo(f"\n{'PASS' if not failed else 'FAIL'} — {len(checks) - len(failed)}/{len(checks)} checks")
    if failed:
        sys.exit(1)


@main.command()
@click.option("--run-id", default=None, help="default: latest run")
@click.option("--format", "fmt", type=click.Choice(["csv", "md"]), default="md")
@click.option("--by", type=click.Choice(["bench", "tier", "category", "provenance"]), default="bench")
def scoreboard(run_id, fmt, by):
    """Print the scoreboard for a run."""
    from tbdoc.report.scoreboard import render
    click.echo(render(_latest_run(run_id), fmt=fmt, by=by, registry=_registry()))


@main.command("list")
@click.argument("what", type=click.Choice(["models", "benches"]))
def list_cmd(what):
    """List registered models or benchmarks."""
    reg = _registry()
    if what == "models":
        for k, e in reg.models.items():
            click.echo(f"{k:20s} kind={e.get('kind','?'):6s} "
                       f"{e.get('repo_id') or e.get('provider','')}  "
                       f"license={e.get('license', e.get('commercial_use', '?'))}")
    else:
        for k, e in reg.benchmarks.items():
            click.echo(f"{k:20s} tier={e.get('tier','?')} unit={e.get('unit','page'):8s} "
                       f"provenance={e.get('provenance','official')}")


@main.command()
@click.option("--run-id", default=None)
def status(run_id):
    """Show live run progress (status.json)."""
    p = Path(_latest_run(run_id)) / "status.json"
    if not p.exists():
        raise click.ClickException(f"no status.json in {p.parent}")
    click.echo(p.read_text())


@main.command()
@click.argument("bench", default="all")
def download(bench):
    """Download benchmark data at pinned revisions (M2)."""
    raise click.ClickException("landing in M2 — see the build plan")


@main.command("estimate-cost")
@click.option("--models", "-m", required=True)
@click.option("--benches", "-b", required=True)
def estimate_cost(models, benches):
    """Estimate API spend for a run BEFORE any calls (M2)."""
    raise click.ClickException("landing in M2 — see the build plan")


def _latest_run(run_id: str | None) -> Path:
    root = Path((_matrix_cfg().get("run") or {}).get("results_dir", "results/runs"))
    if run_id:
        return root / run_id
    runs = sorted(root.glob("run_*"))
    if not runs:
        raise click.ClickException(f"no runs under {root}")
    return runs[-1]


if __name__ == "__main__":
    main()
