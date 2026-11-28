"""Pre-registered HS-R02 confirmatory benchmark: Official ESA SRFs vs. Full 1 nm Hyperspectral GLORIA.

Implements the frozen protocol and 2026-11-28 A01-A10 amendment in:
  pre-registrations/2026-11-26-hs-r02-official-srf-retrieval.md

Key enforced invariants:
- Verified SHA-256 digests on GLORIA-2022.zip, ESA S2A MSI v5.0 XLSX, and ESA S3A OLCI NC4.
- Canonical ID-safe GLORIA cohorts (`hydrospectral.gloria.build_target_cohort`), preserving
  negative Rrs values unclipped and isolating optically derived Chla (`OdermattD_CH_Eawag`).
- Official ESA SRF support rule frozen at `support_rel_tol=1e-6` (S2A B1-B7; S3A Oa02-Oa16).
- Strict paired cohorts (`assert_matching_cohort_keys`) and paired folds (`assert_paired_splits`).
- Strictly nested inner group CV and fold-internal feature scaling (zero test-fold leakage).
- Whole-group cluster bootstrap sign convention `RMSE(HS) - RMSE(ref)` (negative favors HS).
- Byte-deterministic `manifest.json` (`status: "exploratory"` until independently reproduced).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Prevent BLAS/OpenMP oversubscription when outer/inner jobs run in parallel workers.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import h5py
import numpy as np
import pandas as pd
import yaml

from hydrospectral.gloria import build_target_cohort, load_gloria_tables
from hydrospectral.palette import compute_render_key, to_matplotlib_cmap
from hydrospectral.provenance import (
    CohortCounts,
    assert_matching_cohort_keys,
    build_manifest,
    collect_runtime_info,
    compute_cohort_key,
    inspect_git_provenance,
    sha256_file,
    write_manifest,
)
from hydrospectral.radiometry import (
    compute_avw,
    compute_band_ratio,
    normalize_unit_l2,
)
from hydrospectral.splits import (
    assert_disjoint_groups,
    assert_paired_splits,
    compute_regression_metrics,
    make_group_kfold_splits,
    make_temporal_split,
    nearest_neighbor_sam_ood,
    paired_group_bootstrap_delta,
)
from hydrospectral.srf import (
    audit_srf_support,
    build_per_band_srf_weight_matrix,
    build_srf_weight_matrix,
    load_esa_s2_srf_xlsx,
    load_esa_s3_olci_srf_nc4,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = Path(__file__).resolve().parent
SCRIPT_REL_PATH = "results/HS-R02_official_srf_retrieval/run_hs_r02.py"

TARGETS = ("Chla", "TSS", "aCDOM440")
SUPPORT_REL_TOL = 1e-6
SEED = 2026
N_BOOTSTRAP = 2000
INTERESTING_DELTA_THRESHOLD = -0.03  # RMSE(HS) - RMSE(ref) <= -0.03 log10 units

RIDGE_ALPHAS = tuple(float(a) for a in np.logspace(-4, 4, 17))
HGB_GRID = tuple(
    {
        "max_depth": depth,
        "learning_rate": lr,
        "min_samples_leaf": msl,
        "l2_regularization": l2,
    }
    for depth in (3, 6)
    for lr in (0.03, 0.1)
    for msl in (10, 30)
    for l2 in (0.0, 1.0)
)

WATER_BODY_LABELS = {
    1: "Lake",
    2: "Estuary",
    3: "Coastal",
    4: "River",
    5: "Other",
}


def load_manifest_sha256(repo_root: Path, rel_path: str) -> str:
    doc = yaml.safe_load((repo_root / rel_path).read_text(encoding="utf-8"))
    if not doc.get("digest_verified", False):
        raise ValueError(f"source manifest {rel_path} is not digest_verified=true")
    return str(doc["sha256"])


def resolve_local_inputs(repo_root: Path) -> dict[str, Path]:
    local_cfg = repo_root / "config" / "local_paths.yaml"
    if not local_cfg.is_file():
        raise FileNotFoundError(
            f"missing {local_cfg}; copy config/local_paths.example.yaml and point to local archives"
        )
    doc = yaml.safe_load(local_cfg.read_text(encoding="utf-8"))
    ds = doc.get("datasets", {})
    out: dict[str, Path] = {}
    for key in ("gloria_2022_zip", "esa_s2_msi_srf_xlsx", "esa_s3a_olci_srf_nc4"):
        raw = ds.get(key)
        if not raw:
            raise ValueError(f"config/local_paths.yaml missing datasets.{key}")
        p = Path(raw)
        out[key] = p if p.is_absolute() else (repo_root / p).resolve()
    return out


def build_boxcar_weight_matrix(
    target_wl: np.ndarray,
    band_specs: Sequence[tuple[str, float, float]],
) -> tuple[np.ndarray, list[str]]:
    """Build normalized rectangular boxcar weight matrix W from (name, center_nm, fwhm_nm)."""
    dw = np.diff(target_wl)
    trap = np.zeros_like(target_wl, dtype=float)
    trap[0] = 0.5 * dw[0]
    trap[-1] = 0.5 * dw[-1]
    if target_wl.size > 2:
        trap[1:-1] = 0.5 * (dw[:-1] + dw[1:])

    cols: list[np.ndarray] = []
    names: list[str] = []
    for name, center_nm, fwhm_nm in band_specs:
        half = 0.5 * float(fwhm_nm)
        mask = (target_wl >= center_nm - half) & (target_wl <= center_nm + half)
        if not mask.any():
            raise ValueError(f"boxcar band {name!r} [{center_nm-half}, {center_nm+half}] has no grid points")
        w = np.where(mask, trap, 0.0)
        w = w / float(w.sum())
        cols.append(w)
        names.append(name)
    return np.column_stack(cols), names


def _estimate_fwhm_nm(wl: np.ndarray, resp: np.ndarray) -> float:
    half = 0.5 * float(resp.max())
    above = wl[resp >= half]
    if above.size < 2:
        return 1.0
    return float(above[-1] - above[0])


def build_sensor_matrices(
    target_wl: np.ndarray,
    s2_xlsx: Path,
    s3_nc4: Path,
    *,
    s2_sha256: str | None = None,
    s3_sha256: str | None = None,
    support_rel_tol: float = SUPPORT_REL_TOL,
) -> dict[str, Any]:
    """Build verified official ESA SRF and nominal boxcar weight matrices on `target_wl`."""
    s2_wl, s2_curves = load_esa_s2_srf_xlsx(s2_xlsx, expected_sha256=s2_sha256)
    s2_audit = audit_srf_support(
        target_wl, s2_curves, shared_wavelengths_nm=s2_wl, support_rel_tol=support_rel_tol
    )
    s2_eligible = [r["band"] for r in s2_audit if r["eligible"]]
    W_s2, s2_names = build_srf_weight_matrix(
        target_wl,
        s2_wl,
        s2_curves,
        band_order=s2_eligible,
        support_rel_tol=support_rel_tol,
    )
    s2_box_specs: list[tuple[str, float, float]] = []
    for r in s2_audit:
        if r["eligible"]:
            b = r["band"]
            fwhm = _estimate_fwhm_nm(s2_wl, s2_curves[b])
            s2_box_specs.append((b, float(r["effective_wavelength_nm"]), fwhm))
    W_s2_box, _ = build_boxcar_weight_matrix(target_wl, s2_box_specs)

    s3_curves = load_esa_s3_olci_srf_nc4(s3_nc4, expected_sha256=s3_sha256)
    s3_audit = audit_srf_support(target_wl, s3_curves, support_rel_tol=support_rel_tol)
    s3_eligible = [r["band"] for r in s3_audit if r["eligible"]]
    W_s3, s3_names = build_per_band_srf_weight_matrix(
        target_wl,
        s3_curves,
        band_order=s3_eligible,
        support_rel_tol=support_rel_tol,
    )

    with h5py.File(s3_nc4, "r") as hf:
        nom_c = np.asarray(hf["nominal_centre_wavelength"][:], dtype=float)
        nom_w = np.asarray(hf["bandwidth_fwhm"][:], dtype=float)
    s3_box_specs: list[tuple[str, float, float]] = []
    for b in s3_names:
        idx = int(b.replace("Oa", "")) - 1
        s3_box_specs.append((b, float(nom_c[idx]), float(nom_w[idx])))
    W_s3_box, _ = build_boxcar_weight_matrix(target_wl, s3_box_specs)

    return {
        "W_s2": W_s2,
        "s2_bands": s2_names,
        "W_s2_box": W_s2_box,
        "W_s3": W_s3,
        "s3_bands": s3_names,
        "W_s3_box": W_s3_box,
        "s2_audit": s2_audit,
        "s3_audit": s3_audit,
    }


def build_feature_arms(
    X_rrs: np.ndarray,
    wl: np.ndarray,
    meta_rows: pd.DataFrame,
    *,
    target_col: str,
    sensor_mats: Mapping[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Construct all pre-registered feature matrices without clipping negative Rrs.

    Returns (arms_dict, masks_dict) where masks_dict flags finite validity for
    B0_ratio, M0_context, and their intersection (`all_arm_paired`).
    """
    n = X_rrs.shape[0]
    norms = np.linalg.norm(X_rrs, axis=1)
    if np.any(norms <= 0.0) or not np.isfinite(norms).all():
        raise ValueError("encountered zero-norm or non-finite Rrs spectrum in cohort")
    X_l2 = np.column_stack([normalize_unit_l2(X_rrs), np.log10(norms)])

    X_s2 = X_rrs @ sensor_mats["W_s2"]
    X_s3 = X_rrs @ sensor_mats["W_s3"]
    X_s2_box = X_rrs @ sensor_mats["W_s2_box"]
    X_s3_box = X_rrs @ sensor_mats["W_s3_box"]

    def _l2_with_log_norm(arr: np.ndarray) -> np.ndarray:
        nrm = np.linalg.norm(arr, axis=1)
        if np.any(nrm <= 0.0) or not np.isfinite(nrm).all():
            raise ValueError("encountered zero-norm or non-finite multispectral row")
        return np.column_stack([normalize_unit_l2(arr), np.log10(nrm)])

    X_s2_l2 = _l2_with_log_norm(X_s2)
    X_s3_l2 = _l2_with_log_norm(X_s3)

    # B0_ratio: target-specific physical ratio + AVW (400-700 nm, require_nonnegative=True)
    avw = np.asarray(compute_avw(X_rrs, wl, require_nonnegative=True), dtype=float)
    r_705_665 = np.asarray(
        compute_band_ratio(X_rrs, wl, 705.0, 665.0, require_positive_both=True), dtype=float
    )
    r_560_443 = np.asarray(
        compute_band_ratio(X_rrs, wl, 560.0, 443.0, require_positive_both=True), dtype=float
    )
    r_665 = X_rrs[:, int(np.argmin(np.abs(wl - 665.0)))]

    with np.errstate(divide="ignore", invalid="ignore"):
        log_705_665 = np.where(np.isfinite(r_705_665) & (r_705_665 > 0.0), np.log10(r_705_665), np.nan)
        log_560_443 = np.where(np.isfinite(r_560_443) & (r_560_443 > 0.0), np.log10(r_560_443), np.nan)

    if target_col == "Chla":
        X_b0 = np.column_stack([log_705_665, avw])
    elif target_col == "TSS":
        X_b0 = np.column_stack([log_705_665, r_665, avw])
    elif target_col == "aCDOM440":
        X_b0 = np.column_stack([log_560_443, avw])
    else:
        raise ValueError(f"unsupported HS-R02 target: {target_col!r}")

    # M0_context: Latitude, Longitude, circular day-of-year (sin, cos)
    lat = pd.to_numeric(meta_rows["Latitude"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(meta_rows["Longitude"], errors="coerce").to_numpy(dtype=float)
    ts = pd.to_datetime(meta_rows["Date_Time_UTC"], format="ISO8601", errors="coerce", utc=True)
    doy = ts.dt.day_of_year.to_numpy(dtype=float)
    ang = 2.0 * math.pi * (doy / 365.25)
    X_m0 = np.column_stack([lat, lon, np.sin(ang), np.cos(ang)])

    b0_ok = np.isfinite(X_b0).all(axis=1)
    m0_ok = np.isfinite(X_m0).all(axis=1)
    ts_ok = ts.notna().to_numpy(dtype=bool)
    all_arm_ok = b0_ok & m0_ok

    arms = {
        "B0_ratio": X_b0,
        "M0_context": X_m0,
        "S2_SRF": X_s2,
        "S3_SRF": X_s3,
        "S2_SRF_l2": X_s2_l2,
        "S3_SRF_l2": X_s3_l2,
        "S2_boxcar": X_s2_box,
        "S3_boxcar": X_s3_box,
        "HS_401_raw": X_rrs.copy(),
        "HS_401_l2": X_l2,
        "M0_plus_S3": np.hstack([X_m0, X_s3]),
        "M0_plus_S3_l2": np.hstack([X_m0, X_s3_l2]),
        "M0_plus_HS": np.hstack([X_m0, X_l2]),
    }
    masks = {
        "b0_ok": b0_ok,
        "m0_ok": m0_ok,
        "ts_ok": ts_ok,
        "all_arm_ok": all_arm_ok,
        "all_primary": np.ones(n, dtype=bool),
    }
    return arms, masks


def make_random_kfold_splits(n: int, *, n_splits: int = 5, seed: int = SEED) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic shuffled K-fold splits (diagnostic reference only, never for model selection)."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    folds = np.array_split(perm, n_splits)
    all_idx = np.arange(n, dtype=int)
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for f in folds:
        te = np.sort(f.astype(int))
        tr = np.setdiff1d(all_idx, te, assume_unique=True)
        splits.append((tr, te))
    return splits


def _inner_splits(
    inner_groups: np.ndarray | None,
    n_train: int,
    *,
    n_splits: int = 5,
    seed: int = SEED,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if inner_groups is None:
        return make_random_kfold_splits(n_train, n_splits=n_splits, seed=seed)
    n_unique = int(pd.Series(inner_groups).nunique())
    k = min(n_splits, n_unique)
    if k < 2:
        raise ValueError(f"cannot form inner group CV with only {n_unique} unique group(s)")
    return make_group_kfold_splits(inner_groups, n_splits=k)


def _score_predictions(
    truth_log10: np.ndarray,
    pred_log10: np.ndarray,
    groups: np.ndarray | None,
) -> float:
    if groups is None:
        return float(np.sqrt(np.mean((pred_log10 - truth_log10) ** 2)))
    return float(compute_regression_metrics(truth_log10, pred_log10, groups=groups)["equal_group_log10_rmse"])


def _fit_predict_ridge_fold(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    *,
    alpha: float,
) -> np.ndarray:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)
    model = Ridge(alpha=float(alpha))
    model.fit(X_tr_s, y_tr)
    return np.asarray(model.predict(X_te_s), dtype=float)


def _fit_predict_hgb_fold(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    *,
    params: Mapping[str, Any],
    seed: int = SEED,
) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingRegressor

    # Tree quantile binning is invariant to per-feature affine StandardScaler; cast to float32
    # directly (matching HistGradientBoostingRegressor's internal representation).
    model = HistGradientBoostingRegressor(
        max_iter=300,
        early_stopping=False,
        random_state=seed,
        max_depth=int(params["max_depth"]),
        learning_rate=float(params["learning_rate"]),
        min_samples_leaf=int(params["min_samples_leaf"]),
        l2_regularization=float(params["l2_regularization"]),
    )
    model.fit(np.asarray(X_tr, dtype=np.float32), y_tr)
    return np.asarray(model.predict(np.asarray(X_te, dtype=np.float32)), dtype=float)


def _run_hgb_inner_task(
    X_tr_f32: np.ndarray,
    y_tr: np.ndarray,
    in_tr: np.ndarray,
    in_va: np.ndarray,
    params: Mapping[str, Any],
    seed: int,
) -> np.ndarray:
    return _fit_predict_hgb_fold(
        X_tr_f32[in_tr],
        y_tr[in_tr],
        X_tr_f32[in_va],
        params=params,
        seed=seed,
    )


def evaluate_nested_cv(
    X: np.ndarray,
    y_log10: np.ndarray,
    outer_splits: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    estimator_name: str,
    inner_groups: np.ndarray | None,
    require_outer_disjoint_groups: bool = True,
    parallel: Any | None = None,
    seed: int = SEED,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Run leakage-free nested CV and return (eval_indices, oof_preds, chosen_hyperparams).

    For K-fold splits, eval_indices covers 0..N-1 in exact order. For single-split
    temporal holdout, eval_indices is the held-out test index array.
    """
    if not np.isfinite(X).all():
        raise ValueError("feature matrix X contains NaN/inf; caller must enforce paired finite cohorts")
    if not np.isfinite(y_log10).all():
        raise ValueError("target y_log10 contains NaN/inf")

    eval_parts: list[np.ndarray] = []
    pred_parts: list[np.ndarray] = []
    chosen_params: list[dict[str, Any]] = []

    if estimator_name == "Ridge":
        for fold_idx, (tr, te) in enumerate(outer_splits):
            if inner_groups is not None and require_outer_disjoint_groups:
                assert_disjoint_groups(inner_groups, tr, te)
            X_tr, y_tr, X_te = X[tr], y_log10[tr], X[te]
            g_tr = None if inner_groups is None else inner_groups[tr]
            in_splits = _inner_splits(g_tr, len(tr), n_splits=5, seed=seed)

            best_alpha = RIDGE_ALPHAS[0]
            best_loss = float("inf")
            for alpha in RIDGE_ALPHAS:
                in_oof = np.empty(len(tr), dtype=float)
                for in_tr, in_va in in_splits:
                    in_oof[in_va] = _fit_predict_ridge_fold(
                        X_tr[in_tr], y_tr[in_tr], X_tr[in_va], alpha=alpha
                    )
                loss = _score_predictions(y_tr, in_oof, g_tr)
                if loss < best_loss:
                    best_loss = loss
                    best_alpha = alpha

            preds = _fit_predict_ridge_fold(X_tr, y_tr, X_te, alpha=best_alpha)
            eval_parts.append(np.asarray(te, dtype=int))
            pred_parts.append(preds)
            chosen_params.append({"fold": fold_idx, "alpha": best_alpha, "inner_loss": best_loss})

    elif estimator_name == "HGB":
        from joblib import delayed

        X_f32 = np.asarray(X, dtype=np.float32)
        for fold_idx, (tr, te) in enumerate(outer_splits):
            if inner_groups is not None and require_outer_disjoint_groups:
                assert_disjoint_groups(inner_groups, tr, te)
            t_fold = time.perf_counter()
            X_tr, y_tr, X_te = X_f32[tr], y_log10[tr], X_f32[te]
            g_tr = None if inner_groups is None else inner_groups[tr]
            in_splits = _inner_splits(g_tr, len(tr), n_splits=3, seed=seed)

            tasks = [
                (cfg_idx, in_idx, in_tr, in_va, cfg)
                for cfg_idx, cfg in enumerate(HGB_GRID)
                for in_idx, (in_tr, in_va) in enumerate(in_splits)
            ]
            if parallel is not None:
                results = parallel(
                    delayed(_run_hgb_inner_task)(X_tr, y_tr, in_tr, in_va, cfg, seed)
                    for _, _, in_tr, in_va, cfg in tasks
                )
            else:
                results = [
                    _run_hgb_inner_task(X_tr, y_tr, in_tr, in_va, cfg, seed)
                    for _, _, in_tr, in_va, cfg in tasks
                ]

            n_in = len(in_splits)
            best_cfg = HGB_GRID[0]
            best_loss = float("inf")
            for cfg_idx, cfg in enumerate(HGB_GRID):
                in_oof = np.empty(len(tr), dtype=float)
                for in_idx in range(n_in):
                    pos = cfg_idx * n_in + in_idx
                    _, _, _, in_va, _ = tasks[pos]
                    in_oof[in_va] = results[pos]
                loss = _score_predictions(y_tr, in_oof, g_tr)
                if loss < best_loss:
                    best_loss = loss
                    best_cfg = cfg

            preds = _fit_predict_hgb_fold(X_tr, y_tr, X_te, params=best_cfg, seed=seed)
            eval_parts.append(np.asarray(te, dtype=int))
            pred_parts.append(preds)
            chosen_params.append({"fold": fold_idx, **best_cfg, "inner_loss": best_loss})
            if X_f32.shape[1] > 50:
                print(
                    f"    HGB({X_f32.shape[1]}f) outer fold {fold_idx + 1}/{len(outer_splits)} "
                    f"done in {time.perf_counter() - t_fold:.1f}s (best_inner={best_loss:.4f})",
                    flush=True,
                )
    else:
        raise ValueError(f"unknown estimator_name {estimator_name!r}; expected 'Ridge' or 'HGB'")

    eval_idx = np.concatenate(eval_parts)
    oof_preds = np.concatenate(pred_parts)
    order = np.argsort(eval_idx)
    return eval_idx[order], oof_preds[order], chosen_params


def paired_delta_hs_minus_ref(
    truth_log10: np.ndarray,
    pred_hs_log10: np.ndarray,
    pred_ref_log10: np.ndarray,
    *,
    groups: np.ndarray,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> dict[str, float | int]:
    """Compute whole-group cluster bootstrap for delta = RMSE(HS) - RMSE(ref) (A01).

    Calls `paired_group_bootstrap_delta(truth, pred_ref, pred_hs, ...)` because that helper
    returns `RMSE(B) - RMSE(A)`. Negative `delta_hs_minus_ref` and `ci_high < 0` favor HS.
    Also computes a two-sided cluster-bootstrap p-value for Holm-Bonferroni multiplicity audit.
    """
    res = paired_group_bootstrap_delta(
        truth_log10,
        pred_ref_log10,
        pred_hs_log10,
        groups=groups,
        n_bootstrap=n_bootstrap,
        seed=seed,
        ci_level=0.95,
    )
    # Reproduce exact bootstrap draws to compute two-sided p-value consistently with res.
    df = pd.DataFrame(
        {
            "group": [str(x) for x in groups],
            "sq_ref": (np.asarray(pred_ref_log10, dtype=float) - np.asarray(truth_log10, dtype=float)) ** 2,
            "sq_hs": (np.asarray(pred_hs_log10, dtype=float) - np.asarray(truth_log10, dtype=float)) ** 2,
        }
    )
    per_group = df.groupby("group", sort=True)[["sq_ref", "sq_hs"]].mean()
    mse_ref = per_group["sq_ref"].to_numpy(dtype=float)
    mse_hs = per_group["sq_hs"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(per_group), size=(n_bootstrap, len(per_group)))
    boot = np.sqrt(mse_hs[draws].mean(axis=1)) - np.sqrt(mse_ref[draws].mean(axis=1))
    p_le = (int(np.sum(boot <= 0.0)) + 1) / (n_bootstrap + 1)
    p_ge = (int(np.sum(boot >= 0.0)) + 1) / (n_bootstrap + 1)
    p_two_sided = float(min(1.0, 2.0 * min(p_le, p_ge)))

    return {
        "n_groups": int(res["n_groups"]),
        "n_bootstrap": int(res["n_bootstrap"]),
        "delta_hs_minus_ref": float(res["observed_delta_b_minus_a"]),
        "ci_low": float(res["ci_low"]),
        "ci_high": float(res["ci_high"]),
        "p_boot_two_sided": p_two_sided,
        "ci_strictly_below_zero": bool(res["ci_high"] < 0.0),
        "meets_003_magnitude": bool(res["observed_delta_b_minus_a"] <= INTERESTING_DELTA_THRESHOLD),
    }


def holm_bonferroni_adjust(p_values: Sequence[float]) -> list[float]:
    """Step-down Holm-Bonferroni adjusted p-values in original input order."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(float(p) for p in p_values), key=lambda kv: kv[1])
    adj = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        val = min(1.0, (m - rank) * p)
        running_max = max(running_max, val)
        adj[orig_idx] = running_max
    return adj


def _cache_key(parts: Mapping[str, Any]) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def _run_or_load_cell(
    cache_dir: Path | None,
    key_payload: Mapping[str, Any],
    X: np.ndarray,
    y_log10: np.ndarray,
    outer_splits: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    estimator_name: str,
    inner_groups: np.ndarray | None,
    require_outer_disjoint_groups: bool = True,
    parallel: Any | None,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cpath = cache_dir / f"{_cache_key(key_payload)}.json"
        if cpath.is_file():
            saved = json.loads(cpath.read_text(encoding="utf-8"))
            return (
                np.asarray(saved["eval_idx"], dtype=int),
                np.asarray(saved["preds"], dtype=float),
                list(saved["chosen_params"]),
            )
    eval_idx, preds, chosen = evaluate_nested_cv(
        X,
        y_log10,
        outer_splits,
        estimator_name=estimator_name,
        inner_groups=inner_groups,
        require_outer_disjoint_groups=require_outer_disjoint_groups,
        parallel=parallel,
        seed=SEED,
    )
    if cache_dir is not None:
        cpath = cache_dir / f"{_cache_key(key_payload)}.json"
        cpath.write_text(
            json.dumps(
                {
                    "eval_idx": eval_idx.tolist(),
                    "preds": preds.tolist(),
                    "chosen_params": chosen,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return eval_idx, preds, chosen


def make_summary_figure(
    metrics_df: pd.DataFrame,
    deltas_df: pd.DataFrame,
    budget_df: pd.DataFrame,
    strat_df: pd.DataFrame,
    out_path: Path,
) -> str:
    """Render compact 4-panel Crameri summary figure for HS-R02 and return its render_key."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 160,
        }
    )
    cmap_batlow = to_matplotlib_cmap("batlow")
    cols = [cmap_batlow(v) for v in (0.12, 0.40, 0.68, 0.88)]
    render_key = compute_render_key("batlow", 0.0, 1.0, kind="sequential", extra={"figure": "hs_r02_4panel"})

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.8), constrained_layout=True)

    # Panel A: Equal-group log10 RMSE on primary_optical site_kfold & dataset_kfold (matched L2 for Ridge, raw/L2 for HGB)
    ax = axes[0, 0]
    sub_a = metrics_df[
        (metrics_df["cohort_mode"] == "primary_optical")
        & (metrics_df["split"].isin(["site_kfold", "dataset_kfold"]))
    ]
    x_labels = []
    bars_data: dict[str, list[float]] = {"S2_ref": [], "S3_ref": [], "HS_401_l2": []}
    for t in TARGETS:
        for est in ("Ridge", "HGB"):
            s2_arm = "S2_SRF_l2" if est == "Ridge" else "S2_SRF"
            s3_arm = "S3_SRF_l2" if est == "Ridge" else "S3_SRF"
            for sp in ("site_kfold", "dataset_kfold"):
                row_s = sub_a[
                    (sub_a["target"] == t)
                    & (sub_a["estimator"] == est)
                    & (sub_a["split"] == sp)
                    & (sub_a["arm"].isin([s2_arm, s3_arm, "HS_401_l2"]))
                ]
                if len(row_s) == 3:
                    x_labels.append(f"{t}\n{est} {'Site' if sp == 'site_kfold' else 'Study'}")
                    bars_data["S2_ref"].append(float(row_s[row_s["arm"] == s2_arm]["equal_group_log10_rmse"].iloc[0]))
                    bars_data["S3_ref"].append(float(row_s[row_s["arm"] == s3_arm]["equal_group_log10_rmse"].iloc[0]))
                    bars_data["HS_401_l2"].append(float(row_s[row_s["arm"] == "HS_401_l2"]["equal_group_log10_rmse"].iloc[0]))
    x = np.arange(len(x_labels))
    w = 0.26
    for i, (key, lbl) in enumerate(
        (("S2_ref", "S2A SRF (L2 for Ridge)"), ("S3_ref", "S3A SRF (L2 for Ridge)"), ("HS_401_l2", "HS_401_l2"))
    ):
        ax.bar(x + (i - 1) * w, bars_data[key], width=w, color=cols[i], label=lbl)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=35, ha="right", fontsize=7.2)
    ax.set_ylabel("Equal-group log10 RMSE")
    ax.set_title("A. Official S2A/S3A SRFs vs. Full 1 nm HS_401_l2 (Primary Cohort)")
    ax.legend(frameon=False, fontsize=7.4, loc="upper left", ncol=2)

    # Panel B: Paired cluster-bootstrap delta (matched preprocessing: Ridge HS_401_l2 - S3_SRF_l2; HGB HS_401_l2 - S3_SRF)
    ax = axes[0, 1]
    sub_b = deltas_df[
        (deltas_df["cohort_mode"] == "primary_optical")
        & (deltas_df["split"].isin(["site_kfold", "dataset_kfold"]))
        & (
            ((deltas_df["estimator"] == "Ridge") & (deltas_df["contrast"] == "HS_401_l2_vs_S3_SRF_l2"))
            | ((deltas_df["estimator"] == "HGB") & (deltas_df["contrast"] == "HS_401_l2_vs_S3_SRF"))
        )
    ].reset_index(drop=True)
    y_pos = np.arange(len(sub_b))
    for i, row in sub_b.iterrows():
        c = cols[0] if row["split"] == "site_kfold" else cols[2]
        ax.errorbar(
            row["delta_hs_minus_ref"],
            i,
            xerr=[[row["delta_hs_minus_ref"] - row["ci_low"]], [row["ci_high"] - row["delta_hs_minus_ref"]]],
            fmt="o",
            color=c,
            ecolor=c,
            capsize=3,
            ms=5,
        )
    ax.axvline(0.0, color="black", lw=1.0, ls="--", label="Zero delta (null)")
    ax.axvline(-0.03, color="#c94c4c", lw=1.1, ls=":", label="Pre-reg threshold (-0.03)")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(
        [f"{r['target']} | {r['estimator']} | {'Site' if r['split']=='site_kfold' else 'Study'}" for _, r in sub_b.iterrows()],
        fontsize=7.6,
    )
    ax.invert_yaxis()
    ax.set_xlabel("Delta equal-group log10 RMSE: HS_401_l2 - S3A matched ref (negative favors HS)")
    ax.set_title("B. Paired Cluster-Bootstrap 95% CIs (Matched-Preprocessing Contrasts)")
    ax.legend(frameon=False, fontsize=7.5, loc="lower left")

    # Panel C: Validation optimism gap (Random vs Site vs Study vs Temporal) + M0/B0 baselines (Ridge all_arm_paired)
    ax = axes[1, 0]
    sub_c = metrics_df[
        (metrics_df["cohort_mode"] == "all_arm_paired")
        & (metrics_df["estimator"] == "Ridge")
        & (metrics_df["split"].isin(["random_kfold_diag", "site_kfold", "dataset_kfold", "temporal_80_20"]))
        & (metrics_df["arm"].isin(["B0_ratio", "M0_context", "S3_SRF_l2", "HS_401_l2"]))
    ]
    split_order = ["random_kfold_diag", "temporal_80_20", "site_kfold", "dataset_kfold"]
    split_names = ["Random\n(diag)", "Temporal\n80/20", "Site\nholdout", "Study\nholdout"]
    x_c = np.arange(len(split_order))
    for i, arm in enumerate(("M0_context", "B0_ratio", "S3_SRF_l2", "HS_401_l2")):
        vals = []
        for sp in split_order:
            s_rows = sub_c[(sub_c["split"] == sp) & (sub_c["arm"] == arm) & (sub_c["target"] == "Chla")]
            vals.append(float(s_rows["equal_group_log10_rmse"].iloc[0]) if len(s_rows) else math.nan)
        ax.plot(x_c, vals, marker="o", lw=1.8, color=cols[i], label=arm)
    ax.set_xticks(x_c)
    ax.set_xticklabels(split_names)
    ax.set_ylabel("Chla equal-group log10 RMSE (Ridge)")
    ax.set_title("C. Validation-Optimism Gap & Baselines (Chla Paired Cohort)")
    ax.legend(frameon=False, fontsize=7.8, loc="upper left")

    # Panel D: OOD vs In-domain & Water-body stratification (Chla HS_401_l2 Ridge site_kfold)
    ax = axes[1, 1]
    sub_d = strat_df[
        (strat_df["target"] == "Chla")
        & (strat_df["split"] == "site_kfold")
        & (strat_df["estimator"] == "Ridge")
        & (strat_df["arm"].isin(["S3_SRF", "HS_401_l2"]))
    ]
    strata = ["in_domain", "ood", "Lake", "Coastal", "River"]
    x_d = np.arange(len(strata))
    wd = 0.34
    for i, arm in enumerate(("S3_SRF", "HS_401_l2")):
        vals = []
        ns = []
        for st in strata:
            r = sub_d[(sub_d["arm"] == arm) & (sub_d["stratum_value"] == st)]
            vals.append(float(r["pooled_log10_rmse"].iloc[0]) if len(r) else math.nan)
            ns.append(int(r["n"].iloc[0]) if len(r) else 0)
        bars = ax.bar(x_d + (i - 0.5) * wd, vals, width=wd, color=cols[i * 2], label=arm)
        if i == 0:
            for j, n_val in enumerate(ns):
                ax.text(j, 0.02, f"n={n_val}", ha="center", va="bottom", fontsize=7.0, color="white", fontweight="bold")
    ax.set_xticks(x_d)
    ax.set_xticklabels(["In-domain\n(SAM)", "OOD\n(SAM > p95)", "Lake", "Coastal", "River"])
    ax.set_ylabel("Chla pooled log10 RMSE (Ridge, Site CV)")
    ax.set_title("D. Applicability Domain (SAM OOD) & Water-Body Error Profile")
    ax.legend(frameon=False, fontsize=7.8, loc="upper left")

    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return render_key


def run_benchmark(
    *,
    gloria_zip: Path,
    s2_xlsx: Path,
    s3_nc4: Path,
    out_dir: Path,
    repo_root: Path = REPO_ROOT,
    expected_gloria_sha256: str | None = None,
    expected_s2_sha256: str | None = None,
    expected_s3_sha256: str | None = None,
    n_jobs: int = 12,
    run_hgb: bool = True,
    cache_dir: Path | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Execute the pre-registered HS-R02 benchmark and emit compact retained artifacts."""
    from joblib import Parallel

    t_start = time.perf_counter()
    git_info = inspect_git_provenance(repo_root, SCRIPT_REL_PATH)
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = load_gloria_tables(gloria_zip, expected_sha256=expected_gloria_sha256)
    gloria_sha = tables.archive_sha256 or sha256_file(gloria_zip)
    s2_sha = expected_s2_sha256 or sha256_file(s2_xlsx)
    s3_sha = expected_s3_sha256 or sha256_file(s3_nc4)

    wl_800 = np.arange(400.0, 801.0, 1.0)
    wl_700 = np.arange(400.0, 701.0, 1.0)
    mats_800 = build_sensor_matrices(
        wl_800, s2_xlsx, s3_nc4, s2_sha256=s2_sha, s3_sha256=s3_sha, support_rel_tol=SUPPORT_REL_TOL
    )
    mats_700 = build_sensor_matrices(
        wl_700, s2_xlsx, s3_nc4, s2_sha256=s2_sha, s3_sha256=s3_sha, support_rel_tol=SUPPORT_REL_TOL
    )

    inputs_sha = {
        "src.esa-s2a-msi-srf": s2_sha,
        "src.esa-s3a-olci-srf": s3_sha,
        "src.gloria-2022": gloria_sha,
    }

    metrics_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    strat_rows: list[dict[str, Any]] = []
    manifest_counts: dict[str, CohortCounts] = {}
    cohort_keys_by_target: dict[str, dict[str, str]] = {}

    meta_indexed = tables.meta.set_index("GLORIA_ID")

    with Parallel(n_jobs=max(1, int(n_jobs)), max_nbytes=None) as parallel:
        # ---- 1. Main 400-800 nm confirmatory & paired-baseline benchmark ----
        for target in TARGETS:
            coh = build_target_cohort(
                tables,
                target_col=target,
                min_nm=400,
                max_nm=800,
                require_unflagged=True,
                require_all_qc_tested=False,
                exclude_optically_derived_chla=(target == "Chla"),
            )
            manifest_counts[f"{target}_primary_400_800"] = coh["counts"]

            ids_all = coh["gloria_ids"]
            meta_sub = meta_indexed.loc[ids_all].reset_index()
            X_rrs_all = coh["X_rrs"]
            y_log_all = np.log10(coh["y"])
            site_all = coh["site_groups"]
            ds_all = coh["dataset_ids"]
            wb_all = pd.to_numeric(meta_sub["Water_body_type"], errors="coerce").fillna(-1).astype(int).to_numpy()
            ts_all = pd.to_datetime(meta_sub["Date_Time_UTC"], format="ISO8601", errors="coerce", utc=True)

            arms_all, masks_all = build_feature_arms(
                X_rrs_all, wl_800, meta_sub, target_col=target, sensor_mats=mats_800
            )
            cohort_keys_by_target[target] = {}

            # Record explicit CohortCounts for all_arm_paired and temporal_dated subcohorts
            n_prim = len(ids_all)
            n_paired = int(masks_all["all_arm_ok"].sum())
            manifest_counts[f"{target}_all_arm_paired"] = CohortCounts(
                attempted=n_prim,
                completed=n_paired,
                failed=0,
                excluded=n_prim - n_paired,
                exclusion_reasons={
                    "missing_b0_ratio_or_avw": int((~masks_all["b0_ok"]).sum()),
                    "missing_m0_context_after_b0": int((masks_all["b0_ok"] & (~masks_all["m0_ok"])).sum()),
                },
            )
            n_dated = int(masks_all["ts_ok"].sum())
            manifest_counts[f"{target}_temporal_dated"] = CohortCounts(
                attempted=n_prim,
                completed=n_dated,
                failed=0,
                excluded=n_prim - n_dated,
                exclusion_reasons={"missing_or_unparseable_timestamp": n_prim - n_dated},
            )

            mode_specs = [
                (
                    "primary_optical",
                    masks_all["all_primary"],
                    ["S2_SRF", "S3_SRF", "S2_SRF_l2", "S3_SRF_l2", "HS_401_raw", "HS_401_l2"],
                    ["S2_SRF", "S3_SRF", "S2_SRF_l2", "S3_SRF_l2", "HS_401_l2"],
                ),
                (
                    "all_arm_paired",
                    masks_all["all_arm_ok"],
                    [
                        "B0_ratio",
                        "M0_context",
                        "S2_SRF",
                        "S3_SRF",
                        "S2_SRF_l2",
                        "S3_SRF_l2",
                        "HS_401_raw",
                        "HS_401_l2",
                        "M0_plus_S3",
                        "M0_plus_S3_l2",
                        "M0_plus_HS",
                    ],
                    [
                        "B0_ratio",
                        "M0_context",
                        "S2_SRF",
                        "S3_SRF",
                        "S2_SRF_l2",
                        "S3_SRF_l2",
                        "M0_plus_S3",
                        "M0_plus_S3_l2",
                    ],
                ),
            ]

            for cohort_mode, row_mask, ridge_arms, hgb_arms in mode_specs:
                idx_m = np.flatnonzero(row_mask)
                y_m = y_log_all[idx_m]
                site_m = site_all[idx_m]
                ds_m = ds_all[idx_m]
                wb_m = wb_all[idx_m]
                X_rrs_m = X_rrs_all[idx_m]
                ts_m = ts_all.iloc[idx_m].reset_index(drop=True)

                ckey = compute_cohort_key(
                    inputs_sha256=inputs_sha,
                    target_col=target,
                    wavelength_window_nm=[400.0, 800.0],
                    qc_policy={
                        "cohort_mode": cohort_mode,
                        "require_unflagged": True,
                        "require_all_qc_tested": False,
                        "exclude_optically_derived_chla": target == "Chla",
                        "preserve_negative_rrs": True,
                        "support_rel_tol": SUPPORT_REL_TOL,
                        "n_completed": int(len(idx_m)),
                    },
                    srf_spec=f"S2A_v5({','.join(mats_800['s2_bands'])})|S3A_OLCI({','.join(mats_800['s3_bands'])})",
                )
                cohort_keys_by_target[target][cohort_mode] = ckey

                # Build all 4 splits on this cohort_mode
                split_defs: list[tuple[str, np.ndarray, list[tuple[np.ndarray, np.ndarray]], np.ndarray | None, np.ndarray, bool]] = []
                # (split_name, sub_idx_in_mode, splits, inner_groups, eval_groups_for_metrics, diagnostic_only)
                site_splits = make_group_kfold_splits(site_m, n_splits=5)
                ds_splits = make_group_kfold_splits(ds_m, n_splits=5)
                rand_splits = make_random_kfold_splits(len(idx_m), n_splits=5, seed=SEED)

                split_defs.append(("site_kfold", np.arange(len(idx_m)), site_splits, site_m, site_m, False))
                split_defs.append(("dataset_kfold", np.arange(len(idx_m)), ds_splits, ds_m, ds_m, False))

                dated_local = np.flatnonzero(ts_m.notna().to_numpy())
                ts_dated = ts_m.iloc[dated_local]
                cutoff_80 = ts_dated.quantile(0.80)
                tr_t, te_t = make_temporal_split(
                    ts_dated.astype(str).tolist(), cutoff=cutoff_80.isoformat()
                )
                split_defs.append(
                    ("temporal_80_20", dated_local, [(tr_t, te_t)], site_m[dated_local], site_m[dated_local], False)
                )
                split_defs.append(("random_kfold_diag", np.arange(len(idx_m)), rand_splits, None, site_m, True))

                # Precompute per-fold SAM OOD flags on primary_optical site_kfold and dataset_kfold
                ood_flags_by_split: dict[str, np.ndarray] = {}
                if cohort_mode == "primary_optical":
                    for sp_name, _, sp_list, _, _, _ in split_defs[:2]:
                        is_ood_full = np.zeros(len(idx_m), dtype=bool)
                        for tr_i, te_i in sp_list:
                            ood_res = nearest_neighbor_sam_ood(X_rrs_m[tr_i], X_rrs_m[te_i], ood_quantile=0.95)
                            is_ood_full[te_i] = ood_res["is_ood"]
                        ood_flags_by_split[sp_name] = is_ood_full

                for sp_name, local_sub, sp_list, inner_g, eval_g_all, diag_only in split_defs:
                    y_sp = y_m[local_sub]
                    wb_sp = wb_m[local_sub]

                    est_list: list[tuple[str, list[str]]] = [("Ridge", ridge_arms)]
                    if run_hgb:
                        if cohort_mode == "primary_optical":
                            if sp_name == "random_kfold_diag":
                                hgb_sel = ["S2_SRF", "S3_SRF", "S2_SRF_l2", "S3_SRF_l2"]
                            elif sp_name == "temporal_80_20":
                                hgb_sel = ["S2_SRF", "S3_SRF", "S2_SRF_l2", "S3_SRF_l2", "HS_401_raw", "HS_401_l2"]
                            else:
                                hgb_sel = hgb_arms
                        else:
                            if sp_name == "random_kfold_diag":
                                hgb_sel = []
                            elif sp_name == "temporal_80_20":
                                hgb_sel = hgb_arms + ["HS_401_l2", "M0_plus_HS"]
                            else:
                                hgb_sel = hgb_arms
                        if hgb_sel:
                            est_list.append(("HGB", hgb_sel))

                    for est_name, arm_list in est_list:
                        preds_by_arm: dict[str, tuple[np.ndarray, np.ndarray]] = {}
                        ref_splits = sp_list
                        ref_ckey = ckey

                        for arm in arm_list:
                            assert_matching_cohort_keys(ref_ckey, ckey, context=f"{target}/{cohort_mode}/{sp_name}/{arm}")
                            assert_paired_splits(ref_splits, sp_list)
                            X_arm = arms_all[arm][idx_m][local_sub]

                            t0 = time.perf_counter()
                            eval_idx, preds, chosen = _run_or_load_cell(
                                cache_dir,
                                {
                                    "cohort_key": ckey,
                                    "split": sp_name,
                                    "arm": arm,
                                    "estimator": est_name,
                                    "seed": SEED,
                                },
                                X_arm,
                                y_sp,
                                sp_list,
                                estimator_name=est_name,
                                inner_groups=inner_g,
                                require_outer_disjoint_groups=(sp_name in ("site_kfold", "dataset_kfold")),
                                parallel=parallel if est_name == "HGB" else None,
                            )
                            elapsed = time.perf_counter() - t0
                            preds_by_arm[arm] = (eval_idx, preds)

                            m = compute_regression_metrics(
                                y_sp[eval_idx], preds, groups=eval_g_all[eval_idx]
                            )
                            metrics_rows.append(
                                {
                                    "target": target,
                                    "cohort_mode": cohort_mode,
                                    "cohort_key": ckey,
                                    "split": sp_name,
                                    "diagnostic_only": diag_only,
                                    "estimator": est_name,
                                    "arm": arm,
                                    "n_features": int(X_arm.shape[1]),
                                    "n_eval": int(m["n"]),
                                    "n_groups": int(m["n_groups"]),
                                    "equal_group_log10_rmse": round(float(m["equal_group_log10_rmse"]), 6),
                                    "pooled_log10_rmse": round(float(m["pooled_log10_rmse"]), 6),
                                    "pooled_log10_r2": round(float(m["pooled_log10_r2"]), 6),
                                    "raw_mae": round(float(m["raw_mae"]), 6),
                                    "raw_median_ae": round(float(m["raw_median_ae"]), 6),
                                    "raw_mdsa": round(float(m["raw_mdsa"]), 4),
                                }
                            )
                            print(
                                f"[{target} | {cohort_mode} | {sp_name} | {est_name} | {arm}] "
                                f"eq_rmse={m['equal_group_log10_rmse']:.4f} "
                                f"mdsa={m['raw_mdsa']:.1f}% ({elapsed:.1f}s)",
                                flush=True,
                            )

                            # OOD and water-body stratification on primary_optical site & study splits
                            if cohort_mode == "primary_optical" and sp_name in ood_flags_by_split:
                                ood_arr = ood_flags_by_split[sp_name][eval_idx]
                                for label, mask_s in (("in_domain", ~ood_arr), ("ood", ood_arr)):
                                    if int(mask_s.sum()) >= 1:
                                        sm = compute_regression_metrics(
                                            y_sp[eval_idx][mask_s],
                                            preds[mask_s],
                                            groups=eval_g_all[eval_idx][mask_s],
                                        )
                                        strat_rows.append(
                                            {
                                                "target": target,
                                                "split": sp_name,
                                                "estimator": est_name,
                                                "arm": arm,
                                                "stratum_type": "sam_ood_p95",
                                                "stratum_value": label,
                                                "n": int(sm["n"]),
                                                "n_groups": int(sm["n_groups"]),
                                                "equal_group_log10_rmse": round(float(sm["equal_group_log10_rmse"]), 6),
                                                "pooled_log10_rmse": round(float(sm["pooled_log10_rmse"]), 6),
                                                "raw_mdsa": round(float(sm["raw_mdsa"]), 4),
                                            }
                                        )
                                for code, wb_lbl in WATER_BODY_LABELS.items():
                                    mask_w = wb_sp[eval_idx] == code
                                    if int(mask_w.sum()) >= 1:
                                        sm = compute_regression_metrics(
                                            y_sp[eval_idx][mask_w],
                                            preds[mask_w],
                                            groups=eval_g_all[eval_idx][mask_w],
                                        )
                                        strat_rows.append(
                                            {
                                                "target": target,
                                                "split": sp_name,
                                                "estimator": est_name,
                                                "arm": arm,
                                                "stratum_type": "water_body_type",
                                                "stratum_value": wb_lbl,
                                                "n": int(sm["n"]),
                                                "n_groups": int(sm["n_groups"]),
                                                "equal_group_log10_rmse": round(float(sm["equal_group_log10_rmse"]), 6),
                                                "pooled_log10_rmse": round(float(sm["pooled_log10_rmse"]), 6),
                                                "raw_mdsa": round(float(sm["raw_mdsa"]), 4),
                                            }
                                        )

                        # Paired cluster-bootstrap contrasts (A01: RMSE(arm_a) - RMSE(arm_b), negative favors arm_a)
                        contrast_pairs: list[tuple[str, str, str]] = [
                            ("HS_401_l2_vs_S3_SRF_l2", "HS_401_l2", "S3_SRF_l2"),
                            ("HS_401_l2_vs_S2_SRF_l2", "HS_401_l2", "S2_SRF_l2"),
                            ("S3_SRF_l2_vs_S2_SRF_l2", "S3_SRF_l2", "S2_SRF_l2"),
                            ("HS_401_l2_vs_S3_SRF", "HS_401_l2", "S3_SRF"),
                            ("HS_401_l2_vs_S2_SRF", "HS_401_l2", "S2_SRF"),
                            ("HS_401_raw_vs_S3_SRF", "HS_401_raw", "S3_SRF"),
                            ("S3_SRF_vs_S2_SRF", "S3_SRF", "S2_SRF"),
                            ("HS_401_l2_vs_B0_ratio", "HS_401_l2", "B0_ratio"),
                            ("S3_SRF_l2_vs_B0_ratio", "S3_SRF_l2", "B0_ratio"),
                            ("S3_SRF_vs_B0_ratio", "S3_SRF", "B0_ratio"),
                            ("M0_plus_HS_vs_M0_plus_S3_l2", "M0_plus_HS", "M0_plus_S3_l2"),
                            ("M0_plus_HS_vs_M0_plus_S3", "M0_plus_HS", "M0_plus_S3"),
                            ("M0_plus_HS_vs_M0_context", "M0_plus_HS", "M0_context"),
                            ("M0_plus_S3_l2_vs_M0_context", "M0_plus_S3_l2", "M0_context"),
                            ("HS_401_l2_vs_M0_context", "HS_401_l2", "M0_context"),
                        ]
                        for cname, arm_hs, arm_ref in contrast_pairs:
                            if arm_hs in preds_by_arm and arm_ref in preds_by_arm:
                                idx_hs, p_hs = preds_by_arm[arm_hs]
                                idx_ref, p_ref = preds_by_arm[arm_ref]
                                if not np.array_equal(idx_hs, idx_ref):
                                    raise RuntimeError(f"unpaired eval indices in contrast {cname}")
                                bres = paired_delta_hs_minus_ref(
                                    y_sp[idx_hs],
                                    p_hs,
                                    p_ref,
                                    groups=eval_g_all[idx_hs],
                                    n_bootstrap=n_bootstrap,
                                    seed=SEED,
                                )
                                delta_rows.append(
                                    {
                                        "target": target,
                                        "cohort_mode": cohort_mode,
                                        "cohort_key": ckey,
                                        "split": sp_name,
                                        "diagnostic_only": diag_only,
                                        "estimator": est_name,
                                        "contrast": cname,
                                        "arm_candidate": arm_hs,
                                        "arm_reference": arm_ref,
                                        "sign_convention": "RMSE(candidate) - RMSE(reference); negative favors candidate",
                                        "n_groups": bres["n_groups"],
                                        "n_bootstrap": bres["n_bootstrap"],
                                        "delta_hs_minus_ref": round(float(bres["delta_hs_minus_ref"]), 6),
                                        "ci_low": round(float(bres["ci_low"]), 6),
                                        "ci_high": round(float(bres["ci_high"]), 6),
                                        "p_boot_two_sided": round(float(bres["p_boot_two_sided"]), 6),
                                        "ci_strictly_below_zero": bres["ci_strictly_below_zero"],
                                        "meets_003_magnitude": bres["meets_003_magnitude"],
                                    }
                                )

            # ---- 2. Radiometric error budgets (SRF vs boxcar; retain vs exclude negative Rrs) ----
            site_splits_p = make_group_kfold_splits(site_all, n_splits=5)
            ds_splits_p = make_group_kfold_splits(ds_all, n_splits=5)
            for sp_name, sp_list, grp_arr in (
                ("site_kfold", site_splits_p, site_all),
                ("dataset_kfold", ds_splits_p, ds_all),
            ):
                for est_name in (("Ridge", "HGB") if run_hgb else ("Ridge",)):
                    for sensor_lbl, srf_arm, box_arm in (
                        ("S2A_MSI", "S2_SRF", "S2_boxcar"),
                        ("S3A_OLCI", "S3_SRF", "S3_boxcar"),
                    ):
                        idx_srf, p_srf, _ = _run_or_load_cell(
                            cache_dir,
                            {"budget": "srf_vs_boxcar", "target": target, "split": sp_name, "est": est_name, "arm": srf_arm},
                            arms_all[srf_arm],
                            y_log_all,
                            sp_list,
                            estimator_name=est_name,
                            inner_groups=grp_arr,
                            parallel=parallel if est_name == "HGB" else None,
                        )
                        idx_box, p_box, _ = _run_or_load_cell(
                            cache_dir,
                            {"budget": "srf_vs_boxcar", "target": target, "split": sp_name, "est": est_name, "arm": box_arm},
                            arms_all[box_arm],
                            y_log_all,
                            sp_list,
                            estimator_name=est_name,
                            inner_groups=grp_arr,
                            parallel=parallel if est_name == "HGB" else None,
                        )
                        assert np.array_equal(idx_srf, idx_box)
                        m_srf = compute_regression_metrics(y_log_all[idx_srf], p_srf, groups=grp_arr[idx_srf])
                        m_box = compute_regression_metrics(y_log_all[idx_box], p_box, groups=grp_arr[idx_box])
                        b_del = paired_delta_hs_minus_ref(
                            y_log_all[idx_srf], p_srf, p_box, groups=grp_arr[idx_srf], n_bootstrap=n_bootstrap, seed=SEED
                        )
                        budget_rows.append(
                            {
                                "budget_type": "official_srf_vs_boxcar",
                                "target": target,
                                "split": sp_name,
                                "estimator": est_name,
                                "arm_or_sensor": sensor_lbl,
                                "n_a": int(m_srf["n"]),
                                "n_b": int(m_box["n"]),
                                "rmse_a_label": srf_arm,
                                "rmse_b_label": box_arm,
                                "equal_group_rmse_a": round(float(m_srf["equal_group_log10_rmse"]), 6),
                                "equal_group_rmse_b": round(float(m_box["equal_group_log10_rmse"]), 6),
                                "delta_a_minus_b": round(float(b_del["delta_hs_minus_ref"]), 6),
                                "ci_low": round(float(b_del["ci_low"]), 6),
                                "ci_high": round(float(b_del["ci_high"]), 6),
                            }
                        )

                # Negative-Rrs sensitivity (retain vs exclude negative-Rrs rows, Ridge + low-dim HGB)
                pos_mask = ~coh["has_negative_rrs"]
                idx_pos = np.flatnonzero(pos_mask)
                pos_splits = make_group_kfold_splits(grp_arr[idx_pos], n_splits=5)
                for arm_neg in ("S2_SRF", "S3_SRF", "HS_401_l2"):
                    for est_name in (("Ridge", "HGB") if (run_hgb and arm_neg != "HS_401_l2") else ("Ridge",)):
                        idx_full, p_full, _ = _run_or_load_cell(
                            cache_dir,
                            {"budget": "neg_rrs_full", "target": target, "split": sp_name, "est": est_name, "arm": arm_neg},
                            arms_all[arm_neg],
                            y_log_all,
                            sp_list,
                            estimator_name=est_name,
                            inner_groups=grp_arr,
                            parallel=parallel if est_name == "HGB" else None,
                        )
                        idx_no, p_no, _ = _run_or_load_cell(
                            cache_dir,
                            {"budget": "neg_rrs_excl", "target": target, "split": sp_name, "est": est_name, "arm": arm_neg},
                            arms_all[arm_neg][idx_pos],
                            y_log_all[idx_pos],
                            pos_splits,
                            estimator_name=est_name,
                            inner_groups=grp_arr[idx_pos],
                            parallel=parallel if est_name == "HGB" else None,
                        )
                        m_full = compute_regression_metrics(y_log_all[idx_full], p_full, groups=grp_arr[idx_full])
                        m_no = compute_regression_metrics(y_log_all[idx_pos][idx_no], p_no, groups=grp_arr[idx_pos][idx_no])
                        budget_rows.append(
                            {
                                "budget_type": "retain_vs_exclude_negative_rrs",
                                "target": target,
                                "split": sp_name,
                                "estimator": est_name,
                                "arm_or_sensor": arm_neg,
                                "n_a": int(m_full["n"]),
                                "n_b": int(m_no["n"]),
                                "rmse_a_label": "retain_negative_rrs",
                                "rmse_b_label": "exclude_negative_rrs",
                                "equal_group_rmse_a": round(float(m_full["equal_group_log10_rmse"]), 6),
                                "equal_group_rmse_b": round(float(m_no["equal_group_log10_rmse"]), 6),
                                "delta_a_minus_b": round(
                                    float(m_full["equal_group_log10_rmse"] - m_no["equal_group_log10_rmse"]), 6
                                ),
                                "ci_low": math.nan,
                                "ci_high": math.nan,
                            }
                        )

        # ---- 3. A10: 400-700 nm Lake Geneva OdermattD_CH_Eawag circularity stress test ----
        coh_700_excl = build_target_cohort(
            tables, target_col="Chla", min_nm=400, max_nm=700, exclude_optically_derived_chla=True
        )
        coh_700_incl = build_target_cohort(
            tables, target_col="Chla", min_nm=400, max_nm=700, exclude_optically_derived_chla=False
        )
        manifest_counts["Chla_400_700_exclude_optical"] = coh_700_excl["counts"]
        manifest_counts["Chla_400_700_include_optical"] = coh_700_incl["counts"]

        def _arms_700(X700: np.ndarray) -> dict[str, np.ndarray]:
            norms7 = np.linalg.norm(X700, axis=1)
            return {
                "S2_SRF_400_700": X700 @ mats_700["W_s2"],
                "S3_SRF_400_700": X700 @ mats_700["W_s3"],
                "HS_301_l2": np.column_stack([normalize_unit_l2(X700), np.log10(norms7)]),
            }

        arms_700_excl = _arms_700(coh_700_excl["X_rrs"])
        arms_700_incl = _arms_700(coh_700_incl["X_rrs"])
        y7_excl = np.log10(coh_700_excl["y"])
        y7_incl = np.log10(coh_700_incl["y"])

        for sp_name, g_excl, g_incl in (
            ("site_kfold", coh_700_excl["site_groups"], coh_700_incl["site_groups"]),
            ("dataset_kfold", coh_700_excl["dataset_ids"], coh_700_incl["dataset_ids"]),
        ):
            sp_excl = make_group_kfold_splits(g_excl, n_splits=5)
            sp_incl = make_group_kfold_splits(g_incl, n_splits=5)
            for arm7 in ("S2_SRF_400_700", "S3_SRF_400_700", "HS_301_l2"):
                est_700 = ("Ridge", "HGB") if (run_hgb and arm7 != "HS_301_l2") else ("Ridge",)
                for est_name in est_700:
                    i_ex, p_ex, _ = _run_or_load_cell(
                        cache_dir,
                        {"budget": "a10_700_excl", "split": sp_name, "est": est_name, "arm": arm7},
                        arms_700_excl[arm7],
                        y7_excl,
                        sp_excl,
                        estimator_name=est_name,
                        inner_groups=g_excl,
                        parallel=parallel if est_name == "HGB" else None,
                    )
                    i_in, p_in, _ = _run_or_load_cell(
                        cache_dir,
                        {"budget": "a10_700_incl", "split": sp_name, "est": est_name, "arm": arm7},
                        arms_700_incl[arm7],
                        y7_incl,
                        sp_incl,
                        estimator_name=est_name,
                        inner_groups=g_incl,
                        parallel=parallel if est_name == "HGB" else None,
                    )
                    m_ex = compute_regression_metrics(y7_excl[i_ex], p_ex, groups=g_excl[i_ex])
                    m_in = compute_regression_metrics(y7_incl[i_in], p_in, groups=g_incl[i_in])
                    budget_rows.append(
                        {
                            "budget_type": "a10_400_700_odermatt_circularity",
                            "target": "Chla",
                            "split": sp_name,
                            "estimator": est_name,
                            "arm_or_sensor": arm7,
                            "n_a": int(m_ex["n"]),
                            "n_b": int(m_in["n"]),
                            "rmse_a_label": "exclude_OdermattD_CH_Eawag",
                            "rmse_b_label": "include_OdermattD_CH_Eawag",
                            "equal_group_rmse_a": round(float(m_ex["equal_group_log10_rmse"]), 6),
                            "equal_group_rmse_b": round(float(m_in["equal_group_log10_rmse"]), 6),
                            "delta_a_minus_b": round(
                                float(m_ex["equal_group_log10_rmse"] - m_in["equal_group_log10_rmse"]), 6
                            ),
                            "ci_low": math.nan,
                            "ci_high": math.nan,
                        }
                    )

    metrics_df = pd.DataFrame(metrics_rows)
    deltas_df = pd.DataFrame(delta_rows)
    budget_df = pd.DataFrame(budget_rows)
    strat_df = pd.DataFrame(strat_rows)

    # Apply Holm-Bonferroni adjustment within each (cohort_mode, split, contrast) family across targets x estimators
    if not deltas_df.empty:
        deltas_df["p_holm"] = np.nan
        deltas_df["holm_significant_005"] = False
        for (_, _, _), grp in deltas_df.groupby(["cohort_mode", "split", "contrast"]):
            adj = holm_bonferroni_adjust(grp["p_boot_two_sided"].tolist())
            deltas_df.loc[grp.index, "p_holm"] = [round(v, 6) for v in adj]
            deltas_df.loc[grp.index, "holm_significant_005"] = [bool(v < 0.05) for v in adj]

    csv_paths = {
        "metrics.csv": out_dir / "metrics.csv",
        "paired_deltas.csv": out_dir / "paired_deltas.csv",
        "radiometric_budget.csv": out_dir / "radiometric_budget.csv",
        "ood_and_waterbody_stratified.csv": out_dir / "ood_and_waterbody_stratified.csv",
    }
    metrics_df.to_csv(csv_paths["metrics.csv"], index=False, lineterminator="\n")
    deltas_df.to_csv(csv_paths["paired_deltas.csv"], index=False, lineterminator="\n")
    budget_df.to_csv(csv_paths["radiometric_budget.csv"], index=False, lineterminator="\n")
    strat_df.to_csv(csv_paths["ood_and_waterbody_stratified.csv"], index=False, lineterminator="\n")

    fig_path = out_dir / "hs_r02_summary_figure.png"
    render_key = make_summary_figure(metrics_df, deltas_df, budget_df, strat_df, fig_path)

    # Evaluate formal §5 decision rule automatically from matched-preprocessing primary contrasts
    decision_summary: dict[str, Any] = {}
    for target in TARGETS:
        for est_name in (("Ridge", "HGB") if run_hgb else ("Ridge",)):
            pass_both_splits = True
            detail: dict[str, Any] = {}
            s3_contrast = "HS_401_l2_vs_S3_SRF_l2" if est_name == "Ridge" else "HS_401_l2_vs_S3_SRF"
            for sp in ("site_kfold", "dataset_kfold"):
                row_s3 = deltas_df[
                    (deltas_df["target"] == target)
                    & (deltas_df["cohort_mode"] == "primary_optical")
                    & (deltas_df["split"] == sp)
                    & (deltas_df["estimator"] == est_name)
                    & (deltas_df["contrast"] == s3_contrast)
                ]
                row_s3_l2 = deltas_df[
                    (deltas_df["target"] == target)
                    & (deltas_df["cohort_mode"] == "primary_optical")
                    & (deltas_df["split"] == sp)
                    & (deltas_df["estimator"] == est_name)
                    & (deltas_df["contrast"] == "HS_401_l2_vs_S3_SRF_l2")
                ]
                row_b0 = deltas_df[
                    (deltas_df["target"] == target)
                    & (deltas_df["cohort_mode"] == "all_arm_paired")
                    & (deltas_df["split"] == sp)
                    & (deltas_df["estimator"] == est_name)
                    & (deltas_df["contrast"] == "HS_401_l2_vs_B0_ratio")
                ]
                ok_s3 = bool(
                    len(row_s3) == 1
                    and row_s3["ci_strictly_below_zero"].iloc[0]
                    and row_s3["meets_003_magnitude"].iloc[0]
                )
                ok_b0 = bool(
                    len(row_b0) == 1
                    and row_b0["ci_strictly_below_zero"].iloc[0]
                    and row_b0["meets_003_magnitude"].iloc[0]
                )
                detail[sp] = {
                    "primary_s3_contrast": s3_contrast,
                    "delta_vs_S3_primary": None if len(row_s3) != 1 else float(row_s3["delta_hs_minus_ref"].iloc[0]),
                    "ci_vs_S3_primary": None
                    if len(row_s3) != 1
                    else [float(row_s3["ci_low"].iloc[0]), float(row_s3["ci_high"].iloc[0])],
                    "delta_vs_S3_l2": None if len(row_s3_l2) != 1 else float(row_s3_l2["delta_hs_minus_ref"].iloc[0]),
                    "ci_vs_S3_l2": None
                    if len(row_s3_l2) != 1
                    else [float(row_s3_l2["ci_low"].iloc[0]), float(row_s3_l2["ci_high"].iloc[0])],
                    "delta_vs_B0": None if len(row_b0) != 1 else float(row_b0["delta_hs_minus_ref"].iloc[0]),
                    "ci_vs_B0": None
                    if len(row_b0) != 1
                    else [float(row_b0["ci_low"].iloc[0]), float(row_b0["ci_high"].iloc[0])],
                    "passes_s3_003": ok_s3,
                    "passes_b0_003": None if len(row_b0) != 1 else ok_b0,
                }
                pass_both_splits = pass_both_splits and ok_s3 and (ok_b0 if len(row_b0) == 1 else True)
            decision_summary[f"{target}_{est_name}"] = {
                "interesting_supported": pass_both_splits,
                "splits": detail,
            }

    runtime_info = collect_runtime_info(
        packages=(
            "colour-science",
            "h5py",
            "hydrospectral",
            "joblib",
            "jsonschema",
            "matplotlib",
            "numpy",
            "pandas",
            "pyyaml",
            "scikit-learn",
            "scipy",
        )
    )
    output_sha = {name: sha256_file(path) for name, path in csv_paths.items()}
    output_sha["hs_r02_summary_figure.png"] = sha256_file(fig_path)

    manifest = build_manifest(
        experiment_id="HS-R02",
        title="Official ESA S2A/S3A SRF compression vs. full 1 nm hyperspectral bio-optical retrieval on GLORIA",
        status="exploratory",
        script_path=SCRIPT_REL_PATH,
        script_sha256=sha256_file(Path(__file__)),
        inputs=inputs_sha,
        counts=manifest_counts,
        units={
            "Chla": "ug/L",
            "TSS": "mg/L",
            "aCDOM440": "m^-1",
            "Rrs": "sr^-1",
            "equal_group_log10_rmse": "log10(target_unit)",
            "pooled_log10_rmse": "log10(target_unit)",
            "raw_mae": "target_unit",
            "raw_median_ae": "target_unit",
            "raw_mdsa": "percent",
            "sam_rad": "rad",
        },
        git_commit=git_info["git_commit"],
        git_tree_clean=git_info["git_tree_clean"],
        cohort_key=cohort_keys_by_target["Chla"]["primary_optical"],
        render_key=render_key,
        random_seed=SEED,
        pairing_rule=(
            "Byte-identical CohortCounts, cohort_key, and fold index arrays verified via "
            "assert_matching_cohort_keys and assert_paired_splits across all compared arms"
        ),
        prior_exposure=(
            "Disclosed in pre-registrations/2026-11-26-hs-r02-official-srf-retrieval.md "
            "(2026-11-26 preflight + 2026-11-28 ESA SRF support audit and zero-leakage GLORIA dataset EDA; "
            "zero retrieval models fitted prior to 2026-11-28 A01-A10 amendment commit)"
        ),
        extra={
            "bootstrap_sign_convention": "RMSE(candidate) - RMSE(reference); negative values favor candidate (HS_401)",
            "cohort_keys_by_target": cohort_keys_by_target,
            "decision_rule_summary": decision_summary,
            "eligible_s2a_bands_400_800": mats_800["s2_bands"],
            "eligible_s3a_bands_400_800": mats_800["s3_bands"],
            "eligible_s2a_bands_400_700": mats_700["s2_bands"],
            "eligible_s3a_bands_400_700": mats_700["s3_bands"],
            "hgb_inner_cv_folds": 3,
            "output_sha256": output_sha,
            "ridge_inner_cv_folds": 5,
            "script_in_commit": git_info["script_in_commit"],
            "support_rel_tol": SUPPORT_REL_TOL,
        },
        runtime=runtime_info,
    )
    write_manifest(manifest, out_dir / "manifest.json")
    print(f"HS-R02 complete in {time.perf_counter() - t_start:.1f}s -> {out_dir}", flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pre-registered HS-R02 benchmark on GLORIA.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--n-jobs", type=int, default=min(14, max(1, (os.cpu_count() or 4) - 2)))
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--ridge-only", action="store_true", help="Run Ridge only (diagnostic/smoke mode)")
    args = parser.parse_args()

    paths = resolve_local_inputs(REPO_ROOT)
    run_benchmark(
        gloria_zip=paths["gloria_2022_zip"],
        s2_xlsx=paths["esa_s2_msi_srf_xlsx"],
        s3_nc4=paths["esa_s3a_olci_srf_nc4"],
        out_dir=args.out_dir,
        repo_root=REPO_ROOT,
        expected_gloria_sha256=load_manifest_sha256(REPO_ROOT, "manifests/sources/gloria-2022.yaml"),
        expected_s2_sha256=load_manifest_sha256(REPO_ROOT, "manifests/sources/esa-s2a-msi-srf.yaml"),
        expected_s3_sha256=load_manifest_sha256(REPO_ROOT, "manifests/sources/esa-s3a-olci-srf.yaml"),
        n_jobs=args.n_jobs,
        run_hgb=not args.ridge_only,
        cache_dir=args.cache_dir,
    )


if __name__ == "__main__":
    main()
