# you-shall-not-parse 🧙

**An OCR / document-intelligence model gauntlet.** Wire in any model — local
open-weights, commercial doc-AI APIs, or frontier VLMs — and run it through a
three-tier benchmark gauntlet with **deterministic, automatic scoring**:

- **Tier A — parse fidelity**: is the OCR output actually correct?
- **Tier B — downstream extraction**: is it good enough to extract fields from?
- **Tier C — document segmentation**: can it split a PDF containing several merged documents?

> 🚧 **v1 under construction.** Scoreboard, benchmark docs, model list, setup guide,
> example-document gallery, hardware notes, gaps, and attributions land with the v1
> baseline run. Architecture and build plan: see `findings/`.

## Quickstart (preview)

```bash
git clone https://github.com/ashwinchidambaram/you-shall-not-parse
cd you-shall-not-parse && uv sync --extra local   # or --extra api
gauntlet list models
gauntlet run --profile smoke
gauntlet scoreboard
```

Add your own model: one adapter subclass + one YAML entry → `ADD_A_MODEL.md` (soon).

## License

Harness code: MIT. Benchmark datasets keep their own licenses — see the
Attributions section (with the v1 release) and `benchmarks/*/eval.yaml`.
