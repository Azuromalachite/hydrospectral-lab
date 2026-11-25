"""Tests for GLORIA ID-safe loading, QC/circularity filters, leakage-free splits, and OOD."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hydrospectral.gloria import (
    GloriaDataError,
    GloriaTables,
    build_target_cohort,
    load_gloria_tables,
    summarize_qc_flags,
)
from hydrospectral.splits import (
    SplitLeakageError,
    assert_disjoint_groups,
    assert_paired_splits,
    compute_regression_metrics,
    make_group_kfold_splits,
    make_temporal_split,
    nearest_neighbor_sam_ood,
    paired_group_bootstrap_delta,
)


def _make_synthetic_gloria_zip(path: Path) -> Path:
    """Create a tiny GLORIA-shaped zip with deliberately shuffled row orders across tables."""
    wl = np.arange(400, 405)
    meta = pd.DataFrame(
        [
            {"GLORIA_ID": "GID_01", "Dataset_ID": "DS_A", "Country": "VN", "Site_name": "RedRiver", "Chla": 10.0, "Chla_method": "HPLC"},
            {"GLORIA_ID": "GID_02", "Dataset_ID": "DS_A", "Country": "VN", "Site_name": "RedRiver", "Chla": 20.0, "Chla_method": "HPLC"},
            {"GLORIA_ID": "GID_03", "Dataset_ID": "DS_GENEVA", "Country": "CH", "Site_name": "LakeGeneva", "Chla": 5.0, "Chla_method": "Thetis line-height"},
            {"GLORIA_ID": "GID_04", "Dataset_ID": "DS_C", "Country": "US", "Site_name": "Erie", "Chla": 15.0, "Chla_method": "fluorometry"},
            {"GLORIA_ID": "GID_05", "Dataset_ID": "DS_C", "Country": "US", "Site_name": "Erie", "Chla": -1.0, "Chla_method": "fluorometry"},
            {"GLORIA_ID": "GID_06", "Dataset_ID": "DS_D", "Country": "DE", "Site_name": "Constance", "Chla": 8.0, "Chla_method": "HPLC"},
            {"GLORIA_ID": "GID_07", "Dataset_ID": "DS_E", "Country": "US", "Site_name": "Tahoe", "Chla": 0.4, "Chla_method": "HPLC"},
            {"GLORIA_ID": "GID_08", "Dataset_ID": "DS_OPT_ONLY", "Country": "CH", "Site_name": "GenevaStation2", "Chla": 3.2, "Chla_method": "unspecified"},
        ]
    )

    rrs_rows = []
    for gid, vals in [
        ("GID_08", [0.004, 0.004, 0.004, 0.004, 0.004]),
        ("GID_07", [0.009, 0.008, 0.007, 0.006, 0.005]),
        ("GID_06", [0.003, np.nan, 0.003, 0.003, 0.003]),
        ("GID_05", [0.004, 0.004, 0.004, 0.004, 0.004]),
        ("GID_04", [0.005, 0.005, 0.005, 0.005, 0.005]),
        ("GID_03", [0.006, 0.006, 0.006, 0.006, 0.006]),
        ("GID_02", [-0.0005, 0.002, 0.003, 0.002, 0.001]),
        ("GID_01", [0.001, 0.002, 0.003, 0.004, 0.005]),
    ]:
        row = {"GLORIA_ID": gid}
        for w, v in zip(wl, vals, strict=True):
            row[f"Rrs_{w}"] = v
        rrs_rows.append(row)
    rrs = pd.DataFrame(rrs_rows)

    qc = pd.DataFrame(
        [
            {"GLORIA_ID": "GID_02", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_07", "Baseline_shift": 0, "Oxygen_signal": np.nan, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_04", "Baseline_shift": 0, "Oxygen_signal": 1, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_01", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_06", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_05", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_03", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
            {"GLORIA_ID": "GID_08", "Baseline_shift": 0, "Oxygen_signal": 0, "QWIP_fail": 0, "Suspect": 0},
        ]
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("GLORIA-2022/GLORIA_meta_and_lab.csv", meta.to_csv(index=False))
        zf.writestr("GLORIA-2022/GLORIA_Rrs.csv", rrs.to_csv(index=False))
        zf.writestr("GLORIA-2022/GLORIA_qc_flags.csv", qc.to_csv(index=False))
    return path


def test_gloria_joins_by_id_preserves_negatives_isolates_thetis_and_validates_qc(
    tmp_path: Path,
) -> None:
    zpath = _make_synthetic_gloria_zip(tmp_path / "GLORIA-2022.zip")
    tables = load_gloria_tables(zpath)
    assert tables.archive_sha256 is not None and len(tables.archive_sha256) == 64

    assert list(tables.meta["GLORIA_ID"]) == list(tables.rrs["GLORIA_ID"])
    assert list(tables.meta["GLORIA_ID"]) == list(tables.qc_flags["GLORIA_ID"])
    assert float(tables.rrs.loc[0, "Rrs_400"]) == pytest.approx(0.001)
    assert float(tables.rrs.loc[1, "Rrs_400"]) == pytest.approx(-0.0005)

    # Cohort using both substring heuristic (GID_03) and explicit Dataset_ID list (GID_08) (Finding #4).
    cohort = build_target_cohort(
        tables,
        target_col="Chla",
        min_nm=400,
        max_nm=404,
        exclude_optically_derived_chla=True,
        optically_derived_dataset_ids=["DS_OPT_ONLY"],
    )
    assert list(cohort["gloria_ids"]) == ["GID_01", "GID_02", "GID_07"]
    assert cohort["n_with_negative_rrs"] == 1
    assert cohort["counts"].exclusion_reasons["optically_derived_chla_circularity"] == 2
    assert sum(cohort["counts"].exclusion_reasons.values()) == cohort["counts"].excluded

    # Regression for Finding #5: require_unflagged=False + require_all_qc_tested=True keeps GID_04 (flagged
    # but fully tested!) and drops only GID_07 under qc_untested_wavelengths.
    tested_only = build_target_cohort(
        tables,
        target_col="Chla",
        min_nm=400,
        max_nm=404,
        require_unflagged=False,
        require_all_qc_tested=True,
        optically_derived_dataset_ids=["DS_OPT_ONLY"],
    )
    assert "GID_04" in list(tested_only["gloria_ids"])
    assert "GID_07" not in list(tested_only["gloria_ids"])
    assert tested_only["counts"].exclusion_reasons["qc_untested_wavelengths"] == 1

    # Regression for Finding #5: malformed QC values (2 or "suspect") must raise GloriaDataError.
    bad_qc_num = tables.qc_flags.copy()
    bad_qc_num.loc[0, "Baseline_shift"] = 2
    with pytest.raises(GloriaDataError, match="strictly 0, 1, or NaN"):
        summarize_qc_flags(bad_qc_num)

    bad_qc_str = tables.qc_flags.copy()
    bad_qc_str["Suspect"] = bad_qc_str["Suspect"].astype(object)
    bad_qc_str.loc[0, "Suspect"] = "suspect"
    with pytest.raises(GloriaDataError, match="non-numeric"):
        summarize_qc_flags(bad_qc_str)

    # Regression for Finding #10: manually constructing misaligned GloriaTables must fail __post_init__.
    with pytest.raises(GloriaDataError, match="not row-aligned"):
        GloriaTables(
            meta=tables.meta,
            rrs=tables.rrs.iloc[::-1].reset_index(drop=True),
            qc_flags=tables.qc_flags,
            archive_sha256=None,
        )

    # Refuses uncorrected chlorophyll+phaeopigment column names.
    with pytest.raises(GloriaDataError, match="do not silently substitute"):
        build_target_cohort(tables, target_col="Chla_plus_phaeo", min_nm=400, max_nm=404)

    with pytest.raises(GloriaDataError, match="SHA-256 mismatch"):
        load_gloria_tables(zpath, expected_sha256="0" * 64)


def test_gloria_refuses_duplicate_ids_and_directory_expected_sha256(tmp_path: Path) -> None:
    d = tmp_path / "gloria_dir"
    d.mkdir()
    (d / "GLORIA_meta_and_lab.csv").write_text("GLORIA_ID,Country,Site_name,Chla\nA,VN,R,1\nB,VN,R,2\n", encoding="utf-8")
    (d / "GLORIA_Rrs.csv").write_text("GLORIA_ID,Rrs_400\nA,0.01\nB,0.02\n", encoding="utf-8")

    # Regression for Finding #10: passing expected_sha256 on a directory must fail rather than skip!
    with pytest.raises(GloriaDataError, match="cannot be verified against an extracted directory"):
        load_gloria_tables(d, expected_sha256="a" * 64, include_qc_flags=False)

    (d / "GLORIA_meta_and_lab.csv").write_text("GLORIA_ID,Country,Site_name,Chla\nA,VN,R,1\nA,VN,R,2\n", encoding="utf-8")
    with pytest.raises(GloriaDataError, match="duplicate 'GLORIA_ID'"):
        load_gloria_tables(d, include_qc_flags=False)


def test_splits_prevent_leakage_nan_bypasses_and_temporal_precision_bugs() -> None:
    groups = np.array(["G1", "G1", "G1", "G2", "G2", "G3", "G4", "G5", "G6"])
    splits = make_group_kfold_splits(groups, n_splits=3)
    seen_test: list[int] = []
    for tr, te in splits:
        assert_disjoint_groups(groups, tr, te)
        seen_test.extend(te.tolist())
    assert sorted(seen_test) == list(range(len(groups)))

    # Planted group leakage & negative-index bypass (Finding #7).
    with pytest.raises(SplitLeakageError, match="group leakage"):
        assert_disjoint_groups(groups, np.array([0, 3, 4]), np.array([1, 5, 6]))
    with pytest.raises(SplitLeakageError, match="out of bounds"):
        assert_disjoint_groups(groups, np.array([0, 1]), np.array([-1]))

    # Regression for Finding #7: NaN group labels must raise rather than silently passing set & set!
    nan_groups = np.array([np.nan, "G2", np.nan, "G3"], dtype=object)
    with pytest.raises(SplitLeakageError, match="null/NaN"):
        assert_disjoint_groups(nan_groups, np.array([0, 1]), np.array([2, 3]))

    swapped = [(splits[0][0], splits[0][1][::-1])] + splits[1:]
    with pytest.raises(SplitLeakageError, match="not identically paired"):
        assert_paired_splits(splits, swapped)

    # Regression for Finding #6: mixed ISO formats + 50 ns separation before cutoff + invalid cutoff.
    ts_mixed = [
        "2020-01-01",
        "2021-12-31T23:59:59.999999950Z",  # 50 ns before cutoff (would collide under float64!)
        "2022-01-01T00:00:00Z",
        "2023-05-01",
    ]
    tr_t, te_t = make_temporal_split(ts_mixed, cutoff="2022-01-01T00:00:00Z")
    assert tr_t.tolist() == [0, 1]
    assert te_t.tolist() == [2, 3]
    with pytest.raises(SplitLeakageError, match="invalid cutoff"):
        make_temporal_split(ts_mixed, cutoff="not-a-cutoff")

    # Hand-worked unequal-group-size metrics proving equal-group RMSE != pooled RMSE.
    m = compute_regression_metrics([1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 3.0], groups=["A", "A", "A", "B"])
    assert m["pooled_log10_rmse"] == pytest.approx(1.0, rel=1e-12)
    assert m["equal_group_log10_rmse"] == pytest.approx(np.sqrt(2.0), rel=1e-12)
    assert m["raw_mae"] == pytest.approx(990.0 / 4.0)
    assert m["raw_median_ae"] == pytest.approx(0.0)
    with pytest.raises(SplitLeakageError, match="null/NaN"):
        compute_regression_metrics([1.0, 1.0], [1.0, 2.0], groups=["A", np.nan])


def test_cluster_bootstrap_rejects_nans_and_captures_between_group_variance() -> None:
    # Regression for Finding #3: NaN in one arm must fail rather than silently unpairing!
    with pytest.raises(SplitLeakageError, match="finite across all paired"):
        paired_group_bootstrap_delta(
            [1.0, 1.0, 1.0, 1.0],
            [np.nan, 1.0, 1.0, 1.0],
            [2.0, 1.0, 1.0, 1.0],
            groups=["A", "A", "B", "B"],
        )

    # Regression for Finding #14: heterogeneous groups with strong within-group correlation
    # produce a non-degenerate cluster CI strictly wider than naive row-level resampling!
    rng = np.random.default_rng(7)
    n_groups, per_group = 12, 25
    groups = np.repeat([f"Site_{i:02d}" for i in range(n_groups)], per_group)
    truth = np.ones(n_groups * per_group)
    group_bias_b = np.linspace(0.05, 0.95, n_groups)
    pred_a = truth + 0.10
    pred_b = truth + np.repeat(group_bias_b, per_group)

    cluster = paired_group_bootstrap_delta(truth, pred_a, pred_b, groups=groups, n_bootstrap=1000, seed=2026)
    cluster_width = cluster["ci_high"] - cluster["ci_low"]
    assert cluster["ci_low"] < cluster["observed_delta_b_minus_a"] < cluster["ci_high"]
    assert cluster_width > 0.10

    # Compare against naive row-level bootstrap (ignoring group clustering): must be much narrower.
    row_draws = rng.integers(0, truth.size, size=(1000, truth.size))
    sq_a = (pred_a - truth) ** 2
    sq_b = (pred_b - truth) ** 2
    row_boot = np.sqrt(sq_b[row_draws].mean(axis=1)) - np.sqrt(sq_a[row_draws].mean(axis=1))
    row_width = float(np.quantile(row_boot, 0.975) - np.quantile(row_boot, 0.025))
    assert cluster_width > 2.0 * row_width

    # Regression for Finding #11: duplicate training spectra (threshold == 0.0) must NOT falsely flag
    # an exact scaled copy (0.3 * s) as OOD!
    s_401 = np.linspace(0.001, 0.01, 401)
    tr_dup = np.vstack([s_401, s_401, s_401])
    orth = np.zeros_like(s_401)
    orth[-1] = 1.0
    ood = nearest_neighbor_sam_ood(tr_dup, np.vstack([0.3 * s_401, orth]), ood_quantile=0.95)
    assert bool(ood["is_ood"][0]) is False
    assert bool(ood["is_ood"][1]) is True
