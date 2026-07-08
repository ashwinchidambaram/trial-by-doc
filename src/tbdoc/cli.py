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
    from tbdoc.core.hardware import capture_hardware_metadata as hw_fingerprint
    from tbdoc.runner.matrix import run_matrix
    prof = _profile(profile)
    model_keys = [m.strip() for m in models.split(",")] if models else prof["models"]
    prof_benches = prof["benchmarks"]
    bench_caps = prof_benches if isinstance(prof_benches, dict) else {}
    if benches:
        bench_keys = [b.strip() for b in benches.split(",")]
    else:
        bench_keys = list(prof_benches)
    if max_samples is None:
        max_samples = bench_caps or prof.get("max_samples")
    reg = _registry()
    benches_meta = {b: reg.benchmarks.get(b, {}) for b in bench_keys}
    if no_llm_instruments:
        drop = [b for b, meta in benches_meta.items() if meta.get("tier") == "B"]
        if drop:
            click.echo(f"[no-llm-instruments] dropping Tier B benches: {', '.join(drop)}")
        bench_keys = [b for b in bench_keys if b not in drop]
    phases = ("infer", "score") if phase == "all" else (phase,)
    # API budget guard (house rule): estimated spend must clear the per-model cap
    # BEFORE any call is made.
    if "infer" in phases:
        cap = ((_matrix_cfg().get("run") or {}).get("budget") or {}).get("max_usd_per_model")
        if cap is not None:
            est = _estimate(reg, model_keys, bench_keys, max_samples)
            over = {m: usd for m, usd in est.items() if usd > cap}
            if over:
                raise click.ClickException(
                    f"budget guard: estimated spend exceeds max_usd_per_model=${cap}: "
                    + ", ".join(f"{m}=${u:.2f}" for m, u in over.items())
                    + " — shrink the run or raise the cap in configs/matrix.yaml")
            spend = {m: u for m, u in est.items() if u > 0}
            if spend:
                click.echo("estimated API spend: "
                           + ", ".join(f"{m}=${u:.4f}" for m, u in spend.items()))
    try:
        hw = hw_fingerprint()
    except Exception:
        hw = None
    # Tier B needs the frozen extractor during the SCORE phase (own GPU pass, after
    # OCR models have unloaded). Lazy: constructed only if a selected bench needs it.
    extractor = None
    if "score" in phases and not no_llm_instruments:
        needs = [b for b in bench_keys
                 if (reg.benchmarks.get(b, {}).get("scorer") or {}).get("instrument") == "extractor"]
        if needs:
            from tbdoc.instruments.vllm_extractor import VLLMExtractor
            extractor = VLLMExtractor()
            click.echo(f"[instruments] frozen extractor {extractor.identity} for: {', '.join(needs)}")
    judge = None
    if not no_llm_instruments and any(
            reg.benchmarks.get(b, {}).get("tier") == "C" for b in bench_keys):
        from tbdoc.instruments.boundary_judge import BoundaryJudge
        from tbdoc.instruments.vllm_extractor import VLLMExtractor
        if extractor is None:
            extractor = VLLMExtractor()   # same pin; engine shared with the judge
        judge = BoundaryJudge((reg.instruments or {}).get("boundary_judge") or {},
                              shared_extractor=extractor)
        click.echo(f"[instruments] boundary_judge {judge.identity()} (engine shared w/ extractor)")
    try:
        summary = run_matrix(
            models=model_keys, benches=bench_keys,
            model_factory=reg.model, bench_factory=reg.bench,
            results_dir=(_matrix_cfg().get("run") or {}).get("results_dir", "results/runs"),
            run_id=run_id, max_samples=max_samples, phases=phases, rescore=rescore,
            boundary_judge=judge, extractor=extractor,
            hardware=hw, instruments_meta=reg.instruments)
    finally:
        if judge is not None:
            judge.unload()
        if extractor is not None:
            extractor.unload()
    click.echo(json.dumps(summary, indent=2))


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
    """Download benchmark data at PINNED revisions (skips benches with data present)."""
    reg = _registry()
    keys = list(reg.benchmarks) if bench == "all" else [bench]
    for k in keys:
        e = reg.benchmarks.get(k)
        if e is None:
            raise click.ClickException(f"unknown benchmark '{k}'")
        src = e.get("source") or {}
        data_dir = Path(e.get("data_dir") or
                        Path("benchmarks") / e.get("provenance", "official") / k / "data")
        if data_dir.exists() and any(data_dir.iterdir()):
            click.echo(f"{k}: data present at {data_dir} — skipping")
            continue
        repo = src.get("hf_repo")
        if not repo:
            click.echo(f"{k}: no hf_repo source (custom/generated bench?) — see its README")
            continue
        from huggingface_hub import snapshot_download
        click.echo(f"{k}: downloading {repo}@{src.get('revision', 'main')} -> {data_dir}")
        snapshot_download(repo_id=repo, repo_type="dataset",
                          revision=src.get("revision"), local_dir=str(data_dir))
        click.echo(f"{k}: done — re-verify the LICENSE on the live dataset card "
                   f"(pinned license: {src.get('license', '?')})")


# Token assumptions for per-Mtok-priced vision APIs (verified workload model 2026-07-07:
# ~1.5MP page ≈ 1-4k image tokens depending on provider; ~1k output tokens/page).
_EST_IN_TOK, _EST_OUT_TOK = 2000, 1000


def _estimate(reg: Registry, model_keys: list[str], bench_keys: list[str],
              max_samples: int | None) -> dict[str, float]:
    """{model_key: estimated_usd} for API models (0.0 for local)."""
    n_pages = 0
    for b in bench_keys:
        ba = reg.bench(b)
        n = sum(1 for _ in ba.load())
        cap = max_samples.get(b) if isinstance(max_samples, dict) else max_samples
        n_pages += min(n, cap) if cap else n
    out: dict[str, float] = {}
    for m in model_keys:
        e = reg.models.get(m) or {}
        if e.get("kind") != "api":
            out[m] = 0.0
            continue
        p = e.get("pricing") or {}
        if "per_page_usd" in p:
            per_page = p["per_page_usd"]
        else:
            per_page = (_EST_IN_TOK * p.get("per_mtok_in_usd", 0)
                        + _EST_OUT_TOK * p.get("per_mtok_out_usd", 0)) / 1e6
        out[m] = round(per_page * n_pages, 4)
    return out


@main.command("estimate-cost")
@click.option("--models", "-m", required=True)
@click.option("--benches", "-b", required=True)
@click.option("--max-samples", type=int, default=None)
def estimate_cost(models, benches, max_samples):
    """Estimate API spend for a run BEFORE any calls."""
    reg = _registry()
    est = _estimate(reg, models.split(","), benches.split(","), max_samples)
    for m, usd in est.items():
        kind = (reg.models.get(m) or {}).get("kind", "?")
        click.echo(f"{m:20s} {kind:6s} ${usd:.4f}")
    click.echo(f"{'TOTAL':20s}        ${sum(est.values()):.4f}")


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
