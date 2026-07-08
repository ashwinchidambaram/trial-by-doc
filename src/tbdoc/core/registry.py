"""Registry: configs/*.yaml -> adapter instances via importlib dotted paths.

models.yaml entry:    adapter: "tbdoc.models.local.qwen25vl:Qwen25VLAdapter"
benchmarks.yaml entry: adapter: "tbdoc.benches.official.olmocr_bench:OlmOCRBench"

BYO: point `adapter:` at your own installed module. A `@register_model("key")`
decorator also exists so adapter files can self-register without YAML edits
(the YAML entry still supplies revision/knobs).

Provenance enforcement: a benchmark with provenance=custom is REFUSED unless its
`validation_doc` exists on disk.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

_MODEL_CLASSES: dict[str, type] = {}


def register_model(key: str):
    def deco(cls):
        _MODEL_CLASSES[key] = cls
        return cls
    return deco


def _resolve(dotted: str) -> type:
    mod, _, attr = dotted.partition(":")
    return getattr(importlib.import_module(mod), attr)


def load_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


class Registry:
    def __init__(self, config_dir: str | Path = "configs"):
        self.config_dir = Path(config_dir)
        self.models: dict[str, dict] = load_yaml(self.config_dir / "models.yaml").get("models", {})
        bcfg = load_yaml(self.config_dir / "benchmarks.yaml")
        self.benchmarks: dict[str, dict] = bcfg.get("benchmarks", {})
        self.instruments: dict[str, dict] = load_yaml(self.config_dir / "models.yaml").get("instruments", {})

    # ---- models -------------------------------------------------------------
    def model(self, key: str) -> Any:
        entry = self.models.get(key)
        if entry is None:
            raise KeyError(f"unknown model '{key}' (see `gauntlet list models`)")
        if entry.get("adapter"):
            cls = _resolve(entry["adapter"])
        elif key in _MODEL_CLASSES:
            cls = _MODEL_CLASSES[key]
        else:
            raise KeyError(f"model '{key}' has no adapter path and none registered")
        return cls(key, entry)

    # ---- benchmarks ---------------------------------------------------------
    def bench(self, key: str) -> Any:
        entry = self.benchmarks.get(key)
        if entry is None:
            raise KeyError(f"unknown benchmark '{key}' (see `gauntlet list benches`)")
        cls = _resolve(entry["adapter"])
        data_dir = entry.get("data_dir") or str(
            Path("benchmarks") / entry.get("provenance", "official") / key / "data")
        ba = cls(key, data_dir=data_dir, entry=entry)
        # config may override class defaults
        for f in ("tier", "unit", "provenance"):
            if entry.get(f):
                setattr(ba, f, entry[f])
        if entry.get("validation_doc"):
            ba.validation_doc = entry["validation_doc"]
        # provenance enforcement — custom benchmarks must carry a validation doc
        if ba.provenance == "custom":
            if not ba.validation_doc or not Path(ba.validation_doc).exists():
                raise RuntimeError(
                    f"benchmark '{key}' is provenance=custom but has no existing "
                    f"validation_doc ({ba.validation_doc!r}) — custom benchmarks are "
                    "refused without a VALIDATION.md (house rule)")
        return ba
