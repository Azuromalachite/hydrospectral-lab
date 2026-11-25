"""CIE 1931 2-degree water colourimetry, hue angle, display sRGB, and SAM OWT classification.

Design principles (handoff §5.2 & §8):
- Quantitative colourimetry (CIE 1931 2° XYZ tristimulus, chromaticity (x, y),
  and van der Woerd & Wernand 2015 hue angle alpha) is strictly separated from
  approximate display sRGB rendering.
- Uses authoritative ISO/CIE 11664-1 1931 2° Standard Observer colour-matching
  functions and CIE Standard Illuminants ('E' and 'D65') provided by
  `colour-science` rather than hand-transcribed lookup tables.
- Negative Rrs values are never silently clipped before integration.
- Optical Water Type (OWT) matching by Spectral Angle Mapper (SAM) retains
  absolute spectral magnitude alongside nearest-class angle and an explicit
  out-of-distribution (`is_unclassified`) flag.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='.*"Matplotlib" related API features.*')
    import colour

from hydrospectral.radiometry import spectral_angle_rad
from hydrospectral.thresholds import get_threshold, load_qc_thresholds

SUPPORTED_ILLUMINANTS = frozenset({"E", "D65"})
ILLUMINANT_WHITE_POINTS_XY: dict[str, tuple[float, float]] = {
    "E": (1.0 / 3.0, 1.0 / 3.0),
    "D65": (0.3127, 0.3290),
}
_CIE_1931_NAME = "CIE 1931 2 Degree Standard Observer"


class ColorimetryError(ValueError):
    """Raised when colourimetric or OWT classification inputs violate domain invariants."""


def _as_2d_spectra(spectra: ArrayLike) -> tuple[np.ndarray, bool]:
    arr = np.asarray(spectra, dtype=float)
    if arr.ndim == 1:
        return arr[np.newaxis, :], True
    if arr.ndim == 2:
        return arr, False
    raise ColorimetryError(f"spectra must be 1D or 2D array, got ndim={arr.ndim}")


def _validate_wavelengths(wavelengths_nm: ArrayLike, expected_len: int) -> np.ndarray:
    wl = np.asarray(wavelengths_nm, dtype=float)
    if wl.ndim != 1 or wl.size != expected_len:
        raise ColorimetryError(
            f"wavelengths_nm must be 1D of length {expected_len}, got shape {wl.shape}"
        )
    if not np.isfinite(wl).all() or np.any(wl <= 0.0):
        raise ColorimetryError("wavelengths_nm must be strictly positive finite numbers")
    if wl.size > 1 and not np.all(np.diff(wl) > 0.0):
        raise ColorimetryError("wavelengths_nm must be strictly increasing")
    return wl


def _trapezoid_weights(grid: np.ndarray) -> np.ndarray:
    if grid.size < 2:
        raise ColorimetryError(f"trapezoidal integration requires at least 2 wavelengths, got {grid.size}")
    dw = np.diff(grid)
    w = np.zeros_like(grid, dtype=float)
    w[0] = 0.5 * dw[0]
    w[-1] = 0.5 * dw[-1]
    if grid.size > 2:
        w[1:-1] = 0.5 * (dw[:-1] + dw[1:])
    return w


def _cie_1931_cmfs_and_illuminant(
    wavelengths_nm: np.ndarray,
    illuminant: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate official CIE 1931 2° CMFs and standard illuminant onto wavelengths_nm."""
    if illuminant not in SUPPORTED_ILLUMINANTS:
        allowed = ", ".join(sorted(SUPPORTED_ILLUMINANTS))
        raise ColorimetryError(f"unsupported illuminant {illuminant!r}; expected one of: {allowed}")

    cmfs = colour.MSDS_CMFS[_CIE_1931_NAME]
    cmf_wl = np.asarray(cmfs.wavelengths, dtype=float)
    cmf_vals = np.asarray(cmfs.values, dtype=float)
    if wavelengths_nm[0] < cmf_wl[0] or wavelengths_nm[-1] > cmf_wl[-1]:
        raise ColorimetryError(
            f"wavelength window [{wavelengths_nm[0]}, {wavelengths_nm[-1]}] nm exceeds "
            f"CIE 1931 observer range [{cmf_wl[0]}, {cmf_wl[-1]}] nm"
        )

    interp_cmf = np.column_stack(
        [np.interp(wavelengths_nm, cmf_wl, cmf_vals[:, i]) for i in range(3)]
    )

    if illuminant == "E":
        illum_spd = np.ones_like(wavelengths_nm, dtype=float)
    else:
        sd = colour.SDS_ILLUMINANTS[illuminant]
        sd_wl = np.asarray(sd.wavelengths, dtype=float)
        sd_vals = np.asarray(sd.values, dtype=float)
        if wavelengths_nm[0] < sd_wl[0] or wavelengths_nm[-1] > sd_wl[-1]:
            raise ColorimetryError(
                f"wavelength window [{wavelengths_nm[0]}, {wavelengths_nm[-1]}] nm exceeds "
                f"illuminant {illuminant!r} range [{sd_wl[0]}, {sd_wl[-1]}] nm"
            )
        illum_spd = np.interp(wavelengths_nm, sd_wl, sd_vals)

    return interp_cmf, illum_spd


