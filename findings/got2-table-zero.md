# Why got2 scores 0.000 on every table test (v1-interim sanity flag #1)

_Resolved 2026-07-12 — local raw-record analysis, no re-run. Closes the "resolve
before publishing" flag in [v1-interim-analysis.md](v1-interim-analysis.md)._

## Verdict: format mismatch, not a transcription failure

got2 scores **0/103 olmocr_bench table unit-tests** and **TEDS 0.000 on every
omnidocbench table page**. This is dominated by an **output-format mismatch between got2
and the table scorers**, not by got2 failing to read the tables. Two honest caveats keep
it from being *pure* format mismatch (below).

## Evidence

**1. The scorer only parses markdown-pipe and HTML tables — not LaTeX.**
The official olmOCR `TableTest` (wrapped unmodified in
`benchmarks/_scorers/olmocr_bench/.venv/.../olmocr/bench/tests.py`) extracts tables with
`parse_markdown_tables()` and `parse_html_tables()` (BeautifulSoup) only. There is no
LaTeX `tabular` path. When neither parser finds a table it returns **"No tables found in
the content"** and the test auto-fails — this happens *before* any cell-value comparison,
so output correctness is never even examined.

**2. Every failed got2 table page hits exactly that reason.** All 14 scored `tables`-category
pages report `by_type: {"table": [0, N]}` with every fail reason = `"No tables found in
the content"` (`render_tests_excluded: 0` — the tests ran, they just found nothing to grade).

**3. got2 IS emitting tables — in LaTeX.** got2 is the **only** model in the roster that
emits LaTeX table markup, and it does so heavily:

| model | pages with `\begin{tabular}` (LaTeX) | pages with `<table>` (HTML) |
|---|---|---|
| **got2** | **29** (olmocr) / **27** (omni) | 0 / 0 |
| olmocr2 | 0 / 0 | 17 / 24 |
| dots_ocr | 0 / 0 | 20 / 23 |
| doctr | 0 / 0 | 0 / 0 |

11 of got2's 14 failed table pages emitted a `\begin{tabular}` block the scorer ignored;
the other 3 rendered the table region as running prose. The models that *pass* table tests
(olmocr2, dots_ocr) emit HTML `<table>`, which the scorer parses. got2 is uniquely
penalized purely by choosing a markup the harness's table parsers don't read.

## Caveats (why it's not *pure* mismatch)

- **got2's LaTeX is itself malformed.** Sampled tabular blocks are garbled — truncated
  environments (`\end{tabula`), invalid commands (`\hcline`), broken cell structure. A
  LaTeX-aware scorer would credit *some* of the data (the cell values are present) but not
  cleanly parse these tables. So even fixing the format gap, got2's table score would be
  low — just not a categorical zero.
- **This is the got2 adapter's recipe (`format=True`), part of the measured system.** Per
  the harness's own rule ("prompt + output normalization live in your adapter and are part
  of what's measured"), got2's format choice is legitimately its own result — the scoreboard
  isn't *wrong*. But the **table sub-score should not be cited as evidence got2 can't read
  tables**; it primarily measures format compatibility with the scorer.

## What to do with it

- **Do not cite got2's table sub-scores** as a transcription/quality claim (README/docs
  already carry a general got2 caveat; this flag is now explained rather than open).
- Its overall Tier-A standing is unaffected as a *ranking* (got2 is a weak model here
  regardless), but the table columns specifically are a format artifact.
- A future fix, if got2 ever matters: teach the adapter to convert its LaTeX `tabular`
  output to HTML/markdown in `decode()` (normalization, not a scorer change — the scorers
  are wrapped-never-modified), then re-score with `--phase score --rescore`. Not worth it
  now (got2 isn't a contender), so logged, not done.
