"""Resumable result store + live status feed.

Source of truth = append-only JSONL, one record per (model, bench, sample). This makes
the matrix crash-resumable for free: on startup we read what's already recorded and skip
those cells. Aggregates (scoreboard.csv, status.json) are derived from the JSONL.

Layout under results_dir/:
  raw/<model>/<bench>.jsonl   # one JSON record per scored sample (metrics + telemetry + raw)
  scoreboard.csv             # models x benchmarks, mean primary metric (tracked)
  status.json                # live progress feed for the observability site (tracked)
  hardware.json              # hardware fingerprint (written by S0/run start)
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


class CheckpointStore:
    def __init__(self, results_dir: str | Path):
        self.root = Path(results_dir)
        self.raw = self.root / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        # (model, bench) -> set of completed sample ids
        self._done: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._load_done()

    # ---- resumability -------------------------------------------------------
    def _cell_path(self, model: str, bench: str) -> Path:
        return self.raw / model / f"{bench}.jsonl"

    def _load_done(self) -> None:
        for jl in self.raw.rglob("*.jsonl"):
            model = jl.parent.name
            bench = jl.stem
            for line in jl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    self._done[(model, bench)].add(str(rec["sample_id"]))
                except Exception:
                    continue  # tolerate a torn final line from a crash

    def is_done(self, model: str, bench: str, sample_id: str) -> bool:
        return str(sample_id) in self._done[(model, bench)]

    def done_count(self, model: str, bench: str) -> int:
        return len(self._done[(model, bench)])

    # ---- recording ----------------------------------------------------------
    def record(self, model: str, bench: str, sample_id: str, *, metrics: dict,
               telemetry: dict | None = None, category: str | None = None,
               raw: dict | None = None, model_revision: str | None = None,
               error: str | None = None) -> None:
        path = self._cell_path(model, bench)
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "model": model,
            "bench": bench,
            "sample_id": str(sample_id),
            "category": category,
            "metrics": metrics,
            "telemetry": telemetry or {},
            "model_revision": model_revision,
            "error": error,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
        if raw is not None:
            rec["raw"] = raw
        with path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        self._done[(model, bench)].add(str(sample_id))

    def cell_records(self, model: str, bench: str) -> list[dict]:
        path = self._cell_path(model, bench)
        if not path.exists():
            return []
        out = []
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    def iter_records(self) -> Iterable[dict]:
        for jl in self.raw.rglob("*.jsonl"):
            for line in jl.read_text().splitlines():
                if line.strip():
                    try:
                        yield json.loads(line)
                    except Exception:
                        pass

    # ---- aggregates ---------------------------------------------------------
    def latest_cell_records(self, model: str, bench: str) -> list[dict]:
        """Last record per sample wins (a --rescore APPENDS; the JSONL is append-only)."""
        by_id: dict[str, dict] = {}
        for r in self.cell_records(model, bench):
            by_id[str(r.get("sample_id"))] = r
        return list(by_id.values())

    def _cell_primary_mean(self, model: str, bench: str) -> float | None:
        vals = [r["metrics"].get("primary") for r in self.latest_cell_records(model, bench)
                if r.get("error") is None and isinstance(r.get("metrics"), dict)
                and isinstance(r["metrics"].get("primary"), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    def write_scoreboard(self, models: list[str], benches: list[str]) -> Path:
        path = self.root / "scoreboard.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["model", *benches])
            for m in models:
                w.writerow([m, *[self._cell_primary_mean(m, b) for b in benches]])
        return path

    def write_status(self, models: list[str], benches: list[str], *,
                     totals: dict[tuple[str, str], int] | None = None,
                     current: dict | None = None, hardware: dict | None = None,
                     extra: dict | None = None) -> Path:
        """Emit status.json — the live feed the observability site consumes.

        `totals[(model,bench)]` = number of samples in that cell (for % done). If a
        cell's total is unknown, "total" is null and only "done" is reported.
        """
        totals = totals or {}
        cells = []
        grand_done = grand_total = 0
        for m in models:
            for b in benches:
                done = self.done_count(m, b)
                total = totals.get((m, b))
                grand_done += done
                if total is not None:
                    grand_total += total
                if total is None:
                    state = "running" if done else "pending"
                else:
                    state = "done" if done >= total and total > 0 else ("running" if done else "pending")
                cells.append({
                    "model": m, "bench": b, "done": done, "total": total,
                    "primary_mean": self._cell_primary_mean(m, b), "state": state,
                })
        status = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": {"done": grand_done, "total": grand_total or None,
                       "pct": round(100 * grand_done / grand_total, 1) if grand_total else None},
            "current": current,
            "cells": cells,
            "hardware": hardware,
        }
        if extra:
            status.update(extra)
        path = self.root / "status.json"
        path.write_text(json.dumps(status, indent=2))
        return path
