"""Tests for committed QC threshold loading and external dataset source manifests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
import yaml

import hydrospectral.manifests as manifests_mod
import hydrospectral.thresholds as thresholds_mod
from hydrospectral.manifests import (
    DEFAULT_SOURCES_DIR,
    SourceManifestError,
    load_active_sources,
    load_source_manifest,
    load_source_schema,
    validate_manifest_dict,
)
from hydrospectral.thresholds import (
    ThresholdConfigError,
    get_threshold,
    load_qc_thresholds,
)


def test_committed_qc_thresholds_match_published_constants() -> None:
    cfg = load_qc_thresholds()
    assert get_threshold(cfg, "gloria.interpolated_grid_nm.min_nm") == 350
    assert get_threshold(cfg, "gloria.interpolated_grid_nm.max_nm") == 900
    assert get_threshold(cfg, "gloria.interpolated_grid_nm.step_nm") == 1
    assert get_threshold(cfg, "gloria.complete_benchmark_window_nm.min_nm") == 400
    assert get_threshold(cfg, "gloria.complete_benchmark_window_nm.max_nm") == 800
    assert get_threshold(cfg, "gloria.oxygen_a_band_artefact_nm") == 762
    assert get_threshold(cfg, "gloria.optically_derived_chla_dataset_ids") == [
        "OdermattD_CH_Eawag"
    ]
    assert get_threshold(cfg, "avw.visible_window_nm.min_nm") == 400
    assert get_threshold(cfg, "avw.visible_window_nm.max_nm") == 700
    assert get_threshold(cfg, "qwip.ndi_wavelengths_nm") == [492, 665]
    assert get_threshold(cfg, "qwip.polynomial_coefficients_avw_desc") == pytest.approx(
        [-8.399885e-9, 1.715532e-5, -1.301670e-2, 4.357838, -544.9532]
    )
    assert get_threshold(cfg, "qwip.max_abs_deviation") == pytest.approx(0.2)
    assert get_threshold(cfg, "screening_geometry.default_bank_buffer_m") == pytest.approx(20.0)


def test_thresholds_refuse_missing_empty_or_null_values(tmp_path: Path) -> None:
    cfg = load_qc_thresholds()
    with pytest.raises(ThresholdConfigError, match="refusing to invent a silent default"):
        get_threshold(cfg, "qwip.nonexistent_cutoff")

    with pytest.raises(ThresholdConfigError, match="non-empty"):
        get_threshold(cfg, "   ")

    with pytest.raises(ThresholdConfigError, match="empty path segment"):
        get_threshold(cfg, "gloria..min_nm")

    mutated = deepcopy(cfg)
    mutated["qwip"]["max_abs_deviation"] = None
    with pytest.raises(ThresholdConfigError, match="null in config"):
        get_threshold(mutated, "qwip.max_abs_deviation")

    broken = tmp_path / "broken_thresholds.yaml"
    broken.write_text("gloria:\n  min_nm: 350\n", encoding="utf-8")
    with pytest.raises(ThresholdConfigError, match="missing required section"):
        load_qc_thresholds(broken)

    null_section = tmp_path / "null_section.yaml"
    null_section.write_text(
        "gloria: null\navw:\n  x: 1\nqwip:\n  x: 1\nscreening_geometry:\n  x: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ThresholdConfigError, match="non-empty mappings"):
        load_qc_thresholds(null_section)


def test_bundled_fallback_paths_when_installed_outside_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled_cfg = tmp_path / "_bundled" / "qc_thresholds.yaml"
    bundled_schema = tmp_path / "_bundled" / "source_manifest.schema.json"
    bundled_cfg.parent.mkdir(parents=True, exist_ok=True)
    bundled_cfg.write_text(
        thresholds_mod.default_thresholds_path().read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bundled_schema.write_text(
        manifests_mod.default_schema_path().read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setattr(thresholds_mod, "_REPO_THRESHOLDS_PATH", tmp_path / "missing_cfg.yaml")
    monkeypatch.setattr(thresholds_mod, "_BUNDLED_THRESHOLDS_PATH", bundled_cfg)
    monkeypatch.setattr(manifests_mod, "_REPO_SCHEMA_PATH", tmp_path / "missing_schema.json")
    monkeypatch.setattr(manifests_mod, "_BUNDLED_SCHEMA_PATH", bundled_schema)

    assert thresholds_mod.default_thresholds_path() == bundled_cfg
    assert get_threshold(load_qc_thresholds(), "qwip.max_abs_deviation") == pytest.approx(0.2)
    assert manifests_mod.default_schema_path() == bundled_schema
    assert load_source_schema()["title"] == "External dataset source manifest"


def test_committed_manifests_validate_against_json_schema() -> None:
    schema = load_source_schema()
    validator = jsonschema.Draft202012Validator(schema)

    yaml_files = sorted(DEFAULT_SOURCES_DIR.glob("*.yaml"))
    assert len(yaml_files) >= 3

    for path in yaml_files:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        validator.validate(raw)
        validate_manifest_dict(raw, source_label=path.name)


def test_example_manifest_is_refused_as_active_source() -> None:
    example_path = DEFAULT_SOURCES_DIR / "example-source.yaml"
    parsed = load_source_manifest(example_path, allow_example=True)
    assert parsed["example"] is True

    with pytest.raises(SourceManifestError, match="refused as an active dataset source"):
        load_source_manifest(example_path, allow_example=False)

    active = load_active_sources()
    assert "src.example-template" not in active
    assert "src.gloria-2022" in active
    assert "src.pace-oci-20240730-nrt" in active
    assert active["src.gloria-2022"]["digest_verified"] is True
    assert active["src.gloria-2022"]["bytes"] == 58956647
    assert active["src.gloria-2022"]["retrieved_utc"] == "2026-11-26"
    assert active["src.gloria-2022"]["version_string"] == "not declared"
    assert (
        active["src.gloria-2022"]["sha256"]
        == "f5ad5106d5fd74f0d874085a23e4189302e7409aed9f82d629ae6cdb47d21f14"
    )
    assert active["src.pace-oci-20240730-nrt"]["digest_verified"] is True
    assert active["src.pace-oci-20240730-nrt"]["bytes"] == 147995278
    assert active["src.pace-oci-20240730-nrt"]["retrieved_utc"] == "2026-11-26"
    assert (
        active["src.pace-oci-20240730-nrt"]["sha256"]
        == "db38c89499f33603de850e1b321e1adbdbcd0609ebc7c532050c8d16d183e98e"
    )
    assert active["src.esa-s2a-msi-srf"]["digest_verified"] is True
    assert active["src.esa-s2a-msi-srf"]["bytes"] == 1330493
    assert (
        active["src.esa-s2a-msi-srf"]["sha256"]
        == "42be3ebd8bfcbde11c37caeb2e2fdda65fefa8d2b6f8329559b7806d02cdc9e2"
    )
    assert active["src.esa-s3a-olci-srf"]["digest_verified"] is True
    assert active["src.esa-s3a-olci-srf"]["bytes"] == 47804
    assert (
        active["src.esa-s3a-olci-srf"]["sha256"]
        == "e2806df83b6a874e1b5ecd98bd56c70368e4bca6c75e6c7bad6b472cdc5fef7d"
    )


def test_notes_length_boundary_9_fails_and_10_passes() -> None:
    baseline = load_source_manifest(DEFAULT_SOURCES_DIR / "gloria-2022.yaml")
    nine_chars = deepcopy(baseline)
    nine_chars["notes"] = "123456789"
    with pytest.raises(SourceManifestError):
        validate_manifest_dict(nine_chars, source_label="boundary-9")

    ten_chars = deepcopy(baseline)
    ten_chars["notes"] = "1234567890"
    validate_manifest_dict(ten_chars, source_label="boundary-10")


@pytest.mark.parametrize(
    ("field", "bad_value", "match_substr"),
    [
        ("id", "gloria-2022", "schema violation at id"),
        ("sha256", "ABCDEF" + "0" * 58, "schema violation at sha256"),
        ("sha256", "f" * 63, "schema violation at sha256"),
        ("digest_verified", "false", "schema violation at digest_verified"),
        ("local_path_key", "C:/Users/me/GLORIA-2022.zip", "schema violation at local_path_key"),
        ("version_string", "   ", "schema violation at version_string"),
        ("retrieved_utc", "25-11-2026", "schema violation at retrieved_utc"),
        ("retrieved_utc", "2026-02-30", "not a valid ISO calendar date"),
        ("record_count", -1, "schema violation at record_count"),
        ("record_count", True, "schema violation at record_count"),
        ("bytes", -1, "schema violation at bytes"),
        ("bytes", True, "schema violation at bytes"),
        ("used_by", [""], "schema violation at used_by"),
        ("used_by", ["   "], "schema violation at used_by"),
        ("example", "yes", "schema violation at example"),
    ],
)
def test_manifest_validator_catches_planted_field_defects(
    field: str, bad_value: object, match_substr: str
) -> None:
    baseline = load_source_manifest(DEFAULT_SOURCES_DIR / "gloria-2022.yaml")
    mutated = deepcopy(baseline)
    mutated[field] = bad_value
    with pytest.raises(SourceManifestError, match=match_substr):
        validate_manifest_dict(mutated, source_label="planted")


def test_manifest_validator_rejects_unknown_extra_field() -> None:
    baseline = load_source_manifest(DEFAULT_SOURCES_DIR / "gloria-2022.yaml")
    mutated = deepcopy(baseline)
    mutated["local_absolute_path"] = "/tmp/GLORIA-2022.zip"
    with pytest.raises(SourceManifestError, match="Additional properties are not allowed"):
        validate_manifest_dict(mutated, source_label="planted-extra")


def test_active_sources_rejects_duplicate_ids_and_non_yaml_files(tmp_path: Path) -> None:
    baseline = (DEFAULT_SOURCES_DIR / "gloria-2022.yaml").read_text(encoding="utf-8")
    (tmp_path / "a.yaml").write_text(baseline, encoding="utf-8")
    (tmp_path / "b.yaml").write_text(baseline, encoding="utf-8")
    with pytest.raises(SourceManifestError, match="duplicate source manifest id"):
        load_active_sources(tmp_path)

    (tmp_path / "b.yaml").unlink()
    (tmp_path / "stray.yml").write_text(baseline, encoding="utf-8")
    with pytest.raises(SourceManifestError, match="unexpected non-.yaml entry"):
        load_active_sources(tmp_path)


def test_committed_result_manifests_are_valid_and_match_hashes() -> None:
    import json
    from hydrospectral.provenance import sha256_file, validate_manifest

    repo_root = DEFAULT_SOURCES_DIR.parent.parent
    result_manifests = sorted((repo_root / "results").rglob("manifest.json"))
    assert len(result_manifests) >= 1

    active_sources = load_active_sources()
    for mpath in result_manifests:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        validate_manifest(manifest)

        # Verify recorded script hash matches committed script/notebook on disk.
        script_file = repo_root / manifest["script"]["path"]
        assert script_file.is_file(), f"missing script referenced by {mpath}: {script_file}"
        assert sha256_file(script_file) == manifest["script"]["sha256"]

        # Verify recorded input hashes match committed active source manifests.
        for src_id, recorded_sha in manifest["inputs_sha256"].items():
            assert src_id in active_sources
            assert active_sources[src_id]["sha256"] == recorded_sha

        # Verify any recorded output CSV hashes match committed CSVs on disk.
        out_hashes = manifest.get("extra", {}).get("output_csv_sha256", {})
        for csv_name, expected_sha in out_hashes.items():
            csv_path = mpath.parent / csv_name
            assert csv_path.is_file(), f"missing output CSV {csv_path}"
            assert sha256_file(csv_path) == expected_sha
