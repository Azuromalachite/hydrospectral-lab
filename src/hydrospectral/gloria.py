"""ID-safe GLORIA archive loader, QC semantics, and circularity-aware cohort builder.

Invariants enforced (AGENTS.md rule 2):
- Join GLORIA tables strictly on `GLORIA_ID` (one-to-one), never row position.
- Never silently clip negative Rrs values to zero; surface negative-Rrs diagnostics.
- Distinguish missing QC flags (NaN = unmeasured wavelength range) from 0 (passed)
  and 1 (flagged), while rejecting malformed non-binary QC flag values.
- Keep corrected `Chla` strictly separate from uncorrected chlorophyll + phaeopigment
  columns, and isolate optically derived Chla targets (e.g., Lake Geneva Thetis)
  via metadata markers and/or explicit `Dataset_ID` lists.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hydrospectral.provenance import CohortCounts, sha256_file
from hydrospectral.thresholds import get_threshold, load_qc_thresholds

GLORIA_ID_COL = "GLORIA_ID"
ALLOWED_TARGETS = ("Chla", "TSS", "aCDOM440", "Secchi_depth", "Turbidity")
TARGET_UNITS = {
    "Chla": "ug/L",
    "TSS": "mg/L",
    "aCDOM440": "m^-1",
    "Secchi_depth": "m",
    "Turbidity": "NTU",
}
QC_FLAG_COLUMNS = (
    "Baseline_shift",
    "Negative_uv_slope",
    "Noisy_blue",
    "Noisy_red",
    "Oxygen_signal",
    "QWIP_fail",
    "Suspect",
)


class GloriaDataError(ValueError):
    """Raised when GLORIA tables violate ID uniqueness, join, QC, or target invariants."""


def _validate_id_column(df: pd.DataFrame, *, table_name: str, id_col: str) -> pd.Series:
    if id_col not in df.columns:
        raise GloriaDataError(f"{table_name} missing required ID column {id_col!r}")
    if df[id_col].isna().any():
        raise GloriaDataError(f"{table_name} contains null values in {id_col!r}")
    ids = df[id_col].astype(str)
    dups = ids[ids.duplicated()].tolist()
    if dups:
        raise GloriaDataError(
            f"{table_name} contains duplicate {id_col!r} value(s): {dups[:5]}"
        )
    return ids


@dataclass(frozen=True)
class GloriaTables:
    """Joined GLORIA tables guaranteed structurally row-aligned by GLORIA_ID."""

    meta: pd.DataFrame
    rrs: pd.DataFrame
    qc_flags: pd.DataFrame | None
    archive_sha256: str | None
    id_col: str = GLORIA_ID_COL

    def __post_init__(self) -> None:
        meta_ids = _validate_id_column(self.meta, table_name="meta", id_col=self.id_col)
        rrs_ids = _validate_id_column(self.rrs, table_name="rrs", id_col=self.id_col)
        if len(meta_ids) != len(rrs_ids) or not (meta_ids.to_numpy() == rrs_ids.to_numpy()).all():
            raise GloriaDataError(
                "GloriaTables.meta and GloriaTables.rrs are not row-aligned by GLORIA_ID"
            )
        if self.qc_flags is not None:
            qc_ids = _validate_id_column(self.qc_flags, table_name="qc_flags", id_col=self.id_col)
            if len(meta_ids) != len(qc_ids) or not (meta_ids.to_numpy() == qc_ids.to_numpy()).all():
                raise GloriaDataError(
                    "GloriaTables.qc_flags is not row-aligned with GloriaTables.meta by GLORIA_ID"
                )


def _read_csv_from_zip(zf: zipfile.ZipFile, filename: str) -> pd.DataFrame:
    matches = [name for name in zf.namelist() if name.rsplit("/", 1)[-1] == filename]
    if len(matches) != 1:
        raise GloriaDataError(
            f"expected exactly 1 entry named {filename!r} in zip archive, found {matches}"
        )
    text = zf.read(matches[0]).decode("utf-8")
    return pd.read_csv(io.StringIO(text))


def _read_csv_from_dir(root: Path, filename: str) -> pd.DataFrame:
    matches = sorted(root.rglob(filename))
    if len(matches) != 1:
        raise GloriaDataError(
            f"expected exactly 1 file named {filename!r} under {root}, found {matches}"
        )
    return pd.read_csv(matches[0], encoding="utf-8")


def load_gloria_tables(
    source_path: Path,
    *,
    expected_sha256: str | None = None,
    include_qc_flags: bool = True,
    id_col: str = GLORIA_ID_COL,
) -> GloriaTables:
    """Load GLORIA metadata, Rrs, and optional QC flags aligned strictly by GLORIA_ID."""
    target = Path(source_path)
    if not target.exists():
        raise GloriaDataError(f"GLORIA path not found: {target}")

    archive_digest: str | None = None
    if target.is_file():
        archive_digest = sha256_file(target)
        if expected_sha256 is not None and archive_digest != expected_sha256:
            raise GloriaDataError(
                f"GLORIA archive SHA-256 mismatch: expected {expected_sha256}, got {archive_digest}"
            )
        with zipfile.ZipFile(target, "r") as zf:
            meta = _read_csv_from_zip(zf, "GLORIA_meta_and_lab.csv")
            rrs = _read_csv_from_zip(zf, "GLORIA_Rrs.csv")
            qc_flags = _read_csv_from_zip(zf, "GLORIA_qc_flags.csv") if include_qc_flags else None
    elif target.is_dir():
        if expected_sha256 is not None:
            raise GloriaDataError(
                "expected_sha256 cannot be verified against an extracted directory; "
                "pass the original GLORIA zip archive or omit expected_sha256"
            )
        meta = _read_csv_from_dir(target, "GLORIA_meta_and_lab.csv")
        rrs = _read_csv_from_dir(target, "GLORIA_Rrs.csv")
        qc_flags = _read_csv_from_dir(target, "GLORIA_qc_flags.csv") if include_qc_flags else None
    else:
        raise GloriaDataError(f"unsupported GLORIA source path: {target}")

    meta_ids_s = _validate_id_column(meta, table_name="GLORIA_meta_and_lab.csv", id_col=id_col)
    rrs_ids_s = _validate_id_column(rrs, table_name="GLORIA_Rrs.csv", id_col=id_col)

    meta_ids = set(meta_ids_s)
    rrs_ids = set(rrs_ids_s)
    if meta_ids != rrs_ids:
        only_meta = sorted(meta_ids - rrs_ids)[:5]
        only_rrs = sorted(rrs_ids - meta_ids)[:5]
        raise GloriaDataError(
            f"GLORIA_ID mismatch between metadata and Rrs tables "
            f"(only_in_meta={only_meta}, only_in_rrs={only_rrs})"
        )

    # Align strictly by GLORIA_ID (never trusting input row ordering).
    canonical_order = meta_ids_s
    meta_aligned = meta.copy()
    meta_aligned[id_col] = canonical_order
    rrs_aligned = (
        rrs.assign(**{id_col: rrs_ids_s})
        .set_index(id_col)
        .loc[canonical_order]
        .reset_index()
    )

    qc_aligned: pd.DataFrame | None = None
    if qc_flags is not None:
        qc_ids_s = _validate_id_column(qc_flags, table_name="GLORIA_qc_flags.csv", id_col=id_col)
        if set(qc_ids_s) != meta_ids:
            raise GloriaDataError("GLORIA_ID mismatch between metadata and QC flags tables")
        qc_aligned = (
            qc_flags.assign(**{id_col: qc_ids_s})
            .set_index(id_col)
            .loc[canonical_order]
            .reset_index()
        )

    return GloriaTables(
        meta=meta_aligned.reset_index(drop=True),
        rrs=rrs_aligned.reset_index(drop=True),
        qc_flags=None if qc_aligned is None else qc_aligned.reset_index(drop=True),
        archive_sha256=archive_digest,
        id_col=id_col,
    )


def extract_rrs_matrix(
    rrs_df: pd.DataFrame,
    *,
    min_nm: int | None = None,
    max_nm: int | None = None,
    step_nm: int = 1,
    config: Mapping[str, Any] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract numeric Rrs matrix (sr^-1) on [min_nm, max_nm] without clipping negatives."""
    if isinstance(step_nm, bool) or not isinstance(step_nm, int) or step_nm < 1:
        raise GloriaDataError(f"step_nm must be integer >= 1, got {step_nm!r}")

    cfg = load_qc_thresholds() if config is None else dict(config)
    lo = int(get_threshold(cfg, "gloria.complete_benchmark_window_nm.min_nm")) if min_nm is None else int(min_nm)
    hi = int(get_threshold(cfg, "gloria.complete_benchmark_window_nm.max_nm")) if max_nm is None else int(max_nm)
    if hi < lo:
        raise GloriaDataError(f"max_nm ({hi}) must be >= min_nm ({lo})")

    wavelengths = np.arange(lo, hi + 1, step_nm, dtype=int)
    cols = [f"Rrs_{wl}" for wl in wavelengths]
    missing = [col for col in cols if col not in rrs_df.columns]
    if missing:
        raise GloriaDataError(
            f"GLORIA_Rrs table missing {len(missing)} requested wavelength column(s), e.g. {missing[:5]}"
        )

    X = rrs_df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return wavelengths.astype(float), X


