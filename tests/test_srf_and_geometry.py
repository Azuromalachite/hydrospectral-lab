"""Analytical, boundary, and planted-defect tests for hydrospectral.srf and geometry."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from hydrospectral.geometry import (
    GeometryError,
    compute_water_mask_eligibility,
    sensor_screening_table,
    single_pixel_min_width_m,
    window_min_width_m,
)
from hydrospectral.srf import (
    SRFError,
    build_rectangular_weight_matrix,
    build_srf_weight_matrix,
    convolve_spectra,
    load_srf_csv,
)


def _triangle_response(wl: np.ndarray, center: float, half_width: float) -> np.ndarray:
    return np.maximum(0.0, 1.0 - np.abs(wl - center) / half_width)


def test_srf_convolution_preserves_flat_linear_es_weighting_and_isolates_out_of_band_nans(
    tmp_path: Path,
) -> None:
    srf_wl = np.arange(380.0, 821.0, 1.0)
    b2 = _triangle_response(srf_wl, 490.0, 30.0)
    b4 = _triangle_response(srf_wl, 665.0, 15.0)
    csv_path = tmp_path / "s2_srf.csv"
    lines = ["wavelength_nm,B2,B4"] + [
        f"{w:.1f},{r2:.8f},{r4:.8f}" for w, r2, r4 in zip(srf_wl, b2, b4, strict=True)
    ]
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loaded_wl, curves = load_srf_csv(csv_path, bands=["B2", "B4"])
    target_wl = np.arange(400.0, 801.0, 1.0)
    W, names = build_srf_weight_matrix(target_wl, loaded_wl, curves, band_order=["B2", "B4"])
    assert names == ["B2", "B4"]
    np.testing.assert_allclose(W.sum(axis=0), [1.0, 1.0], atol=1e-12)

    flat = np.full_like(target_wl, 0.0123)
    np.testing.assert_allclose(convolve_spectra(flat, W), [0.0123, 0.0123], atol=1e-12)

    linear = 0.001 + 2e-5 * target_wl
    expected = [0.001 + 2e-5 * 490.0, 0.001 + 2e-5 * 665.0]
    np.testing.assert_allclose(convolve_spectra(linear, W), expected, atol=1e-12)

    # Regression for Finding #8: out-of-band NaN at 762 nm (O2 A-band) must NOT contaminate B2 (490) or B4 (665),
    # while an in-band NaN at 665 nm propagates NaN to B4 ONLY (leaving B2 intact).
    with_o2_nan = linear.copy()
    with_o2_nan[target_wl == 762.0] = np.nan
    np.testing.assert_allclose(convolve_spectra(with_o2_nan, W), expected, atol=1e-12)

    with_b4_nan = linear.copy()
    with_b4_nan[target_wl == 665.0] = np.nan
    out_b4_nan = convolve_spectra(with_b4_nan, W)
    assert out_b4_nan[0] == pytest.approx(expected[0], abs=1e-12)
    assert np.isnan(out_b4_nan[1])

    # Narrow per-band SRF CSV with zero boundary endpoints inside target_wl is allowed.
    narrow_wl = np.arange(450.0, 531.0, 1.0)
    narrow_b2 = _triangle_response(narrow_wl, 490.0, 30.0)
    W_narrow, _ = build_srf_weight_matrix(target_wl, narrow_wl, {"B2": narrow_b2})
    assert convolve_spectra(linear, W_narrow)[0] == pytest.approx(expected[0], abs=1e-12)

    # Burggraaff (2020) energy-weighted Es shifts band centroid toward higher-Es wavelengths.
    es_tilted = np.exp(0.01 * (target_wl - 400.0))
    W_es, _ = build_srf_weight_matrix(
        target_wl, loaded_wl, curves, band_order=["B2", "B4"], es_spectrum=es_tilted
    )
    assert convolve_spectra(linear, W_es)[0] > expected[0]


def test_srf_refuses_planted_out_of_range_and_malformed_inputs(tmp_path: Path) -> None:
    srf_wl = np.arange(380.0, 851.0, 1.0)
    target_wl = np.arange(400.0, 801.0, 1.0)

    b8_out = _triangle_response(srf_wl, 820.0, 20.0)
    with pytest.raises(SRFError, match="nonzero SRF support outside target range"):
        build_srf_weight_matrix(target_wl, srf_wl, {"B8": b8_out})

    # Narrow SRF truncated with nonzero boundary response must fail.
    trunc_wl = np.arange(480.0, 501.0, 1.0)
    trunc_b2 = _triangle_response(trunc_wl, 490.0, 30.0)
    with pytest.raises(SRFError, match="nonzero response"):
        build_srf_weight_matrix(target_wl, trunc_wl, {"B2": trunc_b2})

    bad_neg = _triangle_response(srf_wl, 560.0, 20.0)
    bad_neg[0] = -1e-4
    with pytest.raises(SRFError, match="non-negative"):
        build_srf_weight_matrix(target_wl, srf_wl, {"B3": bad_neg})

    # Negative weights in weight_matrix (even if summing to 1.0) must be refused.
    W_bad_sign = np.zeros((target_wl.size, 1))
    W_bad_sign[0, 0] = 1.5
    W_bad_sign[1, 0] = -0.5
    with pytest.raises(SRFError, match="non-negative"):
        convolve_spectra(np.ones_like(target_wl), W_bad_sign)

    W_rect, _ = build_rectangular_weight_matrix(target_wl, {"B3": (560.0, 35.0)})
    with pytest.raises(SRFError, match="sum to 1.0"):
        convolve_spectra(np.ones_like(target_wl), W_rect * 1.05)

    with pytest.raises(SRFError, match="extends outside"):
        build_rectangular_weight_matrix(target_wl, {"B8": (795.0, 30.0)})

    bad_csv = tmp_path / "dup.csv"
    bad_csv.write_text("wavelength_nm,B2\n490,0.5\n490,0.5\n", encoding="utf-8")
    with pytest.raises(SRFError, match="strictly increasing"):
        load_srf_csv(bad_csv)


def test_geometry_screening_matches_handoff_section_3_1_table() -> None:
    table = sensor_screening_table()
    expected_single = {
        "Sentinel-2 visible": math.sqrt(2.0) * 10.0 + 40.0,
        "Sentinel-2 red edge": math.sqrt(2.0) * 20.0 + 40.0,
        "EnMAP / PRISMA": math.sqrt(2.0) * 30.0 + 40.0,
        "Sentinel-3 OLCI": math.sqrt(2.0) * 300.0 + 40.0,
        "PACE OCI": math.sqrt(2.0) * 1200.0 + 40.0,
    }
    expected_3x3 = {
        "Sentinel-2 visible": 3.0 * math.sqrt(2.0) * 10.0 + 40.0,
        "Sentinel-2 red edge": 3.0 * math.sqrt(2.0) * 20.0 + 40.0,
        "EnMAP / PRISMA": 3.0 * math.sqrt(2.0) * 30.0 + 40.0,
        "Sentinel-3 OLCI": 3.0 * math.sqrt(2.0) * 300.0 + 40.0,
        "PACE OCI": 3.0 * math.sqrt(2.0) * 1200.0 + 40.0,
    }
    for row in table.itertuples(index=False):
        assert row.single_pixel_min_width_m == pytest.approx(expected_single[row.sensor], rel=1e-12)
        assert row.window_3x3_min_width_m == pytest.approx(expected_3x3[row.sensor], rel=1e-12)

    assert round(single_pixel_min_width_m(1200.0)) == 1737
    assert round(window_min_width_m(1200.0, window_pixels=3)) == 5131

    with pytest.raises(GeometryError, match="pixel_size_m"):
        single_pixel_min_width_m(0.0)


def test_water_mask_eligibility_edt_edge_padding_and_nodata_rejection() -> None:
    narrow = np.zeros((20, 12), dtype=bool)
    narrow[:, 4:8] = True
    res_narrow = compute_water_mask_eligibility(
        narrow, pixel_spacing_m=(10.0, 10.0), sensor_pixels_m=(10.0,), buffers_m=(20.0,), windows=(1,)
    )
    assert int(res_narrow.loc[0, "eligible_mask_cells"]) == 0
    assert float(res_narrow.loc[0, "eligible_water_fraction"]) == 0.0

    # Strict 0/1 integer mask is accepted and matches boolean mask.
    square_int = np.ones((10, 10), dtype=np.uint8)
    res_sq = compute_water_mask_eligibility(
        square_int, pixel_spacing_m=(10.0, 10.0), sensor_pixels_m=(10.0,), buffers_m=(20.0,), windows=(1,)
    )
    assert int(res_sq.loc[0, "eligible_mask_cells"]) == 16
    assert float(res_sq.loc[0, "eligible_area_km2"]) == pytest.approx(16 * 100.0 / 1e6)
    assert float(res_sq.loc[0, "eligible_water_fraction"]) == pytest.approx(0.16)

    # Regression for Finding #2: float/NaN and nodata integer values (-9999, 255) must raise GeometryError,
    # NEVER silently cast to True (water)!
    float_nan = np.zeros((10, 10), dtype=float)
    float_nan[2:8, 2:8] = np.nan
    with pytest.raises(GeometryError, match="nodata/NaN"):
        compute_water_mask_eligibility(float_nan, pixel_spacing_m=(10.0, 10.0))

    int_nodata = np.zeros((10, 10), dtype=np.int16)
    int_nodata[2:8, 2:8] = -9999
    with pytest.raises(GeometryError, match="unexpected nodata/class value"):
        compute_water_mask_eligibility(int_nodata, pixel_spacing_m=(10.0, 10.0))

    with pytest.raises(GeometryError, match="zero water cells"):
        compute_water_mask_eligibility(np.zeros((5, 5), dtype=bool), pixel_spacing_m=(10.0, 10.0))
