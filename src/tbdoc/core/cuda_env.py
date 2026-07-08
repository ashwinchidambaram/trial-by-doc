"""Locate the CUDA toolkit that ships inside torch's cu13 wheels and expose it as CUDA_HOME.

Finding (verified 2026-06-12, see findings/S7-cuda-toolkit.md): torch 2.11+cu130 pulls in the
full *unified* `nvidia/cu13/{bin,include,lib,nvvm}` wheel layout — a complete nvcc toolchain
(release 13.3, compiles + runs real sm_120 kernels on the RTX 5090). The earlier "no nvcc -> SDPA"
conclusion only held for a *system* toolkit; nothing needs apt/sudo.

Runtime JIT compilers don't know about this layout unless we point them at it. This module finds
the bundled toolkit and sets CUDA_HOME/CUDA_PATH + PATH + LD_LIBRARY_PATH so that:
  - DeepSeek-OCR's custom ops (torch.utils.cpp_extension) can compile -> unblocks deepseek_ocr;
  - vLLM's FlashInfer attention/sampler can JIT -> enables the Blackwell speedup when opted in.

Call `ensure_cuda_home()` before importing/loading any backend that may JIT. Idempotent; safe to
call when no toolkit is present (returns None and changes nothing).
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def _standalone_roots() -> list[Path]:
    """Self-consistent standalone toolkits (compiler+headers same minor), preferred.

    The cu13 *wheel* toolkit is internally version-skewed (compiler 13.3 vs headers 13.0),
    which makes flashinfer/CUTLASS JIT fail its CCCL compiler-vs-headers guard. A standalone
    CUDA 13.0 toolkit installed under $HOME is self-consistent and matches torch's cu130 runtime,
    so we point JIT at it first. Override with OCPARSE_CUDA_HOME.
    """
    roots: list[Path] = []
    env = os.environ.get("OCPARSE_CUDA_HOME")
    if env:
        roots.append(Path(env))
    home = Path.home()
    # Prefer cuda-13.3: its headers fix a glibc(noexcept)/CUDA conflict on Ubuntu 26.04 that 13.0
    # headers trip over, while staying ABI-compatible with torch's 13.0 runtime (libcudart.so.13).
    roots += [home / "cuda-13.3", home / "cuda-13.0", home / "cuda",
              Path("/usr/local/cuda-13.3"), Path("/usr/local/cuda-13.0"), Path("/usr/local/cuda")]
    return roots


def _candidate_roots() -> list[Path]:
    """Directories that may hold a `nvidia/cu13` unified toolkit layout (wheel fallback)."""
    roots: list[Path] = []
    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry)
        # sys.path entries point at site-packages; the wheels live under nvidia/cu13
        if p.name == "site-packages":
            roots.append(p / "nvidia" / "cu13")
    # Fallback: derive site-packages from this file's location (…/site-packages/ocparse/…)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "site-packages":
            roots.append(parent / "nvidia" / "cu13")
            break
    # De-dup, preserve order
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _looks_like_toolkit(root: Path) -> bool:
    return (root / "bin" / "nvcc").exists() and (root / "include" / "cuda_runtime.h").exists()


@lru_cache(maxsize=1)
def find_toolkit() -> Path | None:
    """Return a usable CUDA toolkit root, preferring a self-consistent standalone install.

    Standalone (~/cuda-13.0 etc.) is tried before the version-skewed cu13 wheel layout so that
    flashinfer/CUTLASS JIT compiles cleanly. Returns None if nothing usable is found.
    """
    for root in (*_standalone_roots(), *_candidate_roots()):
        if _looks_like_toolkit(root):
            return root
    return None


def ensure_cuda_home() -> str | None:
    """Wire the bundled toolkit into the process env so JIT compilers can find it.

    Returns the toolkit path as a string if found (and now on PATH/CUDA_HOME), else None.
    A real pre-existing CUDA_HOME pointing at a usable nvcc is respected and left untouched.
    """
    existing = os.environ.get("CUDA_HOME") or os.environ.get("CUDA_PATH")
    if existing and (Path(existing) / "bin" / "nvcc").exists():
        return existing

    toolkit = find_toolkit()
    if toolkit is None:
        return None

    tk = str(toolkit)
    os.environ["CUDA_HOME"] = tk
    os.environ["CUDA_PATH"] = tk

    def _prepend(var: str, path: str) -> None:
        cur = os.environ.get(var, "")
        parts = cur.split(os.pathsep) if cur else []
        if path not in parts:
            os.environ[var] = os.pathsep.join([path, *parts]) if parts else path

    _prepend("PATH", str(toolkit / "bin"))
    # Both lib dir conventions: redist tarballs use a flat lib/, runfiles use lib64/targets.
    for libdir in (toolkit / "lib", toolkit / "lib64"):
        if libdir.exists():
            _prepend("LD_LIBRARY_PATH", str(libdir))  # runtime .so resolution
            _prepend("LIBRARY_PATH", str(libdir))     # link-time -l resolution (ld needs the .so symlink)

    # Bound JIT-compile parallelism. FlashInfer's CUTLASS kernels are RAM-hungry (multi-GB per
    # object in cicc); the naive all-cores default OOM-kills the engine before saturating CPU.
    # Conservative defaults keep peak memory safe; override via the real env for big-RAM hosts.
    os.environ.setdefault("MAX_JOBS", "4")
    os.environ.setdefault("NVCC_THREADS", "2")
    return tk
