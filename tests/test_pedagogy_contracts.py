"""Hostile-pedagogy contract tests for curriculum notebooks and retained Q* results.

Adapted from the teaching-layer discipline of public `arrowfield`: every
curriculum notebook (`notebooks/Q*.ipynb`) and retained result package
(`results/Q*/`) must make limits, denominators, units, evidence status, and
prior exposure explicit so exploratory outputs can never be misread as
confirmatory ecological claims.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hydrospectral.provenance import validate_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_curriculum_notebooks_include_predict_control_and_limits_framing() -> None:
    notebooks = sorted((REPO_ROOT / "notebooks").glob("Q*.ipynb"))
    assert len(notebooks) >= 1, "expected at least one Q* curriculum notebook"

    for nb_path in notebooks:
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        md_text = "\n".join(
            "".join(cell.get("source", []))
            for cell in nb.get("cells", [])
            if cell.get("cell_type") == "markdown"
        ).lower()
        assert "predict" in md_text, f"{nb_path.name} missing Predict step before computation"
        assert "control" in md_text or "baseline" in md_text, (
            f"{nb_path.name} missing Control/Baseline comparison framing"
        )
        assert "limits" in md_text or "may not conclude" in md_text or "caution" in md_text, (
            f"{nb_path.name} missing explicit Limits / You may not conclude framing"
        )


def test_retained_curriculum_result_packages_enforce_epistemic_and_limits_contracts() -> None:
    q_result_dirs = sorted(
        p for p in (REPO_ROOT / "results").iterdir() if p.is_dir() and p.name.startswith("Q")
    )
    assert len(q_result_dirs) >= 1, "expected at least one retained results/Q* package"

    for pkg_dir in q_result_dirs:
        mpath = pkg_dir / "manifest.json"
        rpath = pkg_dir / "README.md"
        assert mpath.is_file(), f"missing manifest.json in {pkg_dir}"
        assert rpath.is_file(), f"missing README.md in {pkg_dir}"

        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        validate_manifest(manifest)

        # Prior exposure must be explicitly documented (not left null on real datasets).
        prior = manifest.get("prior_exposure")
        assert isinstance(prior, str) and len(prior.strip()) >= 10, (
            f"{mpath} must document explicit prior_exposure rather than null/empty"
        )

        readme = rpath.read_text(encoding="utf-8")
        status = manifest["status"]
        assert f"`{status}`" in readme, (
            f"{rpath} must explicitly state evidence status `{status}` matching manifest.json"
        )

        # Must contain an explicit Limits / Caveats / What this does NOT prove section.
        has_limits = bool(
            re.search(
                r"^##\s+.*(limits|caveats|does\s+not\s+prove|may\s+not\s+conclude)",
                readme,
                re.IGNORECASE | re.MULTILINE,
            )
        )
        assert has_limits, f"{rpath} missing explicit Limits / Caveats section"

        # Exploratory packages must never declare themselves reproduced or confirmed as status.
        if status == "exploratory":
            assert not re.search(
                r"evidence\s+status:\s*`?(reproduced|verified|confirmed)`?",
                readme,
                re.IGNORECASE,
            ), f"{rpath} overclaims status for an exploratory package"
