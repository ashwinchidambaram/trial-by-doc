"""degrade() — deterministic scan/fax degradation (Part D, spec §4.1)."""
import numpy as np
import pytest
from PIL import Image

from tbdoc.benches.degrade import PARAMS, degrade, params_fingerprint


def _synthetic_page(w=400, h=300):
    """A simple synthetic 'page' with text-like structure (not blank, not noise)."""
    img = Image.new("RGB", (w, h), "white")
    arr = np.asarray(img).copy()
    arr[40:60, 40:360] = 0        # a "text line"
    arr[100:110, 40:200] = 0      # another
    return Image.fromarray(arr, "RGB")


@pytest.mark.parametrize("level", ["light", "heavy"])
def test_same_seed_same_bytes(level):
    img = _synthetic_page()
    out1 = degrade(img, level, seed=42)
    out2 = degrade(img, level, seed=42)
    assert np.array_equal(np.asarray(out1), np.asarray(out2))


def test_different_seed_different_bytes():
    img = _synthetic_page()
    out1 = degrade(img, "light", seed=1)
    out2 = degrade(img, "light", seed=2)
    assert not np.array_equal(np.asarray(out1), np.asarray(out2))


def test_light_differs_from_heavy_and_from_clean():
    img = _synthetic_page()
    clean_arr = np.asarray(img.convert("RGB"))
    light = np.asarray(degrade(img, "light", seed=0))
    heavy = np.asarray(degrade(img, "heavy", seed=0))
    assert light.shape == heavy.shape == clean_arr.shape
    assert not np.array_equal(light, clean_arr)
    assert not np.array_equal(heavy, clean_arr)
    assert not np.array_equal(light, heavy)


def test_output_is_grayscale_content_in_rgb_container():
    # degrade() converts to "L" internally then back to "RGB" for JPEG — every
    # pixel's R/G/B channels should be equal (no color information survives).
    img = _synthetic_page()
    out = np.asarray(degrade(img, "heavy", seed=0))
    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        degrade(_synthetic_page(), "medium", seed=0)


def test_params_are_frozen_spec_values():
    # Frozen parameters (spec §4.1 table) — a change here is a spec deviation.
    assert PARAMS["light"] == dict(scale=0.62, blur=0.6, noise=7, angle=0.6, jpeg=45)
    assert PARAMS["heavy"] == dict(scale=0.42, blur=1.0, noise=15, angle=1.5, jpeg=27)


def test_params_fingerprint_matches_level():
    assert params_fingerprint("light") == PARAMS["light"]
    assert params_fingerprint("heavy") == PARAMS["heavy"]
