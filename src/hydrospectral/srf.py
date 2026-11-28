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
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from hydrospectral.provenance import sha256_file

_XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_XLSX_COL_RE = re.compile(r"^([A-Z]+)")


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


def _xlsx_col_to_index(cell_ref: str) -> int:
    match = _XLSX_COL_RE.match(cell_ref)
    if not match:
        raise SRFError(f"invalid XLSX cell reference: {cell_ref!r}")
    idx = 0
    for ch in match.group(1):
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _read_xlsx_sheet_rows(path: Path, sheet_name: str) -> list[list[str]]:
    """Read a named XLSX worksheet with exact column-letter alignment (stdlib XML only)."""
    try:
        with zipfile.ZipFile(path, "r") as xz:
            names = set(xz.namelist())
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                sroot = ET.fromstring(xz.read("xl/sharedStrings.xml"))
                for si in sroot.findall("a:si", _XLSX_NS):
                    shared.append("".join(t.text or "" for t in si.findall(".//a:t", _XLSX_NS)))

            wb = ET.fromstring(xz.read("xl/workbook.xml"))
            rels = ET.fromstring(xz.read("xl/_rels/workbook.xml.rels"))
            rel_map = {
                rel.attrib["Id"]: rel.attrib["Target"]
                for rel in rels
                if "Id" in rel.attrib and "Target" in rel.attrib
            }

            target_path: str | None = None
            available: list[str] = []
            for sh in wb.findall(".//a:sheet", _XLSX_NS):
                name = sh.attrib.get("name", "")
                available.append(name)
                if name == sheet_name:
                    rid = sh.attrib.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                    )
                    rel_target = rel_map.get(rid or "", "")
                    rel_norm = rel_target.lstrip("/")
                    target_path = rel_norm if rel_norm.startswith("xl/") else f"xl/{rel_norm}"
                    break

            if not target_path or target_path not in names:
                raise SRFError(
                    f"XLSX worksheet {sheet_name!r} not found in {path.name}; available: {available}"
                )

            sheet_xml = ET.fromstring(xz.read(target_path))

        rows_sparse: list[dict[int, str]] = []
        max_col = 0
        for row in sheet_xml.findall(".//a:sheetData/a:row", _XLSX_NS):
            row_cells: dict[int, str] = {}
            next_col = 0
            for cell in row.findall("a:c", _XLSX_NS):
                ref = cell.attrib.get("r", "")
                cidx = _xlsx_col_to_index(ref) if ref else next_col
                next_col = cidx + 1
                ctype = cell.attrib.get("t", "")
                v_el = cell.find("a:v", _XLSX_NS)
                is_el = cell.find("a:is", _XLSX_NS)
                if ctype == "s" and v_el is not None and v_el.text is not None:
                    val = shared[int(v_el.text)]
                elif ctype == "inlineStr" and is_el is not None:
                    val = "".join(t.text or "" for t in is_el.findall(".//a:t", _XLSX_NS))
                elif v_el is not None and v_el.text is not None:
                    val = v_el.text
                else:
                    val = ""
                if val.strip():
                    row_cells[cidx] = val.strip()
                    max_col = max(max_col, cidx)
            if row_cells:
                rows_sparse.append(row_cells)
    except SRFError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, ValueError) as exc:
        raise SRFError(f"failed to read XLSX SRF workbook {path}: {exc}") from exc

    return [[r.get(i, "") for i in range(max_col + 1)] for r in rows_sparse]


