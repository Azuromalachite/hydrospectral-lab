"""Analytical, boundary, and planted-defect tests for hydrospectral.radiometry."""

from __future__ import annotations

import math

import numpy as np
import pytest

from hydrospectral.radiometry import (
    RadiometryError,
    compute_above_water_lw,
    compute_avw,
    compute_band_ratio,
    compute_ndi,
    compute_qwip_score,
    compute_rrs_from_lw_es,
    normalize_snv,
    normalize_unit_l2,
    spectral_angle_rad,
    spectral_derivative,
)


def test_above_water_lw_and_rrs_preserve_negatives_and_flag_invalid_es() -> None:
    lt = np.array([10.0, 2.0, 5.0])
    lsky = np.array([100.0, 200.0, 50.0])
    lw = compute_above_water_lw(lt, lsky, rho=0.028)
    np.testing.assert_allclose(lw, [7.2, -3.6, 3.6], rtol=1e-12)

    es = np.array([1000.0, 1000.0, 0.0])
    rrs = compute_rrs_from_lw_es(lw, es)
    assert rrs[0] == pytest.approx(0.0072)
    assert rrs[1] == pytest.approx(-0.0036)
    assert np.isnan(rrs[2])

    with pytest.raises(RadiometryError, match="rho"):
        compute_above_water_lw(lt, lsky, rho=-0.01)

    with pytest.raises(RadiometryError, match="incompatible"):
        compute_above_water_lw(np.ones(3), np.ones(4), rho=0.028)


def test_avw_matches_analytical_harmonic_means_and_guards_negatives_and_truncation() -> None:
    wl = np.arange(400.0, 701.0, 1.0)

    # 1. Single Dirac impulses (interior 550 nm and boundary 400 nm / 700 nm with float rounding).
    dirac = np.zeros_like(wl)
    dirac[wl == 550.0] = 0.015
    assert compute_avw(dirac, wl) == pytest.approx(550.0, rel=1e-12)

    dirac_lo = np.zeros_like(wl)
    dirac_lo[wl == 400.0] = 0.007  # 0.007 / (0.007 / 400.0) == 399.99999999999994 in float64
    assert compute_avw(dirac_lo, wl) == pytest.approx(400.0, rel=1e-12)

    dirac_hi = np.zeros_like(wl)
    dirac_hi[wl == 700.0] = 0.007
    assert compute_avw(dirac_hi, wl) == pytest.approx(700.0, rel=1e-12)

    # 2. Equal weights at 400 nm and 600 nm -> harmonic mean 480.0 nm (not arithmetic 500 nm).
    two_peak = np.zeros_like(wl)
    two_peak[wl == 400.0] = 0.01
    two_peak[wl == 600.0] = 0.01
    assert compute_avw(two_peak, wl) == pytest.approx(480.0, rel=1e-12)

    # 3. Flat spectrum over 400..700 nm -> exact closed-form 301 / sum(1/k).
    flat = np.full_like(wl, 0.005)
    expected_flat = 301.0 / sum(1.0 / k for k in range(400, 701))
    assert compute_avw(flat, wl) == pytest.approx(expected_flat, rel=1e-12)

    # 4. Regression for negative-Rrs blowup (Finding #1):
    #    Rrs(400)=-0.0049, Rrs(650)=0.008 -> raw sum/sum ratio would blow up to 53,733 nm!
    #    Rrs(400)=0.010, Rrs(700)=-0.008 -> raw sum/sum ratio would collapse to 147.37 nm!
    blowup_hi = np.zeros_like(wl)
    blowup_hi[wl == 400.0] = -0.0049
    blowup_hi[wl == 650.0] = 0.008
    blowup_lo = np.zeros_like(wl)
    blowup_lo[wl == 400.0] = 0.010
    blowup_lo[wl == 700.0] = -0.008

    # Both default require_nonnegative=True AND require_nonnegative=False must return NaN (never out-of-range AVW).
    assert np.isnan(compute_avw(blowup_hi, wl))
    assert np.isnan(compute_avw(blowup_hi, wl, require_nonnegative=False))
    assert np.isnan(compute_avw(blowup_lo, wl, require_nonnegative=False))

    # 5. Truncated wavelength window (550..700 nm for default 400..700 nm AVW) must raise RadiometryError.
    wl_trunc = np.arange(550.0, 701.0, 1.0)
    with pytest.raises(RadiometryError, match="does not span full AVW window"):
        compute_avw(np.ones_like(wl_trunc), wl_trunc)

    # 6. Non-uniform grid refuses 'discrete' mode and integrates cleanly under 'trapezoid'.
    wl_nonunif = np.array([400.0, 450.0, 500.0, 700.0])
    flat_nu = np.full_like(wl_nonunif, 0.01)
    with pytest.raises(RadiometryError, match="uniformly spaced"):
        compute_avw(flat_nu, wl_nonunif, integration="discrete")
    avw_trap = compute_avw(flat_nu, wl_nonunif, integration="trapezoid")
    assert 400.0 < avw_trap < 700.0


