"""Byte-deterministic run provenance and denominator accounting for hydrospectral-lab."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MEASUREMENT_CONTRACT = "hydrospectral.numeric/1"
MEASUREMENT_CONTRACTS = (MEASUREMENT_CONTRACT,)
CONTRACT_BY_RELEASE: dict[str, str] = {}

VALID_EVIDENCE_STATUSES = frozenset(
    {"provenance-incomplete", "exploratory", "reproduced"}
)
FORBIDDEN_TIMESTAMP_KEYS = frozenset(
    {"timestamp", "created_at", "executed_at", "run_time", "wall_clock_utc"}
)
DEFAULT_RUNTIME_PACKAGES = (
    "colour-science",
    "h5py",
    "hydrospectral",
    "jsonschema",
    "numpy",
    "pandas",
    "pyyaml",
    "scipy",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHORT_KEY_RE = re.compile(r"^[0-9a-f]{16,64}$")


class ProvenanceError(ValueError):
    """Raised when a provenance manifest violates determinism or accounting invariants."""


@dataclass(frozen=True)
class CohortCounts:
    """Explicit denominator accounting for an analysis cohort or fold.

    When `exclusion_reasons` is provided, reasons must represent mutually
    exclusive sequential exclusions whose counts sum exactly to `excluded`.
    """

    attempted: int
    completed: int
    failed: int = 0
    excluded: int = 0
    exclusion_reasons: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        for field_name in ("attempted", "completed", "failed", "excluded"):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise ProvenanceError(
                    f"CohortCounts.{field_name} must be a non-negative integer, got {val!r}"
                )
        if self.completed + self.failed + self.excluded != self.attempted:
            raise ProvenanceError(
                "CohortCounts denominator mismatch: "
                f"completed ({self.completed}) + failed ({self.failed}) + excluded ({self.excluded}) "
                f"!= attempted ({self.attempted})"
            )
        if self.exclusion_reasons is not None:
            if not isinstance(self.exclusion_reasons, Mapping):
                raise ProvenanceError("exclusion_reasons must be a mapping when provided")
            total_reasons = 0
            for reason, count in self.exclusion_reasons.items():
                if not isinstance(reason, str) or not reason.strip():
                    raise ProvenanceError("exclusion reason keys must be non-empty strings")
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ProvenanceError(
                        f"exclusion reason '{reason}' count must be a non-negative integer"
                    )
                total_reasons += count
            if total_reasons != self.excluded:
                raise ProvenanceError(
                    f"sum(exclusion_reasons) ({total_reasons}) != excluded ({self.excluded})"
                )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attempted": self.attempted,
            "completed": self.completed,
            "failed": self.failed,
            "excluded": self.excluded,
            "denominator": self.attempted,
        }
        if self.exclusion_reasons is not None:
            payload["exclusion_reasons"] = {
                k: int(self.exclusion_reasons[k])
                for k in sorted(self.exclusion_reasons)
            }
        return payload


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute lowercase hexadecimal SHA-256 digest of a file on disk."""
    target = Path(path)
    if not target.is_file():
        raise ProvenanceError(f"cannot hash missing file: {target}")
    digest = hashlib.sha256()
    with target.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_runtime_info(
    packages: Sequence[str] = DEFAULT_RUNTIME_PACKAGES,
) -> dict[str, Any]:
    """Collect deterministic Python/platform/package version metadata."""
    versions: dict[str, str | None] = {}
    for pkg in sorted(set(packages)):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": versions,
    }


def _assert_relative_posix_path(path_str: Any, *, field_name: str) -> None:
    if not isinstance(path_str, str) or not path_str.strip():
        raise ProvenanceError(f"{field_name} must be a non-empty repository-relative path")
    normalized = path_str.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise ProvenanceError(
            f"{field_name} must be repository-relative, not an absolute path: {path_str!r}"
        )
    if ".." in Path(normalized).parts:
        raise ProvenanceError(
            f"{field_name} must not escape repository root with '..': {path_str!r}"
        )