def load_esa_s2_srf_xlsx(
    path: Path,
    *,
    unit: str = "S2A",
    expected_sha256: str | None = None,
    bands: Sequence[str] | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Load official ESA Copernicus Sentinel-2 MSI SRF spreadsheet (`COPE-GSEG-EOPG-TN-15-0007`).

    Reads worksheet `Spectral Responses (<unit>)` (e.g., `S2A`, `S2B`, `S2C`),
    normalizes column headers like `S2A_SR_AV_B1` to canonical band names (`B1`..`B12`),
    and validates monotonicity, finiteness, and non-negativity.
    """
    target = Path(path)
    if not target.is_file():
        raise SRFError(f"ESA Sentinel-2 SRF workbook not found: {target}")
    if expected_sha256 is not None:
        actual = sha256_file(target)
        if actual != expected_sha256:
            raise SRFError(
                f"ESA Sentinel-2 SRF SHA-256 mismatch: expected {expected_sha256}, got {actual}"
            )

    unit_clean = unit.strip().upper()
    if unit_clean not in {"S2A", "S2B", "S2C"}:
        raise SRFError(f"unsupported Sentinel-2 unit {unit!r}; expected 'S2A', 'S2B', or 'S2C'")

    rows = _read_xlsx_sheet_rows(target, f"Spectral Responses ({unit_clean})")
    if len(rows) < 3:
        raise SRFError(f"Sentinel-2 SRF worksheet for {unit_clean} contains too few rows")

    header = [h.strip() for h in rows[0]]
    if not header or header[0] != "SR_WL":
        raise SRFError(f"expected first column 'SR_WL' in {unit_clean} sheet, got {header[:3]}")

    prefix = f"{unit_clean}_SR_AV_"
    col_specs: list[tuple[int, str]] = []
    seen_bands: set[str] = set()
    for idx, col_name in enumerate(header[1:], start=1):
        if not col_name:
            continue
        short = col_name[len(prefix) :] if col_name.startswith(prefix) else col_name
        if short in seen_bands:
            raise SRFError(f"duplicate normalized band column {short!r} in {unit_clean} SRF sheet")
        seen_bands.add(short)
        col_specs.append((idx, short))
    if not col_specs:
        raise SRFError(f"no band response columns found in {unit_clean} SRF sheet")

    wl_vals: list[float] = []
    raw_cols: dict[str, list[float]] = {name: [] for _, name in col_specs}
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        try:
            wl_vals.append(float(row[0]))
        except ValueError as exc:
            raise SRFError(f"non-numeric wavelength {row[0]!r} in {unit_clean} SRF sheet") from exc
        for idx, name in col_specs:
            cell_txt = row[idx].strip() if idx < len(row) else ""
            if not cell_txt:
                raw_cols[name].append(0.0)
            else:
                try:
                    raw_cols[name].append(float(cell_txt))
                except ValueError as exc:
                    raise SRFError(
                        f"non-numeric response {cell_txt!r} in {unit_clean} band {name!r}"
                    ) from exc

    wl = np.asarray(wl_vals, dtype=float)
    if wl.size < 2 or not np.isfinite(wl).all() or not np.all(np.diff(wl) > 0):
        raise SRFError(f"{unit_clean} SRF wavelength grid must be finite and strictly increasing")

    selected = [name for _, name in col_specs] if bands is None else list(bands)
    if not selected:
        raise SRFError(f"no sensor bands selected from {unit_clean} SRF workbook")
    missing = [b for b in selected if b not in raw_cols]
    if missing:
        raise SRFError(f"{unit_clean} SRF sheet missing requested band(s): {', '.join(missing)}")

    curves: dict[str, np.ndarray] = {}
    for band in selected:
        r = np.asarray(raw_cols[band], dtype=float)
        if not np.isfinite(r).all() or np.any(r < 0.0):
            raise SRFError(f"{unit_clean} band {band!r} response must be finite and non-negative")
        if float(r.max()) <= 0.0:
            raise SRFError(f"{unit_clean} band {band!r} response has zero peak")
        curves[band] = r

    return wl, curves


def load_esa_s3_olci_srf_nc4(
    path: Path,
    *,
    expected_sha256: str | None = None,
    bands: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Load official ESA Sentinel-3 OLCI mean SRF NetCDF-4/HDF5 file (`*_mean_rsr.nc4`).

    Each OLCI band (`Oa01`..`Oa21`) carries its own 200-sample wavelength grid.
    Returns `{band_name: {'wavelengths_nm', 'response', 'nominal_centre_nm',
    'fwhm_nm', 'srf_centre_nm'}}` with strictly increasing wavelengths.
    """
    target = Path(path)
    if not target.is_file():
        raise SRFError(f"ESA Sentinel-3 OLCI SRF file not found: {target}")
    if expected_sha256 is not None:
        actual = sha256_file(target)
        if actual != expected_sha256:
            raise SRFError(
                f"ESA Sentinel-3 OLCI SRF SHA-256 mismatch: expected {expected_sha256}, got {actual}"
            )

    try:
        with h5py.File(target, "r") as h5:
            for req in ("mean_spectral_response_function", "mean_spectral_response_function_wavelength"):
                if req not in h5:
                    raise SRFError(f"OLCI SRF NetCDF4 missing required dataset {req!r}")
            msrf = np.asarray(h5["mean_spectral_response_function"], dtype=float)
            mwl = np.asarray(h5["mean_spectral_response_function_wavelength"], dtype=float)
            fv_r = h5["mean_spectral_response_function"].attrs.get("_FillValue")
            fv_w = h5["mean_spectral_response_function_wavelength"].attrs.get("_FillValue")
            nom_cw = (
                np.asarray(h5["nominal_centre_wavelength"], dtype=float)
                if "nominal_centre_wavelength" in h5
                else None
            )
            fwhm = np.asarray(h5["bandwidth_fwhm"], dtype=float) if "bandwidth_fwhm" in h5 else None
            srf_cw = (
                np.asarray(h5["srf_centre_wavelength"], dtype=float)
                if "srf_centre_wavelength" in h5
                else None
            )
    except OSError as exc:
        raise SRFError(f"failed to open OLCI SRF NetCDF4 file {target}: {exc}") from exc

    if msrf.ndim != 2 or mwl.shape != msrf.shape or msrf.shape[0] == 0:
        raise SRFError(f"unexpected OLCI SRF array shapes: resp={msrf.shape}, wl={mwl.shape}")

    all_names = [f"Oa{i + 1:02d}" for i in range(msrf.shape[0])]
    selected = all_names if bands is None else list(bands)
    if not selected:
        raise SRFError("no OLCI sensor bands selected")
    unknown = [b for b in selected if b not in all_names]
    if unknown:
        raise SRFError(f"unknown OLCI band(s) requested: {', '.join(unknown)}")

    fill_r = None if fv_r is None else float(np.asarray(fv_r).ravel()[0])
    fill_w = None if fv_w is None else float(np.asarray(fv_w).ravel()[0])

    out: dict[str, dict[str, Any]] = {}
    for band in selected:
        i = all_names.index(band)
        w = mwl[i].copy()
        r = msrf[i].copy()
        keep = np.ones(w.shape, dtype=bool)
        if fill_w is not None:
            keep &= (~np.isnan(w)) if math.isnan(fill_w) else (w != fill_w)
        if fill_r is not None:
            keep &= (~np.isnan(r)) if math.isnan(fill_r) else (r != fill_r)
        w, r = w[keep], r[keep]
        if not np.isfinite(w).all() or not np.isfinite(r).all():
            raise SRFError(f"OLCI band {band!r} contains unexpected non-finite wavelength or response values")
        if w.size < 2:
            raise SRFError(f"OLCI band {band!r} has fewer than 2 valid wavelength samples")
        order = np.argsort(w)
        w, r = w[order], r[order]
        if not np.all(np.diff(w) > 0.0) or np.any(w <= 0.0):
            raise SRFError(f"OLCI band {band!r} wavelength grid is not strictly increasing and positive")
        if np.any(r < 0.0) or float(r.max()) <= 0.0:
            raise SRFError(f"OLCI band {band!r} response must be non-negative with positive peak")
        out[band] = {
            "wavelengths_nm": w,
            "response": r,
            "nominal_centre_nm": None if nom_cw is None else float(nom_cw[i]),
            "fwhm_nm": None if fwhm is None else float(fwhm[i]),
            "srf_centre_nm": None if srf_cw is None else float(srf_cw[i]),
        }
    return out


def _validate_support_rel_tol(support_rel_tol: float) -> float:
    if isinstance(support_rel_tol, bool) or not isinstance(support_rel_tol, (int, float)):
        raise SRFError(f"support_rel_tol must be a finite float in [0, 1), got {support_rel_tol!r}")
    tol = float(support_rel_tol)
    if not math.isfinite(tol) or not (0.0 <= tol < 1.0):
        raise SRFError(f"support_rel_tol must be finite and in [0, 1), got {support_rel_tol!r}")
    return tol


def build_per_band_srf_weight_matrix(
    target_wavelengths_nm: ArrayLike,
    per_band_curves: Mapping[str, Mapping[str, Any]],
    *,
    band_order: Sequence[str] | None = None,
    es_spectrum: ArrayLike | None = None,
    support_rel_tol: float = 1e-6,
) -> tuple[np.ndarray, list[str]]:
    """Build a (n_wavelengths, n_bands) SRF weight matrix when each band has its own grid.

    Delegates each band directly to `build_srf_weight_matrix` so integration and
    support-boundary enforcement have a single implementation. Default
    `support_rel_tol=1e-6` accommodates ESA S3A OLCI 200-point mean RSR windows
    (`Oa02`-`Oa16` peak-normalized endpoints 1.20e-8..8.57e-8; all 21 bands up
    to 3.64e-7) while rejecting truncated bands or bands extending outside
    `target_wavelengths_nm`. Note: `build_srf_weight_matrix` defaults to `1e-8`;
    pass an explicit `support_rel_tol` when comparing shared-grid and per-band
    sensors under one frozen protocol rule.
    """
    tol = _validate_support_rel_tol(support_rel_tol)
    names = list(per_band_curves.keys()) if band_order is None else list(band_order)
    if not names:
        raise SRFError("per_band_curves must contain at least one band")
    cols: list[np.ndarray] = []
    for name in names:
        if name not in per_band_curves:
            raise SRFError(f"band {name!r} missing from per_band_curves")
        entry = per_band_curves[name]
        w_col, _ = build_srf_weight_matrix(
            target_wavelengths_nm,
            entry["wavelengths_nm"],
            {name: entry["response"]},
            band_order=[name],
            es_spectrum=es_spectrum,
            support_rel_tol=tol,
        )
        cols.append(w_col[:, 0])
    return np.stack(cols, axis=1), names


def audit_srf_support(
    target_wavelengths_nm: ArrayLike,
    srf_curves: Mapping[str, Any],
    *,
    shared_wavelengths_nm: ArrayLike | None = None,
    support_rel_tol: float = 1e-6,
) -> list[dict[str, Any]]:
    """Audit every band's support against `target_wavelengths_nm` without silent dropping.

    Accepts either:
    - Shared-grid curves (`shared_wavelengths_nm` provided, `srf_curves` maps band -> 1D response), or
    - Per-band curves (`shared_wavelengths_nm is None`, `srf_curves` maps band -> {'wavelengths_nm', 'response'}).

    Pass the exact `support_rel_tol` that will be supplied to
    `build_srf_weight_matrix` / `build_per_band_srf_weight_matrix` so audit and
    convolution eligibility match identically.
    """
    tol = _validate_support_rel_tol(support_rel_tol)
    target_wl = np.asarray(target_wavelengths_nm, dtype=float)
    records: list[dict[str, Any]] = []
    for band, entry in srf_curves.items():
        if shared_wavelengths_nm is not None:
            wl = np.asarray(shared_wavelengths_nm, dtype=float)
            resp = np.asarray(entry, dtype=float)
        else:
            wl = np.asarray(entry["wavelengths_nm"], dtype=float)
            resp = np.asarray(entry["response"], dtype=float)

        try:
            W_col, _ = build_srf_weight_matrix(
                target_wl, wl, {band: resp}, band_order=[band], support_rel_tol=tol
            )
            eff_wl = float(target_wl @ W_col[:, 0])
            eligible = True
            reason = "eligible"
        except SRFError as exc:
            eff_wl = math.nan
            eligible = False
            reason = str(exc)

        if (
            wl.ndim == 1
            and resp.ndim == 1
            and wl.size == resp.size
            and wl.size > 0
            and np.isfinite(wl).all()
            and np.isfinite(resp).all()
            and float(resp.max()) > 0.0
        ):
            rmax = float(resp.max())
            nz = wl[resp > tol * rmax]
            sup_min = float(nz[0]) if nz.size else math.nan
            sup_max = float(nz[-1]) if nz.size else math.nan
            end_rel = float(max(resp[0], resp[-1]) / rmax)
        else:
            sup_min, sup_max, end_rel = math.nan, math.nan, math.nan

        records.append(
            {
                "band": band,
                "eligible": eligible,
                "reason": reason,
                "support_min_nm": sup_min,
                "support_max_nm": sup_max,
                "endpoint_rel_max": end_rel,
                "effective_wavelength_nm": eff_wl,
            }
        )
    return records


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
    support_rel_tol = _validate_support_rel_tol(support_rel_tol)
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