def test_qwip_threshold_boundaries_below_at_and_above_0_2() -> None:
    wl = np.arange(400.0, 701.0, 1.0)
    coeffs_zero = [0.0, 0.0, 0.0, 0.0, 0.0]

    def _spectrum_with_ndi(target_ndi: float) -> np.ndarray:
        s = np.full_like(wl, 0.002)
        s[wl == 492.0] = 0.005 * (1.0 - target_ndi)
        s[wl == 665.0] = 0.005 * (1.0 + target_ndi)
        return s

    res = compute_qwip_score(
        np.vstack(
            [
                _spectrum_with_ndi(0.199),
                _spectrum_with_ndi(0.200),
                _spectrum_with_ndi(0.201),
                _spectrum_with_ndi(-0.201),
            ]
        ),
        wl,
        polynomial_coefficients_desc=coeffs_zero,
    )
    np.testing.assert_allclose(res["qwip_score"], [0.199, 0.200, 0.201, -0.201], atol=1e-12)
    assert res["qwip_fail"].tolist() == [0.0, 0.0, 1.0, 1.0]

    s_nan = _spectrum_with_ndi(0.100)
    s_nan[wl == 550.0] = np.nan
    res_nan = compute_qwip_score(s_nan, wl, polynomial_coefficients_desc=coeffs_zero)
    assert np.isnan(res_nan["qwip_fail"][0])

    with pytest.raises(RadiometryError, match="5 finite floats"):
        compute_qwip_score(s_nan, wl, polynomial_coefficients_desc=[1.0, 2.0])


def test_ndi_and_band_ratio_handle_negatives_and_missing_wavelengths() -> None:
    wl = np.arange(650.0, 721.0, 1.0)
    s_pos = np.full_like(wl, 0.004)
    s_pos[wl == 665.0] = 0.002
    s_pos[wl == 705.0] = 0.006

    s_neg = s_pos.copy()
    s_neg[wl == 705.0] = -0.001

    assert compute_ndi(s_pos, wl, 665.0, 705.0) == pytest.approx((0.006 - 0.002) / 0.008)
    ratios = compute_band_ratio(np.vstack([s_pos, s_neg]), wl, 705.0, 665.0)
    assert isinstance(ratios, np.ndarray)
    assert ratios[0] == pytest.approx(3.0)
    assert np.isnan(ratios[1])

    with pytest.raises(RadiometryError, match="not found within"):
        compute_band_ratio(s_pos, wl, 800.0, 665.0)


def test_preprocessing_derivatives_and_stable_spectral_angle() -> None:
    wl = np.arange(400.0, 421.0, 1.0)
    x = wl - 400.0
    quad = 3.0 * x**2 - 2.0 * x + 5.0

    d1_grad = spectral_derivative(quad, wl, order=1, method="gradient")
    d2_grad = spectral_derivative(quad, wl, order=2, method="gradient")
    np.testing.assert_allclose(d1_grad[1:-1], 6.0 * x[1:-1] - 2.0, atol=1e-10)
    np.testing.assert_allclose(d2_grad[2:-2], 6.0, atol=1e-10)

    d1_sg = spectral_derivative(quad, wl, order=1, method="savgol", window_length=7, polyorder=3)
    d2_sg = spectral_derivative(quad, wl, order=2, method="savgol", window_length=7, polyorder=3)
    np.testing.assert_allclose(d1_sg, 6.0 * x - 2.0, atol=1e-9)
    np.testing.assert_allclose(d2_sg, 6.0, atol=1e-9)

    with pytest.raises(RadiometryError, match="at least 2 wavelengths"):
        spectral_derivative(np.array([1.0]), np.array([500.0]), order=1)

    u = normalize_unit_l2(np.array([[3.0, 4.0], [0.0, 0.0]]))
    np.testing.assert_allclose(u[0], [0.6, 0.8], atol=1e-12)
    assert np.isnan(u[1]).all()

    snv = normalize_snv(np.array([[2.0, 4.0, 6.0], [5.0, 5.0, 5.0]]))
    assert float(np.mean(snv[0])) == pytest.approx(0.0, abs=1e-12)
    assert float(np.std(snv[0], ddof=0)) == pytest.approx(1.0, abs=1e-12)
    assert np.isnan(snv[1]).all()

    # Chord-based SAM eliminates arccos(1-eps) ~1.5e-8 small-angle error on collinear 401-band spectra.
    spec_401 = np.linspace(0.001, 0.01, 401)
    sam_collinear = spectral_angle_rad(0.3 * spec_401, spec_401)[0, 0]
    assert sam_collinear < 1e-14

    q = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, 0.0]])
    r = np.array([[1.0, 0.0]])
    angles = spectral_angle_rad(q, r)[:, 0]
    assert angles[0] == pytest.approx(0.0, abs=1e-15)
    assert angles[1] == pytest.approx(math.pi / 2.0, abs=1e-15)
    assert angles[2] == pytest.approx(math.pi, abs=1e-15)
    assert np.isnan(angles[3])
