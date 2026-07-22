"""gauntlet — the trial-by-doc CLI. Every command is resumable and provenance-stamped."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from tbdoc.core.registry import Registry, load_yaml
from tbdoc.core.secrets import load_dotenv


def _require_repo_root() -> None:
    """The harness reads configs/ and benchmarks/ relative to the CWD."""
    if not Path("configs/models.yaml").exists():
        raise click.ClickException(
            "configs/models.yaml not found — run `gauntlet` from the trial-by-doc repo root "
            "(the harness resolves configs/, benchmarks/ and results/ relative to the CWD)")


def _registry() -> Registry:
    _require_repo_root()
    return Registry("configs")


def _matrix_cfg() -> dict:
    _require_repo_root()
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
@click.option("--reader", default="local", show_default=True,
              help="Tier-B B.2 comprehension reader: local (Phi-4-mini) | local_qwen15 | "
                   "haiku45 | gpt5mini")
def run(models, benches, profile, max_samples, run_id, phase, rescore, no_llm_instruments, reader):
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
    # Same house rule for the B.2 reader instrument: API reader calls are paid spend and
    # must clear the per-model cap BEFORE any call (readers run once per (model, sample)).
    if "score" in phases and not no_llm_instruments:
        from tbdoc.instruments.reader import api_backend, estimate_call_usd
        rb = api_backend(reader, (reg.instruments or {}).get("reader") or {})
        needs_reader = [b for b in bench_keys
                        if (reg.benchmarks.get(b, {}).get("scorer") or {}).get("instrument") == "extractor"]
        if rb is not None and needs_reader:
            cap = ((_matrix_cfg().get("run") or {}).get("budget") or {}).get("max_usd_per_model")
            per_call = estimate_call_usd(rb.get("pricing"))
            if per_call is None:
                if cap is not None:
                    raise click.ClickException(
                        f"budget guard: reader '{reader}' has no pricing in configs/models.yaml — "
                        "cannot estimate B.2 reader spend; add pricing or use a local reader")
            else:
                n_calls = _count_samples(reg, needs_reader, max_samples)
                per_model = per_call * n_calls
                click.echo(f"estimated B.2 reader spend ({reader}, upper bound): "
                           f"${per_model:.2f}/model × {len(model_keys)} models "
                           f"= ${per_model * len(model_keys):.2f} ({n_calls} calls/model)")
                if cap is not None and per_model > cap:
                    raise click.ClickException(
                        f"budget guard: estimated B.2 reader spend ${per_model:.2f}/model exceeds "
                        f"max_usd_per_model=${cap} — shrink the run, use a local reader, or raise "
                        "the cap in configs/matrix.yaml")
    try:
        hw = hw_fingerprint()
    except Exception:
        hw = None
    # Tier-B B.2 reader — pluggable; may be a small LOCAL model (default Phi-4-mini, or the
    # named 'local_qwen15' rung) or an API reader (direct or via OpenRouter).
    extractor = None
    if "score" in phases and not no_llm_instruments:
        needs = [b for b in bench_keys
                 if (reg.benchmarks.get(b, {}).get("scorer") or {}).get("instrument") == "extractor"]
        if needs:
            from tbdoc.instruments.reader import build_reader
            extractor = build_reader(reader, (reg.instruments or {}).get("reader") or {})
            click.echo(f"[instruments] B.2 reader {extractor.identity} for: {', '.join(needs)}")
    judge = None
    judge_engine = None
    if not no_llm_instruments and any(
            reg.benchmarks.get(b, {}).get("tier") == "C" for b in bench_keys):
        from tbdoc.instruments.boundary_judge import BoundaryJudge
        from tbdoc.instruments.vllm_extractor import VLLMExtractor
        judge_engine = VLLMExtractor()   # pinned 7B — the Tier C judge's own engine
        judge = BoundaryJudge((reg.instruments or {}).get("boundary_judge") or {},
                              shared_extractor=judge_engine)
        click.echo(f"[instruments] boundary_judge {judge.identity()} (own pinned 7B engine)")
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
        if judge_engine is not None:
            judge_engine.unload()
        if extractor is not None and hasattr(extractor, "unload"):
            extractor.unload()   # API readers have no unload(); guard it
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
@click.option("--readme-inject", is_flag=True, help="write the scores into README.md's scoreboard block")
@click.option("--perf", is_flag=True, help="show per-page latency / VRAM / cost instead")
@click.option("--tier-b", is_flag=True, help="show Tier-B scores (B.1 + coverage + B.2 + reader)")
@click.option("--write-summary", is_flag=True,
              help="(re)generate the tracked summary.json from per-sample records")
@click.option("--ci", default=None, metavar="MODEL_A,MODEL_B",
              help="paired bootstrap 95% CI on a metric gap between two models "
                   "(needs raw records; --bench/--metric select the cell/column)")
@click.option("--bench", default="realdoc_qa", show_default=True, help="cell for --ci")
@click.option("--metric", default="b2", show_default=True, help="per-sample metric key for --ci")
def scoreboard(run_id, fmt, by, readme_inject, perf, tier_b, write_summary, ci, bench, metric):
    """Print the scoreboard for a run."""
    from tbdoc.report.scoreboard import (
        inject_readme,
        render,
        render_perf,
        render_tier_b,
    )
    from tbdoc.report.scoreboard import (
        write_summary as _write_summary,
    )
    try:
        if ci:
            from tbdoc.report.stats import paired_bootstrap_diff, per_sample_metric
            try:
                a, b = [x.strip() for x in ci.split(",")]
            except ValueError:
                raise click.ClickException("--ci expects MODEL_A,MODEL_B")
            run = _latest_run(run_id)
            sa = per_sample_metric(run, a, bench, metric)
            sb = per_sample_metric(run, b, bench, metric)
            r = paired_bootstrap_diff(sa, sb)
            if not r["n"]:
                raise click.ClickException(
                    f"no shared per-sample '{metric}' records for {a}/{b} in {bench} "
                    f"(run needs raw/; not available from summary.json alone)")
            verdict = ("gap is within noise (CI spans 0)" if r["ci_low"] <= 0 <= r["ci_high"]
                       else "gap is significant (CI excludes 0)")
            click.echo(f"{a} vs {b} — {metric} on {bench} (paired bootstrap, n={r['n']}, seed=0):\n"
                       f"  Δ = {r['diff']:+.3f}   95% CI [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]"
                       f"   p≈{r['p_two_sided']:.2f}\n  → {verdict}")
            return
        if write_summary:
            p = _write_summary(_latest_run(run_id))
            if p is None:
                raise click.ClickException("no per-sample records here to summarize")
            click.echo(f"wrote {p}")
            return
        if tier_b:
            click.echo(render_tier_b(_latest_run(run_id)))
            return
        if perf:
            click.echo(render_perf(_latest_run(run_id)))
            return
        if readme_inject:
            inject_readme(_latest_run(run_id), Path("README.md"), registry=_registry())
            click.echo("README.md scoreboard block updated")
            return
        click.echo(render(_latest_run(run_id), fmt=fmt, by=by, registry=_registry()))
    except FileNotFoundError as e:
        raise click.ClickException(str(e))


@main.command()
@click.option("--out", default="docs/leaderboard.md", show_default=True,
              help="where to write the rendered markdown")
def leaderboard(out):
    """Regenerate the cross-run four-tier leaderboard (docs/leaderboard.md)."""
    from tbdoc.report.leaderboard import leaderboard_data, render_md
    try:
        data = leaderboard_data(Path("results/runs"), _registry())
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_md(data))
    click.echo(f"wrote {p}")


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
            ba = reg.bench(k)
            if hasattr(ba, "fetch_data"):
                click.echo(f"{k}: fetching via the benchmark's own fetch_data()")
                ba.fetch_data()
            else:
                click.echo(f"{k}: no hf_repo source and no fetch_data() — see its README")
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


def _count_samples(reg: Registry, bench_keys: list[str], max_samples) -> int:
    """Page inferences a run will touch across bench_keys, honoring per-bench caps.

    APIs bill per page call, NOT per sample, and the two diverge in both directions:
      - unit="document": one stream == len(pages) calls (merged_forms: ~17x a sample count)
      - unit="page":     question-samples sharing one rendered image are OCR'd once,
                         because infer.py memoizes on id(s.image) (realdoc_qa: ~4 questions/doc)
    Counting samples under-quoted a v1 API run by ~1.5x, which silently leaked the
    matrix.yaml budget cap. Caps stay SAMPLE caps (as the runner applies them); pages
    are counted within the capped slice.
    """
    n = 0
    for b in bench_keys:
        ba = reg.bench(b)
        cap = max_samples.get(b) if isinstance(max_samples, dict) else max_samples
        # id() is only unique among LIVE objects — hold a ref so a GC'd page's id
        # can't be recycled and silently alias a distinct page into one call.
        alive: dict[int, object] = {}
        c = 0
        for s in ba.load():
            if cap and c >= cap:      # don't walk the whole dataset past the cap
                break
            c += 1
            if ba.unit == "document":
                n += len(s.pages)
            elif id(s.image) not in alive:
                alive[id(s.image)] = s.image
                n += 1
    return n


def _estimate(reg: Registry, model_keys: list[str], bench_keys: list[str],
              max_samples: int | None) -> dict[str, float]:
    """{model_key: estimated_usd} for API models (0.0 for local)."""
    # Local models cost nothing, so a local-only run needs no page count at all.
    # Counting via `ba.load()` enumerates (and, for some benches, decodes) EVERY
    # sample — e.g. all 1651 omnidocbench pages — which made local runs appear to
    # hang at startup for minutes. Skip it entirely unless an API model is present.
    if not any((reg.models.get(m) or {}).get("kind") == "api" for m in model_keys):
        return {m: 0.0 for m in model_keys}
    n_pages = _count_samples(reg, bench_keys, max_samples)
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


@main.command()
@click.option("--run-id", default=None, help="default: most-recently-modified scored run")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="localhost only — this is a read-only local dev tool, never expose it")
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--no-browser", is_flag=True, help="don't auto-open a browser tab")
def ui(run_id, host, port, no_browser):
    """Launch the read-only results dashboard (C3a): leaderboard, bench explorer, per-example review."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise click.ClickException(
            f"refusing to bind {host!r} — this is a read-only local dev tool (localhost only)")
    import uvicorn

    from tbdoc.ui.app import create_app
    results_dir = (_matrix_cfg().get("run") or {}).get("results_dir", "results/runs")
    app = create_app(results_dir=results_dir, config_dir=str(_registry().config_dir))
    if run_id:
        from tbdoc.ui.runs import _is_run_dir
        if not _is_run_dir(Path(results_dir) / run_id):
            raise click.ClickException(f"no scored run '{run_id}' under {results_dir} "
                                       "(needs raw/ or a tracked summary.json)")
    url = f"http://{host}:{port}/" + (f"#/?run_id={run_id}" if run_id else "")
    click.echo(f"gauntlet ui: {url}  (results_dir={results_dir}, Ctrl-C to stop)")
    if not no_browser:
        import threading
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


@main.command("verify-env")
@click.option("--strict", is_flag=True, help="also treat WARN as failure (nonzero exit)")
def verify_env(strict):
    """Fresh-clone preflight: GPU, version pins, CPU, scorers, datasets, secrets (presence-only)."""
    from tbdoc.core.preflight import run_preflight
    report = run_preflight()
    for line in report.lines():
        click.echo(line)
    counts = report.counts()
    click.echo(f"\n{counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL"
               + (" (--strict: WARN counts as failure)" if strict else ""))
    code = report.exit_code(strict=strict)
    if code:
        sys.exit(code)


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
