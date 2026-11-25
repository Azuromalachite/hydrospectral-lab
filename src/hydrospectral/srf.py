"""Sensor Spectral Response Function (SRF) loading and band convolution.

Implements trapezoidal integration over measured sensor response curves:
- Reflectance-only approximation:
    R_b = integral(Rrs(lambda) * S_b(lambda) dlambda) / integral(S_b(lambda) dlambda)
- Energy-weighted irradiance convolution (Burggraaff 2020, DOI: 10.1364/OE.391470):
    R_b = integral(Rrs(lambda) * Es(lambda) * S_b(lambda) dlambda)
          / integral(Es(lambda) * S_b(lambda) dlambda)
  Note: For photon-counting quantum-efficiency SRFs, Burggraaff (2020) Eq. (5)
  includes an additional wavelength factor `lambda` (i.e., pass `es_spectrum * lambda`).

Refuses non-monotonic wavelength grids, negative responses, or nonzero SRF
support extending outside the target hyperspectral interval.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike


class SRFError(ValueError):
    """Raised when an SRF table or convolution grid violates radiometric invariants."""


def load_srf_csv(
    path: Path,
    *,
    wavelength_col: str = "wavelength_nm",
    bands: Sequence[str] | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Load a measured sensor SRF CSV (UTF-8) and validate monotonicity & non-negativity."""
    target = Path(path)
    if not target.is_file():
        raise SRFError(f"SRF CSV file not found: {target}")

    df = pd.read_csv(target, encoding="utf-8")
    if wavelength_col not in df.columns:
        raise SRFError(f"SRF CSV missing wavelength column {wavelength_col!r}")

    df = df.sort_values(wavelength_col).reset_index(drop=True)
    wl = df[wavelength_col].to_numpy(dtype=float)
    if wl.size < 2 or not np.isfinite(wl).all() or not np.all(np.diff(wl) > 0):
        raise SRFError("SRF wavelength grid must be finite and strictly increasing")

    selected = [c for c in df.columns if c != wavelength_col] if bands is None else list(bands)
    if not selected:
        raise SRFError("no sensor bands selected from SRF CSV")

    missing = [b for b in selected if b not in df.columns]
    if missing:
        raise SRFError(f"SRF CSV missing requested band column(s): {', '.join(missing)}")

    curves: dict[str, np.ndarray] = {}
    for band in selected:
        r = df[band].to_numpy(dtype=float)
        if not np.isfinite(r).all():
            raise SRFError(f"band {band!r} contains non-finite response values")
        if np.any(r < 0.0):
            raise SRFError(f"band {band!r} contains negative spectral response values")
        if float(r.sum()) <= 0.0:
            raise SRFError(f"band {band!r} has zero total spectral response")
        curves[band] = r

    return wl, curves


def _trapezoid_grid_weights(grid_nm: np.ndarray) -> np.ndarray:
    """Exact composite trapezoidal integration weights for an arbitrary increasing grid."""
    dw = np.diff(grid_nm)
    trap = np.zeros_like(grid_nm, dtype=float)
    trap[0] = 0.5 * dw[0]
    trap[-1] = 0.5 * dw[-1]
    if grid_nm.size > 2:
        trap[1:-1] = 0.5 * (dw[:-1] + dw[1:])
    return trap


def build_srf_weight_matrix(
    target_wavelengths_nm: ArrayLike,
    srf_wavelengths_nm: ArrayLike,
    band_responses: dict[str, ArrayLike],
    *,
    band_order: Sequence[str] | None = None,
    es_spectrum: ArrayLike | None = None,
    support_rel_tol: float = 1e-8,
) -> tuple[np.ndarray, list[str]]:
    """Build a (n_wavelengths, n_bands) normalized SRF convolution matrix W.

    Every column of W is non-negative and sums to 1 so a flat spectrum
    Rrs(lambda) == c maps exactly to c in every band. Refuses any band with
    significant response (> support_rel_tol * max) outside
    [target_wavelengths_nm.min(), target_wavelengths_nm.max()] or truncated at
    an interior SRF grid boundary with nonzero endpoint response.
    """
    target_wl = np.asarray(target_wavelengths_nm, dtype=float)
    if target_wl.ndim != 1 or target_wl.size < 2 or not np.isfinite(target_wl).all() or not np.all(np.diff(target_wl) > 0):
        raise SRFError("target_wavelengths_nm must be 1D, finite, and strictly increasing")

    srf_wl = np.asarray(srf_wavelengths_nm, dtype=float)
    if srf_wl.ndim != 1 or srf_wl.size < 2 or not np.isfinite(srf_wl).all() or not np.all(np.diff(srf_wl) > 0):
        raise SRFError("srf_wavelengths_nm must be 1D, finite, and strictly increasing")

    es_arr: np.ndarray | None = None
    if es_spectrum is not None:
        es_arr = np.asarray(es_spectrum, dtype=float)
        if es_arr.shape != target_wl.shape:
            raise SRFError(
                f"es_spectrum shape {es_arr.shape} must match target_wavelengths_nm {target_wl.shape}"
            )
        if not np.isfinite(es_arr).all() or np.any(es_arr <= 0.0):
            raise SRFError("es_spectrum must be strictly positive and finite")

    names = list(band_responses.keys()) if band_order is None else list(band_order)
    if not names:
        raise SRFError("band_responses must contain at least one band")

    trap_w = _trapezoid_grid_weights(target_wl)
    columns: list[np.ndarray] = []

    for name in names:
        if name not in band_responses:
            raise SRFError(f"band {name!r} missing from band_responses")
        resp = np.asarray(band_responses[name], dtype=float)
        if resp.shape != srf_wl.shape:
            raise SRFError(
                f"band {name!r} response shape {resp.shape} does not match SRF grid {srf_wl.shape}"
            )
        if not np.isfinite(resp).all() or np.any(resp < 0.0):
            raise SRFError(f"band {name!r} response must be finite and non-negative")
        rmax = float(resp.max())
        if rmax <= 0.0:
            raise SRFError(f"band {name!r} response has zero peak")

        outside = (srf_wl < target_wl[0]) | (srf_wl > target_wl[-1])
        if np.any((resp > support_rel_tol * rmax) & outside):
            raise SRFError(
                f"band {name!r} has nonzero SRF support outside target range "
                f"[{target_wl[0]}, {target_wl[-1]}] nm"
            )
        # If the SRF table covers a narrower window inside target_wl, require
        # its endpoints to have decayed to zero so zero-padding does not clip tails.
        if srf_wl[0] > target_wl[0] and float(resp[0]) > support_rel_tol * rmax:
            raise SRFError(
                f"band {name!r} SRF grid starts inside target range at {srf_wl[0]} nm with nonzero response {resp[0]}"
            )
        if srf_wl[-1] < target_wl[-1] and float(resp[-1]) > support_rel_tol * rmax:
            raise SRFError(
                f"band {name!r} SRF grid ends inside target range at {srf_wl[-1]} nm with nonzero response {resp[-1]}"
            )

        interp_resp = np.interp(target_wl, srf_wl, resp, left=0.0, right=0.0)
        weighted = interp_resp * trap_w
        if es_arr is not None:
            weighted = weighted * es_arr
        denom = float(weighted.sum())
        if denom <= 0.0:
            raise SRFError(f"band {name!r} has zero integrated weight over target range")
        columns.append(weighted / denom)

    W = np.stack(columns, axis=1)
    return W, names


