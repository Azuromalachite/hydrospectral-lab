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
    audit_srf_support,
    build_per_band_srf_weight_matrix,
    build_rectangular_weight_matrix,
    build_srf_weight_matrix,
    convolve_spectra,
    load_esa_s2_srf_xlsx,
    load_esa_s3_olci_srf_nc4,
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


def test_esa_s2_xlsx_and_s3_olci_nc4_loaders_and_support_audit(tmp_path: Path) -> None:
    import zipfile
    import h5py
    from hydrospectral.provenance import sha256_file

    # 1. Synthetic minimal ESA S2 XLSX with sparse cells (omitted zero cells must align by column letter!).
    xlsx_path = tmp_path / "s2_srf.xlsx"
    wl_s2 = np.arange(380.0, 861.0, 1.0)
    b2 = _triangle_response(wl_s2, 490.0, 30.0)
    b8 = _triangle_response(wl_s2, 830.0, 20.0)
    rows_xml = [
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
    ]
    for idx, (w, r2, r8) in enumerate(zip(wl_s2, b2, b8, strict=True), start=2):
        cells = [f'<c r="A{idx}"><v>{w:.1f}</v></c>']
        if r2 > 0.0:
            cells.append(f'<c r="B{idx}"><v>{r2:.8f}</v></c>')
        if r8 > 0.0:
            cells.append(f'<c r="C{idx}"><v>{r8:.8f}</v></c>')
        rows_xml.append(f'<row r="{idx}">' + "".join(cells) + "</row>")

    with zipfile.ZipFile(xlsx_path, "w") as xz:
        xz.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>SR_WL</t></si><si><t>S2A_SR_AV_B2</t></si><si><t>S2A_SR_AV_B8</t></si>"
            "</sst>",
        )
        xz.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Spectral Responses (S2A)" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        xz.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        xz.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>" + "".join(rows_xml) + "</sheetData></worksheet>",
        )

    s2_sha = sha256_file(xlsx_path)
    wl_loaded, s2_curves = load_esa_s2_srf_xlsx(xlsx_path, unit="S2A", expected_sha256=s2_sha)
    assert list(s2_curves.keys()) == ["B2", "B8"]
    np.testing.assert_allclose(s2_curves["B2"], b2, atol=1e-7)
    np.testing.assert_allclose(s2_curves["B8"], b8, atol=1e-7)
    with pytest.raises(SRFError, match="SHA-256 mismatch"):
        load_esa_s2_srf_xlsx(xlsx_path, unit="S2A", expected_sha256="0" * 64)

    target_wl = np.arange(400.0, 801.0, 1.0)
    s2_audit = {r["band"]: r for r in audit_srf_support(target_wl, s2_curves, shared_wavelengths_nm=wl_loaded)}
    assert s2_audit["B2"]["eligible"] is True
    assert s2_audit["B2"]["effective_wavelength_nm"] == pytest.approx(490.0, abs=1e-6)
    assert s2_audit["B8"]["eligible"] is False

    # 2. Synthetic ESA S3A OLCI NetCDF-4 with per-band grids and realistic ~5e-8 wing endpoints.
    nc_path = tmp_path / "olci_mean_rsr.nc4"
    w_oa01 = np.linspace(388.0, 412.0, 200)
    r_oa01 = _triangle_response(w_oa01, 400.0, 11.9) + 5e-8
    w_oa02 = np.linspace(402.5, 421.2, 200)
    r_oa02 = _triangle_response(w_oa02, 411.85, 9.0) + 5e-8
    w_oa03 = np.linspace(851.0, 880.0, 200)
    r_oa03 = _triangle_response(w_oa03, 865.0, 14.0) + 5e-8

    with h5py.File(nc_path, "w") as h5:
        h5.create_dataset("mean_spectral_response_function", data=np.vstack([r_oa01, r_oa02, r_oa03]))
        h5.create_dataset(
            "mean_spectral_response_function_wavelength", data=np.vstack([w_oa01, w_oa02, w_oa03])
        )
        h5.create_dataset("nominal_centre_wavelength", data=np.array([400.0, 412.5, 865.0]))
        h5.create_dataset("bandwidth_fwhm", data=np.array([15.0, 10.0, 20.0]))
        h5.create_dataset("srf_centre_wavelength", data=np.array([400.0, 411.85, 865.0]))

    olci_sha = sha256_file(nc_path)
    olci = load_esa_s3_olci_srf_nc4(nc_path, expected_sha256=olci_sha)
    assert list(olci.keys()) == ["Oa01", "Oa02", "Oa03"]

    # Boundary check for A03: 5e-8 wing fails at tol=1e-8, passes at tol=1e-6; Oa01/Oa03 fail at both!
    with pytest.raises(SRFError, match="nonzero response"):
        build_per_band_srf_weight_matrix(target_wl, olci, band_order=["Oa02"], support_rel_tol=1e-8)

    olci_audit = {r["band"]: r for r in audit_srf_support(target_wl, olci, support_rel_tol=1e-6)}
    assert olci_audit["Oa01"]["eligible"] is False
    assert olci_audit["Oa02"]["eligible"] is True
    assert olci_audit["Oa03"]["eligible"] is False

    W_olci, names_olci = build_per_band_srf_weight_matrix(
        target_wl, olci, band_order=["Oa02"], support_rel_tol=1e-6
    )
    assert names_olci == ["Oa02"]
    assert convolve_spectra(np.full_like(target_wl, 0.02), W_olci)[0] == pytest.approx(0.02, abs=1e-12)

    # Planted-defect regressions: invalid support_rel_tol, empty bands, OLCI SHA/NaN/FillValue, duplicate S2 col.
    for bad_tol in (float("nan"), -1e-3, 1.0, True):
        with pytest.raises(SRFError, match="support_rel_tol"):
            build_srf_weight_matrix(target_wl, wl_loaded, {"B2": s2_curves["B2"]}, support_rel_tol=bad_tol)

    with pytest.raises(SRFError, match="no sensor bands selected"):
        load_esa_s2_srf_xlsx(xlsx_path, unit="S2A", bands=[])
    with pytest.raises(SRFError, match="no OLCI sensor bands selected"):
        load_esa_s3_olci_srf_nc4(nc_path, bands=[])
    with pytest.raises(SRFError, match="SHA-256 mismatch"):
        load_esa_s3_olci_srf_nc4(nc_path, expected_sha256="0" * 64)

    # Explicit _FillValue is stripped cleanly, whereas unexpected NaN raises SRFError.
    nc_fill = tmp_path / "olci_fill.nc4"
    w_pad = np.concatenate([w_oa02, np.array([-999.0])])
    r_pad = np.concatenate([r_oa02, np.array([-999.0])])
    with h5py.File(nc_fill, "w") as h5:
        ds_r = h5.create_dataset("mean_spectral_response_function", data=r_pad[np.newaxis, :])
        ds_w = h5.create_dataset("mean_spectral_response_function_wavelength", data=w_pad[np.newaxis, :])
        ds_r.attrs["_FillValue"] = -999.0
        ds_w.attrs["_FillValue"] = -999.0
    loaded_fill = load_esa_s3_olci_srf_nc4(nc_fill)
    assert loaded_fill["Oa01"]["wavelengths_nm"].size == 200

    nc_nan = tmp_path / "olci_nan.nc4"
    r_bad_nan = r_oa02.copy()
    r_bad_nan[10] = np.nan
    with h5py.File(nc_nan, "w") as h5:
        h5.create_dataset("mean_spectral_response_function", data=r_bad_nan[np.newaxis, :])
        h5.create_dataset("mean_spectral_response_function_wavelength", data=w_oa02[np.newaxis, :])
    with pytest.raises(SRFError, match="unexpected non-finite"):
        load_esa_s3_olci_srf_nc4(nc_nan)

    # Duplicate normalized S2 band header & non-numeric response cell raise SRFError.
    dup_xlsx = tmp_path / "dup_s2.xlsx"
    with zipfile.ZipFile(dup_xlsx, "w") as xz:
        xz.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>SR_WL</t></si><si><t>S2A_SR_AV_B2</t></si><si><t>B2</t></si><si><t>#N/A</t></si>"
            "</sst>",
        )
        xz.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Spectral Responses (S2A)" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        xz.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        xz.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
            '<row r="2"><c r="A2"><v>400</v></c><c r="B2"><v>0.1</v></c><c r="C2"><v>0.1</v></c></row>'
            '<row r="3"><c r="A3"><v>401</v></c><c r="B3"><v>0.2</v></c><c r="C3"><v>0.2</v></c></row>'
            "</sheetData></worksheet>",
        )
    with pytest.raises(SRFError, match="duplicate normalized band column"):
        load_esa_s2_srf_xlsx(dup_xlsx, unit="S2A")

    # Malformed empty/mismatched array in audit_srf_support returns eligible=False without raw ValueError.
    bad_aud = audit_srf_support(target_wl, {"BAD": np.array([])}, shared_wavelengths_nm=wl_loaded)
    assert bad_aud[0]["eligible"] is False


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
