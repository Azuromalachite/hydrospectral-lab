"""Tests for Crameri scientific palettes, render_key, cohort_key, and git provenance checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from hydrospectral.palette import (
    AVAILABLE_PALETTES,
    PaletteError,
    assert_matching_render_keys,
    compute_render_key,
    get_palette_rgb,
    load_palette_tables,
    map_values_to_rgb,
)
from hydrospectral.provenance import (
    CohortCounts,
    ProvenanceError,
    assert_matching_cohort_keys,
    build_manifest,
    compute_cohort_key,
    inspect_git_provenance,
    validate_manifest,
)


def test_crameri_palettes_verify_checksums_and_known_orientations() -> None:
    tables = load_palette_tables()
    for name in AVAILABLE_PALETTES:
        rgb = get_palette_rgb(name)
        assert rgb.shape == (256, 3)
        assert np.isfinite(rgb).all()
        assert rgb.min() >= 0.0 and rgb.max() <= 1.0
        assert tables["maps"][name]["N"] == 256

    # Orientation physics/perception checks (analogous to espmap --selftest):
    batlow = get_palette_rgb("batlow")
    assert batlow[0].mean() < 0.25 and batlow[-1].mean() > 0.75  # dark low -> light high

    vik = get_palette_rgb("vik")
    assert vik[0, 2] > vik[0, 0] + 0.25  # index 0 cool blue
    assert vik[-1, 0] > vik[-1, 2] + 0.25  # index 255 warm red
    assert vik[128].mean() > 0.85  # near-white diverging centre

    lajolla = get_palette_rgb("lajolla")
    assert lajolla[0].mean() < 0.20 and lajolla[-1].mean() > 0.80  # dark brown-black -> pale yellow

    # Reversal must flip endpoints cleanly without mutating cached array.
    batlow_r = get_palette_rgb("batlow", reverse=True)
    np.testing.assert_allclose(batlow_r[0], batlow[-1])
    np.testing.assert_allclose(get_palette_rgb("batlow")[0], batlow[0])

    with pytest.raises(PaletteError, match="unknown scientific colormap"):
        get_palette_rgb("turbo")


def test_render_key_gates_visual_comparisons_and_maps_boundaries() -> None:
    k1 = compute_render_key("batlow", 440.0, 570.0, kind="sequential")
    k2 = compute_render_key("batlow", 440.0, 570.0, kind="sequential")
    assert len(k1) == 16 and k1 == k2
    assert_matching_render_keys(k1, k2, context="PACE-01 AVW")

    k_diff_scale = compute_render_key("batlow", 440.0, 580.0, kind="sequential")
    k_diff_rev = compute_render_key("batlow", 440.0, 570.0, kind="sequential", reverse=True)
    with pytest.raises(PaletteError, match="render_key mismatch"):
        assert_matching_render_keys(k1, k_diff_scale, context="scale drift")
    with pytest.raises(PaletteError, match="render_key mismatch"):
        assert_matching_render_keys(k1, k_diff_rev, context="orientation flip")
    with pytest.raises(PaletteError, match="invalid key"):
        assert_matching_render_keys("", "", context="empty keys")

    with pytest.raises(PaletteError, match="not 'diverging'"):
        compute_render_key("batlow", -1.0, 1.0, kind="diverging")
    with pytest.raises(PaletteError, match="finite vmin < vmax"):
        compute_render_key("vik", 1.0, 1.0, kind="diverging")

    # Boundary lookup & NaN handling in pure NumPy.
    batlow = get_palette_rgb("batlow")
    bad = (0.1, 0.2, 0.3)
    mapped = map_values_to_rgb([-5.0, 0.0, 0.5, 1.0, 5.0, np.nan], "batlow", 0.0, 1.0, bad_rgb=bad)
    assert mapped.shape == (6, 3)
    np.testing.assert_allclose(mapped[0], batlow[0])
    np.testing.assert_allclose(mapped[1], batlow[0])
    np.testing.assert_allclose(mapped[2], batlow[128])
    np.testing.assert_allclose(mapped[3], batlow[255])
    np.testing.assert_allclose(mapped[4], batlow[255])
    np.testing.assert_allclose(mapped[5], bad)


def test_cohort_key_and_manifest_key_validation() -> None:
    sha = "a" * 64
    ck1 = compute_cohort_key(
        inputs_sha256={"src.gloria-2022": sha},
        target_col="Chla",
        wavelength_window_nm=[400, 800],
        qc_policy={"require_unflagged": True, "exclude_optical_chla": True},
        split_spec={"kind": "GroupKFold", "group": "Country|Site_name", "k": 5},
    )
    # Identical content with different dict insertion order must yield identical key.
    ck2 = compute_cohort_key(
        inputs_sha256={"src.gloria-2022": sha},
        target_col="Chla",
        wavelength_window_nm=(400.0, 800.0),
        qc_policy={"exclude_optical_chla": True, "require_unflagged": True},
        split_spec={"k": 5, "kind": "GroupKFold", "group": "Country|Site_name"},
    )
    assert len(ck1) == 16 and ck1 == ck2
    assert_matching_cohort_keys(ck1, ck2, context="HS-R02 paired arms")

    # Changing target, window, QC, or split must fail comparison!
    ck_win = compute_cohort_key(
        inputs_sha256={"src.gloria-2022": sha},
        target_col="Chla",
        wavelength_window_nm=[400, 700],
        qc_policy={"require_unflagged": True, "exclude_optical_chla": True},
        split_spec={"kind": "GroupKFold", "group": "Country|Site_name", "k": 5},
    )
    with pytest.raises(ProvenanceError, match="cohort_key mismatch"):
        assert_matching_cohort_keys(ck1, ck_win, context="window mismatch")
    with pytest.raises(ProvenanceError, match="invalid key"):
        assert_matching_cohort_keys("", "", context="empty keys")

    rk = compute_render_key("batlow", 440.0, 570.0, kind="sequential")
    m = build_manifest(
        experiment_id="TEST-01",
        title="Key provenance validation",
        status="exploratory",
        script_path="notebooks/Q01_water_colour_and_owts.ipynb",
        script_sha256="b" * 64,
        inputs={"src.gloria-2022": sha},
        counts={"main": CohortCounts(attempted=10, completed=10)},
        units={"Chla": "ug/L"},
        git_tree_clean=True,
        cohort_key=ck1,
        render_key=rk,
    )
    validate_manifest(m)
    assert m["cohort_key"] == ck1
    assert m["render_key"] == rk
    assert m["git_tree_clean"] is True

    bad_m = dict(m, cohort_key="not-hex!")
    with pytest.raises(ProvenanceError, match="manifest.cohort_key"):
        validate_manifest(bad_m)
    bad_mc = dict(m, measurement_contract="hydrospectral.numeric/999")
    with pytest.raises(ProvenanceError, match="measurement_contract"):
        validate_manifest(bad_mc)


def test_inspect_git_provenance_detects_dirty_untracked_and_missing_blobs(tmp_path: Path) -> None:
    # Non-git directory returns clean=False and commit=None.
    non_repo = tmp_path / "plain"
    non_repo.mkdir()
    info_none = inspect_git_provenance(non_repo, "scripts/run.py")
    assert info_none == {"git_commit": None, "git_tree_clean": False, "script_in_commit": False}

    # Real tiny git repo.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", "--quiet"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True, capture_output=True)

    script = repo / "scripts" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "scripts/run.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "init", "--quiet"], cwd=repo, check=True, capture_output=True)

    clean_info = inspect_git_provenance(repo, "scripts/run.py")
    assert clean_info["git_commit"] is not None and len(clean_info["git_commit"]) == 40
    assert clean_info["git_tree_clean"] is True
    assert clean_info["script_in_commit"] is True

    # Uncommitted script is not a blob in HEAD.
    assert inspect_git_provenance(repo, "scripts/missing.py")["script_in_commit"] is False

    # Adding an untracked file must mark git_tree_clean=False (never ignore untracked!).
    (repo / "stray.txt").write_text("untracked\n", encoding="utf-8")
    dirty_info = inspect_git_provenance(repo, "scripts/run.py")
    assert dirty_info["git_tree_clean"] is False


def test_version_single_source_of_truth_and_citation_parity() -> None:
    import tomllib
    import yaml

    import hydrospectral
    from hydrospectral.provenance import MEASUREMENT_CONTRACT, MEASUREMENT_CONTRACTS

    repo_root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in pyproject["project"].get("dynamic", [])
    assert pyproject["tool"]["hatch"]["version"]["path"] == "src/hydrospectral/__init__.py"

    citation = yaml.safe_load((repo_root / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["version"] == hydrospectral.__version__
    assert MEASUREMENT_CONTRACT in MEASUREMENT_CONTRACTS