def rrs_to_xyz(
    rrs: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    illuminant: str = "E",
    min_nm: float | None = None,
    max_nm: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Integrate hyperspectral Rrs into CIE 1931 2-degree XYZ tristimulus values.

    Computes trapezoidal integrals:
        [X, Y, Z] = integral(Rrs(lambda) * I(lambda) * [xbar, ybar, zbar](lambda) dlambda)
                    / integral(I(lambda) * ybar(lambda) dlambda)

    Default visible window [400, 700] nm is loaded from config/qc_thresholds.yaml
    (`avw.visible_window_nm`). Preserves negative Rrs values during integration
    and returns NaN rows for any spectrum containing non-finite values inside
    [min_nm, max_nm].
    """
    spec, was_1d = _as_2d_spectra(rrs)
    wl = _validate_wavelengths(wavelengths_nm, spec.shape[1])

    cfg = load_qc_thresholds() if config is None else dict(config)
    lo = float(get_threshold(cfg, "avw.visible_window_nm.min_nm")) if min_nm is None else float(min_nm)
    hi = float(get_threshold(cfg, "avw.visible_window_nm.max_nm")) if max_nm is None else float(max_nm)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        raise ColorimetryError(
            f"colour integration window must be finite with max_nm > min_nm, got [{lo}, {hi}]"
        )
    if wl[0] > lo or wl[-1] < hi:
        raise ColorimetryError(
            f"wavelength grid [{wl[0]}, {wl[-1]}] nm does not span colour window [{lo}, {hi}] nm"
        )

    mask = (wl >= lo) & (wl <= hi)
    sub_wl = wl[mask]
    if sub_wl.size < 2:
        raise ColorimetryError(f"colour window [{lo}, {hi}] nm contains fewer than 2 wavelengths")

    cmf, illum = _cie_1931_cmfs_and_illuminant(sub_wl, illuminant)
    trap_w = _trapezoid_weights(sub_wl)
    k_norm = float(np.sum(illum * cmf[:, 1] * trap_w))
    if k_norm <= 0.0:
        raise ColorimetryError("illuminant luminance integral is non-positive")

    kernel = (illum * trap_w)[:, np.newaxis] * cmf / k_norm
    sub_rrs = spec[:, mask]
    finite_rows = np.isfinite(sub_rrs).all(axis=1)

    xyz = np.full((spec.shape[0], 3), np.nan, dtype=float)
    if np.any(finite_rows):
        xyz[finite_rows] = sub_rrs[finite_rows] @ kernel

    return xyz[0] if was_1d else xyz


def xyz_to_chromaticity(xyz: ArrayLike) -> np.ndarray:
    """Convert CIE XYZ tristimulus values to chromaticity coordinates (x, y).

    Returns NaN rows wherever any XYZ component is non-finite or negative, or
    where X + Y + Z <= 0, avoiding unphysical coordinates outside the CIE locus.
    """
    arr = np.asarray(xyz, dtype=float)
    was_1d = arr.ndim == 1
    if was_1d:
        arr = arr[np.newaxis, :]
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ColorimetryError(f"xyz must have shape (3,) or (n, 3), got {arr.shape}")

    finite = np.isfinite(arr).all(axis=1)
    nonneg = (arr >= 0.0).all(axis=1)
    total = np.sum(arr, axis=1)
    valid = finite & nonneg & (total > 0.0)

    xy = np.full((arr.shape[0], 2), np.nan, dtype=float)
    xy[valid, 0] = arr[valid, 0] / total[valid]
    xy[valid, 1] = arr[valid, 1] / total[valid]
    return xy[0] if was_1d else xy


def chromaticity_to_hue_angle_deg(
    xy: ArrayLike,
    *,
    white_point: tuple[float, float] = (1.0 / 3.0, 1.0 / 3.0),
) -> np.ndarray | float:
    """Compute ocean-colour CIE hue angle alpha strictly in [0, 360) degrees (van der Woerd & Wernand 2015).

    alpha = atan2(y - y_w, x - x_w) * (180 / pi) mod 360 (wrapping 360.0 -> 0.0).
    Under illuminant E white point (1/3, 1/3), deep indigo-blue clear ocean lies
    near ~225-230 deg (Forel-Ule 1), blue-green >90 deg, yellow-green ~65-90 deg,
    and brown/CDOM-rich waters toward ~20-60 deg. Returns NaN at the exact
    achromatic white point (dx == 0 and dy == 0) or for non-finite inputs.
    """
    arr = np.asarray(xy, dtype=float)
    was_1d = arr.ndim == 1
    if was_1d:
        arr = arr[np.newaxis, :]
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ColorimetryError(f"xy must have shape (2,) or (n, 2), got {arr.shape}")

    if len(white_point) != 2:
        raise ColorimetryError(f"white_point must be a 2-tuple (xw, yw), got {white_point!r}")
    xw, yw = float(white_point[0]), float(white_point[1])
    if not (math.isfinite(xw) and math.isfinite(yw)):
        raise ColorimetryError(f"white_point must be finite, got {white_point!r}")

    dx = arr[:, 0] - xw
    dy = arr[:, 1] - yw
    finite = np.isfinite(dx) & np.isfinite(dy)
    nonzero = np.hypot(dx, dy) > 1e-15
    valid = finite & nonzero

    alpha = np.full(arr.shape[0], np.nan, dtype=float)
    wrapped = np.mod(np.degrees(np.arctan2(dy[valid], dx[valid])), 360.0)
    wrapped = np.where(wrapped >= 360.0, 0.0, wrapped)
    alpha[valid] = wrapped
    return float(alpha[0]) if was_1d else alpha


def _srgb_oetf(linear_rgb: np.ndarray) -> np.ndarray:
    """IEC 61966-2-1 sRGB opto-electronic transfer function on [0, 1]."""
    clipped = np.clip(linear_rgb, 0.0, 1.0)
    return np.where(
        clipped <= 0.0031308,
        12.92 * clipped,
        1.055 * np.power(clipped, 1.0 / 2.4) - 0.055,
    )


def xyz_to_display_srgb(
    xyz: ArrayLike,
    *,
    illuminant: str = "E",
    exposure: str = "max_y",
    gamut: str = "clip",
) -> np.ndarray:
    """Convert CIE XYZ tristimulus values to approximate display sRGB in [0, 1].

    Separate from quantitative CIE chromaticity: display sRGB depends on explicit
    white-point chromatic adaptation (Bradford to D65), exposure normalization,
    and gamut mapping.
    """
    if illuminant not in SUPPORTED_ILLUMINANTS:
        allowed = ", ".join(sorted(SUPPORTED_ILLUMINANTS))
        raise ColorimetryError(f"unsupported illuminant {illuminant!r}; expected one of: {allowed}")
    if exposure not in ("max_y", "per_spectrum_max", "none"):
        raise ColorimetryError(f"unknown exposure mode {exposure!r}")
    if gamut not in ("clip", "desaturate"):
        raise ColorimetryError(f"unknown gamut mode {gamut!r}")

    arr = np.asarray(xyz, dtype=float)
    was_1d = arr.ndim == 1
    if was_1d:
        arr = arr[np.newaxis, :]
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ColorimetryError(f"xyz must have shape (3,) or (n, 3), got {arr.shape}")

    valid = np.isfinite(arr).all(axis=1) & (arr[:, 1] > 0.0) & (arr >= 0.0).all(axis=1)
    out = np.full_like(arr, np.nan, dtype=float)
    if not np.any(valid):
        return out[0] if was_1d else out

    xyz_v = arr[valid].copy()
    if exposure == "max_y":
        max_y = float(np.max(xyz_v[:, 1]))
        if max_y > 0.0:
            xyz_v = xyz_v / max_y

    if illuminant != "D65":
        src_wp = colour.xy_to_XYZ(np.array(ILLUMINANT_WHITE_POINTS_XY[illuminant]))
        dst_wp = colour.xy_to_XYZ(np.array(ILLUMINANT_WHITE_POINTS_XY["D65"]))
        xyz_d65 = colour.chromatic_adaptation(xyz_v, src_wp, dst_wp, transform="Bradford")
    else:
        xyz_d65 = xyz_v

    m_xyz_to_rgb = np.array(
        [
            [3.2406, -1.5372, -0.4986],
            [-0.9689, 1.8758, 0.0415],
            [0.0557, -0.2040, 1.0570],
        ],
        dtype=float,
    )
    lin_rgb = xyz_d65 @ m_xyz_to_rgb.T

    if gamut == "desaturate":
        y_lum = xyz_d65[:, 1:2]
        min_ch = np.min(lin_rgb, axis=1, keepdims=True)
        neg_mask = (min_ch < 0.0) & (y_lum > 0.0)
        scale = np.ones_like(min_ch)
        scale[neg_mask] = y_lum[neg_mask] / (y_lum[neg_mask] - min_ch[neg_mask])
        lin_rgb = y_lum + scale * (lin_rgb - y_lum)

    if exposure == "per_spectrum_max":
        lin_pos = np.maximum(lin_rgb, 0.0)
        peak = np.max(lin_pos, axis=1, keepdims=True)
        pos_peak = peak > 0.0
        lin_rgb = np.where(pos_peak, lin_pos / np.where(pos_peak, peak, 1.0), 0.0)

    out[valid] = _srgb_oetf(lin_rgb)
    return out[0] if was_1d else out


def classify_owt_by_sam(
    spectra: ArrayLike,
    reference_spectra: ArrayLike,
    class_labels: Sequence[str],
    *,
    wavelengths_nm: ArrayLike | None = None,
    max_angle_rad: float | None = None,
) -> dict[str, Any]:
    """Classify aquatic spectra into reference Optical Water Types via Spectral Angle Mapper.

    Retains absolute spectral magnitude (`magnitude`: trapezoidal integral area
    when `wavelengths_nm` is provided, else L2 norm) alongside `min_sam_rad` and
    `is_unclassified` so spectral-shape matching never silently discards
    brightness or out-of-distribution distance.
    """
    q, _ = _as_2d_spectra(spectra)
    ref, _ = _as_2d_spectra(reference_spectra)
    if q.shape[1] != ref.shape[1]:
        raise ColorimetryError(
            f"wavelength dimension mismatch: spectra has {q.shape[1]}, reference has {ref.shape[1]}"
        )
    labels = [str(lbl) for lbl in class_labels]
    if len(labels) != ref.shape[0] or not labels:
        raise ColorimetryError(
            f"class_labels length ({len(labels)}) must match reference_spectra rows ({ref.shape[0]})"
        )
    if len(set(labels)) != len(labels):
        raise ColorimetryError("class_labels must be unique")
    if any(not lbl.strip() for lbl in labels):
        raise ColorimetryError("class_labels must not contain empty strings")
    if not np.isfinite(ref).all() or np.any(np.linalg.norm(ref, axis=1) <= 0.0):
        raise ColorimetryError("reference_spectra must contain finite, non-zero-norm rows")
    if max_angle_rad is not None:
        if not math.isfinite(max_angle_rad) or max_angle_rad <= 0.0 or max_angle_rad > math.pi:
            raise ColorimetryError(f"max_angle_rad must be in (0, pi], got {max_angle_rad!r}")

    if wavelengths_nm is not None:
        wl = _validate_wavelengths(wavelengths_nm, q.shape[1])
        trap_w = _trapezoid_weights(wl)
        finite_q = np.isfinite(q).all(axis=1)
        magnitude = np.full(q.shape[0], np.nan, dtype=float)
        magnitude[finite_q] = q[finite_q] @ trap_w
        magnitude_kind = "trapezoidal_area_sr^-1_nm"
    else:
        finite_q = np.isfinite(q).all(axis=1)
        magnitude = np.full(q.shape[0], np.nan, dtype=float)
        magnitude[finite_q] = np.linalg.norm(q[finite_q], axis=1)
        magnitude_kind = "l2_norm_sr^-1"

    angles = spectral_angle_rad(q, ref)
    assigned = np.full(q.shape[0], None, dtype=object)
    min_sam = np.full(q.shape[0], np.nan, dtype=float)
    unclassified = np.ones(q.shape[0], dtype=bool)

    for i in range(q.shape[0]):
        row = angles[i]
        if not np.isfinite(row).all():
            continue
        best_idx = int(np.argmin(row))
        best_angle = float(row[best_idx])
        min_sam[i] = best_angle
        if max_angle_rad is None or best_angle <= max_angle_rad:
            assigned[i] = labels[best_idx]
            unclassified[i] = False

    return {
        "assigned_label": assigned,
        "min_sam_rad": min_sam,
        "all_sam_rad": angles,
        "is_unclassified": unclassified,
        "magnitude": magnitude,
        "magnitude_kind": magnitude_kind,
        "class_labels": labels,
    }
