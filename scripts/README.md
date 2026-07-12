# scripts/ — historical one-shot scripts

These produced parts of the v1 baseline and are kept for provenance, **not for re-use**:
they hardcode `--run-id v1-baseline` era assumptions and owner-machine paths.

- `run_v1.sh` — launched the original 8-model core run (profile `full`).
- `batched_throughput.py`, `device_perf.py` — ad-hoc perf measurements behind
  `findings/ws1-cpu-engines.md` / the batched-throughput cost rows.

The deleted `scripts_finalize_scoring.sh` scored `merged_forms` with
`--no-llm-instruments` — a known-bad invocation (it disabled the boundary judge and
produced all-error Tier-C rows that had to be re-scored). It was removed rather than
kept, since re-running it against the published run would corrupt it.
