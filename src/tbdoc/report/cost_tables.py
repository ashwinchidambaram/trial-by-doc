"""Single source of truth for the harness's cost tables.

Consolidates the two cost datasets that used to live in different places:

- **Classic-engine CPU-vs-GPU throughput** (was inline in ``scoreboard.render_cost``):
  single-stream pages/hr on this box (RTX 5090), from ``findings/ws1-cpu-engines.md``.
- **Per-model self-host $/1k pages** (was hand-authored prose in the README's Azure AI
  Foundry Managed-Compute table): the smallest GPU SKU that fits each model's footprint,
  single-stream + vLLM-batched.

``render_cost`` (README block), the README Azure-table render, and the dashboard's
``/api/cost`` endpoint all read from here, so per-model cost has one code source of truth
and stays consistent everywhere. All prices are same-hardware relative floors, not cloud
invoices (carry the caveat forward wherever these are shown).

SKU prices verified LIVE 2026-07-09 (Vantage / CloudPrice, on-demand). Re-pin before quoting.
"""
from __future__ import annotations

# ── Classic OCR engines: single-stream throughput (findings/ws1-cpu-engines.md) ──
CLASSIC_ENGINES: dict[str, dict[str, float | None]] = {
    # engine key (registry name): {cpu_pages_hr, gpu_pages_hr}
    "tesseract": {"cpu_pages_hr": 3006, "gpu_pages_hr": None},   # CPU-native, no GPU path
    "rapidocr":  {"cpu_pages_hr": 1214, "gpu_pages_hr": None},   # no onnxruntime-gpu wheel for cu130/sm_120
    "doctr":     {"cpu_pages_hr": 983,  "gpu_pages_hr": 24328},
    "easyocr":   {"cpu_pages_hr": 43,   "gpu_pages_hr": 2300},
}

# ── Commodity VM SKUs for the classic-engine cost rows (Vantage, us-east-1, Linux) ──
CPU_VM = {
    "sku": "AWS EC2 c6i.xlarge (4 vCPU, 8 GiB, no GPU)",
    "usd_per_hr": 0.17,
    "source": "https://instances.vantage.sh/aws/ec2/c6i.xlarge",
}
GPU_VM = {
    "sku": "AWS EC2 g5.xlarge (1x NVIDIA A10G, 24 GiB)",
    "usd_per_hr": 1.006,
    "source": "https://instances.vantage.sh/aws/ec2/g5.xlarge",
}

PRICING_AS_OF = "2026-07-09"

# ── Per-model self-host cost — Azure AI Foundry Managed Compute (smallest fitting SKU) ──
# $/1k pages = SKU $/hr ÷ pages/hr; single-stream (conservative) + vLLM continuous-batching
# (measured N=24). T4-16GB ≈ $0.53/hr (≤3B), A100-80GB ≈ $3.67/hr (7-8B); verified 2026-07-08.
# batched = None for transformers-backend models (no vLLM continuous batching).
SELF_HOST: list[dict[str, object]] = [
    {"model": "paddleocr_vl",    "sku": "T4-16GB",   "usd_per_1k_single": 0.52,  "usd_per_1k_batched": 0.13},
    {"model": "lightonocr",      "sku": "T4-16GB",   "usd_per_1k_single": 0.63,  "usd_per_1k_batched": 0.18},
    {"model": "got2",            "sku": "T4-16GB",   "usd_per_1k_single": 0.78,  "usd_per_1k_batched": None},
    {"model": "granite_docling", "sku": "T4-16GB",   "usd_per_1k_single": 0.81,  "usd_per_1k_batched": None},
    {"model": "dots_ocr",        "sku": "T4-16GB",   "usd_per_1k_single": 0.87,  "usd_per_1k_batched": 0.11},
    {"model": "deepseek_ocr",    "sku": "T4-16GB",   "usd_per_1k_single": 0.97,  "usd_per_1k_batched": 0.11},
    {"model": "qwen25vl",        "sku": "A100-80GB", "usd_per_1k_single": 7.85,  "usd_per_1k_batched": 1.38},
    {"model": "olmocr2",         "sku": "A100-80GB", "usd_per_1k_single": 8.67,  "usd_per_1k_batched": 1.19},
    {"model": "gemma4",          "sku": "A100-80GB", "usd_per_1k_single": 10.60, "usd_per_1k_batched": 1.08},
]


def classic_cost_rows(models: list[str] | None = None) -> list[dict[str, object]]:
    """One row per (classic engine, device): CPU-VM for every engine, GPU-VM where a GPU
    path exists. ``usd_per_1k`` = VM $/hr ÷ pages/hr."""
    order = [m for m in (models or CLASSIC_ENGINES) if m in CLASSIC_ENGINES]
    if not order:
        order = list(CLASSIC_ENGINES)
    rows: list[dict[str, object]] = []
    for eng in order:
        t = CLASSIC_ENGINES[eng]
        cpu_rate = t["cpu_pages_hr"]
        rows.append({"engine": eng, "device": "CPU-VM", "sku": CPU_VM["sku"],
                     "pages_hr": cpu_rate, "usd_per_1k": CPU_VM["usd_per_hr"] / cpu_rate * 1000})
        gpu_rate = t["gpu_pages_hr"]
        if gpu_rate:
            rows.append({"engine": eng, "device": "GPU-VM", "sku": GPU_VM["sku"],
                         "pages_hr": gpu_rate, "usd_per_1k": GPU_VM["usd_per_hr"] / gpu_rate * 1000})
    return rows


def self_host_rows() -> list[dict[str, object]]:
    """Per-model self-host $/1k pages (single-stream + batched)."""
    return [dict(r) for r in SELF_HOST]
