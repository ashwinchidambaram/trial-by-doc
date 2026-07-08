"""Telemetry helpers — latency, GPU peak memory, and logprob/entropy summaries.

Backend-agnostic: adapters extract raw signals however their backend exposes them
(vLLM `SamplingParams(logprobs=k)` or transformers `output_scores`) and pass the
lists here to be summarized into the `Telemetry` fields.
"""
from __future__ import annotations

import math
import time
from contextlib import contextmanager
from dataclasses import dataclass

try:
    import torch
    _HAS_TORCH = True
except Exception:  # torch always present in this project, but keep helpers importable
    _HAS_TORCH = False


def cuda_available() -> bool:
    return _HAS_TORCH and torch.cuda.is_available()


def reset_peak_vram(device: int = 0) -> None:
    # Defensive: in a process without an active CUDA context (e.g. the caller when vLLM
    # runs the model in a separate engine subprocess), this raises — never let it crash.
    try:
        if cuda_available():
            torch.cuda.reset_peak_memory_stats(device)
    except Exception:
        pass


def peak_vram_mb(device: int = 0) -> float | None:
    """In-process peak allocated VRAM (meaningful for transformers; ~0 for vLLM subprocess)."""
    try:
        if cuda_available():
            return round(torch.cuda.max_memory_allocated(device) / 1e6, 1)
    except Exception:
        pass
    return None


def gpu_used_mb_smi(device: int = 0) -> float | None:
    """Whole-GPU used memory via nvidia-smi — the right VRAM proxy for the vLLM subprocess case."""
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", str(device)],
            capture_output=True, text=True, timeout=10,
        )
        return float(out.stdout.strip().splitlines()[0])
    except Exception:
        return None


@dataclass
class Timing:
    latency_s: float
    peak_vram_mb: float | None


def _sync(device: int = 0) -> None:
    try:
        if cuda_available():
            torch.cuda.synchronize(device)
    except Exception:
        pass


@contextmanager
def track(device: int = 0):
    """Time a block and capture peak VRAM over it. Yields a one-element list that
    holds a `Timing` after the block exits."""
    holder: list[Timing] = []
    reset_peak_vram(device)
    _sync(device)
    t0 = time.perf_counter()
    try:
        yield holder
    finally:
        _sync(device)
        dt = time.perf_counter() - t0
        holder.append(Timing(latency_s=round(dt, 4), peak_vram_mb=peak_vram_mb(device)))


def summarize_logprobs(chosen_logprobs: list[float] | None) -> dict[str, float | None]:
    """mean/min over the chosen tokens' log-probs (a confidence proxy)."""
    if not chosen_logprobs:
        return {"mean_logprob": None, "min_logprob": None}
    return {
        "mean_logprob": round(sum(chosen_logprobs) / len(chosen_logprobs), 5),
        "min_logprob": round(min(chosen_logprobs), 5),
    }


def summarize_entropy(per_token_topk_logprobs: list[list[float]] | None) -> float | None:
    """Mean per-token entropy (nats) over the available top-k logprob distribution.

    `per_token_topk_logprobs` is a list (one per generated token) of lists of the
    top-k log-probs at that step. We renormalize the top-k to a distribution and take
    its entropy — an approximation (top-k, not full vocab) but a useful uncertainty signal.
    """
    if not per_token_topk_logprobs:
        return None
    ents = []
    for topk in per_token_topk_logprobs:
        if not topk:
            continue
        ps = [math.exp(lp) for lp in topk]
        z = sum(ps)
        if z <= 0:
            continue
        ps = [p / z for p in ps]
        ents.append(-sum(p * math.log(p) for p in ps if p > 0))
    if not ents:
        return None
    return round(sum(ents) / len(ents), 5)
