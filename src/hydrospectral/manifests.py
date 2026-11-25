"""Validate external dataset source manifests against JSON Schema and refuse templates."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = _PACKAGE_DIR.parents[1]
_REPO_SCHEMA_PATH = REPO_ROOT / "schemas" / "source_manifest.schema.json"
_BUNDLED_SCHEMA_PATH = _PACKAGE_DIR / "_bundled" / "source_manifest.schema.json"
DEFAULT_SOURCES_DIR = REPO_ROOT / "manifests" / "sources"


class SourceManifestError(ValueError):
    """Raised when a source manifest violates schema invariants or is an example template."""


def default_schema_path() -> Path:
    """Resolve schemas/source_manifest.schema.json in a checkout or bundled wheel."""
    if _REPO_SCHEMA_PATH.is_file():
        return _REPO_SCHEMA_PATH
    if _BUNDLED_SCHEMA_PATH.is_file():
        return _BUNDLED_SCHEMA_PATH
    return _REPO_SCHEMA_PATH


def load_source_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the JSON Schema governing manifests/sources/*.yaml."""
    target = default_schema_path() if schema_path is None else Path(schema_path)
    if not target.is_file():
        raise SourceManifestError(f"source manifest schema not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SourceManifestError(f"schema root must be a JSON object: {target}")
    return data


def validate_manifest_dict(
    record: Any,
    *,
    source_label: str = "<memory>",
    schema_path: Path | None = None,
) -> None:
    """Validate manifest against Draft 2020-12 JSON Schema plus calendar and whitespace invariants."""
    if not isinstance(record, dict):
        raise SourceManifestError(f"{source_label}: manifest must be a YAML mapping")

    schema = load_source_schema(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda err: list(err.absolute_path))
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise SourceManifestError(
            f"{source_label}: schema violation at {loc}: {first.message}"
        )

    if len(record["logical_name"].strip()) < 3:
        raise SourceManifestError(f"{source_label}: logical_name must be >= 3 non-space chars")
    if len(record["source"].strip()) < 5:
        raise SourceManifestError(f"{source_label}: source must be >= 5 non-space chars")
    if len(record["license"].strip()) < 2:
        raise SourceManifestError(f"{source_label}: license must be >= 2 non-space chars")
    if len(record["notes"].strip()) < 10:
        raise SourceManifestError(
            f"{source_label}: notes must be at least 10 non-whitespace characters documenting dataset caveats"
        )

    retrieved = record.get("retrieved_utc")
    if retrieved is not None:
        try:
            dt.date.fromisoformat(retrieved)
        except ValueError as exc:
            raise SourceManifestError(
                f"{source_label}: retrieved_utc {retrieved!r} is not a valid ISO calendar date"
            ) from exc


def load_source_manifest(
    path: Path,
    *,
    allow_example: bool = False,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Load a single YAML source manifest, rejecting example: true unless explicitly allowed."""
    target = Path(path)
    if not target.is_file():
        raise SourceManifestError(f"manifest file not found: {target}")
    if target.suffix != ".yaml":
        raise SourceManifestError(
            f"{target.name}: source manifests must use the '.yaml' extension"
        )
    record = yaml.safe_load(target.read_text(encoding="utf-8"))
    validate_manifest_dict(record, source_label=target.name, schema_path=schema_path)
    if record.get("example") is True and not allow_example:
        raise SourceManifestError(
            f"{target.name}: worked example record (example: true) is refused as an active dataset source"
        )
    return record


def load_active_sources(
    sources_dir: Path | None = None,
    *,
    schema_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load all non-example source manifests in sources_dir, rejecting stray files and duplicate IDs."""
    directory = DEFAULT_SOURCES_DIR if sources_dir is None else Path(sources_dir)
    if not directory.is_dir():
        raise SourceManifestError(f"sources directory not found: {directory}")

    entries = sorted(p for p in directory.iterdir() if not p.name.startswith("."))
    non_yaml = [p.name for p in entries if not p.is_file() or p.suffix != ".yaml"]
    if non_yaml:
        raise SourceManifestError(
            f"unexpected non-.yaml entry in {directory}: {', '.join(non_yaml)}"
        )
    if not entries:
        raise SourceManifestError(f"no source manifests found in {directory}")

    active: dict[str, dict[str, Any]] = {}
    for path in entries:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate_manifest_dict(raw, source_label=path.name, schema_path=schema_path)
        if raw.get("example") is True:
            continue
        source_id = raw["id"]
        if source_id in active:
            raise SourceManifestError(
                f"duplicate source manifest id {source_id!r} in {path.name}"
            )
        active[source_id] = raw

    if not active:
        raise SourceManifestError(
            f"zero active (non-example) source manifests found in {directory}"
        )
    return active
