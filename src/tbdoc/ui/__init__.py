"""tbdoc.ui — read-only local results dashboard (`gauntlet ui`, C3a).

Self-contained FastAPI app + vanilla-JS frontend over an existing `results/runs/<id>/`
directory. Never writes to `results/`, `configs/`, or scorer/instrument code; never makes
a model/API call. See docs/superpowers/specs/2026-07-09-dashboard-ui-design.md.
"""
