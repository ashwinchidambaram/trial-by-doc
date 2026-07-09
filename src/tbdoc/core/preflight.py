"""`gauntlet verify-env` — fresh-clone preflight: is this machine ready to run the gauntlet?

Six check groups, each returning a list of `CheckResult`s:
  1. GPU        — torch CUDA availability, device/capability/driver/runtime/VRAM, a REAL bf16 matmul.
  2. versions   — installed torch/vllm/transformers vs the pins recorded at repo root.
  3. CPU        — logical/physical cores, RAM, AVX2/AVX512 flags, a numpy matmul micro-smoke.
  4. scorers    — per-benchmark isolated scorer venv / docker image presence (configs/benchmarks.yaml).
  5. datasets   — per-benchmark local data dir presence (+ revision, where locally determinable).
  6. secrets    — PRESENCE-ONLY check for required API keys. Values are NEVER read into a result,
                  logged, or printed — only `bool(...)` / `in` membership is evaluated.

Heavy imports (torch, vllm, huggingface metadata parsing) are kept LAZY inside the check
functions so importing this module — e.g. at CLI startup — stays cheap.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_STATUS_RANK = {PASS: 0, WARN: 1, FAIL: 2}

_PIN_PACKAGES = ("torch", "vllm", "transformers")
_REQUIRED_SECRETS = ("OPEN_ROUTER_API_KEY", "HF_TOKEN")
_EXPECTED_CAPABILITY = (12, 0)   # RTX 5090 / Blackwell sm_120 — see CLAUDE.md environment notes


@dataclass
class CheckResult:
    name: str
    status: str
    found: Any
    expected: Any = None
    detail: str = ""

    def line(self) -> str:
        exp = f" expected={self.expected}" if self.expected is not None else ""
        det = f" ({self.detail})" if self.detail else ""
        return f"[{self.status}] {self.name}: found={self.found}{exp}{det}"


@dataclass
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> CheckResult:
        self.results.append(result)
        return result

    def extend(self, results: list[CheckResult]) -> None:
        self.results.extend(results)

    def lines(self) -> list[str]:
        return [r.line() for r in self.results]

    def counts(self) -> dict[str, int]:
        out = {PASS: 0, WARN: 0, FAIL: 0}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def exit_code(self, strict: bool = False) -> int:
        bad = {FAIL} | ({WARN} if strict else set())
        return 1 if any(r.status in bad for r in self.results) else 0


# ---- 1. GPU ----------------------------------------------------------------------------------

def _nvidia_smi_driver_version() -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else None
    except Exception:
        return None


def check_gpu() -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        import torch
    except Exception as e:
        return [CheckResult("gpu.torch_import", FAIL, found=f"import failed: {e!r}",
                            expected="importable")]

    available = torch.cuda.is_available()
    results.append(CheckResult("gpu.cuda_available", PASS if available else FAIL,
                                found=available, expected=True))
    if not available:
        return results

    idx = 0
    name = torch.cuda.get_device_name(idx)
    cap = tuple(torch.cuda.get_device_capability(idx))
    driver = _nvidia_smi_driver_version()
    cuda_runtime = torch.version.cuda
    vram_gb = round(torch.cuda.get_device_properties(idx).total_memory / 1e9, 1)

    results.append(CheckResult("gpu.device_name", PASS, found=name))
    results.append(CheckResult(
        "gpu.compute_capability", PASS if cap == _EXPECTED_CAPABILITY else WARN,
        found=list(cap), expected=list(_EXPECTED_CAPABILITY)))
    results.append(CheckResult("gpu.driver_version", PASS if driver else WARN,
                                found=driver or "unknown"))
    results.append(CheckResult("gpu.cuda_runtime", PASS if cuda_runtime else WARN,
                                found=cuda_runtime or "unknown"))
    results.append(CheckResult("gpu.vram_gb", PASS, found=vram_gb))

    # Real tiny bf16 matmul — a broken sm_120 build raises or silently misbehaves; a smoke that
    # merely checks "torch.cuda.is_available()" would miss that (see CLAUDE.md: never trust a
    # char-count smoke over an actual kernel run).
    try:
        a = torch.randn(256, 256, dtype=torch.bfloat16, device="cuda")
        b = torch.randn(256, 256, dtype=torch.bfloat16, device="cuda")
        c = a @ b
        torch.cuda.synchronize()
        ok = tuple(c.shape) == (256, 256) and bool(torch.isfinite(c).all().item())
        results.append(CheckResult(
            "gpu.bf16_matmul_smoke", PASS if ok else FAIL,
            found="ran, finite output" if ok else "ran but produced non-finite output",
            expected="runs cleanly on sm_120"))
    except Exception as e:
        results.append(CheckResult("gpu.bf16_matmul_smoke", FAIL, found=f"error: {e!r}",
                                    expected="runs cleanly on sm_120"))
    return results


# ---- 2. Version pins ---------------------------------------------------------------------------

def _parse_requirements_lock(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)", line)
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def _parse_uv_lock(path: Path) -> dict[str, str]:
    import tomllib
    data = tomllib.loads(path.read_text())
    pins: dict[str, str] = {}
    for pkg in data.get("package", []):
        pkg_name, version = pkg.get("name"), pkg.get("version")
        if pkg_name and version:
            pins[pkg_name.lower().replace("_", "-")] = version
    return pins


def _read_pins(repo_root: Path) -> tuple[dict[str, str], str | None]:
    """Version pins keyed by lowercased-hyphenated package name, + which file they came from.

    `requirements.lock` is this project family's usual pin file; this repo pins via `uv.lock`
    instead (no requirements.lock exists at repo root — verified by directory listing, not
    assumed). Fall back to uv.lock so the check still means something; report which file matched.
    """
    reqlock = repo_root / "requirements.lock"
    if reqlock.exists():
        return _parse_requirements_lock(reqlock), "requirements.lock"
    uvlock = repo_root / "uv.lock"
    if uvlock.exists():
        try:
            return _parse_uv_lock(uvlock), "uv.lock"
        except Exception:
            return {}, None
    return {}, None


def _installed_version(pkg: str) -> str | None:
    try:
        mod = __import__(pkg)
    except Exception:
        raise
    return getattr(mod, "__version__", None)


def check_versions(repo_root: str | Path = ".") -> list[CheckResult]:
    repo_root = Path(repo_root)
    pins, pin_source = _read_pins(repo_root)
    results: list[CheckResult] = []
    if pin_source is None:
        results.append(CheckResult(
            "version.pin_source", WARN, found="none",
            expected="requirements.lock or uv.lock",
            detail="no lock file found at repo root — version checks are unpinned"))
    else:
        results.append(CheckResult("version.pin_source", PASS, found=pin_source))

    for pkg in _PIN_PACKAGES:
        expected = pins.get(pkg)
        try:
            installed = _installed_version(pkg)
        except Exception as e:
            results.append(CheckResult(f"version.{pkg}", FAIL, found=f"import failed: {e!r}",
                                        expected=expected or "importable"))
            continue
        if installed is None:
            results.append(CheckResult(f"version.{pkg}", FAIL, found="no __version__ attribute",
                                        expected=expected))
            continue
        if expected is None:
            results.append(CheckResult(f"version.{pkg}", WARN, found=installed,
                                        expected="unknown (no pin found)"))
            continue
        # Local version segments (e.g. torch's "+cu130") aren't part of the upstream pin.
        installed_base = installed.split("+")[0]
        expected_base = expected.split("+")[0]
        status = PASS if installed_base == expected_base else WARN
        results.append(CheckResult(f"version.{pkg}", status, found=installed, expected=expected))
    return results


# ---- 3. CPU -------------------------------------------------------------------------------------

def _cpu_flags() -> set[str]:
    try:
        text = Path("/proc/cpuinfo").read_text()
    except Exception:
        return set()
    m = re.search(r"^flags\s*:\s*(.*)$", text, re.MULTILINE)
    return set(m.group(1).split()) if m else set()


def _physical_cores_from_proc() -> int | None:
    try:
        text = Path("/proc/cpuinfo").read_text()
    except Exception:
        return None
    pairs: set[tuple[str, str]] = set()
    phys_id = core_id = None
    for line in text.splitlines():
        if line.startswith("physical id"):
            phys_id = line.split(":", 1)[1].strip()
        elif line.startswith("core id"):
            core_id = line.split(":", 1)[1].strip()
            if phys_id is not None and core_id is not None:
                pairs.add((phys_id, core_id))
    return len(pairs) or None


def _mem_from_proc() -> tuple[float | None, float | None]:
    try:
        text = Path("/proc/meminfo").read_text()
    except Exception:
        return None, None

    def _kb(key: str) -> int | None:
        m = re.search(rf"^{key}:\s*(\d+)\s*kB", text, re.MULTILINE)
        return int(m.group(1)) if m else None

    total_kb, avail_kb = _kb("MemTotal"), _kb("MemAvailable")
    total_gb = round(total_kb / 1e6, 1) if total_kb is not None else None
    avail_gb = round(avail_kb / 1e6, 1) if avail_kb is not None else None
    return total_gb, avail_gb


def check_cpu() -> list[CheckResult]:
    results: list[CheckResult] = []
    logical = os.cpu_count()
    results.append(CheckResult("cpu.logical_cores", PASS if logical else WARN, found=logical))

    physical: int | None
    total_gb: float | None
    avail_gb: float | None
    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
        vm = psutil.virtual_memory()
        total_gb, avail_gb = round(vm.total / 1e9, 1), round(vm.available / 1e9, 1)
    except ImportError:
        physical = _physical_cores_from_proc()
        total_gb, avail_gb = _mem_from_proc()

    results.append(CheckResult("cpu.physical_cores", PASS if physical else WARN, found=physical))
    results.append(CheckResult("cpu.ram_total_gb", PASS if total_gb is not None else WARN,
                                found=total_gb))
    ram_status = WARN if avail_gb is None or avail_gb < 16 else PASS
    results.append(CheckResult("cpu.ram_available_gb", ram_status, found=avail_gb, expected=">=16"))

    flags = _cpu_flags()
    has_avx2 = "avx2" in flags
    has_avx512 = any(f.startswith("avx512") for f in flags)
    results.append(CheckResult("cpu.avx2", PASS if has_avx2 else WARN, found=has_avx2))
    results.append(CheckResult("cpu.avx512", PASS if has_avx512 else WARN, found=has_avx512))

    try:
        import time

        import numpy as np
        n = 512
        rng = np.random.default_rng(0)
        a = rng.random((n, n), dtype=np.float64)
        b = rng.random((n, n), dtype=np.float64)
        t0 = time.perf_counter()
        c = a @ b
        dt = time.perf_counter() - t0
        ok = c.shape == (n, n)
        gflops = round((2 * n ** 3) / dt / 1e9, 2) if dt > 0 else None
        results.append(CheckResult(
            "cpu.numpy_matmul_smoke", PASS if ok else FAIL,
            found=f"~{gflops} GFLOP/s" if gflops is not None else "ran (timing unavailable)",
            expected="runs cleanly"))
    except Exception as e:
        results.append(CheckResult("cpu.numpy_matmul_smoke", FAIL, found=f"error: {e!r}",
                                    expected="runs cleanly"))
    return results


# ---- 4. Scorers -----------------------------------------------------------------------------

def _docker_image_present(image: str) -> bool:
    try:
        out = subprocess.run(["docker", "image", "inspect", image],
                             capture_output=True, timeout=15)
        return out.returncode == 0
    except Exception:
        return False


def check_scorers(benchmarks: dict[str, dict], repo_root: str | Path = ".") -> list[CheckResult]:
    """Per-benchmark scorer readiness: isolated venv (scoring/venv_scorer.py), Docker image
    (scoring/container_scorer.py), or in-process 'native' (no external dep — always PASS)."""
    repo_root = Path(repo_root)
    results: list[CheckResult] = []
    for key, entry in benchmarks.items():
        scorer = entry.get("scorer") or {}
        kind = scorer.get("kind", "native")
        name = f"scorer.{key}"
        if kind == "native":
            results.append(CheckResult(name, PASS, found="native (in-process, no isolation needed)"))
        elif kind == "venv":
            venv_dir = repo_root / "benchmarks" / "_scorers" / key
            venv_py = venv_dir / ".venv" / "bin" / "python"
            present = venv_py.exists()
            results.append(CheckResult(
                name, PASS if present else WARN,
                found="present" if present else "absent", expected=str(venv_py),
                detail="" if present else
                f"run: uv venv {venv_dir}/.venv && uv pip install -p {venv_dir}/.venv/bin/python "
                f"-r {venv_dir}/requirements.txt (see {venv_dir}/README.md)"))
        elif kind == "container":
            image = scorer.get("image")
            present = bool(image) and _docker_image_present(image)
            results.append(CheckResult(
                name, PASS if present else WARN,
                found="present" if present else "absent", expected=image or "?",
                detail="" if present else
                f"build via benchmarks/_scorers/{key}/Dockerfile (docker build -t {image} .)"))
        else:
            results.append(CheckResult(name, WARN, found=f"unknown scorer kind {kind!r}",
                                        expected="native | venv | container"))
    return results


# ---- 5. Datasets -----------------------------------------------------------------------------

def _detect_local_revision(data_dir: Path) -> str | None:
    """Best-effort: huggingface_hub's `snapshot_download(local_dir=...)` writes one
    `<file>.metadata` per downloaded file under `.cache/huggingface/download/`, whose first line
    is the resolved commit hash. Returns None (not a mismatch) when this can't be determined —
    e.g. data fetched a different way, or an older huggingface_hub that doesn't write it."""
    cache = data_dir / ".cache" / "huggingface" / "download"
    if not cache.exists():
        return None
    for meta in cache.rglob("*.metadata"):
        try:
            first_line = meta.read_text().splitlines()[0].strip()
        except Exception:
            continue
        if first_line:
            return first_line
    return None


