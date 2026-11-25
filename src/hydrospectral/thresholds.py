"""Load committed quality-control and radiometric thresholds without silent defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_THRESHOLDS_PATH = _PACKAGE_DIR.parents[1] / "config" / "qc_thresholds.yaml"
_BUNDLED_THRESHOLDS_PATH = _PACKAGE_DIR / "_bundled" / "qc_thresholds.yaml"
REQUIRED_SECTIONS = ("gloria", "avw", "qwip", "screening_geometry")


class ThresholdConfigError(ValueError):
    """Raised when the threshold configuration file is missing, malformed, or incomplete."""


def default_thresholds_path() -> Path:
    """Resolve the repository config path in editable checkouts or bundled wheel fallback."""
    if _REPO_THRESHOLDS_PATH.is_file():
        return _REPO_THRESHOLDS_PATH
    if _BUNDLED_THRESHOLDS_PATH.is_file():
        return _BUNDLED_THRESHOLDS_PATH
    return _REPO_THRESHOLDS_PATH


def load_qc_thresholds(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the top-level structure of config/qc_thresholds.yaml."""
    target = default_thresholds_path() if path is None else Path(path)
    if not target.is_file():
        raise ThresholdConfigError(f"threshold config file not found: {target}")

    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ThresholdConfigError(
            f"threshold config must be a non-empty mapping: {target}"
        )

    missing = [section for section in REQUIRED_SECTIONS if section not in raw]
    if missing:
        raise ThresholdConfigError(
            f"threshold config missing required section(s): {', '.join(missing)}"
        )

    empty_sections = [
        section
        for section in REQUIRED_SECTIONS
        if not isinstance(raw[section], dict) or not raw[section]
    ]
    if empty_sections:
        raise ThresholdConfigError(
            f"threshold config section(s) must be non-empty mappings: {', '.join(empty_sections)}"
        )
    return raw


def get_threshold(config: dict[str, Any], dotted_key: str) -> Any:
    """Look up a nested threshold by dotted key, refusing missing or null keys explicitly."""
    if not isinstance(dotted_key, str) or not dotted_key.strip():
        raise ThresholdConfigError("dotted_key must be non-empty")

    parts = dotted_key.split(".")
    if any(not part.strip() for part in parts):
        raise ThresholdConfigError(
            f"invalid dotted_key {dotted_key!r}: empty path segment"
        )

    cursor: Any = config
    traversed: list[str] = []
    for part in parts:
        traversed.append(part)
        if not isinstance(cursor, dict) or part not in cursor:
            joined = ".".join(traversed)
            raise ThresholdConfigError(
                f"threshold '{joined}' is not defined in committed config; "
                "refusing to invent a silent default"
            )
        cursor = cursor[part]

    if cursor is None:
        raise ThresholdConfigError(
            f"threshold '{dotted_key}' is null in config; refusing unset threshold"
        )
    return cursor
