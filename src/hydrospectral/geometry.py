"""Footprint geometric screening and water-mask distance eligibility (HS-R03).

These functions compute conservative geometric footprint margins for square
pixels in idealized straight channels and projected water masks. They are
screening thresholds, NOT corrections for atmospheric adjacency, point-spread
function, glint, clouds, or shallow-water bottom reflectance.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy.ndimage import distance_transform_edt

from hydrospectral.thresholds import get_threshold, load_qc_thresholds

DEFAULT_SENSOR_PIXELS_M: dict[str, float] = {
    "Sentinel-2 visible": 10.0,
    "Sentinel-2 red edge": 20.0,
    "EnMAP / PRISMA": 30.0,
    "Sentinel-3 OLCI": 300.0,
    "PACE OCI": 1200.0,
}


class GeometryError(ValueError):
    """Raised when geometric screening parameters or raster masks are invalid."""


def window_min_width_m(
    pixel_size_m: float,
    *,
    window_pixels: int = 1,
    bank_buffer_m: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> float:
    """Compute conservative minimum channel width W_min = k * sqrt(2) * p + 2 * b.

    For a straight channel of width W, a centred k x k block of square pixels of
    side p requires bank clearance at least k * p / sqrt(2) + b on each bank to
    guarantee no direct land intersection at any orientation.
    """
    p = float(pixel_size_m)
    if not math.isfinite(p) or p <= 0.0:
        raise GeometryError(f"pixel_size_m must be finite and > 0, got {pixel_size_m!r}")
    if isinstance(window_pixels, bool) or not isinstance(window_pixels, int) or window_pixels < 1:
        raise GeometryError(f"window_pixels must be an integer >= 1, got {window_pixels!r}")

    if bank_buffer_m is None:
        cfg = load_qc_thresholds() if config is None else dict(config)
        b = float(get_threshold(cfg, "screening_geometry.default_bank_buffer_m"))
    else:
        b = float(bank_buffer_m)
    if not math.isfinite(b) or b < 0.0:
        raise GeometryError(f"bank_buffer_m must be finite and >= 0, got {bank_buffer_m!r}")

    return float(window_pixels) * math.sqrt(2.0) * p + 2.0 * b


def single_pixel_min_width_m(
    pixel_size_m: float,
    *,
    bank_buffer_m: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> float:
    """Compute single-pixel conservative screening width W_min = sqrt(2) * p + 2 * b."""
    return window_min_width_m(
        pixel_size_m,
        window_pixels=1,
        bank_buffer_m=bank_buffer_m,
        config=config,
    )


def sensor_screening_table(
    sensors_m: Mapping[str, float] | None = None,
    *,
    bank_buffer_m: float | None = None,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of single-pixel and 3x3 screening widths per sensor."""
    mapping = DEFAULT_SENSOR_PIXELS_M if sensors_m is None else dict(sensors_m)
    if not mapping:
        raise GeometryError("sensors_m must contain at least one sensor")

    rows: list[dict[str, Any]] = []
    for name, px in mapping.items():
        rows.append(
            {
                "sensor": name,
                "pixel_size_m": float(px),
                "single_pixel_min_width_m": single_pixel_min_width_m(
                    px, bank_buffer_m=bank_buffer_m, config=config
                ),
                "window_3x3_min_width_m": window_min_width_m(
                    px, window_pixels=3, bank_buffer_m=bank_buffer_m, config=config
                ),
            }
        )
    return pd.DataFrame(rows)


def _validate_binary_water_mask(water_mask: ArrayLike) -> np.ndarray:
    raw = np.asarray(water_mask)
    if raw.ndim != 2 or raw.size == 0:
        raise GeometryError(
            f"water_mask must be a non-empty 2D boolean or 0/1 integer array, got shape {raw.shape}"
        )
    if raw.dtype == np.bool_:
        return raw
    if np.issubdtype(raw.dtype, np.integer):
        unique_vals = set(np.unique(raw).tolist())
        if not unique_vals.issubset({0, 1}):
            bad = sorted(unique_vals - {0, 1})[:5]
            raise GeometryError(
                f"integer water_mask must contain strictly 0 (land) and 1 (water); "
                f"found unexpected nodata/class value(s) {bad}"
            )
        return raw.astype(bool)
    raise GeometryError(
        f"water_mask must have boolean or 0/1 integer dtype (got {raw.dtype}); "
        "convert nodata/NaN values explicitly before eligibility screening"
    )


def compute_water_mask_eligibility(
    water_mask: ArrayLike,
    *,
    pixel_spacing_m: tuple[float, float],
    sensor_pixels_m: Sequence[float] = (10.0, 20.0, 30.0, 300.0, 1200.0),
    buffers_m: Sequence[float] = (0.0, 20.0, 50.0),
    windows: Sequence[int] = (1, 3),
) -> pd.DataFrame:
    """Compute eligible water cells, area (km^2), and fraction via Euclidean distance transform.

    Requires an explicit boolean or strictly {0, 1} integer 2D mask (refusing
    float/NaN or nodata values such as -9999 or 255).

    Matches the conservative geometry in HS-R03:
    - Pads the 2D boolean water mask with a 1-cell non-water border so cropped
      raster edges are treated as unknown/non-water rather than infinite water.
    - Subtracts a half-pixel diagonal margin `hypot(dx, dy) / 2` from the EDT
      distance before testing `dist >= k * p / sqrt(2) + b`.
    """
    mask = _validate_binary_water_mask(water_mask)
    total_water = int(mask.sum())
    if total_water == 0:
        raise GeometryError("water_mask contains zero water cells")

    if len(pixel_spacing_m) != 2:
        raise GeometryError("pixel_spacing_m must be a (dy_m, dx_m) pair")
    dy_m, dx_m = float(pixel_spacing_m[0]), float(pixel_spacing_m[1])
    if not (math.isfinite(dy_m) and math.isfinite(dx_m) and dy_m > 0.0 and dx_m > 0.0):
        raise GeometryError(f"pixel_spacing_m must be positive finite meters, got {pixel_spacing_m!r}")

    padded = np.pad(mask, pad_width=1, mode="constant", constant_values=False)
    dist_m = (
        distance_transform_edt(padded, sampling=(dy_m, dx_m))[1:-1, 1:-1]
        - 0.5 * math.hypot(dx_m, dy_m)
    )

    cell_area_km2 = (dx_m * dy_m) / 1e6
    rows: list[dict[str, Any]] = []
    for p in sensor_pixels_m:
        p_f = float(p)
        if not math.isfinite(p_f) or p_f <= 0.0:
            raise GeometryError(f"sensor pixel size must be > 0, got {p!r}")
        for b in buffers_m:
            b_f = float(b)
            if not math.isfinite(b_f) or b_f < 0.0:
                raise GeometryError(f"buffer must be >= 0, got {b!r}")
            for k in windows:
                if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                    raise GeometryError(f"window size must be integer >= 1, got {k!r}")
                required_dist = (float(k) * p_f) / math.sqrt(2.0) + b_f
                eligible = mask & (dist_m >= required_dist)
                n_elig = int(eligible.sum())
                rows.append(
                    {
                        "pixel_m": p_f,
                        "buffer_m": b_f,
                        "window": k,
                        "required_bank_dist_m": required_dist,
                        "eligible_mask_cells": n_elig,
                        "eligible_area_km2": n_elig * cell_area_km2,
                        "eligible_water_fraction": n_elig / total_water,
                    }
                )
    return pd.DataFrame(rows)
