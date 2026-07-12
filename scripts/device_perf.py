"""Single-stream throughput for a classic/CPU OCR engine on a chosen device.

Complements `scripts_batched_throughput.py` (which measures vLLM continuous batching).
Classic engines (Tesseract/RapidOCR/docTR/EasyOCR) process one page at a time, so the
meaningful number is single-stream s/page → pages/hr, measured per DEVICE (cpu|gpu) so we
can publish two cost rows (CPU-VM vs GPU-VM). Accuracy is device-invariant; only speed differs.

One (engine, device) per process — same rationale as the batched script (avoid any
cross-run state / VRAM leakage).

Usage: python scripts_device_perf.py <engine_key> <cpu|gpu> [n_pages=10]
Prints: RESULT <engine> device=<d> pages=<n> elapsed_s=<t> pages_per_hr=<r> s_per_page=<s>
"""
import glob
import io
import sys
import time

import fitz
from PIL import Image

from tbdoc.core.registry import Registry

engine = sys.argv[1]
device = sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 10

pdfs = sorted(glob.glob(
    "benchmarks/official/olmocr_bench/data/bench_data/pdfs/**/*.pdf", recursive=True))[:n]
imgs = []
for p in pdfs:
    try:
        imgs.append(Image.open(io.BytesIO(
            fitz.open(p)[0].get_pixmap(dpi=150).tobytes("png"))).convert("RGB"))
    except Exception:
        pass

reg = Registry("configs")
ad = reg.model(engine)
# Override the registry device so the SAME adapter is timed on cpu and on gpu.
ad.entry = {**ad.entry, "device": device}
with ad:
    _ = ad.predict(imgs[0])            # warm (model load / first-call JIT excluded from timing)
    t0 = time.time()
    for img in imgs:
        ad.predict(img)
    dt = time.time() - t0

print(f"RESULT {engine} device={device} pages={len(imgs)} elapsed_s={dt:.1f} "
      f"pages_per_hr={len(imgs) / dt * 3600:.0f} s_per_page={dt / len(imgs):.3f}", flush=True)