def summarize_qc_flags(
    qc_df: pd.DataFrame,
    *,
    flag_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Summarize per-observation QC status distinguishing failed (1), passed (0), and untested (NaN).

    Refuses malformed non-numeric strings or numeric flag values outside {0, 1}.
    """
    cols = (
        [c for c in QC_FLAG_COLUMNS if c in qc_df.columns]
        if flag_columns is None
        else list(flag_columns)
    )
    if not cols:
        raise GloriaDataError("no recognized QC flag columns found in GLORIA_qc_flags")
    missing = [c for c in cols if c not in qc_df.columns]
    if missing:
        raise GloriaDataError(f"requested QC flag column(s) missing: {', '.join(missing)}")

    parsed_cols: dict[str, pd.Series] = {}
    for col in cols:
        raw_series = qc_df[col]
        is_missing = raw_series.isna()
        if raw_series.dtype == object or pd.api.types.is_string_dtype(raw_series.dtype):
            is_missing = is_missing | (raw_series.fillna("").astype(str).str.strip() == "")
        numeric = pd.to_numeric(raw_series, errors="coerce")
        bad_parse = (~is_missing) & numeric.isna()
        if bad_parse.any():
            samples = raw_series[bad_parse].tolist()[:5]
            raise GloriaDataError(
                f"QC column {col!r} contains non-numeric value(s): {samples}"
            )
        valid_vals = numeric[~is_missing]
        bad_domain = (~np.isfinite(valid_vals)) | (~valid_vals.isin([0, 1]))
        if bad_domain.any():
            samples = valid_vals[bad_domain].tolist()[:5]
            raise GloriaDataError(
                f"QC column {col!r} must contain strictly 0, 1, or NaN; found {samples}"
            )
        parsed_cols[col] = numeric.where(~is_missing, np.nan)

    mat = pd.DataFrame(parsed_cols, index=qc_df.index)
    n_flagged = (mat == 1).sum(axis=1).to_numpy(dtype=int)
    n_passed = (mat == 0).sum(axis=1).to_numpy(dtype=int)
    n_untested = mat.isna().sum(axis=1).to_numpy(dtype=int)

    return pd.DataFrame(
        {
            "any_flag": n_flagged > 0,
            "n_flagged": n_flagged,
            "n_passed": n_passed,
            "n_untested": n_untested,
            "all_tested_passed": (n_flagged == 0) & (n_untested == 0),
        },
        index=qc_df.index,
    )


def identify_optically_derived_chla(
    meta_df: pd.DataFrame,
    *,
    optically_derived_dataset_ids: Sequence[str] | None = None,
) -> np.ndarray:
    """Identify observations whose Chla target is optically inferred (e.g., Lake Geneva Thetis).

    Matches either:
    1. Explicit `Dataset_ID` values supplied via `optically_derived_dataset_ids`
       (recommended when cross-referencing `GLORIA_variables_and_methods.xlsx`), or
    2. Case-insensitive metadata markers `'thetis'`, `'line height'`, or
       `'line-height'` in `Dataset_ID`, `Site_name`, `Chla_method`, `Chla_note`,
       or `Comments`.
    """
    n = len(meta_df)
    mask = np.zeros(n, dtype=bool)

    if optically_derived_dataset_ids:
        if "Dataset_ID" not in meta_df.columns:
            raise GloriaDataError(
                "optically_derived_dataset_ids provided but 'Dataset_ID' column is absent"
            )
        target_ids = {str(x).strip() for x in optically_derived_dataset_ids if str(x).strip()}
        ds_clean = meta_df["Dataset_ID"].where(meta_df["Dataset_ID"].notna(), "").astype(str).str.strip()
        mask |= ds_clean.isin(target_ids).to_numpy(dtype=bool)

    candidate_cols = [
        col
        for col in ("Dataset_ID", "Site_name", "Chla_method", "Chla_note", "Comments")
        if col in meta_df.columns
    ]
    for col in candidate_cols:
        series = meta_df[col].fillna("").astype(str).str.lower()
        hit = (
            series.str.contains("thetis", regex=False)
            | series.str.contains("line height", regex=False)
            | series.str.contains("line-height", regex=False)
        )
        mask |= hit.to_numpy(dtype=bool)
    return mask


def build_site_group_keys(meta_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Build globally unique `Country|Site_name` group strings and validity mask."""
    for col in ("Country", "Site_name"):
        if col not in meta_df.columns:
            raise GloriaDataError(f"GLORIA metadata missing grouping column {col!r}")
    country = meta_df["Country"]
    site = meta_df["Site_name"]
    valid = (
        country.notna()
        & site.notna()
        & (country.fillna("").astype(str).str.strip() != "")
        & (site.fillna("").astype(str).str.strip() != "")
    )
    keys = (
        country.fillna("").astype(str).str.strip()
        + "|"
        + site.fillna("").astype(str).str.strip()
    )
    return keys.to_numpy(dtype=object), valid.to_numpy(dtype=bool)


def build_target_cohort(
    tables: GloriaTables,
    *,
    target_col: str,
    min_nm: int | None = None,
    max_nm: int | None = None,
    step_nm: int = 1,
    require_unflagged: bool = True,
    require_all_qc_tested: bool = False,
    exclude_optically_derived_chla: bool = True,
    optically_derived_dataset_ids: Sequence[str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an explicit, auditable analysis cohort with full denominator accounting.

    Never clips negative Rrs values; instead returns `has_negative_rrs` boolean
    diagnostics for retained spectra.
    """
    if target_col not in ALLOWED_TARGETS:
        raise GloriaDataError(
            f"target_col {target_col!r} not in documented GLORIA core targets {ALLOWED_TARGETS}; "
            "do not silently substitute uncorrected chlorophyll+phaeopigment columns"
        )
    if target_col not in tables.meta.columns:
        raise GloriaDataError(f"GLORIA metadata missing target column {target_col!r}")

    wl, X = extract_rrs_matrix(
        tables.rrs, min_nm=min_nm, max_nm=max_nm, step_nm=step_nm, config=config
    )
    y = pd.to_numeric(tables.meta[target_col], errors="coerce").to_numpy(dtype=float)

    n_total = len(tables.meta)
    complete_spectra = np.isfinite(X).all(axis=1)
    positive_target = np.isfinite(y) & (y > 0.0)
    site_keys, valid_site = build_site_group_keys(tables.meta)

    if tables.qc_flags is not None:
        qc_summary = summarize_qc_flags(tables.qc_flags)
        any_flag = qc_summary["any_flag"].to_numpy(dtype=bool)
        all_tested = (qc_summary["n_untested"] == 0).to_numpy(dtype=bool)
    else:
        if require_unflagged or require_all_qc_tested:
            raise GloriaDataError(
                "QC filtering requested but GloriaTables.qc_flags is None"
            )
        any_flag = np.zeros(n_total, dtype=bool)
        all_tested = np.ones(n_total, dtype=bool)

    optical_chla = (
        identify_optically_derived_chla(
            tables.meta,
            optically_derived_dataset_ids=optically_derived_dataset_ids,
        )
        if (target_col == "Chla" and exclude_optically_derived_chla)
        else np.zeros(n_total, dtype=bool)
    )

    # Sequential exclusion accounting so reasons sum exactly to `excluded`.
    remaining = np.ones(n_total, dtype=bool)
    reasons: dict[str, int] = {}

    def _apply(reason: str, keep_cond: np.ndarray) -> None:
        nonlocal remaining
        dropped = remaining & (~keep_cond)
        reasons[reason] = int(dropped.sum())
        remaining = remaining & keep_cond

    _apply("missing_or_nonpositive_target", positive_target)
    _apply("incomplete_rrs_window", complete_spectra)
    if require_unflagged:
        _apply("qc_flagged", ~any_flag)
    if require_all_qc_tested:
        _apply("qc_untested_wavelengths", all_tested)
    if target_col == "Chla" and exclude_optically_derived_chla:
        _apply("optically_derived_chla_circularity", ~optical_chla)
    _apply("missing_site_group", valid_site)

    idx = np.flatnonzero(remaining)
    X_sel = X[idx]
    y_sel = y[idx]
    has_neg = np.any(X_sel < 0.0, axis=1)

    counts = CohortCounts(
        attempted=n_total,
        completed=int(idx.size),
        failed=0,
        excluded=int(n_total - idx.size),
        exclusion_reasons=reasons,
    )

    if "Dataset_ID" in tables.meta.columns:
        raw_ds = tables.meta["Dataset_ID"].iloc[idx].tolist()
        dataset_ids: np.ndarray | None = np.array(
            [None if pd.isna(v) or str(v).strip() == "" else str(v).strip() for v in raw_ds],
            dtype=object,
        )
    else:
        dataset_ids = None

    return {
        "target_col": target_col,
        "target_unit": TARGET_UNITS[target_col],
        "wavelengths_nm": wl,
        "gloria_ids": tables.meta[tables.id_col].astype(str).to_numpy()[idx],
        "X_rrs": X_sel,
        "y": y_sel,
        "site_groups": site_keys[idx],
        "dataset_ids": dataset_ids,
        "has_negative_rrs": has_neg,
        "n_with_negative_rrs": int(has_neg.sum()),
        "counts": counts,
    }
