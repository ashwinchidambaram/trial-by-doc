#!/bin/bash
# v1 baseline: full profile, resumable. Line-buffered log; errors preserved (no grep filter
# so a driver crash is never hidden — MuPDF noise tolerated).
cd /home/ashwinc/dev/projects/trial-by-doc
exec stdbuf -oL -eL uv run gauntlet run --profile full --run-id v1-baseline
