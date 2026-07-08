# Add a benchmark to the gauntlet

One `BenchAdapter` subclass + one `configs/benchmarks.yaml` entry.

## The contract

```python
from tbdoc.core.bench_adapter import BenchAdapter, Sample

class MyBench(BenchAdapter):
    tier = "A"            # A parse fidelity | B downstream extraction | C segmentation
    unit = "page"         # page (predict per image) | document (segment over pages)
    provenance = "official"   # official | custom — see rules below

    def load(self):       # yield Samples: id, gold, pages, category
        ...
    def evaluate(self, sample, prediction, extractor=None) -> dict:
        # MUST return {"primary": float, ...components}. DETERMINISTIC scoring only.
        ...
    # override evaluate_batch() to score a whole cell in one subprocess/container run
```

Registry entry:

```yaml
  my_bench:
    adapter: "my_pkg.my_bench:MyBench"
    tier: A
    unit: page
    provenance: official
    source: { hf_repo: org/dataset, revision: <pin>, license: <verify live> }
    scorer: { kind: native | venv | container, image: my-scorer:v1 }
```

## The provenance rules (enforced)

- **official** = third-party dataset AND its official scorer, wrapped never
  reimplemented. Scorer deps live in their own isolated venv
  (`benchmarks/_scorers/<name>/.venv`) or Docker image — never in the main env.
  Follow `benchmarks/_scorers/olmocr_bench/score.py`'s JSON-lines contract
  (stdin `{pdf_id, markdown}` per line → one JSON result line each).
- **custom** = you own the ground truth and the scorer. The registry REFUSES the
  benchmark unless `validation_doc:` points to an existing VALIDATION.md covering:
  how ground truth was made, generator determinism (if synthesized), scorer
  sanity checks, and known gaming risks. See
  `benchmarks/custom/merged_forms/VALIDATION.md`.
- **No LLM-as-judge.** If scoring needs an LLM step, it must be a frozen instrument
  (pinned, temp=0, seeded, identical across models) whose output feeds a
  deterministic comparison — like the Tier-B extractor.

## Data

`gauntlet download my_bench` snapshots `source.hf_repo` at the pinned revision into
`benchmarks/<provenance>/<name>/data/`. Re-verify the license on the live card at
download time and record it. Data dirs are gitignored; add a credit line to the
README Attributions section (required for CC BY / ODC-BY sources).
