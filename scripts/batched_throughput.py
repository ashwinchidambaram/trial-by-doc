"""Measure BATCHED throughput for ONE local vLLM model (arg: model key).

Run one model per process — vLLM's in-process engine teardown leaks VRAM, so the harness
(and this script) uses a fresh process per model. Submits N real olmOCR-Bench pages to the
engine in ONE llm.chat() call (vLLM continuous batching) and reports pages/hour.

Usage: python scripts_batched_throughput.py <model_key>
"""
import glob
import io
import sys
import time

import fitz
from PIL import Image

from tbdoc.core.registry import Registry
from tbdoc.models.local._vllm_base import resize_longest, to_data_url

N = 24
model = sys.argv[1]

pdfs = sorted(glob.glob(
    "benchmarks/official/olmocr_bench/data/bench_data/pdfs/**/*.pdf", recursive=True))[:N]
imgs = []
for p in pdfs:
    try:
        imgs.append(Image.open(io.BytesIO(
            fitz.open(p)[0].get_pixmap(dpi=150).tobytes("png"))).convert("RGB"))
    except Exception:
        pass

ad = Registry("configs").model(model)
with ad:
    batch = [ad.build_messages(to_data_url(resize_longest(img, ad.longest_side)))
             for img in imgs]
    sp = ad._SamplingParams(temperature=0.0, seed=0, max_tokens=ad.max_tokens,
                            repetition_penalty=ad.repetition_penalty,
                            skip_special_tokens=ad.skip_special_tokens)
    _ = ad.llm.chat(batch[:1], sampling_params=sp, use_tqdm=False)  # warm (Triton JIT)
    t0 = time.time()
    outs = ad.llm.chat(batch, sampling_params=sp, use_tqdm=False)
    dt = time.time() - t0
    out_tok = sum(len(o.outputs[0].token_ids) for o in outs)
    print(f"RESULT {model} pages={len(imgs)} elapsed_s={dt:.1f} "
          f"pages_per_hr={len(imgs)/dt*3600:.0f} out_tok_per_s={out_tok/dt:.0f}", flush=True)
