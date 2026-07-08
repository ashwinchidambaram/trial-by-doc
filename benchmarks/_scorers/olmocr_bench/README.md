# olmOCR-Bench scorer (isolated venv)

Rebuild:
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python 'olmocr[bench]' numpy

Invoke (from repo root): JSON {pdf_id, markdown} on stdin ->
    .venv/bin/python score.py <bench_data_dir>

LIMITATION on Ubuntu 26.04: olmOCR's `math` + `table` tests render via Playwright/Chromium, which has
no build for this OS. `score.py` scores the native text/order tests (present/absent/order/baseline) and
reports `render_tests_excluded`. Score math/tables in a Playwright-supported container (see findings/S9).
