"""Leakage-resistant validation splitters, grouped metrics, bootstrap CIs, and OOD diagnostics.

Enforces AGENTS.md rule 3:
- Zero group leakage across train/test splits (`Country|Site_name`, `Dataset_ID`,
  or chronological temporal holdouts).
- Identical observation pairing across compared feature arms (e.g., hyperspectral
  vs. official SRF multispectral; M0 vs. M1 vs. M2 vs. M3).
- Whole-group cluster bootstrapping for paired metric deltas rather than treating
  repeated observations from the same waterbody as independent.
- Spectral-angle nearest-neighbour applicability-domain / OOD distance diagnostics.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from hydrospectral.radiometry import spectral_angle_rad


class SplitLeakageError(ValueError):
    """Raised when a split violates group disjointness, temporal ordering, or pairing."""


def _validate_group_labels(groups: ArrayLike, *, expected_len: int | None = None) -> np.ndarray:
    g = np.asarray(groups, dtype=object)
    if g.ndim != 1 or g.size == 0:
        raise SplitLeakageError("groups must be a non-empty 1D array")
    if expected_len is not None and g.size != expected_len:
        raise SplitLeakageError(
            f"groups length {g.size} does not match expected length {expected_len}"
        )
    if pd.isna(g).any():
        raise SplitLeakageError("groups must not contain null/NaN labels")
    labels = np.array([str(x) for x in g], dtype=object)
    if any(not s.strip() for s in labels):
        raise SplitLeakageError("groups must not contain empty/whitespace-only labels")
    return labels


def assert_disjoint_groups(
    groups: ArrayLike,
    train_idx: ArrayLike,
    test_idx: ArrayLike,
) -> None:
    """Assert valid bounds, zero row overlap, non-null labels, and zero group overlap."""
    g = np.asarray(groups, dtype=object)
    if g.ndim != 1 or g.size == 0:
        raise SplitLeakageError("groups must be a non-empty 1D array")

    tr = np.asarray(train_idx, dtype=int)
    te = np.asarray(test_idx, dtype=int)
    if tr.ndim != 1 or te.ndim != 1 or tr.size == 0 or te.size == 0:
        raise SplitLeakageError("train_idx and test_idx must both be non-empty 1D integer arrays")

    n = g.size
    if np.any(tr < 0) or np.any(tr >= n) or np.any(te < 0) or np.any(te >= n):
        raise SplitLeakageError(
            f"train_idx/test_idx out of bounds for {n} observations (negative indices are disallowed)"
        )

    if pd.isna(g[tr]).any() or pd.isna(g[te]).any():
        raise SplitLeakageError("train/test group labels must not contain null/NaN values")

    row_overlap = np.intersect1d(tr, te)
    if row_overlap.size > 0:
        raise SplitLeakageError(f"row leakage detected: {row_overlap.size} overlapping row(s)")

    tr_labels = {str(x) for x in g[tr].tolist()}
    te_labels = {str(x) for x in g[te].tolist()}
    group_overlap = tr_labels & te_labels
    if group_overlap:
        sample = sorted(group_overlap)[:5]
        raise SplitLeakageError(
            f"group leakage detected across train/test split: {sample}"
        )


def assert_paired_splits(
    splits_a: Sequence[tuple[np.ndarray, np.ndarray]],
    splits_b: Sequence[tuple[np.ndarray, np.ndarray]],
) -> None:
    """Assert two arms use byte-identical train/test index pairings on every fold."""
    if len(splits_a) != len(splits_b) or len(splits_a) == 0:
        raise SplitLeakageError(
            f"split count mismatch: {len(splits_a)} vs {len(splits_b)}"
        )
    for fold, ((tr_a, te_a), (tr_b, te_b)) in enumerate(zip(splits_a, splits_b, strict=True)):
        if not (np.array_equal(tr_a, tr_b) and np.array_equal(te_a, te_b)):
            raise SplitLeakageError(
                f"fold {fold} indices are not identically paired across compared arms"
            )


def make_group_kfold_splits(
    groups: ArrayLike,
    *,
    n_splits: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic greedy balanced GroupKFold with explicit zero-leakage assertions.

    Assigns whole groups (largest group first, lexicographical tie-break) to the
    fold with the fewest assigned observations, matching scikit-learn's GroupKFold
    balancing strategy while refusing missing/null group labels or fewer than
    `n_splits` distinct groups.
    """
    if isinstance(n_splits, bool) or not isinstance(n_splits, int) or n_splits < 2:
        raise SplitLeakageError(f"n_splits must be an integer >= 2, got {n_splits!r}")

    labels = _validate_group_labels(groups)
    group_to_indices: dict[str, list[int]] = {}
    for idx, label in enumerate(labels):
        group_to_indices.setdefault(label, []).append(idx)

    if len(group_to_indices) < n_splits:
        raise SplitLeakageError(
            f"cannot form {n_splits} group folds with only {len(group_to_indices)} distinct group(s)"
        )

    ordered_groups = sorted(
        group_to_indices.items(),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    fold_bins: list[list[int]] = [[] for _ in range(n_splits)]
    fold_counts = [0] * n_splits

    for _, indices in ordered_groups:
        target_fold = int(np.argmin(fold_counts))
        fold_bins[target_fold].extend(indices)
        fold_counts[target_fold] += len(indices)

    all_idx = np.arange(labels.size, dtype=int)
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        te = np.array(sorted(fold_bins[k]), dtype=int)
        tr = np.setdiff1d(all_idx, te, assume_unique=True)
        assert_disjoint_groups(labels, tr, te)
        splits.append((tr, te))

    return splits


def make_temporal_split(
    timestamps: ArrayLike,
    *,
    cutoff: str | pd.Timestamp,
    groups: ArrayLike | None = None,
    require_disjoint_groups: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a strictly causal chronological split: train < cutoff, test >= cutoff.

    Supports mixed ISO-8601 date and datetime strings; refuses NaT/unparseable
    timestamps or cutoffs so missing dates cannot silently leak future samples.
    """
    raw_series = pd.Series(timestamps)
    ts = pd.to_datetime(raw_series, format="ISO8601", errors="coerce", utc=True)
    if ts.isna().any():
        raise SplitLeakageError(
            f"timestamps contain {int(ts.isna().sum())} unparseable/NaT value(s)"
        )
    cut = pd.to_datetime(cutoff, errors="coerce", utc=True)
    if pd.isna(cut):
        raise SplitLeakageError(f"invalid cutoff timestamp: {cutoff!r}")

    tr = np.flatnonzero((ts < cut).to_numpy())
    te = np.flatnonzero((ts >= cut).to_numpy())
    if tr.size == 0 or te.size == 0:
        raise SplitLeakageError(
            f"temporal cutoff {cut.isoformat()} produced empty split (train={tr.size}, test={te.size})"
        )
    if ts.iloc[tr].max() >= ts.iloc[te].min():
        raise SplitLeakageError("temporal leakage: max(train timestamp) >= min(test timestamp)")

    if require_disjoint_groups:
        if groups is None:
            raise SplitLeakageError("groups must be provided when require_disjoint_groups=True")
        assert_disjoint_groups(groups, tr, te)
    return tr, te


def compute_regression_metrics(
    truth_log10: ArrayLike,
    pred_log10: ArrayLike,
    *,
    groups: ArrayLike,
) -> dict[str, float | int]:
    """Compute pooled and equal-group log10 RMSE, pooled log10 R^2, and raw-scale MAE/MdAE."""
    t = np.asarray(truth_log10, dtype=float)
    p = np.asarray(pred_log10, dtype=float)
    if not (t.ndim == 1 and t.shape == p.shape and t.size > 0):
        raise SplitLeakageError("truth_log10 and pred_log10 must be non-empty 1D arrays of equal length")
    if not (np.isfinite(t).all() and np.isfinite(p).all()):
        raise SplitLeakageError("truth_log10 and pred_log10 must contain only finite values")
    g = _validate_group_labels(groups, expected_len=t.size)

    sq_err = (p - t) ** 2
    pooled_log_rmse = float(np.sqrt(np.mean(sq_err)))

    ss_res = float(np.sum(sq_err))
    ss_tot = float(np.sum((t - np.mean(t)) ** 2))
    pooled_log_r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0.0 else float("nan")

    df = pd.DataFrame({"group": g, "sq_err": sq_err})
    equal_group_log_rmse = float(np.sqrt(df.groupby("group")["sq_err"].mean().mean()))

    raw_abs_err = np.abs((10.0 ** p) - (10.0 ** t))
    # Median Symmetric Accuracy (Morley et al. 2018): 100 * (exp(median(|ln(y_hat / y)|)) - 1)
    # In log10 space, |ln(y_hat / y)| = |p - t| * ln(10), so exp(median * ln(10)) = 10**median(|p - t|).
    med_abs_log10_err = float(np.median(np.abs(p - t)))
    raw_mdsa = float(100.0 * (10.0 ** med_abs_log10_err - 1.0))
    return {
        "n": int(t.size),
        "n_groups": int(df["group"].nunique()),
        "pooled_log10_rmse": pooled_log_rmse,
        "equal_group_log10_rmse": equal_group_log_rmse,
        "pooled_log10_r2": pooled_log_r2,
        "raw_mae": float(np.mean(raw_abs_err)),
        "raw_median_ae": float(np.median(raw_abs_err)),
        "raw_mdsa": raw_mdsa,
    }


def paired_group_bootstrap_delta(
    truth_log10: ArrayLike,
    pred_a_log10: ArrayLike,
    pred_b_log10: ArrayLike,
    *,
    groups: ArrayLike,
    n_bootstrap: int = 1000,
    seed: int = 2026,
    ci_level: float = 0.95,
) -> dict[str, float | int]:
    """Whole-group cluster bootstrap CI for delta = equal_group_log10_rmse(B) - equal_group_log10_rmse(A).

    Resamples whole groups with replacement (never independent rows) so repeated
    observations within a waterbody or study do not artificially shrink CIs.
    Positive delta means Arm A has lower equal-group log10 RMSE than Arm B.
    Requires finite truth and predictions for both arms and non-null group labels
    so paired-observation correspondence is never silently broken by NaNs.
    """
    if isinstance(n_bootstrap, bool) or not isinstance(n_bootstrap, int) or n_bootstrap < 100:
        raise SplitLeakageError(f"n_bootstrap must be an integer >= 100, got {n_bootstrap!r}")
    if not (0.0 < ci_level < 1.0):
        raise SplitLeakageError(f"ci_level must be in (0, 1), got {ci_level}")

    t = np.asarray(truth_log10, dtype=float)
    pa = np.asarray(pred_a_log10, dtype=float)
    pb = np.asarray(pred_b_log10, dtype=float)
    if not (t.ndim == 1 and t.shape == pa.shape == pb.shape and t.size > 0):
        raise SplitLeakageError("all input arrays must be non-empty 1D arrays of matching length")
    if not (np.isfinite(t).all() and np.isfinite(pa).all() and np.isfinite(pb).all()):
        raise SplitLeakageError(
            "truth_log10, pred_a_log10, and pred_b_log10 must be finite across all paired observations"
        )
    g = _validate_group_labels(groups, expected_len=t.size)

    df = pd.DataFrame(
        {
            "group": g,
            "sq_a": (pa - t) ** 2,
            "sq_b": (pb - t) ** 2,
        }
    )
    per_group = df.groupby("group", sort=True)[["sq_a", "sq_b"]].mean()
    n_groups = len(per_group)
    if n_groups < 2:
        raise SplitLeakageError("need at least 2 distinct groups for cluster bootstrap")

    mse_a = per_group["sq_a"].to_numpy(dtype=float)
    mse_b = per_group["sq_b"].to_numpy(dtype=float)
    observed = float(np.sqrt(mse_b.mean()) - np.sqrt(mse_a.mean()))

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_groups, size=(n_bootstrap, n_groups))
    boot_delta = np.sqrt(mse_b[draws].mean(axis=1)) - np.sqrt(mse_a[draws].mean(axis=1))

    alpha = 0.5 * (1.0 - ci_level)
    ci_low, ci_high = np.quantile(boot_delta, [alpha, 1.0 - alpha])
    return {
        "n_groups": int(n_groups),
        "n_bootstrap": int(n_bootstrap),
        "observed_delta_b_minus_a": observed,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "ci_level": float(ci_level),
    }


def nearest_neighbor_sam_ood(
    train_spectra: ArrayLike,
    query_spectra: ArrayLike,
    *,
    ood_quantile: float = 0.95,
    atol_rad: float = 1e-12,
) -> dict[str, Any]:
    """Compute nearest-neighbour Spectral Angle Mapper (SAM) OOD diagnostics.

    Derives the applicability-domain threshold strictly from leave-one-out
    nearest-neighbour SAM distances inside `train_spectra` (no peeking at
    `query_spectra`), then flags query spectra exceeding `threshold + atol_rad`
    (default `1e-12` rad absorbs float64 unit-normalization rounding for exact
    collinear duplicates).
    Note: when `train_spectra` contains replicate spectra from the same site,
    row-level LOO distances can be artificially small; deduplicate or average
    site replicates when calibrating site-level applicability thresholds.
    """
    if not (0.0 < ood_quantile <= 1.0):
        raise SplitLeakageError(f"ood_quantile must be in (0, 1], got {ood_quantile}")
    if not np.isfinite(atol_rad) or atol_rad < 0.0:
        raise SplitLeakageError(f"atol_rad must be finite and >= 0, got {atol_rad}")

    tr = np.asarray(train_spectra, dtype=float)
    qu = np.asarray(query_spectra, dtype=float)
    if tr.ndim != 2 or qu.ndim != 2 or tr.shape[0] < 2 or qu.shape[0] < 1:
        raise SplitLeakageError("train_spectra must have >= 2 rows and query_spectra >= 1 row")

    train_dist = spectral_angle_rad(tr, tr)
    np.fill_diagonal(train_dist, np.inf)
    if not np.isfinite(np.min(train_dist, axis=1)).all():
        raise SplitLeakageError("train_spectra contains zero-norm or non-finite rows")
    train_nn = np.min(train_dist, axis=1)
    threshold_rad = float(np.quantile(train_nn, ood_quantile))

    query_dist = spectral_angle_rad(qu, tr)
    query_nn = np.full(qu.shape[0], np.nan, dtype=float)
    query_idx = np.full(qu.shape[0], -1, dtype=int)
    is_ood = np.ones(qu.shape[0], dtype=bool)

    for i in range(qu.shape[0]):
        row = query_dist[i]
        if np.isfinite(row).any():
            best = int(np.nanargmin(row))
            query_idx[i] = best
            query_nn[i] = float(row[best])
            is_ood[i] = bool(query_nn[i] > threshold_rad + atol_rad)

    return {
        "train_nn_sam_rad": train_nn,
        "threshold_sam_rad": threshold_rad,
        "query_nn_sam_rad": query_nn,
        "nearest_train_index": query_idx,
        "is_ood": is_ood,
    }