def check_datasets(benchmarks: dict[str, dict], repo_root: str | Path = ".") -> list[CheckResult]:
    repo_root = Path(repo_root)
    results: list[CheckResult] = []
    for key, entry in benchmarks.items():
        data_dir = Path(entry.get("data_dir") or
                        Path("benchmarks") / entry.get("provenance", "official") / key / "data")
        if not data_dir.is_absolute():
            data_dir = repo_root / data_dir
        name = f"dataset.{key}"
        present = data_dir.exists() and any(data_dir.iterdir())
        if not present:
            results.append(CheckResult(name, WARN, found="missing", expected=str(data_dir),
                                        detail=f"run: gauntlet download {key}"))
            continue

        expected_rev = (entry.get("source") or {}).get("revision")
        found_rev = _detect_local_revision(data_dir)
        if expected_rev and found_rev:
            matches = found_rev.startswith(expected_rev) or expected_rev.startswith(found_rev)
            results.append(CheckResult(
                name, PASS if matches else WARN,
                found=f"present @ {found_rev[:12]}", expected=expected_rev,
                detail="" if matches else "local revision hash does not match the pinned revision"))
        else:
            results.append(CheckResult(
                name, PASS, found="present", expected=expected_rev or "n/a",
                detail="revision unverifiable — no local HF download metadata" if expected_rev else ""))
    return results