def _assert_sha256(digest: Any, *, field_name: str) -> None:
    if not isinstance(digest, str) or not _SHA256_RE.match(digest):
        raise ProvenanceError(
            f"{field_name} must be 64 lowercase hex characters, got {digest!r}"
        )


def _check_no_forbidden_keys(obj: Any, *, prefix: str = "") -> None:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            loc = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_TIMESTAMP_KEYS:
                raise ProvenanceError(
                    f"wall-clock timestamp key '{loc}' is forbidden in deterministic manifests"
                )
            _check_no_forbidden_keys(value, prefix=loc)
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            _check_no_forbidden_keys(item, prefix=f"{prefix}[{idx}]")


def compute_cohort_key(
    *,
    inputs_sha256: Mapping[str, str],
    target_col: str | None,
    wavelength_window_nm: Sequence[float],
    qc_policy: Mapping[str, Any],
    split_spec: Mapping[str, Any] | None = None,
    srf_spec: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Compute a deterministic 16-char hex cohort_key for apples-to-apples evaluation gating.

    Analogous to `espmap`'s `analysis_key`: two benchmark runs or model cells
    may only be compared directly when their `cohort_key` matches.
    """
    if not isinstance(inputs_sha256, Mapping) or not inputs_sha256:
        raise ProvenanceError("inputs_sha256 must be a non-empty mapping")
    norm_inputs: dict[str, str] = {}
    for label, digest in sorted(inputs_sha256.items()):
        _assert_sha256(digest, field_name=f"inputs_sha256[{label!r}]")
        norm_inputs[str(label)] = digest
    wl = [float(x) for x in wavelength_window_nm]
    if len(wl) < 2 or not all(x > 0 for x in wl):
        raise ProvenanceError("wavelength_window_nm must contain at least [min_nm, max_nm] > 0")
    if not isinstance(qc_policy, Mapping) or not qc_policy:
        raise ProvenanceError("qc_policy must be a non-empty mapping")

    payload: dict[str, Any] = {
        "measurement_contract": MEASUREMENT_CONTRACT,
        "inputs_sha256": norm_inputs,
        "target_col": target_col,
        "wavelength_window_nm": wl,
        "qc_policy": dict(qc_policy),
        "split_spec": None if split_spec is None else dict(split_spec),
        "srf_spec": srf_spec,
    }
    if extra is not None:
        payload["extra"] = dict(extra)
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"cohort_key inputs are not strict JSON serializable: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()[:16]


def assert_matching_cohort_keys(key_a: str, key_b: str, *, context: str = "") -> None:
    """Refuse direct comparison between two runs whose cohort_key differs."""
    if not isinstance(key_a, str) or not isinstance(key_b, str) or key_a != key_b:
        prefix = f"{context}: " if context else ""
        raise ProvenanceError(
            f"{prefix}cohort_key mismatch ({key_a!r} != {key_b!r}); "
            "refusing direct comparison across different cohorts, targets, QC rules, or splits"
        )


def inspect_git_provenance(repo_root: Path, script_path: str) -> dict[str, Any]:
    """Inspect commit SHA, clean-tree state (including untracked files), and script blob presence."""
    _assert_relative_posix_path(script_path, field_name="script_path")
    root = Path(repo_root).resolve()
    rel_posix = script_path.replace("\\", "/")

    top_proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if top_proc.returncode != 0 or Path(top_proc.stdout.strip()).resolve() != root:
        return {"git_commit": None, "git_tree_clean": False, "script_in_commit": False}

    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    commit = head_proc.stdout.strip()
    if head_proc.returncode != 0 or not _GIT_SHA_RE.match(commit):
        return {"git_commit": None, "git_tree_clean": False, "script_in_commit": False}

    status_proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    tree_clean = status_proc.returncode == 0 and (not status_proc.stdout.strip())

    blob_proc = subprocess.run(
        ["git", "cat-file", "-t", f"{commit}:{rel_posix}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    script_in_commit = blob_proc.returncode == 0 and blob_proc.stdout.strip() == "blob"

    return {
        "git_commit": commit,
        "git_tree_clean": tree_clean,
        "script_in_commit": script_in_commit,
    }


def build_manifest(
    *,
    experiment_id: str,
    title: str,
    status: str,
    script_path: str,
    script_sha256: str,
    inputs: Mapping[str, str],
    counts: Mapping[str, CohortCounts],
    units: Mapping[str, str],
    git_commit: str | None = None,
    git_tree_clean: bool | None = None,
    cohort_key: str | None = None,
    render_key: str | None = None,
    random_seed: int | None = None,
    pairing_rule: str = "",
    prior_exposure: str | None = None,
    extra: Mapping[str, Any] | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a validated, byte-deterministic experiment provenance manifest."""
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ProvenanceError("experiment_id must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ProvenanceError("title must be a non-empty string")
    if status not in VALID_EVIDENCE_STATUSES:
        allowed = ", ".join(sorted(VALID_EVIDENCE_STATUSES))
        raise ProvenanceError(
            f"invalid evidence status {status!r}; allowed values: {allowed}"
        )
    if git_commit is not None and (not isinstance(git_commit, str) or not _GIT_SHA_RE.match(git_commit)):
        raise ProvenanceError(
            f"git_commit must be a 40-char lowercase hex SHA or null, got {git_commit!r}"
        )
    _assert_relative_posix_path(script_path, field_name="script_path")
    _assert_sha256(script_sha256, field_name="script_sha256")

    if not isinstance(inputs, Mapping) or not inputs:
        raise ProvenanceError("inputs mapping must contain at least one named SHA-256 digest")
    for label, digest in inputs.items():
        if not isinstance(label, str) or not label.strip():
            raise ProvenanceError("input keys must be non-empty strings")
        _assert_sha256(digest, field_name=f"inputs[{label!r}]")
    if not isinstance(counts, Mapping) or not counts:
        raise ProvenanceError("counts mapping must record at least one cohort")
    if not isinstance(units, Mapping) or not units:
        raise ProvenanceError("units mapping must document physical units for targets/metrics")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "measurement_contract": MEASUREMENT_CONTRACT,
        "experiment_id": experiment_id.strip(),
        "title": title.strip(),
        "status": status,
        "git_commit": git_commit,
        "script": {
            "path": script_path.replace("\\", "/"),
            "sha256": script_sha256,
        },
        "inputs_sha256": {k: inputs[k] for k in sorted(inputs)},
        "counts": {k: counts[k].to_dict() for k in sorted(counts)},
        "units": {str(k): str(units[k]) for k in sorted(units)},
        "randomness": {
            "seed": random_seed,
            "pairing_rule": pairing_rule,
        },
        "prior_exposure": prior_exposure,
        "runtime": dict(runtime) if runtime is not None else collect_runtime_info(),
    }
    if git_tree_clean is not None:
        if not isinstance(git_tree_clean, bool):
            raise ProvenanceError(f"git_tree_clean must be bool or null, got {git_tree_clean!r}")
        manifest["git_tree_clean"] = git_tree_clean
    if cohort_key is not None:
        if not isinstance(cohort_key, str) or not _SHORT_KEY_RE.match(cohort_key):
            raise ProvenanceError(f"cohort_key must be 16-64 lowercase hex chars, got {cohort_key!r}")
        manifest["cohort_key"] = cohort_key
    if render_key is not None:
        if not isinstance(render_key, str) or not _SHORT_KEY_RE.match(render_key):
            raise ProvenanceError(f"render_key must be 16-64 lowercase hex chars, got {render_key!r}")
        manifest["render_key"] = render_key
    if extra is not None:
        manifest["extra"] = dict(extra)

    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate structural, denominator, status, and determinism invariants on a manifest."""
    if not isinstance(manifest, Mapping):
        raise ProvenanceError("manifest must be a mapping")
    _check_no_forbidden_keys(manifest)

    if manifest.get("schema_version") != 1:
        raise ProvenanceError(f"unsupported schema_version: {manifest.get('schema_version')!r}")
    for field in ("experiment_id", "title"):
        val = manifest.get(field)
        if not isinstance(val, str) or not val.strip():
            raise ProvenanceError(f"manifest.{field} must be a non-empty string")

    status = manifest.get("status")
    if status not in VALID_EVIDENCE_STATUSES:
        raise ProvenanceError(f"invalid status {status!r}")

    git_commit = manifest.get("git_commit")
    if git_commit is not None and (not isinstance(git_commit, str) or not _GIT_SHA_RE.match(git_commit)):
        raise ProvenanceError(f"manifest.git_commit must be 40 lowercase hex chars or null, got {git_commit!r}")
    if "git_tree_clean" in manifest and manifest["git_tree_clean"] is not None:
        if not isinstance(manifest["git_tree_clean"], bool):
            raise ProvenanceError(
                f"manifest.git_tree_clean must be bool or null, got {manifest['git_tree_clean']!r}"
            )
    for key_field in ("cohort_key", "render_key"):
        if key_field in manifest and manifest[key_field] is not None:
            val = manifest[key_field]
            if not isinstance(val, str) or not _SHORT_KEY_RE.match(val):
                raise ProvenanceError(
                    f"manifest.{key_field} must be 16-64 lowercase hex chars, got {val!r}"
                )

    script = manifest.get("script")
    if not isinstance(script, Mapping):
        raise ProvenanceError("manifest.script must be a mapping")
    _assert_relative_posix_path(script.get("path"), field_name="script.path")
    _assert_sha256(script.get("sha256"), field_name="script.sha256")

    inputs = manifest.get("inputs_sha256")
    if not isinstance(inputs, Mapping) or not inputs:
        raise ProvenanceError("manifest.inputs_sha256 must be a non-empty mapping")
    for label, digest in inputs.items():
        if not isinstance(label, str) or not label.strip():
            raise ProvenanceError("manifest.inputs_sha256 keys must be non-empty strings")
        _assert_sha256(digest, field_name=f"inputs_sha256[{label!r}]")

    units = manifest.get("units")
    if not isinstance(units, Mapping) or not units:
        raise ProvenanceError("manifest.units must be a non-empty mapping")
    for key, unit in units.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(unit, str) or not unit.strip():
            raise ProvenanceError("manifest.units keys and values must be non-empty strings")

    counts = manifest.get("counts")
    if not isinstance(counts, Mapping) or not counts:
        raise ProvenanceError("manifest.counts must be a non-empty mapping")
    for cohort_name, entry in counts.items():
        if not isinstance(entry, Mapping):
            raise ProvenanceError(f"manifest.counts['{cohort_name}'] must be a mapping")
        for req in ("attempted", "completed", "failed", "excluded"):
            if req not in entry:
                raise ProvenanceError(
                    f"manifest.counts['{cohort_name}'] missing required field {req!r}"
                )
        if "denominator" in entry and entry["denominator"] != entry["attempted"]:
            raise ProvenanceError(
                f"manifest.counts['{cohort_name}'].denominator ({entry['denominator']}) "
                f"!= attempted ({entry['attempted']})"
            )
        CohortCounts(
            attempted=entry["attempted"],
            completed=entry["completed"],
            failed=entry["failed"],
            excluded=entry["excluded"],
            exclusion_reasons=entry.get("exclusion_reasons"),
        )


def serialize_manifest(manifest: Mapping[str, Any]) -> str:
    """Serialize a manifest as strict RFC 8259 JSON with sorted keys and trailing LF."""
    validate_manifest(manifest)
    try:
        return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"manifest is not strict JSON serializable: {exc}") from exc


def write_manifest(manifest: Mapping[str, Any], path: Path) -> str:
    """Write a deterministic manifest JSON file with explicit UTF-8 encoding and LF newlines."""
    text = serialize_manifest(manifest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text
