"""Analytical, synthetic NetCDF4/HDF5, and planted-defect tests for hydrospectral.pace."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from hydrospectral.pace import (
    PaceDataError,
    build_rgb_composite,
    compute_swath_pca,
    decode_l2_flags,
    decode_packed_variable,
    load_pace_l2_aop,
    parse_l2_flag_definitions,
)


def _write_synthetic_pace_granule(
    path: Path,
    *,
    rotated: bool = False,
    float_valid_bounds: bool = False,
) -> Path:
    """Create a synthetic CF-1.8 PACE OCI L2 AOP HDF5/NetCDF4 granule in tmp_path."""
    H, W = 12, 10
    wl = np.arange(340.0, 720.0, 5.0)
    n_wl = wl.size

    scale_factor = 2.0e-6
    add_offset = 0.05
    fill_value = np.int16(-32767)

    yy, xx = np.meshgrid(np.linspace(0.0, 1.0, H), np.linspace(0.0, 1.0, W), indexing="ij")
    phys = np.zeros((H, W, n_wl), dtype=float)
    b_shape = np.exp(-0.5 * ((wl - 450.0) / 50.0) ** 2)
    g_shape = np.exp(-0.5 * ((wl - 560.0) / 55.0) ** 2)
    for r in range(H):
        for c in range(W):
            phys[r, c] = (0.006 * (1.0 - xx[r, c]) + 0.001) * b_shape + (0.007 * yy[r, c] + 0.001) * g_shape

    idx_705 = int(np.argmin(np.abs(wl - 705.0)))
    phys[0, 0, idx_705] = -0.00024

    packed = np.rint((phys - add_offset) / scale_factor).astype(np.int16)
    packed[11, 9, :] = fill_value
    packed[0, 9, :] = np.int16(24000)

    if rotated:
        # 45-degree rotated curvilinear swath (like inclined sun-synchronous PACE orbits).
        u = np.linspace(-2.0, 2.0, H)[:, np.newaxis]
        v = np.linspace(-2.0, 2.0, W)[np.newaxis, :]
        lat = 28.0 + 0.7071 * (u + v)
        lon = -90.0 + 0.7071 * (v - u)
    else:
        lat = np.linspace(25.0, 30.0, H)[:, np.newaxis] * np.ones((1, W))
        lon = np.ones((H, 1)) * np.linspace(-92.0, -87.0, W)[np.newaxis, :]

    # Include duplicate SPARE bits (bit 7 = 128 and bit 31 = -2147483648) and 1-element ndarray flag_meanings!
    flag_masks = np.array([1, 2, 128, 512, -2147483648], dtype=np.int32)
    flag_meanings = np.array([b"ATMFAIL LAND SPARE CLDICE SPARE"])
    l2_flags = np.zeros((H, W), dtype=np.int32)
    l2_flags[0, 9] = 2  # LAND
    l2_flags[1, 9] = 512  # CLDICE
    l2_flags[2, 9] = 128  # SPARE bit 7
    l2_flags[3, 9] = -2147483648  # SPARE bit 31

    with h5py.File(path, "w") as h5:
        h5.attrs["instrument"] = "OCI"
        h5.attrs["processing_version"] = "V2_0.NRT"
        sbp = h5.create_group("sensor_band_parameters")
        sbp.create_dataset("wavelength_3d", data=wl)
        nav = h5.create_group("navigation_data")
        nav.create_dataset("latitude", data=lat)
        nav.create_dataset("longitude", data=lon)
        geo = h5.create_group("geophysical_data")
        rrs_ds = geo.create_dataset("Rrs", data=packed)
        rrs_ds.attrs["scale_factor"] = scale_factor
        rrs_ds.attrs["add_offset"] = add_offset
        rrs_ds.attrs["_FillValue"] = fill_value
        if float_valid_bounds:
            # CF-1.8 §2.5.1: float valid_min/valid_max on packed int16 are in unpacked physical units!
            rrs_ds.attrs["valid_min"] = np.float32(-0.01)
            rrs_ds.attrs["valid_max"] = np.float32(0.10)
        else:
            rrs_ds.attrs["valid_min"] = np.int16(-30000)
            rrs_ds.attrs["valid_max"] = np.int16(25000)
        flg_ds = geo.create_dataset("l2_flags", data=l2_flags)
        flg_ds.attrs["flag_masks"] = flag_masks
        flg_ds.attrs["flag_meanings"] = flag_meanings
    return path


def test_decode_packed_variable_preserves_negatives_and_handles_float32_fill() -> None:
    raw = np.array([-32767, -25120, -25000, 0, 25001], dtype=np.int16)
    unpacked = decode_packed_variable(
        raw,
        scale_factor=2.0e-6,
        add_offset=0.05,
        fill_value=-32767,
        valid_min=-30000,
        valid_max=25000,
    )
    assert np.isnan(unpacked[0])
    assert unpacked[1] == pytest.approx(-0.00024, abs=1e-12)
    assert unpacked[2] == pytest.approx(0.0, abs=1e-12)
    assert unpacked[3] == pytest.approx(0.05, abs=1e-12)
    assert np.isnan(unpacked[4])

    # Regression for Finding #5: float32 _FillValue (-999.9) matches cleanly despite float64 widening.
    f32 = np.array([-999.9, -0.001, 0.02, 0.5], dtype=np.float32)
    dec_f32 = decode_packed_variable(
        f32, fill_value=-999.9, valid_min=-0.01, valid_max=0.2, valid_range_is_packed=False
    )
    assert np.isnan(dec_f32[0])
    assert dec_f32[1] == pytest.approx(-0.001, abs=1e-6)
    assert dec_f32[2] == pytest.approx(0.02, abs=1e-6)
    assert np.isnan(dec_f32[3])

    with pytest.raises(PaceDataError, match="numeric dtype"):
        decode_packed_variable(np.array([True, False]))
    with pytest.raises(PaceDataError, match="valid_min"):
        decode_packed_variable(raw, valid_min=10, valid_max=5)


def test_l2_flags_combines_duplicate_spare_bits_and_handles_ndarray_meanings() -> None:
    # Regression for Finding #3: duplicate SPARE bits are OR'd and 1-element ndarray meanings parse cleanly.
    defs = parse_l2_flag_definitions(
        np.array([1, 2, 128, 512, -2147483648], dtype=np.int32),
        np.array([b"ATMFAIL LAND SPARE CLDICE SPARE"]),
    )
    assert defs["SPARE"] == (128 | 0x80000000)

    flags = np.array([[0, 2], [128, -2147483648]], dtype=np.int32)
    dec = decode_l2_flags(flags, defs, exclude_flags=("LAND", "SPARE"))
    assert dec["valid_mask"].tolist() == [[True, False], [False, False]]
    assert dec["flag_counts"] == {"LAND": 1, "SPARE": 2}

    with pytest.raises(PaceDataError, match="unknown PACE l2_flags"):
        decode_l2_flags(flags, defs, exclude_flags=("CLD_ICE",))


def test_load_pace_granule_rotated_bbox_cf_float_bounds_rgb_and_gram_pca(tmp_path: Path) -> None:
    nc_path = _write_synthetic_pace_granule(tmp_path / "PACE_OCI.synthetic.L2.OC_AOP.nc")
    swath = load_pace_l2_aop(nc_path)
    assert swath.file_sha256 is not None and len(swath.file_sha256) == 64
    assert swath.rrs.shape == (12, 10, 76)
    assert swath.in_bbox_mask is None

    idx_705 = int(np.argmin(np.abs(swath.wavelengths_nm - 705.0)))
    assert swath.rrs[0, 0, idx_705] == pytest.approx(-0.00024, abs=1e-6)
    assert np.isnan(swath.rrs[11, 9]).all()

    with pytest.raises(PaceDataError, match="SHA-256 mismatch"):
        load_pace_l2_aop(nc_path, expected_sha256="0" * 64)

    # Regression for Finding #5: float valid_min/valid_max on packed int16 uses unpacked physical bounds.
    nc_float_bounds = _write_synthetic_pace_granule(
        tmp_path / "PACE_float_bounds.nc", float_valid_bounds=True
    )
    swath_fb = load_pace_l2_aop(nc_float_bounds, compute_sha256=False)
    assert np.isfinite(swath_fb.rrs[0, 0]).all()  # ocean pixels (< 0.05 sr^-1) stay valid!

    # Regression for Finding #2: rotated swath bbox exposes exact in_bbox_mask and optionally masks corners.
    nc_rot = _write_synthetic_pace_granule(tmp_path / "PACE_rotated.nc", rotated=True)
    rot_sub = load_pace_l2_aop(
        nc_rot, bbox=(-91.0, 27.0, -89.0, 29.0), mask_outside_bbox=True, compute_sha256=False
    )
    assert rot_sub.in_bbox_mask is not None
    assert not rot_sub.in_bbox_mask.all()  # corners lie outside bbox on rotated swath
    assert np.isnan(rot_sub.rrs[~rot_sub.in_bbox_mask]).all()
    assert float(np.nanmin(rot_sub.latitude[rot_sub.in_bbox_mask])) >= 27.0
    assert float(np.nanmax(rot_sub.longitude[rot_sub.in_bbox_mask])) <= -89.0

    fl = decode_l2_flags(swath.l2_flags, swath.flag_definitions, exclude_flags=("LAND", "CLDICE", "SPARE"))
    assert int((~fl["valid_mask"]).sum()) == 4

    rgb, matched = build_rgb_composite(
        swath.rrs,
        swath.wavelengths_nm,
        rgb_wavelengths_nm=(665.0, 550.0, 440.0),
        valid_mask=fl["valid_mask"],
    )
    assert matched == (665.0, 550.0, 440.0)
    assert np.isnan(rgb[0, 9]).all()
    assert np.isnan(rgb[11, 9]).all()
    assert float(np.nanmax(rgb)) == pytest.approx(1.0)
    assert float(np.nanmin(rgb)) == pytest.approx(0.0)

    # Regression for Finding #6: NaN in wavelengths_nm must raise PaceDataError in build_rgb_composite.
    bad_wl = swath.wavelengths_nm.copy()
    bad_wl[0] = np.nan
    with pytest.raises(PaceDataError, match="strictly positive finite"):
        build_rgb_composite(swath.rrs, bad_wl, valid_mask=fl["valid_mask"])

    # Gram-matrix PCA branch (n_valid=115 > n_sub_wl=64) + unit_norm zero-norm pixel accounting.
    rrs_with_zero = swath.rrs.copy()
    rrs_with_zero[5, 5, :] = 0.0
    pca = compute_swath_pca(
        rrs_with_zero,
        swath.wavelengths_nm,
        valid_mask=fl["valid_mask"],
        min_nm=400.0,
        max_nm=715.0,
        n_components=3,
        unit_norm=True,
    )
    assert float(pca["explained_variance_ratio"][:2].sum()) > 0.99
    assert np.isnan(pca["scores_cube"][5, 5]).all()
    assert pca["counts"].attempted == 120
    assert pca["counts"].completed == 114
    assert pca["counts"].exclusion_reasons == {
        "l2_flags_or_mask_excluded": 4,
        "nonfinite_rrs_in_window": 1,
        "zero_norm_spectrum": 1,
    }
