from tbdoc.report import cost_tables as ct


def test_classic_cost_rows_arithmetic():
    rows = ct.classic_cost_rows()
    tess = next(r for r in rows if r["engine"] == "tesseract" and r["device"] == "CPU-VM")
    assert abs(tess["usd_per_1k"] - ct.CPU_VM["usd_per_hr"] / 3006 * 1000) < 1e-6
    devs = {(r["engine"], r["device"]) for r in rows}
    assert ("doctr", "GPU-VM") in devs and ("easyocr", "GPU-VM") in devs
    # tesseract/rapidocr are CPU-only (no GPU path)
    assert ("tesseract", "GPU-VM") not in devs and ("rapidocr", "GPU-VM") not in devs


def test_self_host_rows_present_for_vlms():
    rows = ct.self_host_rows()
    models = {r["model"] for r in rows}
    assert {"olmocr2", "qwen25vl", "deepseek_ocr"} <= models
    olmo = next(r for r in rows if r["model"] == "olmocr2")
    assert olmo["usd_per_1k_single"] > 0 and olmo["sku"]
    # transformers-backend models have no batched figure
    got2 = next(r for r in rows if r["model"] == "got2")
    assert got2["usd_per_1k_batched"] is None
