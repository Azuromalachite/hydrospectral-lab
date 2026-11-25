"""Perceptually uniform Crameri scientific colormaps and render_key comparison guards.

Design principles (adapted from public espmap & arrowfield conventions):
- Scalar geophysical maps (AVW, Chla, TSS, QWIP residuals, SAM OOD distance)
  use Fabio Crameri's perceptually uniform, colour-vision-deficiency-safe
  colour maps (`batlow`, `vik`, `lajolla`) rather than rainbow/turbo scales,
  while reserving CIE 1931 display sRGB (`hydrospectral.color`) strictly for
  perceived water colour.
- Frozen 256-entry RGB lookup tables live in `_bundled/crameri_colormaps.json`
  with embedded SHA-256 checksums and MIT attribution (`LICENSE-cmcrameri`),
  requiring zero extra runtime dependencies.
- Two rendered maps may only be compared visually when they share an identical
  `render_key` (encoding colormap, orientation, scale bounds, and kind).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")
VALID_PALETTE_KINDS = frozenset({"sequential", "diverging"})
_SHORT_KEY_RE = re.compile(r"^[0-9a-f]{16,64}$")
_BUNDLED_PALETTES_PATH = Path(__file__).resolve().parent / "_bundled" / "crameri_colormaps.json"


class PaletteError(ValueError):
    """Raised when colormap lookup, integrity verification, or render_key comparison fails."""


@lru_cache(maxsize=1)
def load_palette_tables() -> dict[str, Any]:
    """Load and SHA-256 verify frozen Fabio Crameri RGB lookup tables."""
    if not _BUNDLED_PALETTES_PATH.is_file():
        raise PaletteError(f"bundled Crameri colormap table missing: {_BUNDLED_PALETTES_PATH}")
    doc = json.loads(_BUNDLED_PALETTES_PATH.read_text(encoding="utf-8"))
    maps = doc.get("maps")
    if not isinstance(maps, Mapping):
        raise PaletteError("crameri_colormaps.json missing 'maps' mapping")
    for name in AVAILABLE_PALETTES:
        if name not in maps:
            raise PaletteError(f"missing required Crameri colormap {name!r} in bundled tables")
        entry = maps[name]
        rgb = entry.get("rgb")
        if not isinstance(rgb, list) or len(rgb) != 256 or entry.get("N") != 256:
            raise PaletteError(f"colormap {name!r} must have exactly 256 RGB rows")
        digest = hashlib.sha256(
            json.dumps(rgb, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if digest != entry.get("sha256"):
            raise PaletteError(
                f"SHA-256 mismatch for bundled colormap {name!r}: expected {entry.get('sha256')}, got {digest}"
            )
    return doc


def get_palette_rgb(name: str, *, reverse: bool = False) -> np.ndarray:
    """Return a copy of the (256, 3) float64 RGB table in [0, 1] for `name`."""
    if name not in AVAILABLE_PALETTES:
        raise PaletteError(
            f"unknown scientific colormap {name!r}; expected one of {AVAILABLE_PALETTES}"
        )
    tables = load_palette_tables()
    arr = np.asarray(tables["maps"][name]["rgb"], dtype=float)
    if reverse:
        arr = arr[::-1].copy()
    return arr.copy()


def compute_render_key(
    cmap: str,
    vmin: float,
    vmax: float,
    *,
    kind: str,
    reverse: bool = False,
    bad_color: str = "#12171f",
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Compute a deterministic 16-char hex render_key for visual comparison gating.

    Two maps can be placed side-by-side on one scale only when their `render_key`
    matches. Diverging maps (`kind='diverging'`) require symmetric finite bounds
    or explicit caller bounds; `vmin < vmax` is always enforced.
    """
    if cmap not in AVAILABLE_PALETTES:
        raise PaletteError(
            f"unknown scientific colormap {cmap!r}; expected one of {AVAILABLE_PALETTES}"
        )
    if kind not in VALID_PALETTE_KINDS:
        raise PaletteError(
            f"invalid palette kind {kind!r}; expected one of {sorted(VALID_PALETTE_KINDS)}"
        )
    tables = load_palette_tables()
    expected_kind = tables["maps"][cmap]["kind"]
    if kind != expected_kind:
        raise PaletteError(
            f"colormap {cmap!r} is {expected_kind!r}, not {kind!r}; refusing mismatched scale kind"
        )
    if isinstance(vmin, bool) or isinstance(vmax, bool):
        raise PaletteError("vmin and vmax must be finite numeric bounds, not booleans")
    lo, hi = float(vmin), float(vmax)
    if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
        raise PaletteError(f"render bounds must satisfy finite vmin < vmax, got [{vmin!r}, {vmax!r}]")
    if not isinstance(bad_color, str) or not bad_color.strip():
        raise PaletteError("bad_color must be a non-empty colour string")

    payload: dict[str, Any] = {
        "cmap": cmap,
        "cmap_sha256": tables["maps"][cmap]["sha256"],
        "reverse": bool(reverse),
        "kind": kind,
        "vmin": lo,
        "vmax": hi,
        "bad_color": bad_color.strip().lower(),
    }
    if extra is not None:
        payload["extra"] = dict(extra)
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PaletteError(f"render_key inputs are not strict JSON serializable: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()[:16]


def assert_matching_render_keys(key_a: str, key_b: str, *, context: str = "") -> None:
    """Refuse visual comparison between two plots that do not share a valid render_key."""
    valid_pair = (
        isinstance(key_a, str)
        and isinstance(key_b, str)
        and bool(_SHORT_KEY_RE.match(key_a))
        and bool(_SHORT_KEY_RE.match(key_b))
        and key_a == key_b
    )
    if not valid_pair:
        prefix = f"{context}: " if context else ""
        raise PaletteError(
            f"{prefix}render_key mismatch or invalid key ({key_a!r} vs {key_b!r}); "
            "refusing side-by-side comparison across incompatible colour scales"
        )


def map_values_to_rgb(
    values: ArrayLike,
    cmap: str,
    vmin: float,
    vmax: float,
    *,
    reverse: bool = False,
    bad_rgb: tuple[float, float, float] = (0.07, 0.09, 0.12),
) -> np.ndarray:
    """Map scalar array of arbitrary shape to RGB (..., 3) in [0, 1] via Crameri table.

    Uses the exact matplotlib index rule `i = min(int(clip(t, 0, 1) * N), N - 1)`
    for finite entries and fills non-finite entries with `bad_rgb`.
    """
    if isinstance(vmin, bool) or isinstance(vmax, bool):
        raise PaletteError("vmin and vmax must be finite numbers, not booleans")
    lo, hi = float(vmin), float(vmax)
    if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
        raise PaletteError(f"scale bounds must satisfy finite vmin < vmax, got [{vmin!r}, {vmax!r}]")
    bad = np.asarray(bad_rgb, dtype=float)
    if bad.shape != (3,) or not np.isfinite(bad).all() or np.any(bad < 0.0) or np.any(bad > 1.0):
        raise PaletteError(f"bad_rgb must be 3 finite floats in [0, 1], got {bad_rgb!r}")

    table = get_palette_rgb(cmap, reverse=reverse)
    n = table.shape[0]
    arr = np.asarray(values, dtype=float)
    out = np.empty(arr.shape + (3,), dtype=float)
    out[...] = bad

    finite = np.isfinite(arr)
    if finite.any():
        t = np.clip((arr[finite] - lo) / (hi - lo), 0.0, 1.0)
        idx = np.minimum((t * n).astype(int), n - 1)
        out[finite] = table[idx]
    return out


def to_matplotlib_cmap(
    name: str,
    *,
    reverse: bool = False,
    bad_color: str | None = "#12171f",
) -> Any:
    """Build a matplotlib ListedColormap backed by the frozen Crameri RGB table."""
    from matplotlib.colors import ListedColormap

    table = get_palette_rgb(name, reverse=reverse)
    label = f"crameri_{name}{'_r' if reverse else ''}"
    cmap = ListedColormap(table, name=label)
    if bad_color is not None:
        cmap.set_bad(bad_color)
    return cmap
