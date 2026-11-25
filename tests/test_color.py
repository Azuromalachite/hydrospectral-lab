"""Analytical, boundary, and planted-defect tests for hydrospectral.color and default QWIP."""

from __future__ import annotations

import math

import numpy as np
import pytest

from hydrospectral.color import (
    ColorimetryError,
    chromaticity_to_hue_angle_deg,
    classify_owt_by_sam,
    rrs_to_xyz,
    xyz_to_chromaticity,
    xyz_to_display_srgb,
)
from hydrospectral.radiometry import compute_qwip_score


def test_flat_spectrum_recovers_exact_cie_1931_white_points_and_preserves_negatives() -> None:
    wl = np.arange(380.0, 781.0, 1.0)
    flat = np.ones_like(wl)

    xyz_e = rrs_to_xyz(flat, wl, illuminant="E", min_nm=380.0, max_nm=780.0)
    assert xyz_e[1] == pytest.approx(1.0, rel=1e-12)
    xy_e = xyz_to_chromaticity(xyz_e)
    assert xy_e[0] == pytest.approx(1.0 / 3.0, abs=1e-3)
    assert xy_e[1] == pytest.approx(1.0 / 3.0, abs=1e-3)

    xyz_d65 = rrs_to_xyz(flat, wl, illuminant="D65", min_nm=380.0, max_nm=780.0)
    assert xyz_d65[1] == pytest.approx(1.0, rel=1e-12)
    xy_d65 = xyz_to_chromaticity(xyz_d65)
    assert xy_d65[0] == pytest.approx(0.3127, abs=5e-4)
    assert xy_d65[1] == pytest.approx(0.3290, abs=5e-4)

    # Negative Rrs values are preserved in XYZ integration (never clipped) and negative XYZ -> NaN xy.
    all_neg = -flat * 0.01
    xyz_neg = rrs_to_xyz(all_neg, wl, illuminant="E", min_nm=380.0, max_nm=780.0)
    assert xyz_neg[1] == pytest.approx(-0.01, rel=1e-12)
    assert np.isnan(xyz_to_chromaticity(xyz_neg)).all()

    partial_neg = flat * 0.01
    partial_neg[wl < 420.0] = -0.002
    xyz_partial = rrs_to_xyz(partial_neg, wl, illuminant="E", min_nm=380.0, max_nm=780.0)
    assert xyz_partial[2] < rrs_to_xyz(np.maximum(partial_neg, 0.0), wl, illuminant="E", min_nm=380.0, max_nm=780.0)[2]

    # Truncated wavelength window and NaN bounds must raise ColorimetryError.
    wl_trunc = np.arange(450.0, 701.0, 1.0)
    with pytest.raises(ColorimetryError, match="does not span colour window"):
        rrs_to_xyz(np.ones_like(wl_trunc), wl_trunc)
    with pytest.raises(ColorimetryError, match="finite"):
        rrs_to_xyz(flat, wl, min_nm=float("nan"), max_nm=700.0)


def test_water_hue_angles_progression_and_360_wrap_boundary() -> None:
    wl = np.arange(400.0, 701.0, 1.0)
    clear_blue = np.exp(-0.5 * ((wl - 445.0) / 30.0) ** 2) * 0.008
    blue_green = np.exp(-0.5 * ((wl - 510.0) / 30.0) ** 2) * 0.008
    yellow_green = np.exp(-0.5 * ((wl - 555.0) / 35.0) ** 2) * 0.008
    turbid_brown = np.exp(-0.5 * ((wl - 635.0) / 45.0) ** 2) * 0.008
    incomplete = clear_blue.copy()
    incomplete[100] = np.nan

    xyz = rrs_to_xyz(
        np.vstack([clear_blue, blue_green, yellow_green, turbid_brown, incomplete]),
        wl,
        illuminant="E",
    )
    xy = xyz_to_chromaticity(xyz)
    angles = chromaticity_to_hue_angle_deg(xy)
    assert isinstance(angles, np.ndarray)

    assert 200.0 < angles[0] < 250.0
    assert 95.0 < angles[1] < 175.0
    assert 60.0 < angles[2] < 90.0
    assert 0.0 < angles[3] < 50.0
    assert angles[0] > angles[1] > angles[2] > angles[3]
    assert np.isnan(angles[4])

    # Exact white point has undefined hue angle (NaN).
    assert np.isnan(chromaticity_to_hue_angle_deg(np.array([1.0 / 3.0, 1.0 / 3.0])))

    # Regression for Finding #8: angle immediately below 0 deg wraps strictly into [0, 360), never 360.0.
    just_below_zero = np.array([1.0 / 3.0 + 0.5, np.nextafter(1.0 / 3.0, 0.0)])
    wrapped = chromaticity_to_hue_angle_deg(just_below_zero)
    assert 0.0 <= float(wrapped) < 360.0


