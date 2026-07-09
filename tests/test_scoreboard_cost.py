from pathlib import Path

from tbdoc.core.checkpoint import CheckpointStore
from tbdoc.report.scoreboard import (
    _CLASSIC_ENGINE_THROUGHPUT,
    _CPU_VM_USD_PER_HR,
    _GPU_VM_USD_PER_HR,
    inject_readme,
    render_cost,
)


def test_render_cost_emits_cpu_and_gpu_rows_where_gpu_path_exists():
    out = render_cost()
    # tesseract/rapidocr: CPU-native, no GPU row. doctr/easyocr: both rows.
    assert out.count("| tesseract | CPU-VM |") == 1
    assert "| tesseract | GPU-VM |" not in out
    assert out.count("| doctr | CPU-VM |") == 1
    assert out.count("| doctr | GPU-VM |") == 1
    assert out.count("| easyocr | GPU-VM |") == 1


def test_render_cost_math_matches_sku_rate_over_throughput():
    out = render_cost(models=["doctr"])
    cpu_rate = _CLASSIC_ENGINE_THROUGHPUT["doctr"]["cpu_pages_hr"]
    gpu_rate = _CLASSIC_ENGINE_THROUGHPUT["doctr"]["gpu_pages_hr"]
    expected_cpu = f"${_CPU_VM_USD_PER_HR / cpu_rate * 1000:.3f}"
    expected_gpu = f"${_GPU_VM_USD_PER_HR / gpu_rate * 1000:.3f}"
    assert expected_cpu in out
    assert expected_gpu in out


def test_render_cost_cites_source_and_as_of_date():
    out = render_cost()
    assert "findings/ws1-cpu-engines.md" in out
    assert "2026-07-09" in out
    assert "instances.vantage.sh" in out


def test_inject_readme_assembles_all_four_subtables(tmp_path: Path):
    run_dir = tmp_path / "run"
    store = CheckpointStore(run_dir)
    store.record("tesseract", "olmocr_bench", "s1",
                 metrics={"primary": 0.5}, category="cat_a")
    store.record("tesseract", "realdoc_qa", "q1",
                 metrics={"primary": 1.0, "b1": 1.0, "extractive": True,
                          "b2": 1.0, "reader": "qwen2.5-1.5b"})

    readme = tmp_path / "README.md"
    readme.write_text("intro\n<!-- SCOREBOARD:BEGIN -->\nstale\n<!-- SCOREBOARD:END -->\noutro\n")

    inject_readme(run_dir, readme, registry=None)
    text = readme.read_text()

    assert "intro" in text and "outro" in text
    assert "stale" not in text
    assert "### Tier-B" in text
    assert "### Performance" in text
    assert "### Cost — classic OCR engines" in text
    assert "tesseract" in text
