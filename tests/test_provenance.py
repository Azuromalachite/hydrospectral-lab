"""Tests for byte-deterministic provenance manifests and denominator accounting."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from hydrospectral.provenance import (
    CohortCounts,
    ProvenanceError,
    build_manifest,
    serialize_manifest,
    sha256_file,
    validate_manifest,
    write_manifest,
)

SHA_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
GIT_COMMIT = "1e0e27d87ca5755baf049b91cc9c578a6851b543"


def test_sha256_file_matches_independent_nist_vectors(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.bin"
    empty_file.write_bytes(b"")
    assert sha256_file(empty_file) == SHA_EMPTY

    abc_file = tmp_path / "abc.txt"
    abc_file.write_bytes(b"abc")
    assert sha256_file(abc_file) == SHA_ABC

    with pytest.raises(ProvenanceError, match="missing file"):
        sha256_file(tmp_path / "nonexistent.bin")


def test_cohort_counts_enforces_exact_denominator_and_exclusion_sum() -> None:
    counts = CohortCounts(
        attempted=100,
        completed=72,
        failed=3,
        excluded=25,
        exclusion_reasons={"qc_flagged": 15, "incomplete_window": 10},
    )
    as_dict = counts.to_dict()
    assert as_dict["denominator"] == 100
    assert list(as_dict["exclusion_reasons"].keys()) == ["incomplete_window", "qc_flagged"]

    with pytest.raises(ProvenanceError, match="denominator mismatch"):
        CohortCounts(attempted=100, completed=70, failed=3, excluded=25)

    with pytest.raises(ProvenanceError, match="sum\\(exclusion_reasons\\)"):
        CohortCounts(
            attempted=100,
            completed=75,
            failed=0,
            excluded=25,
            exclusion_reasons={"qc_flagged": 10},
        )

    with pytest.raises(ProvenanceError, match="non-negative integer"):
        CohortCounts(attempted=10, completed=True, failed=0, excluded=9)  # type: ignore[arg-type]


def test_manifest_is_byte_deterministic_and_rejects_unpermitted_claims(tmp_path: Path) -> None:
    fixed_runtime = {"implementation": "CPython", "python_version": "3.12.0", "packages": {"numpy": "2.0.0"}}
    m1 = build_manifest(
        experiment_id="HS-R01",
        title="GLORIA baseline benchmark",
        status="exploratory",
        git_commit=GIT_COMMIT,
        script_path="src/hydrospectral/gloria.py",
        script_sha256=SHA_ABC,
        inputs={"src.gloria-2022": SHA_EMPTY},
        counts={"Chla": CohortCounts(attempted=50, completed=40, failed=0, excluded=10)},
        units={"Chla": "ug/L", "Rrs": "sr^-1"},
        random_seed=2026,
        pairing_rule="identical 5-fold GroupKFold across arms",
        runtime=fixed_runtime,
    )
    m2 = build_manifest(
        experiment_id="HS-R01",
        title="GLORIA baseline benchmark",
        status="exploratory",
        git_commit=GIT_COMMIT,
        script_path="src/hydrospectral/gloria.py",
        script_sha256=SHA_ABC,
        inputs={"src.gloria-2022": SHA_EMPTY},
        counts={"Chla": CohortCounts(attempted=50, completed=40, failed=0, excluded=10)},
        units={"Rrs": "sr^-1", "Chla": "ug/L"},
        random_seed=2026,
        pairing_rule="identical 5-fold GroupKFold across arms",
        runtime=fixed_runtime,
    )

    p1 = tmp_path / "m1.json"
    p2 = tmp_path / "m2.json"
    write_manifest(m1, p1)
    write_manifest(m2, p2)
    assert p1.read_bytes() == p2.read_bytes()
    assert b"\r\n" not in p1.read_bytes()
    assert serialize_manifest(m1) == p1.read_text(encoding="utf-8")

    # Forbidden overclaimed status labels must fail.
    for bad_status in ("verified", "confirmed", "validated"):
        with pytest.raises(ProvenanceError, match="invalid evidence status"):
            build_manifest(
                experiment_id="HS-R01",
                title="t",
                status=bad_status,
                script_path="scripts/run.py",
                script_sha256=SHA_ABC,
                inputs={"a": SHA_EMPTY},
                counts={"c": CohortCounts(attempted=1, completed=1)},
                units={"Chla": "ug/L"},
                runtime=fixed_runtime,
            )

    # Non-strict JSON (NaN) must fail serialization (allow_nan=False).
    m_nan = deepcopy(m1)
    m_nan["extra"] = {"score": float("nan")}
    with pytest.raises(ProvenanceError, match="not strict JSON"):
        serialize_manifest(m_nan)

    # Bad git_commit, missing script path, bad script sha256, mismatched denominator must fail validate_manifest.
    m_bad_commit = deepcopy(m1)
    m_bad_commit["git_commit"] = "not-a-sha"
    with pytest.raises(ProvenanceError, match="git_commit"):
        validate_manifest(m_bad_commit)

    m_none_path = deepcopy(m1)
    m_none_path["script"]["path"] = None
    with pytest.raises(ProvenanceError, match="script.path"):
        validate_manifest(m_none_path)

    m_bad_denom = deepcopy(m1)
    m_bad_denom["counts"]["Chla"]["denominator"] = 999
    with pytest.raises(ProvenanceError, match="denominator"):
        validate_manifest(m_bad_denom)

    m_missing_field = deepcopy(m1)
    del m_missing_field["counts"]["Chla"]["failed"]
    with pytest.raises(ProvenanceError, match="missing required field"):
        validate_manifest(m_missing_field)

    # Wall-clock timestamp nested inside extra must fail.
    with pytest.raises(ProvenanceError, match="wall-clock timestamp"):
        build_manifest(
            experiment_id="HS-R01",
            title="t",
            status="exploratory",
            script_path="scripts/run.py",
            script_sha256=SHA_ABC,
            inputs={"a": SHA_EMPTY},
            counts={"c": CohortCounts(attempted=1, completed=1)},
            units={"Chla": "ug/L"},
            extra={"nested": {"created_at": "2026-11-25T00:00:00Z"}},
            runtime=fixed_runtime,
        )
