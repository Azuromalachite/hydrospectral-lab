"""NASA PACE OCI Level-2 AOP NetCDF4/HDF5 reader, flag decoder, RGB, and swath PCA.

Physical and provenance conventions (handoff §7.2-7.3 & AGENTS.md rule 2):
- Unpacks CF-1.8 packed integer variables using `_FillValue`, `scale_factor`,
  `add_offset`, and `valid_min`/`valid_max`/`valid_range` while preserving
  negative Rrs values for QC diagnostics (never silently clipping to zero).
- Decodes `l2_flags` bitmasks using unsigned 32-bit operations so bit 31
  (`0x80000000`) never overflows signed int32 arithmetic, and bitwise-ORs
  duplicate flag names (such as NASA's repeated `SPARE` bits).
- Exposes exact `in_bbox_mask` on curvilinear/rotated swaths so corners outside
  a geographic bounding box can be cleanly masked.
- Computes swath PCA via zero-copy wavelength slicing and the O(n_wl^2) Gram
  matrix `Xc.T @ Xc` when `n_valid > n_wl` to stay well inside CPU memory on
  full 1710 x 1272 PACE granules.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from numpy.typing import ArrayLike

from hydrospectral.provenance import CohortCounts, sha256_file

DEFAULT_PACE_EXCLUDE_FLAGS: tuple[str, ...] = (
    "ATMFAIL",
    "LAND",
    "HIGLINT",
    "HILT",
    "HISATZEN",
    "STRAYLIGHT",
    "CLDICE",
    "HISOLZEN",
    "LOWLW",
    "CHLFAIL",
    "NAVFAIL",
)


class PaceDataError(ValueError):
    """Raised when PACE OCI granule structure, packing, flags, or swath inputs are invalid."""


@dataclass(frozen=True)
class PaceL2AopSwath:
    """Unpacked NASA PACE OCI Level-2 AOP swath data and metadata."""

    rrs: np.ndarray  # (n_lines, n_pixels, n_wavelengths), sr^-1 (negatives preserved, fill -> NaN)
    wavelengths_nm: np.ndarray  # (n_wavelengths,)
    latitude: np.ndarray  # (n_lines, n_pixels)
    longitude: np.ndarray  # (n_lines, n_pixels)
    l2_flags: np.ndarray  # (n_lines, n_pixels), uint32
    flag_definitions: dict[str, int]
    file_sha256: str | None
    global_attrs: dict[str, Any]
    in_bbox_mask: np.ndarray | None = None  # (n_lines, n_pixels) bool when loaded with bbox


def _validate_swath_wavelengths(wl: np.ndarray, expected_len: int) -> np.ndarray:
    if wl.ndim != 1 or wl.size != expected_len:
        raise PaceDataError(
            f"wavelengths_nm must be 1D of length {expected_len}, got shape {wl.shape}"
        )
    if not np.isfinite(wl).all() or np.any(wl <= 0.0):
        raise PaceDataError("wavelengths_nm must be strictly positive finite numbers")
    if wl.size > 1 and not np.all(np.diff(wl) > 0.0):
        raise PaceDataError("wavelengths_nm must be strictly increasing")
    return wl


def decode_packed_variable(
    raw: ArrayLike,
    *,
    scale_factor: float = 1.0,
    add_offset: float = 0.0,
    fill_value: float | int | None = None,
    valid_min: float | int | None = None,
    valid_max: float | int | None = None,
    valid_range_is_packed: bool = True,
) -> np.ndarray:
    """Unpack a CF-1.8 packed numeric variable to float64, preserving negative physical values.

    Masks `_FillValue` to NaN prior to scaling (casting float fill values to
    `raw.dtype` so float32 fill sentinels match accurately). Per CF-1.8 §2.5.1,
    `valid_min` and `valid_max` are checked against packed values when
    `valid_range_is_packed=True`, or against unpacked physical values when
    `valid_range_is_packed=False`.
    """
    arr = np.asarray(raw)
    if arr.size == 0:
        raise PaceDataError("raw variable array must be non-empty")
    if arr.dtype == np.bool_ or not (
        np.issubdtype(arr.dtype, np.integer) or np.issubdtype(arr.dtype, np.floating)
    ):
        raise PaceDataError(f"raw variable must have numeric dtype, got {arr.dtype}")

    sf = float(scale_factor)
    ao = float(add_offset)
    if not (math.isfinite(sf) and math.isfinite(ao) and sf > 0.0):
        raise PaceDataError(
            f"scale_factor must be finite > 0 and add_offset finite; got ({scale_factor!r}, {add_offset!r})"
        )
    if valid_min is not None and valid_max is not None and float(valid_min) > float(valid_max):
        raise PaceDataError(f"valid_min ({valid_min}) must be <= valid_max ({valid_max})")

    is_int = np.issubdtype(arr.dtype, np.integer)
    invalid = np.zeros(arr.shape, dtype=bool)
    if not is_int:
        invalid |= ~np.isfinite(arr)

    if fill_value is not None:
        if is_int:
            invalid |= arr == fill_value
        else:
            fv = float(fill_value)
            if math.isnan(fv):
                invalid |= np.isnan(arr)
            else:
                # Match in raw's native floating precision (handles float32 -999.9 cleanly).
                fv_native = arr.dtype.type(fv)
                invalid |= arr == fv_native

    if valid_range_is_packed:
        if valid_min is not None:
            invalid |= arr < (valid_min if is_int else arr.dtype.type(float(valid_min)))
        if valid_max is not None:
            invalid |= arr > (valid_max if is_int else arr.dtype.type(float(valid_max)))

    out = np.full(arr.shape, np.nan, dtype=float)
    valid = ~invalid
    out[valid] = arr[valid].astype(float) * sf + ao

    if not valid_range_is_packed:
        if valid_min is not None:
            out[valid & (out < float(valid_min))] = np.nan
        if valid_max is not None:
            out[valid & (out > float(valid_max))] = np.nan

    return out


def parse_l2_flag_definitions(
    flag_masks: ArrayLike,
    flag_meanings: str | bytes | np.ndarray | Sequence[str],
) -> dict[str, int]:
    """Parse CF `flag_masks` and `flag_meanings` attributes into {FLAG_NAME: uint32_mask}.

    Handles 1-element HDF5 ndarray string attributes and combines duplicate flag
    names (such as NASA's multiple reserved `SPARE` bits) via bitwise OR so no
    bitmask is silently overwritten.
    """
    masks_arr = np.asarray(flag_masks)
    if masks_arr.ndim != 1 or masks_arr.size == 0:
        raise PaceDataError("flag_masks must be a non-empty 1D integer array")
    if not np.issubdtype(masks_arr.dtype, np.integer):
        raise PaceDataError(f"flag_masks must have integer dtype, got {masks_arr.dtype}")

    meanings_obj: Any = flag_meanings
    if isinstance(meanings_obj, np.ndarray) and meanings_obj.size == 1:
        meanings_obj = meanings_obj.reshape(()).item()

    if isinstance(meanings_obj, bytes):
        names = meanings_obj.decode("utf-8").split()
    elif isinstance(meanings_obj, str):
        names = meanings_obj.split()
    else:
        raw_items = [
            item.decode("utf-8") if isinstance(item, bytes) else str(item)
            for item in meanings_obj
        ]
        if len(raw_items) == 1 and " " in raw_items[0]:
            names = raw_items[0].split()
        else:
            names = raw_items

    if len(names) != masks_arr.size:
        raise PaceDataError(
            f"flag_meanings count ({len(names)}) != flag_masks length ({masks_arr.size})"
        )

    defs: dict[str, int] = {}
    for name, raw_mask in zip(names, masks_arr.tolist(), strict=True):
        u32_mask = int(raw_mask) & 0xFFFFFFFF
        if u32_mask == 0:
            raise PaceDataError(f"flag {name!r} has zero bitmask")
        defs[name] = defs.get(name, 0) | u32_mask
    return defs


def decode_l2_flags(
    l2_flags: ArrayLike,
    flag_definitions: Mapping[str, int],
    *,
    exclude_flags: Sequence[str] = DEFAULT_PACE_EXCLUDE_FLAGS,
) -> dict[str, Any]:
    """Decode pixel-level `l2_flags` bitmasks using unsigned 32-bit bitwise logic.

    Refuses any flag name in `exclude_flags` that does not exist in
    `flag_definitions` so typos never silently skip quality screening.
    """
    raw = np.asarray(l2_flags)
    if raw.ndim != 2 or raw.size == 0:
        raise PaceDataError(f"l2_flags must be a non-empty 2D integer array, got shape {raw.shape}")
    if not np.issubdtype(raw.dtype, np.integer):
        raise PaceDataError(f"l2_flags must have integer dtype, got {raw.dtype}")

    unknown = [flag for flag in exclude_flags if flag not in flag_definitions]
    if unknown:
        raise PaceDataError(
            f"unknown PACE l2_flags requested in exclude_flags: {', '.join(unknown)}"
        )

    flags_u32 = (raw.astype(np.int64) & 0xFFFFFFFF).astype(np.uint32)

    combined_mask = np.uint32(0)
    flag_counts: dict[str, int] = {}
    for flag_name in exclude_flags:
        bit = np.uint32(int(flag_definitions[flag_name]) & 0xFFFFFFFF)
        combined_mask = np.uint32(combined_mask | bit)
        flag_counts[flag_name] = int(np.count_nonzero((flags_u32 & bit) != 0))

    excluded_mask = (flags_u32 & combined_mask) != 0
    valid_mask = ~excluded_mask
    return {
        "valid_mask": valid_mask,
        "excluded_mask": excluded_mask,
        "flag_counts": flag_counts,
        "excluded_flags_used": list(exclude_flags),
    }


def _scalar_attr(attrs: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key not in attrs:
        return default
    val = attrs[key]
    if isinstance(val, np.ndarray) and val.size == 1:
        val = val.reshape(()).item()
    if isinstance(val, bytes):
        return val.decode("utf-8")
    return val


def _extract_valid_bounds(
    attrs: Mapping[str, Any],
    raw_dtype: np.dtype,
) -> tuple[Any, Any, bool]:
    """Read CF-1.8 valid_min/valid_max (or valid_range) and determine packed vs unpacked units."""
    vmin = _scalar_attr(attrs, "valid_min", None)
    vmax = _scalar_attr(attrs, "valid_max", None)
    if vmin is None and vmax is None and "valid_range" in attrs:
        vr = np.asarray(attrs["valid_range"]).ravel()
        if vr.size != 2:
            raise PaceDataError(f"valid_range must have length 2, got shape {vr.shape}")
        vmin, vmax = vr[0].item(), vr[1].item()

    if vmin is None and vmax is None:
        return None, None, True

    # CF-1.8 §2.5.1: for packed integer variables, integer valid bounds are in
    # packed units while floating-point valid bounds are in unpacked physical units.
    if np.issubdtype(raw_dtype, np.integer):
        bound_sample = vmin if vmin is not None else vmax
        is_packed = isinstance(bound_sample, (int, np.integer)) and not isinstance(bound_sample, bool)
        return vmin, vmax, is_packed
    return vmin, vmax, False


def load_pace_l2_aop(
    path: Path,
    *,
    expected_sha256: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    mask_outside_bbox: bool = False,
    compute_sha256: bool = True,
) -> PaceL2AopSwath:
    """Load a NASA PACE OCI Level-2 AOP NetCDF4/HDF5 granule via h5py.

    Parameters
    ----------
    path : Path
        Path to `PACE_OCI.*.L2.OC_AOP.*.nc`.
    expected_sha256 : str | None
        Optional lowercase hex SHA-256 to verify before reading arrays.
    bbox : (west, south, east, north) | None
        Optional geographic bounding box in degrees (`west < east`, `south < north`;
        antimeridian-crossing bboxes with `west > east` are not supported). Crops
        to the minimal swath index rectangle covering pixels inside `bbox` and
        records exact per-pixel membership in `PaceL2AopSwath.in_bbox_mask`.
    mask_outside_bbox : bool
        When True and `bbox` is provided, sets `rrs` to NaN at rotated-swath
        corner pixels outside `bbox`.
    """
    target = Path(path)
    if not target.is_file():
        raise PaceDataError(f"PACE granule file not found: {target}")

    digest: str | None = None
    if expected_sha256 is not None or compute_sha256:
        digest = sha256_file(target)
        if expected_sha256 is not None and digest != expected_sha256:
            raise PaceDataError(
                f"PACE granule SHA-256 mismatch: expected {expected_sha256}, got {digest}"
            )

    with h5py.File(target, "r") as h5:
        for req_path in (
            "geophysical_data/Rrs",
            "geophysical_data/l2_flags",
            "navigation_data/latitude",
            "navigation_data/longitude",
        ):
            if req_path not in h5:
                raise PaceDataError(f"PACE granule missing required dataset {req_path!r}")

        if "sensor_band_parameters/wavelength_3d" in h5:
            wl = np.asarray(h5["sensor_band_parameters/wavelength_3d"][:], dtype=float)
        elif "sensor_band_parameters/wavelength" in h5:
            wl = np.asarray(h5["sensor_band_parameters/wavelength"][:], dtype=float)
        else:
            raise PaceDataError(
                "PACE granule missing 'sensor_band_parameters/wavelength_3d' (and fallback 'wavelength')"
            )

        lat_ds = h5["navigation_data/latitude"]
        lon_ds = h5["navigation_data/longitude"]
        rrs_ds = h5["geophysical_data/Rrs"]
        flags_ds = h5["geophysical_data/l2_flags"]

        if rrs_ds.ndim != 3:
            raise PaceDataError(f"geophysical_data/Rrs must be 3D, got shape {rrs_ds.shape}")
        swath_shape = rrs_ds.shape[:2]
        if lat_ds.shape != swath_shape or lon_ds.shape != swath_shape or flags_ds.shape != swath_shape:
            raise PaceDataError(
                f"spatial shape mismatch across Rrs {swath_shape}, latitude {lat_ds.shape}, "
                f"longitude {lon_ds.shape}, and l2_flags {flags_ds.shape}"
            )
        wl = _validate_swath_wavelengths(wl, rrs_ds.shape[2])

        lat_full = decode_packed_variable(
            lat_ds[:],
            scale_factor=_scalar_attr(lat_ds.attrs, "scale_factor", 1.0),
            add_offset=_scalar_attr(lat_ds.attrs, "add_offset", 0.0),
            fill_value=_scalar_attr(lat_ds.attrs, "_FillValue", None),
        )
        lon_full = decode_packed_variable(
            lon_ds[:],
            scale_factor=_scalar_attr(lon_ds.attrs, "scale_factor", 1.0),
            add_offset=_scalar_attr(lon_ds.attrs, "add_offset", 0.0),
            fill_value=_scalar_attr(lon_ds.attrs, "_FillValue", None),
        )

        in_bbox_cropped: np.ndarray | None = None
        if bbox is not None:
            west, south, east, north = (float(x) for x in bbox)
            if not (west < east and south < north):
                raise PaceDataError(f"bbox must satisfy west < east and south < north, got {bbox!r}")
            in_box = (
                np.isfinite(lat_full)
                & np.isfinite(lon_full)
                & (lon_full >= west)
                & (lon_full <= east)
                & (lat_full >= south)
                & (lat_full <= north)
            )
            if not np.any(in_box):
                raise PaceDataError(f"no swath pixels fall inside requested bbox {bbox!r}")
            rows_idx, cols_idx = np.nonzero(in_box)
            r0, r1 = int(rows_idx.min()), int(rows_idx.max()) + 1
            c0, c1 = int(cols_idx.min()), int(cols_idx.max()) + 1
            row_sl, col_sl = slice(r0, r1), slice(c0, c1)
            in_bbox_cropped = in_box[row_sl, col_sl]
        else:
            row_sl, col_sl = slice(None), slice(None)

        lat = lat_full[row_sl, col_sl]
        lon = lon_full[row_sl, col_sl]

        rrs_raw = rrs_ds[row_sl, col_sl, :]
        vmin, vmax, is_packed_bounds = _extract_valid_bounds(rrs_ds.attrs, rrs_raw.dtype)
        rrs = decode_packed_variable(
            rrs_raw,
            scale_factor=_scalar_attr(rrs_ds.attrs, "scale_factor", 1.0),
            add_offset=_scalar_attr(rrs_ds.attrs, "add_offset", 0.0),
            fill_value=_scalar_attr(rrs_ds.attrs, "_FillValue", None),
            valid_min=vmin,
            valid_max=vmax,
            valid_range_is_packed=is_packed_bounds,
        )
        if mask_outside_bbox and in_bbox_cropped is not None:
            rrs[~in_bbox_cropped] = np.nan

        flags_raw = flags_ds[row_sl, col_sl]
        flags_u32 = (flags_raw.astype(np.int64) & 0xFFFFFFFF).astype(np.uint32)
        if "flag_masks" in flags_ds.attrs and "flag_meanings" in flags_ds.attrs:
            flag_defs = parse_l2_flag_definitions(
                flags_ds.attrs["flag_masks"],
                flags_ds.attrs["flag_meanings"],
            )
        else:
            flag_defs = {}

        global_attrs: dict[str, Any] = {}
        for k in h5.attrs:
            global_attrs[str(k)] = _scalar_attr(h5.attrs, k)

    return PaceL2AopSwath(
        rrs=rrs,
        wavelengths_nm=wl,
        latitude=lat,
        longitude=lon,
        l2_flags=flags_u32,
        flag_definitions=flag_defs,
        file_sha256=digest,
        global_attrs=global_attrs,
        in_bbox_mask=in_bbox_cropped,
    )


def build_rgb_composite(
    rrs_cube: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    rgb_wavelengths_nm: tuple[float, float, float] = (665.0, 550.0, 442.0),
    valid_mask: ArrayLike | None = None,
    percentile_stretch: tuple[float, float] = (2.0, 98.0),
    gamma: float = 1.0,
    tolerance_nm: float = 3.0,
) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Build a display RGB or false-colour composite from a 3D (H, W, n_wl) Rrs cube.

    Default (665, 550, 442) nm matches handoff §7.3 visible water colour;
    pass (704, 620, 550) nm for false colour. Stretches strictly over valid
    finite pixels and leaves invalid/masked pixels as NaN (never interpolated).
    """
    cube = np.asarray(rrs_cube, dtype=float)
    if cube.ndim != 3:
        raise PaceDataError(f"rrs_cube must be 3D (H, W, n_wl), got shape {cube.shape}")
    wl = _validate_swath_wavelengths(np.asarray(wavelengths_nm, dtype=float), cube.shape[2])

    if len(rgb_wavelengths_nm) != 3:
        raise PaceDataError(
            f"rgb_wavelengths_nm must contain 3 wavelengths (R, G, B), got {len(rgb_wavelengths_nm)}"
        )
    if not math.isfinite(tolerance_nm) or tolerance_nm < 0.0:
        raise PaceDataError(f"tolerance_nm must be finite >= 0, got {tolerance_nm!r}")

    p_lo, p_hi = float(percentile_stretch[0]), float(percentile_stretch[1])
    if not (0.0 <= p_lo < p_hi <= 100.0):
        raise PaceDataError(f"percentile_stretch must satisfy 0 <= lo < hi <= 100, got {percentile_stretch!r}")
    if not math.isfinite(gamma) or gamma <= 0.0:
        raise PaceDataError(f"gamma must be finite > 0, got {gamma!r}")

    if valid_mask is None:
        base_mask = np.ones(cube.shape[:2], dtype=bool)
    else:
        bm = np.asarray(valid_mask)
        if bm.dtype != np.bool_ or bm.shape != cube.shape[:2]:
            raise PaceDataError(
                f"valid_mask must be boolean with shape {cube.shape[:2]}, got {bm.dtype} {bm.shape}"
            )
        base_mask = bm

    indices: list[int] = []
    matched_wl: list[float] = []
    for target_nm in rgb_wavelengths_nm:
        t_val = float(target_nm)
        if not math.isfinite(t_val):
            raise PaceDataError(f"RGB target wavelength must be finite, got {target_nm!r}")
        idx = int(np.argmin(np.abs(wl - t_val)))
        if abs(float(wl[idx]) - t_val) > tolerance_nm:
            raise PaceDataError(
                f"band {target_nm} nm not found within +/-{tolerance_nm} nm (nearest is {wl[idx]} nm)"
            )
        indices.append(idx)
        matched_wl.append(float(wl[idx]))

    rgb_raw = cube[:, :, indices]
    pixel_ok = base_mask & np.isfinite(rgb_raw).all(axis=2)
    if not np.any(pixel_ok):
        raise PaceDataError("zero valid finite pixels available for RGB composite")

    rgb = np.full((cube.shape[0], cube.shape[1], 3), np.nan, dtype=float)
    for ch in range(3):
        vals = rgb_raw[pixel_ok, ch]
        lo = float(np.percentile(vals, p_lo))
        hi = float(np.percentile(vals, p_hi))
        if hi <= lo:
            scaled = np.zeros_like(vals)
        else:
            scaled = np.clip((vals - lo) / (hi - lo), 0.0, 1.0)
        if gamma != 1.0:
            scaled = np.power(scaled, 1.0 / gamma)
        rgb[pixel_ok, ch] = scaled

    return rgb, (matched_wl[0], matched_wl[1], matched_wl[2])


def compute_swath_pca(
    rrs_cube: ArrayLike,
    wavelengths_nm: ArrayLike,
    *,
    valid_mask: ArrayLike,
    min_nm: float = 400.0,
    max_nm: float = 719.0,
    n_components: int = 3,
    unit_norm: bool = False,
) -> dict[str, Any]:
    """Run memory-efficient CPU PCA over quality-screened swath pixels in [min_nm, max_nm].

    Uses zero-copy spectral slicing on strictly increasing wavelengths and solves
    the O(n_wl^2) Gram eigendecomposition (`Xc.T @ Xc`) when `n_valid > n_wl`
    rather than allocating an `(n_valid, n_wl)` full SVD left-singular matrix.
    Returns spatial score maps (NaN at excluded pixels), loadings, explained
    variance ratios, and exact CohortCounts denominator accounting.
    """
    cube = np.asarray(rrs_cube, dtype=float)
    if cube.ndim != 3:
        raise PaceDataError(f"rrs_cube must be 3D (H, W, n_wl), got shape {cube.shape}")
    wl = _validate_swath_wavelengths(np.asarray(wavelengths_nm, dtype=float), cube.shape[2])

    vm = np.asarray(valid_mask)
    if vm.dtype != np.bool_ or vm.shape != cube.shape[:2]:
        raise PaceDataError(f"valid_mask must be boolean with shape {cube.shape[:2]}")
    if isinstance(n_components, bool) or not isinstance(n_components, int) or n_components < 1:
        raise PaceDataError(f"n_components must be integer >= 1, got {n_components!r}")
    if not (math.isfinite(min_nm) and math.isfinite(max_nm)) or max_nm <= min_nm:
        raise PaceDataError(f"max_nm ({max_nm}) must be finite and > min_nm ({min_nm})")

    # Zero-copy spectral slice since wl is strictly increasing.
    i0 = int(np.searchsorted(wl, min_nm, side="left"))
    i1 = int(np.searchsorted(wl, max_nm, side="right"))
    sub_wl = wl[i0:i1]
    if sub_wl.size < n_components:
        raise PaceDataError(
            f"selected wavelength window [{min_nm}, {max_nm}] nm has only {sub_wl.size} bands "
            f"for n_components={n_components}"
        )

    sub_cube = cube[:, :, i0:i1]
    total_pixels = int(cube.shape[0] * cube.shape[1])

    # Check finiteness only for unflagged pixels to avoid a full-swath 3D scan when mostly masked.
    flagged_out = ~vm
    unflagged_specs = sub_cube[vm]
    finite_unflagged = np.isfinite(unflagged_specs).all(axis=1)
    n_nonfinite_unflagged = int((~finite_unflagged).sum())

    eligible = vm.copy()
    eligible[vm] = finite_unflagged

    X = unflagged_specs[finite_unflagged]
    zero_norm_dropped = 0
    if unit_norm:
        norms = np.linalg.norm(X, axis=1)
        nz = norms > 0.0
        zero_norm_dropped = int((~nz).sum())
        if zero_norm_dropped > 0:
            eligible[eligible] = nz
        X = X[nz] / norms[nz, np.newaxis]

    n_valid = int(X.shape[0])
    if n_valid <= n_components:
        raise PaceDataError(
            f"need > {n_components} valid pixels for PCA, found {n_valid}"
        )

    mean_spec = np.mean(X, axis=0)
    Xc = X - mean_spec[np.newaxis, :]

    if n_valid > sub_wl.size:
        # O(n_wl^2) Gram matrix eigendecomposition avoids O(n_valid * n_wl) SVD U allocation.
        gram = Xc.T @ Xc
        eigvals, eigvecs = np.linalg.eigh(gram)
        order = np.argsort(eigvals)[::-1]
        eigvals = np.maximum(eigvals[order], 0.0)
        eigvecs = eigvecs[:, order]
        total_var = float(np.sum(eigvals))
        if total_var <= 0.0:
            raise PaceDataError("zero total spectral variance across valid swath pixels")
        loadings = eigvecs[:, :n_components].T.copy()
        scores = Xc @ loadings.T
        explained_ratio = eigvals[:n_components] / total_var
    else:
        u, s, vt = np.linalg.svd(Xc, full_matrices=False)
        total_var = float(np.sum(s**2))
        if total_var <= 0.0:
            raise PaceDataError("zero total spectral variance across valid swath pixels")
        loadings = vt[:n_components].copy()
        scores = (u[:, :n_components] * s[:n_components]).copy()
        explained_ratio = (s[:n_components] ** 2) / total_var

    # Deterministic sign convention: largest absolute loading in each component is positive.
    for comp in range(n_components):
        max_idx = int(np.argmax(np.abs(loadings[comp])))
        if loadings[comp, max_idx] < 0.0:
            loadings[comp] *= -1.0
            scores[:, comp] *= -1.0

    scores_cube = np.full((cube.shape[0], cube.shape[1], n_components), np.nan, dtype=float)
    scores_cube[eligible] = scores

    reasons: dict[str, int] = {
        "l2_flags_or_mask_excluded": int(flagged_out.sum()),
        "nonfinite_rrs_in_window": n_nonfinite_unflagged,
    }
    if unit_norm:
        reasons["zero_norm_spectrum"] = zero_norm_dropped

    counts = CohortCounts(
        attempted=total_pixels,
        completed=n_valid,
        failed=0,
        excluded=total_pixels - n_valid,
        exclusion_reasons=reasons,
    )

    return {
        "scores_cube": scores_cube,
        "loadings": loadings,
        "mean_spectrum": mean_spec,
        "explained_variance_ratio": explained_ratio,
        "wavelengths_nm": sub_wl,
        "valid_mask_used": eligible,
        "counts": counts,
    }
