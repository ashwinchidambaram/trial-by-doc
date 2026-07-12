"""Capture the hardware/software fingerprint stamped onto every result row.

A baseline you can't reproduce is not a baseline — so we record exactly which GPU,
driver, CUDA build, and library versions produced each number.
"""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime
from typing import Any


def _ver(mod: str) -> str | None:
    try:
        return __import__(mod).__version__
    except Exception:
        return None


def _smi(query: str) -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _nvcc_version() -> str | None:
    """Return the nvcc release (e.g. '13.3') if a usable toolkit is on PATH, else None."""
    try:
        out = subprocess.run(["nvcc", "--version"], capture_output=True, text=True,
                             timeout=10, check=True).stdout
        import re
        m = re.search(r"release (\d+\.\d+)", out)
        return m.group(1) if m else "unknown"
    except Exception:
        return None


def _cuda_toolkit() -> dict[str, Any]:
    """Record the JIT-compile toolkit: a standalone CUDA toolkit wired in via cuda_env, if present.

    deepseek_ocr + FlashInfer JIT-compile against this; it lives outside the repo/venv (see
    the CLAUDE.md environment notes on the host toolkit), so capturing its identity is part
    of reproducibility.
    """
    import torch
    info: dict[str, Any] = {"torch_cuda_build": torch.version.cuda}
    try:
        from tbdoc.core.cuda_env import ensure_cuda_home, find_toolkit
        home = ensure_cuda_home()        # wires CUDA_HOME/PATH so nvcc is detectable
        tk = find_toolkit()
        info["toolkit_home"] = str(home) if home else None
        info["toolkit_path"] = str(tk) if tk else None
    except Exception:
        info["toolkit_home"] = info["toolkit_path"] = None
    info["nvcc_version"] = _nvcc_version()
    info["nvcc_present"] = info["nvcc_version"] is not None
    info["note"] = ("standalone CUDA toolkit, build-time only (JIT compile for FlashInfer/deepseek); "
                    "torch runtime stays at torch_cuda_build. Lives outside the repo — see the "
                    "CLAUDE.md environment notes.")
    return info


def capture_hardware_metadata() -> dict[str, Any]:
    import torch

    gpu: dict[str, Any] = {"available": torch.cuda.is_available()}
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability(0)
        gpu.update({
            "name": torch.cuda.get_device_name(0),
            "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1),
            "capability": list(cap),
            "arch": f"sm_{cap[0]}{cap[1]}",
            "driver_version": _smi("driver_version"),
            "supported_arch_list": torch.cuda.get_arch_list(),
        })

    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "gpu": gpu,
        "cuda": _cuda_toolkit(),
        "software": {
            "python": platform.python_version(),
            "torch": _ver("torch"),
            "torchvision": _ver("torchvision"),
            "triton": _ver("triton"),
            "vllm": _ver("vllm"),
            "transformers": _ver("transformers"),
            "datasets": _ver("datasets"),
            "accelerate": _ver("accelerate"),
            "huggingface_hub": _ver("huggingface_hub"),
        },
        "system": {
            "os": platform.system(),
            "kernel": platform.release(),
            "cpu_count": os.cpu_count(),
        },
    }