# ---- 6. Secrets -----------------------------------------------------------------------------

def _dotenv_key_names(path: Path) -> set[str]:
    """Parse `.env` for the SET of key NAMES only. Never returns, stores, or inspects values."""
    if not path.exists():
        return set()
    names: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, _ = line.partition("=")
        names.add(k.strip())
    return names


def check_secrets(names: tuple[str, ...] = _REQUIRED_SECRETS,
                  repo_root: str | Path = ".") -> list[CheckResult]:
    """Presence-only. CRITICAL: no secret VALUE is ever read into a CheckResult or printed —
    only `bool(os.environ.get(n))` / membership-in-a-name-set is evaluated."""
    repo_root = Path(repo_root)
    dotenv_names = _dotenv_key_names(repo_root / ".env")
    results: list[CheckResult] = []
    for n in names:
        present = bool(os.environ.get(n)) or n in dotenv_names
        results.append(CheckResult(f"secret.{n}", PASS if present else WARN,
                                    found="present" if present else "absent", expected="present"))
    return results


# ---- orchestration --------------------------------------------------------------------------

def run_preflight(config_dir: str | Path = "configs", repo_root: str | Path | None = None) -> PreflightReport:
    """Run every check group and return the assembled report. Never raises for an individual
    check's own failure — a check that itself errors is reported as FAIL, not propagated."""
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    report = PreflightReport()

    report.extend(check_gpu())
    report.extend(check_versions(repo_root))
    report.extend(check_cpu())

    benchmarks: dict[str, dict] = {}
    try:
        from tbdoc.core.registry import Registry
        benchmarks = Registry(config_dir).benchmarks
    except Exception as e:
        report.add(CheckResult("registry.load", FAIL, found=f"error: {e!r}",
                                expected="loads cleanly from configs/benchmarks.yaml"))

    report.extend(check_scorers(benchmarks, repo_root))
    report.extend(check_datasets(benchmarks, repo_root))
    report.extend(check_secrets(repo_root=repo_root))
    return report
