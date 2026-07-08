"""merged_forms (Tier C, provenance=CUSTOM) — the production hard case: one PDF stream
containing several visually-similar documents (same form faces, different filled data),
boundaries detectable only via content change.

Raw material: NIST SD2 (SFRS) — 900 simulated 1988 IRS tax submissions on 20 form
faces, US-government work (public domain). Each submission is a multi-page packet;
we concatenate K=3-4 packets per stream with seed-controlled selection.

Ground truth = the known packet boundaries. Scoring = deterministic PQ/F1/STP
(scoring/native.py). See benchmarks/custom/merged_forms/VALIDATION.md for the
generator-determinism, seam-artifact, and human-spot-check evidence (required for
custom provenance — the registry refuses this bench without it).
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterable

from tbdoc.core.bench_adapter import BenchAdapter, Sample
from tbdoc.scoring.native import segmentation_metrics

SEED = 0
N_STREAMS = 30           # streams in the generated benchmark
DOCS_PER_STREAM = (3, 4)  # K sampled per stream


def generate_manifest(raw_dir: Path, out_path: Path, *, seed: int = SEED,
                      n_streams: int = N_STREAMS) -> dict:
    """Deterministically compose streams from SD2 submission packets.

    SD2 layout: submissions are directories of page images (one dir = one taxpayer's
    packet). We sort dirs for determinism, then sample with a seeded RNG.
    Emits a manifest JSON {streams: [{id, docs: [{dir, pages: [...]}], boundaries}]}.
    """
    rng = random.Random(seed)
    packets = sorted([d for d in raw_dir.rglob("*") if d.is_dir()
                      and any(f.suffix.lower() in (".png", ".pct", ".tif") for f in d.iterdir())])
    if len(packets) < 10:
        raise RuntimeError(f"too few SD2 packets under {raw_dir} ({len(packets)}) — "
                           "run `gauntlet download merged_forms` / see the bench README")
    streams = []
    for i in range(n_streams):
        k = rng.choice(range(DOCS_PER_STREAM[0], DOCS_PER_STREAM[1] + 1))
        chosen = rng.sample(packets, k)
        docs, boundaries, page_count = [], [], 0
        for d in chosen:
            pages = sorted(str(f.relative_to(raw_dir)) for f in d.iterdir()
                           if f.suffix.lower() in (".png", ".pct", ".tif"))
            if page_count:
                boundaries.append(page_count)
            docs.append({"dir": str(d.relative_to(raw_dir)), "pages": pages})
            page_count += len(pages)
        streams.append({"id": f"stream_{i:03d}", "docs": docs,
                        "boundaries": boundaries, "n_pages": page_count})
    manifest = {"seed": seed, "n_streams": n_streams, "source": "NIST SD2 (public domain)",
                "streams": streams}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=1))
    return manifest


class MergedFormsBench(BenchAdapter):
    tier = "C"
    unit = "document"
    provenance = "custom"

    SD2_URL = "https://s3.amazonaws.com/nist-srd/SD2/sd02.zip"  # verified live 2026-07-07

    def fetch_data(self) -> None:
        """Download NIST SD2 (public domain) + generate the seeded manifest."""
        import subprocess
        root = Path(self.data_dir)
        raw = root.parent / "raw"
        sd02 = raw / "sd02"
        if not sd02.exists():
            raw.mkdir(parents=True, exist_ok=True)
            zip_path = raw / "sd02.zip"
            print(f"downloading {self.SD2_URL} (~300MB)...")
            subprocess.run(["curl", "-sL", "-o", str(zip_path), self.SD2_URL], check=True)
            subprocess.run(["unzip", "-q", str(zip_path), "-d", str(sd02)], check=True)
        if not (root / "manifest.json").exists():
            m = generate_manifest(sd02, root / "manifest.json")
            print(f"generated {len(m['streams'])} streams (seed={m['seed']})")

    def load(self) -> Iterable[Sample]:
        root = Path(self.data_dir)
        manifest_path = root / "manifest.json"
        raw_dir = root.parent / "raw" / "sd02"
        if not manifest_path.exists():
            generate_manifest(raw_dir, manifest_path)
        man = json.loads(manifest_path.read_text())
        from PIL import Image
        for st in man["streams"]:
            pages = []
            ok = True
            for d in st["docs"]:
                for rel in d["pages"]:
                    p = raw_dir / rel
                    if not p.exists():
                        ok = False
                        break
                    pages.append(Image.open(p).convert("RGB"))
            if ok and pages:
                yield Sample(id=st["id"], gold=st["boundaries"], pages=pages,
                             category="tax_forms_sd2")

    def evaluate(self, sample: Sample, prediction: Any, extractor: Any | None = None) -> dict:
        m = segmentation_metrics(prediction.boundaries, sample.gold, len(sample.pages))
        m["method"] = getattr(prediction, "method", "?")
        return m