def test_display_srgb_adaptation_exposure_and_gamut_modes() -> None:
    wl = np.arange(380.0, 781.0, 1.0)
    bright_flat = np.full_like(wl, 0.010)
    dim_flat = np.full_like(wl, 0.002)
    xyz_pair = rrs_to_xyz(np.vstack([bright_flat, dim_flat]), wl, illuminant="E", min_nm=380.0, max_nm=780.0)

    rgb_max_y = xyz_to_display_srgb(xyz_pair, illuminant="E", exposure="max_y")
    assert np.allclose(rgb_max_y[0], rgb_max_y[0, 0], atol=0.01)
    assert np.allclose(rgb_max_y[1], rgb_max_y[1, 0], atol=0.01)
    assert rgb_max_y[0, 0] > rgb_max_y[1, 0]

    rgb_per = xyz_to_display_srgb(xyz_pair, illuminant="E", exposure="per_spectrum_max")
    assert float(np.max(rgb_per[0])) == pytest.approx(1.0, abs=1e-12)
    assert float(np.max(rgb_per[1])) == pytest.approx(1.0, abs=1e-12)

    mono_520 = np.zeros_like(wl)
    mono_520[wl == 520.0] = 0.01
    xyz_mono = rrs_to_xyz(mono_520, wl, illuminant="D65", min_nm=380.0, max_nm=780.0)
    rgb_clip = xyz_to_display_srgb(xyz_mono, illuminant="D65", exposure="max_y", gamut="clip")
    rgb_desat = xyz_to_display_srgb(xyz_mono, illuminant="D65", exposure="max_y", gamut="desaturate")
    assert np.all((rgb_clip >= 0.0) & (rgb_clip <= 1.0))
    assert np.all((rgb_desat >= 0.0) & (rgb_desat <= 1.0))
    assert rgb_desat[0] == pytest.approx(0.0, abs=1e-12)
    assert rgb_desat[2] > rgb_clip[2]
    assert rgb_desat[1] <= rgb_clip[1]

    bad_xyz = np.array([[np.nan, 0.5, 0.5], [-0.1, 0.5, 0.5]])
    assert np.isnan(xyz_to_display_srgb(bad_xyz)).all()


def test_sam_owt_classifier_magnitude_threshold_boundaries_and_1wl_guard() -> None:
    wl = np.arange(400.0, 701.0, 5.0)
    ref_blue = np.exp(-0.5 * ((wl - 445.0) / 35.0) ** 2)
    ref_green = np.exp(-0.5 * ((wl - 555.0) / 35.0) ** 2)
    ref_turbid = np.exp(-0.5 * ((wl - 650.0) / 35.0) ** 2)
    refs = np.vstack([ref_blue, ref_green, ref_turbid])
    labels = ["OWT_blue", "OWT_green", "OWT_turbid"]

    ood_spike = np.zeros_like(wl)
    ood_spike[-1] = 1.0
    queries = np.vstack([ref_green, 2.5 * ref_green, ood_spike])

    out = classify_owt_by_sam(queries, refs, labels, wavelengths_nm=wl, max_angle_rad=0.25)
    assert out["assigned_label"][0] == "OWT_green"
    assert out["assigned_label"][1] == "OWT_green"
    assert out["assigned_label"][2] is None
    assert out["is_unclassified"].tolist() == [False, False, True]
    assert out["min_sam_rad"][0] < 1e-12
    assert out["magnitude"][1] / out["magnitude"][0] == pytest.approx(2.5, rel=1e-12)

    # Boundary check immediately below and above max_angle_rad = 0.20 rad.
    ref_2d = np.array([[1.0, 0.0]])
    q_below = np.array([[math.cos(0.199), math.sin(0.199)]])
    q_above = np.array([[math.cos(0.201), math.sin(0.201)]])
    res_b = classify_owt_by_sam(np.vstack([q_below, q_above]), ref_2d, ["C1"], max_angle_rad=0.20)
    assert res_b["is_unclassified"].tolist() == [False, True]
    assert res_b["assigned_label"][0] == "C1"
    assert res_b["assigned_label"][1] is None

    # Regression for Finding #9: 1-wavelength trapezoidal area raises ColorimetryError, not IndexError.
    with pytest.raises(ColorimetryError, match="at least 2 wavelengths"):
        classify_owt_by_sam(np.array([[1.0]]), np.array([[1.0]]), ["A"], wavelengths_nm=[500.0])

    with pytest.raises(ColorimetryError, match="unique"):
        classify_owt_by_sam(queries, refs[:2], ["dup", "dup"])


def test_default_qwip_uses_published_dierssen_2022_polynomial_from_config() -> None:
    wl = np.arange(400.0, 701.0, 1.0)
    s450 = np.zeros_like(wl)
    s450[wl == 450.0] = 0.01
    s450[wl == 492.0] = 1e-9
    s600 = np.zeros_like(wl)
    s600[wl == 600.0] = 0.01
    s600[wl == 665.0] = 1e-9

    res = compute_qwip_score(np.vstack([s450, s600]), wl)
    assert res["ndi_pred"][0] == pytest.approx(-0.977, abs=0.002)
    assert res["ndi_pred"][1] == pytest.approx(0.662, abs=0.002)
    assert math.isfinite(res["qwip_score"][0])
    assert math.isfinite(res["qwip_score"][1])
