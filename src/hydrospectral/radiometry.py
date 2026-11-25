"""Radiometric conversions, bio-optical colour/quality metrics, and spectral preprocessing.

Physical conventions:
- Remote-sensing reflectance Rrs(lambda) has units sr^-1: Rrs = Lw / Es.
- Negative Rrs values are preserved by default for baseline-shift and QC
  diagnostics; no function here silently clips negative reflectance to zero.
- Wavelength bounds and QWIP thresholds are loaded from config/qc_thresholds.yaml
  via hydrospectral.thresholds rather than hardcoded silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy.signal import savgol_filter
from scipy.spatial.distance import cdist

from hydrospectral.thresholds import get_threshold, load_qc_thresholds


class RadiometryError(ValueError):
    """Raised when radiometric inputs violate shape, wavelength, or domain invariants."""


def _as_2d_spectra(spectra: ArrayLike) -> tuple[np.ndarray, bool]:
    arr = np.asarray(spectra, dtype=float)
    if arr.ndim == 1:
        return arr[np.newaxis, :], True
    if arr.ndim == 2:
        return arr, False
    raise RadiometryError(f"spectra must be 1D or 2D array, got ndim={arr.ndim}")


def _validate_wavelengths(wavelengths_nm: ArrayLike, expected_len: int) -> np.ndarray:
    wl = np.asarray(wavelengths_nm, dtype=float)
    if wl.ndim != 1 or wl.size != expected_len:
        raise RadiometryError(
            f"wavelengths_nm must be 1D of length {expected_len}, got shape {wl.shape}"
        )
    if not np.isfinite(wl).all() or np.any(wl <= 0):
        raise RadiometryError("wavelengths_nm must be strictly positive finite numbers")
    if wl.size > 1 and not np.all(np.diff(wl) > 0):
        raise RadiometryError("wavelengths_nm must be strictly increasing")
    return wl


def _trapezoid_weights(grid: np.ndarray) -> np.ndarray:
    dw = np.diff(grid)
    w = np.zeros_like(grid, dtype=float)
    w[0] = 0.5 * dw[0]
    w[-1] = 0.5 * dw[-1]
    if grid.size > 2:
        w[1:-1] = 0.5 * (dw[:-1] + dw[1:])
    return w


def compute_above_water_lw(
    lt: ArrayLike,
    lsky: ArrayLike,
    rho: float | ArrayLike,
) -> np.ndarray:
    """Compute simplified above-water leaving radiance Lw = Lt - rho * Lsky.

    Preserves negative results so over-corrected sky glint remains visible to QC.
    """
    lt_arr = np.asarray(lt, dtype=float)
    lsky_arr = np.asarray(lsky, dtype=float)
    rho_arr = np.asarray(rho, dtype=float)
    if np.any(rho_arr < 0) or not np.isfinite(rho_arr).all():
        raise RadiometryError("surface reflectance factor rho must be finite and >= 0")
    try:
        lt_b, lsky_b, rho_b = np.broadcast_arrays(lt_arr, lsky_arr, rho_arr)
    except ValueError as exc:
        raise RadiometryError(f"incompatible Lt, Lsky, and rho shapes: {exc}") from exc
    return lt_b - rho_b * lsky_b


def compute_rrs_from_lw_es(lw: ArrayLike, es: ArrayLike) -> np.ndarray:
    """Compute remote-sensing reflectance Rrs = Lw / Es (sr^-1).

    Returns NaN wherever Es <= 0 or non-finite (where irradiance division is
    physically undefined), while preserving negative Lw/Rrs values intact.
    """
    lw_arr = np.asarray(lw, dtype=float)
    es_arr = np.asarray(es, dtype=float)
    try:
        lw_b, es_b = np.broadcast_arrays(lw_arr, es_arr)
    except ValueError as exc:
        raise RadiometryError(f"incompatible Lw and Es shapes: {exc}") from exc

    out = np.full(lw_b.shape, np.nan, dtype=float)
    valid_es = np.isfinite(es_b) & (es_b > 0.0) & np.isfinite(lw_b)
    out[valid_es] = lw_b[valid_es] / es_b[valid_es]
    return out


def compute_avw(
    rrs: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    min_nm: float | None = None,
    max_nm: float | None = None,
    integration: str = "discrete",
    require_nonnegative: bool = True,
    config: Mapping[str, Any] | None = None,
) -> np.ndarray | float:
    """Compute Apparent Visible Wavelength (AVW, nm) via Vandermeulen et al. (2020).

    Over [min_nm, max_nm] (default 400-700 nm from config/qc_thresholds.yaml):
    - `integration="discrete"` (default, requires uniformly spaced wavelengths):
        AVW = sum(Rrs(lambda)) / sum(Rrs(lambda) / lambda)
    - `integration="trapezoid"` (for non-uniform wavelength grids):
        AVW = integral(Rrs(lambda) dlambda) / integral((Rrs(lambda) / lambda) dlambda)

    Refuses wavelength grids that fail to span [min_nm, max_nm]. Never silently
    clips negative Rrs: with `require_nonnegative=True` (default), spectra having
    any negative Rrs inside [min_nm, max_nm] return NaN; with
    `require_nonnegative=False`, any cancellation yielding AVW outside
    [min_nm, max_nm] still returns NaN rather than an unphysical wavelength.
    """
    spec, was_1d = _as_2d_spectra(rrs)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    cfg = load_qc_thresholds() if config is None else dict(config)
    lo = float(get_threshold(cfg, "avw.visible_window_nm.min_nm")) if min_nm is None else float(min_nm)
    hi = float(get_threshold(cfg, "avw.visible_window_nm.max_nm")) if max_nm is None else float(max_nm)
    if hi <= lo:
        raise RadiometryError(f"AVW window must satisfy max_nm > min_nm, got [{lo}, {hi}]")

    if wl[0] > lo or wl[-1] < hi:
        raise RadiometryError(
            f"wavelength grid [{wl[0]}, {wl[-1]}] nm does not span full AVW window [{lo}, {hi}] nm"
        )

    mask = (wl >= lo) & (wl <= hi)
    sub_wl = wl[mask]
    if sub_wl.size < 2:
        raise RadiometryError(f"AVW window [{lo}, {hi}] nm contains fewer than 2 wavelengths")

    if integration == "discrete":
        diffs = np.diff(sub_wl)
        if not np.allclose(diffs, diffs[0], rtol=1e-6, atol=1e-9):
            raise RadiometryError(
                "discrete AVW requires uniformly spaced wavelengths; use integration='trapezoid' for non-uniform grids"
            )
        weights = np.ones_like(sub_wl, dtype=float)
    elif integration == "trapezoid":
        weights = _trapezoid_weights(sub_wl)
    else:
        raise RadiometryError(
            f"unknown integration mode {integration!r}; expected 'discrete' or 'trapezoid'"
        )

    sub_rrs = spec[:, mask]
    finite_row = np.isfinite(sub_rrs).all(axis=1)
    nonneg_ok = np.all(sub_rrs >= 0.0, axis=1) if require_nonnegative else np.ones(spec.shape[0], dtype=bool)

    num = sub_rrs @ weights
    den = (sub_rrs / sub_wl[np.newaxis, :]) @ weights

    avw = np.full(spec.shape[0], np.nan, dtype=float)
    valid = finite_row & nonneg_ok & (den > 0.0) & (num > 0.0)
    candidate = np.full(spec.shape[0], np.nan, dtype=float)
    candidate[valid] = num[valid] / den[valid]
    bound_tol = 1e-9 * (hi - lo)
    in_bounds = valid & (candidate >= lo - bound_tol) & (candidate <= hi + bound_tol)
    avw[in_bounds] = np.clip(candidate[in_bounds], lo, hi)

    return float(avw[0]) if was_1d else avw


def _select_wavelength_column(
    spec: np.ndarray,
    wl: np.ndarray,
    target_nm: float,
    *,
    tolerance_nm: float = 0.5,
) -> np.ndarray:
    idx = int(np.argmin(np.abs(wl - target_nm)))
    if abs(float(wl[idx]) - target_nm) > tolerance_nm:
        raise RadiometryError(
            f"target wavelength {target_nm} nm not found within +/-{tolerance_nm} nm "
            f"(nearest is {wl[idx]} nm)"
        )
    return spec[:, idx]


def compute_ndi(
    rrs: ArrayLike,
    wavelengths_nm: ArrayLike,
    lambda_short_nm: float,
    lambda_long_nm: float,
    *,
    tolerance_nm: float = 0.5,
) -> np.ndarray | float:
    """Compute Normalized Difference Index (Rrs(long) - Rrs(short)) / (Rrs(long) + Rrs(short))."""
    spec, was_1d = _as_2d_spectra(rrs)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    r_short = _select_wavelength_column(spec, wl, float(lambda_short_nm), tolerance_nm=tolerance_nm)
    r_long = _select_wavelength_column(spec, wl, float(lambda_long_nm), tolerance_nm=tolerance_nm)

    denom = r_long + r_short
    out = np.full(spec.shape[0], np.nan, dtype=float)
    valid = np.isfinite(r_short) & np.isfinite(r_long) & (denom != 0.0)
    out[valid] = (r_long[valid] - r_short[valid]) / denom[valid]
    return float(out[0]) if was_1d else out


def compute_band_ratio(
    rrs: ArrayLike,
    wavelengths_nm: ArrayLike,
    numerator_nm: float,
    denominator_nm: float,
    *,
    tolerance_nm: float = 0.5,
    require_positive_both: bool = True,
) -> np.ndarray | float:
    """Compute a two-band reflectance ratio Rrs(numerator_nm) / Rrs(denominator_nm).

    By default returns NaN when either band is <= 0 (appropriate before taking
    log10 ratios, matching the 705/665 nm baseline cohort convention).
    """
    spec, was_1d = _as_2d_spectra(rrs)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    r_num = _select_wavelength_column(spec, wl, float(numerator_nm), tolerance_nm=tolerance_nm)
    r_den = _select_wavelength_column(spec, wl, float(denominator_nm), tolerance_nm=tolerance_nm)

    out = np.full(spec.shape[0], np.nan, dtype=float)
    if require_positive_both:
        valid = np.isfinite(r_num) & np.isfinite(r_den) & (r_num > 0.0) & (r_den > 0.0)
    else:
        valid = np.isfinite(r_num) & np.isfinite(r_den) & (r_den != 0.0)
    out[valid] = r_num[valid] / r_den[valid]
    return float(out[0]) if was_1d else out


def compute_qwip_score(
    rrs: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    polynomial_coefficients_desc: Sequence[float],
    config: Mapping[str, Any] | None = None,
    tolerance_nm: float = 0.5,
    integration: str = "discrete",
    require_nonnegative_avw: bool = True,
) -> dict[str, np.ndarray]:
    """Compute QWIP deviation = NDI_obs(492, 665) - P_4(AVW) and pass/fail flags.

    Requires caller-supplied `polynomial_coefficients_desc` (highest power first,
    5 coefficients for the 4th-order AVW polynomial verified from Dierssen et al.
    2022 / Zenodo 10.5281/zenodo.7373840) rather than embedding unverified memory
    constants. Reads `ndi_wavelengths_nm` and `max_abs_deviation` (0.2) from
    config/qc_thresholds.yaml.

    Flag semantics preserve missingness: `qwip_fail` is a float array of
    0.0 (passed), 1.0 (failed: |score| > max_abs_deviation), or NaN (untested).
    """
    coeffs = np.asarray(polynomial_coefficients_desc, dtype=float)
    if coeffs.ndim != 1 or coeffs.size != 5 or not np.isfinite(coeffs).all():
        raise RadiometryError(
            "polynomial_coefficients_desc must be 5 finite floats [p4, p3, p2, p1, p0]"
        )

    spec, _ = _as_2d_spectra(rrs)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    cfg = load_qc_thresholds() if config is None else dict(config)
    ndi_pair = get_threshold(cfg, "qwip.ndi_wavelengths_nm")
    cutoff = float(get_threshold(cfg, "qwip.max_abs_deviation"))

    avw = np.asarray(
        compute_avw(
            spec,
            wl,
            integration=integration,
            require_nonnegative=require_nonnegative_avw,
            config=cfg,
        ),
        dtype=float,
    )
    ndi_obs = np.asarray(
        compute_ndi(spec, wl, float(ndi_pair[0]), float(ndi_pair[1]), tolerance_nm=tolerance_nm),
        dtype=float,
    )
    ndi_pred = np.polyval(coeffs, avw)
    score = ndi_obs - ndi_pred

    qwip_fail = np.full(spec.shape[0], np.nan, dtype=float)
    valid = np.isfinite(score)
    qwip_fail[valid] = (np.abs(score[valid]) > cutoff).astype(float)

    return {
        "avw_nm": avw,
        "ndi_obs": ndi_obs,
        "ndi_pred": ndi_pred,
        "qwip_score": score,
        "qwip_fail": qwip_fail,
    }


def normalize_unit_l2(spectra: ArrayLike) -> np.ndarray:
    """Normalize each spectrum to unit L2 norm (returns NaN row if norm == 0 or non-finite)."""
    spec, was_1d = _as_2d_spectra(spectra)
    norms = np.linalg.norm(spec, axis=1)
    finite_rows = np.isfinite(spec).all(axis=1)
    out = np.full_like(spec, np.nan, dtype=float)
    valid = finite_rows & (norms > 0.0)
    out[valid] = spec[valid] / norms[valid, np.newaxis]
    return out[0] if was_1d else out


def normalize_snv(spectra: ArrayLike) -> np.ndarray:
    """Standard Normal Variate (zero mean, unit population std per spectrum)."""
    spec, was_1d = _as_2d_spectra(spectra)
    finite_rows = np.isfinite(spec).all(axis=1)
    means = np.mean(spec, axis=1)
    stds = np.std(spec, axis=1, ddof=0)
    out = np.full_like(spec, np.nan, dtype=float)
    valid = finite_rows & (stds > 0.0)
    out[valid] = (spec[valid] - means[valid, np.newaxis]) / stds[valid, np.newaxis]
    return out[0] if was_1d else out


def spectral_derivative(
    spectra: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    order: int = 1,
    method: str = "gradient",
    window_length: int = 9,
    polyorder: int = 3,
) -> np.ndarray:
    """Compute 1st or 2nd spectral derivative via finite differences or Savitzky-Golay."""
    if order not in (1, 2):
        raise RadiometryError(f"derivative order must be 1 or 2, got {order}")
    spec, was_1d = _as_2d_spectra(spectra)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    if wl.size < order + 1:
        raise RadiometryError(
            f"order-{order} derivative requires at least {order + 1} wavelengths, got {wl.size}"
        )

    if method == "gradient":
        d1 = np.gradient(spec, wl, axis=1)
        out = d1 if order == 1 else np.gradient(d1, wl, axis=1)
    elif method == "savgol":
        diffs = np.diff(wl)
        if not np.allclose(diffs, diffs[0], rtol=1e-6, atol=1e-9):
            raise RadiometryError("Savitzky-Golay derivative requires uniformly spaced wavelengths")
        if window_length % 2 == 0 or window_length < 3 or window_length > wl.size:
            raise RadiometryError(
                f"window_length must be odd in [3, {wl.size}], got {window_length}"
            )
        if polyorder < order or polyorder >= window_length:
            raise RadiometryError(
                f"polyorder must satisfy order <= polyorder < window_length, got {polyorder}"
            )
        out = savgol_filter(
            spec,
            window_length=window_length,
            polyorder=polyorder,
            deriv=order,
            delta=float(diffs[0]),
            axis=1,
        )
    else:
        raise RadiometryError(f"unknown derivative method {method!r}; expected 'gradient' or 'savgol'")

    return out[0] if was_1d else out


def spectral_angle_rad(query: ArrayLike, reference: ArrayLike) -> np.ndarray:
    """Compute pairwise Spectral Angle Mapper (SAM) distance in radians in [0, pi].

    Uses the numerically stable chord formula 2 * arcsin(min(1, ||u - v||_2 / 2))
    (avoiding arccos(1 - eps) small-angle precision loss for nearly collinear spectra).
    Rows or columns with zero norm or NaN produce NaN distances.
    """
    q, _ = _as_2d_spectra(query)
    r, _ = _as_2d_spectra(reference)
    if q.shape[1] != r.shape[1]:
        raise RadiometryError(
            f"wavelength dimension mismatch: query has {q.shape[1]}, reference has {r.shape[1]}"
        )

    q_norm = np.linalg.norm(q, axis=1)
    r_norm = np.linalg.norm(r, axis=1)
    q_ok = np.isfinite(q).all(axis=1) & (q_norm > 0.0)
    r_ok = np.isfinite(r).all(axis=1) & (r_norm > 0.0)

    out = np.full((q.shape[0], r.shape[0]), np.nan, dtype=float)
    if np.any(q_ok) and np.any(r_ok):
        q_u = q[q_ok] / q_norm[q_ok, np.newaxis]
        r_u = r[r_ok] / r_norm[r_ok, np.newaxis]
        chord = cdist(q_u, r_u, metric="euclidean")
        angles = 2.0 * np.arcsin(np.clip(0.5 * chord, 0.0, 1.0))
        out[np.ix_(q_ok, r_ok)] = angles
    return out
