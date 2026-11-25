"""Core provenance, radiometry, colourimetry, PACE swath, SRF, geometry, GLORIA, and split utilities."""

from __future__ import annotations

from hydrospectral import (
    color,
    geometry,
    gloria,
    manifests,
    pace,
    provenance,
    radiometry,
    splits,
    srf,
    thresholds,
)

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "color",
    "geometry",
    "gloria",
    "manifests",
    "pace",
    "provenance",
    "radiometry",
    "splits",
    "srf",
    "thresholds",
]
