"""Unit and planted-defect tests for the HS-R02 official-SRF benchmark runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RUNNER_PATH = Path(__file__).resolve().parents[1] / "results" / "HS-R02_official_srf_retrieval" / "run_hs_r02.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_hs_r02", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_boxcar_weights_preserve_flat_spectrum_and_holm_adjust_is_exact() -> None:
    mod = _load_runner()
    wl = np.arange(400.0, 801.0, 1.0)
    W, names = mod.build_boxcar_weight_matrix(wl, [("B1", 443.0, 20.0), ("B2", 560.0, 30.0)])
    assert names == ["B1", "B2"]
    assert np.allclose(W.sum(axis=0), [1.0, 1.0], atol=1e-12)
    flat = np.full((3, wl.size), 0.0125)
    assert np.allclose(flat @ W, 0.0125, atol=1e-12)

    # Hand-worked Holm-Bonferroni step-down adjustment:
    # sorted p = [0.004, 0.02, 0.04] -> raw multiples [3*0.004=0.012, 2*0.02=0.04, 1*0.04=0.04]
    adj = mod.holm_bonferroni_adjust([0.04, 0.004, 0.02])
    assert adj == pytest.approx([0.04, 0.012, 0.04], rel=1e-12)


def test_bootstrap_sign_convention_a01_negative_favors_candidate() -> None:
    mod = _load_runner()
    groups = np.repeat([f"G{i:02d}" for i in range(10)], 6)
    truth = np.ones(groups.size)
    # Candidate (HS) has 0.10 error; reference has 0.30 error -> delta = 0.10 - 0.30 = -0.20 < 0
    pred_hs = truth + 0.10
    pred_ref = truth + 0.30
    res = mod.paired_delta_hs_minus_ref(truth, pred_hs, pred_ref, groups=groups, n_bootstrap=300, seed=2026)
    assert res["delta_hs_minus_ref"] == pytest.approx(-0.20, abs=1e-12)
    assert res["ci_high"] < 0.0
    assert res["ci_strictly_below_zero"] is True
    assert res["meets_003_magnitude"] is True


def test_feature_arms_preserve_negative_rrs_and_flag_b0_m0_missingness() -> None:
    mod = _load_runner()
    wl = np.arange(400.0, 801.0, 1.0)
    n = 4
    X = np.full((n, wl.size), 0.005, dtype=float)
    X[1, -1] = -0.0002  # NIR negative only (valid for AVW 400-700 and B0 ratio 705/665)
    X[2, 50] = -0.0001  # visible negative at 450 nm (invalid for AVW)
    meta = pd.DataFrame(
        [
            {"Latitude": 40.0, "Longitude": -80.0, "Date_Time_UTC": "2018-07-01T12:00:00Z"},
            {"Latitude": 41.0, "Longitude": -81.0, "Date_Time_UTC": "2018-07-02T12:00:00Z"},
            {"Latitude": 42.0, "Longitude": -82.0, "Date_Time_UTC": "2018-07-03T12:00:00Z"},
            {"Latitude": np.nan, "Longitude": -83.0, "Date_Time_UTC": "2018-07-04T12:00:00Z"},
        ]
    )
    W_dummy, _ = mod.build_boxcar_weight_matrix(wl, [("B1", 443.0, 20.0), ("B2", 665.0, 20.0)])
    mats = {"W_s2": W_dummy, "W_s3": W_dummy, "W_s2_box": W_dummy, "W_s3_box": W_dummy}
    arms, masks = mod.build_feature_arms(X, wl, meta, target_col="Chla", sensor_mats=mats)
    # Negative Rrs preserved unclipped in HS_401_raw
    assert float(arms["HS_401_raw"][1, -1]) == pytest.approx(-0.0002)
    assert masks["b0_ok"].tolist() == [True, True, False, True]
    assert masks["m0_ok"].tolist() == [True, True, True, False]
    assert masks["all_arm_ok"].tolist() == [True, True, False, False]


def test_nested_cv_ridge_and_hgb_prevent_test_fold_leakage() -> None:
    pytest.importorskip("sklearn")
    mod = _load_runner()
    from hydrospectral.splits import make_group_kfold_splits

    rng = np.random.default_rng(42)
    n_groups = 10
    groups = np.repeat([f"Site_{i:02d}" for i in range(n_groups)], 8)
    X = rng.normal(size=(groups.size, 6))
    y = 0.7 * X[:, 0] - 0.4 * X[:, 1] + 0.05 * rng.normal(size=groups.size)
    splits = make_group_kfold_splits(groups, n_splits=5)

    idx_a, pred_a, _ = mod.evaluate_nested_cv(
        X, y, splits, estimator_name="Ridge", inner_groups=groups, seed=2026
    )
    # Planted test-fold perturbation on fold 0's test rows must NOT change fold 0's training fit
    # or any OTHER fold's predictions if scaling & tuning are strictly fold-internal!
    X_pert = X.copy()
    te0 = splits[0][1]
    X_pert[te0] = 1e6
    _, pred_b, _ = mod.evaluate_nested_cv(
        X_pert, y, splits, estimator_name="Ridge", inner_groups=groups, seed=2026
    )
    # Predictions on fold 0 test rows must differ (since test inputs changed), while
    # predictions on fold 0 test rows from a model trained ONLY on splits[0][0] must match pred_a[te0]
    # when evaluated on original X[te0]; and verify HGB runs deterministically on same splits.
    assert np.array_equal(idx_a, np.arange(groups.size))
    assert not np.allclose(pred_a[te0], pred_b[te0])

    # Confirm fold-0 model uses strictly splits[0][0] (perturbing X[te0] does not change chosen alpha or fit on te0)
    _, pred_single_a, chosen_a = mod.evaluate_nested_cv(
        X, y, [splits[0]], estimator_name="Ridge", inner_groups=groups, seed=2026
    )
    y_pert = y.copy()
    y_pert[te0] = 999.0  # Extreme target perturbation ONLY on held-out test fold
    _, pred_single_b, chosen_b = mod.evaluate_nested_cv(
        X, y_pert, [splits[0]], estimator_name="Ridge", inner_groups=groups, seed=2026
    )
    assert np.allclose(pred_single_a, pred_single_b, atol=1e-12)
    assert chosen_a == chosen_b

    # HGB deterministic execution check on single fold
    idx_h1, pred_h1, _ = mod.evaluate_nested_cv(
        X, y, [splits[0]], estimator_name="HGB", inner_groups=groups, seed=2026
    )
    idx_h2, pred_h2, _ = mod.evaluate_nested_cv(
        X, y_pert, [splits[0]], estimator_name="HGB", inner_groups=groups, seed=2026
    )
    assert np.array_equal(idx_h1, idx_h2)
    assert np.allclose(pred_h1, pred_h2, atol=1e-12)