def build_rectangular_weight_matrix(
    target_wavelengths_nm: ArrayLike,
    band_specs_nm: dict[str, tuple[float, float]],
) -> tuple[np.ndarray, list[str]]:
    """Build an approximate rectangular bandpass matrix from {band: (center_nm, width_nm)}.

    Uses trapezoidal grid weights over the covered wavelengths so non-uniform
    grids remain unbiased. Intended strictly for transparent comparison with
    approximate rectangular baselines (e.g., GL-R06), never as a substitute for
    official measured SRFs.
    """
    wl = np.asarray(target_wavelengths_nm, dtype=float)
    if wl.ndim != 1 or wl.size < 2 or not np.isfinite(wl).all() or not np.all(np.diff(wl) > 0):
        raise SRFError("target_wavelengths_nm must be 1D, finite, and strictly increasing")
    if not band_specs_nm:
        raise SRFError("band_specs_nm must be non-empty")

    trap_w = _trapezoid_grid_weights(wl)
    names = list(band_specs_nm.keys())
    columns: list[np.ndarray] = []
    for name in names:
        center, width = band_specs_nm[name]
        c_f, w_f = float(center), float(width)
        if not (math.isfinite(c_f) and math.isfinite(w_f)) or w_f <= 0.0:
            raise SRFError(f"band {name!r} center and width must be finite with width > 0")
        lo, hi = c_f - 0.5 * w_f, c_f + 0.5 * w_f
        if lo < wl[0] or hi > wl[-1]:
            raise SRFError(
                f"rectangular band {name!r} [{lo}, {hi}] nm extends outside "
                f"target grid [{wl[0]}, {wl[-1]}] nm"
            )
        mask = (wl >= lo) & (wl <= hi)
        if not np.any(mask):
            raise SRFError(f"rectangular band {name!r} covers zero target wavelengths")
        col = np.where(mask, trap_w, 0.0)
        columns.append(col / col.sum())
    return np.stack(columns, axis=1), names


def convolve_spectra(spectra: ArrayLike, weight_matrix: ArrayLike) -> np.ndarray:
    """Convolve 1D or 2D spectra with a normalized non-negative (n_wavelengths, n_bands) matrix.

    Integrates each band over its strictly positive support (`W[:, b] > 0`) so
    out-of-band NaNs (e.g., a masked O2 A-band at 762 nm) do not contaminate
    unrelated bands (e.g., 490 nm), while any in-band NaN still propagates NaN.
    """
    spec = np.asarray(spectra, dtype=float)
    W = np.asarray(weight_matrix, dtype=float)
    if W.ndim != 2:
        raise SRFError(f"weight_matrix must be 2D, got ndim={W.ndim}")
    if not np.isfinite(W).all() or np.any(W < 0.0):
        raise SRFError("weight_matrix must be finite and non-negative")
    if not np.allclose(W.sum(axis=0), 1.0, rtol=1e-6, atol=1e-9):
        raise SRFError("every column of weight_matrix must sum to 1.0")

    was_1d = spec.ndim == 1
    if was_1d:
        spec_2d = spec[np.newaxis, :]
    elif spec.ndim == 2:
        spec_2d = spec
    else:
        raise SRFError(f"spectra must be 1D or 2D, got ndim={spec.ndim}")

    if spec_2d.shape[1] != W.shape[0]:
        raise SRFError(
            f"spectra wavelength dimension {spec_2d.shape[1]} != weight_matrix rows {W.shape[0]}"
        )

    out = np.empty((spec_2d.shape[0], W.shape[1]), dtype=float)
    for b in range(W.shape[1]):
        support = W[:, b] > 0.0
        out[:, b] = spec_2d[:, support] @ W[support, b]
    return out[0] if was_1d else out
