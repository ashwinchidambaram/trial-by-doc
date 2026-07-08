# olmOCR-Bench scorer container — runs the FULL suite incl. Playwright-rendered math/table tests,
# which the host (Ubuntu 26.04) can't run. CPU-only: consumes predicted markdown, emits JSON scores.
# Base ships Python 3.12 + Playwright 1.60 + browsers on Ubuntu 24.04 (Playwright-supported, and
# Python >=3.11 which olmocr requires — the -jammy/22.04 tag ships 3.10 and pip rejects olmocr).
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV SCORER_RENDER=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir 'olmocr[bench]==0.4.27' numpy

WORKDIR /scorer
COPY score.py /scorer/score.py

# bench_data is mounted read-only at /data; predicted markdown comes in on stdin as JSON.
ENTRYPOINT ["python", "/scorer/score.py", "/data"]
