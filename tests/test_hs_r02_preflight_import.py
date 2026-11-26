"""Guard the imported HS-R02 GLORIA preflight against silent denominator edits."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from hydrospectral.provenance import sha256_file, validate_manifest

ROOT = Path("results/HS-R02_gloria_preflight")


def test_imported_preflight_manifest_matches_tables_and_script() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    assert manifest["status"] == "provenance-incomplete"
    assert manifest["git_commit"] is None
    assert manifest["extra"]["archive_recomputed_in_this_import"] is False
    assert manifest["extra"]["author_optical_exclusion_on_primary_chla"] == 0

    committed_sha = sha256_file(ROOT / "audit_gloria.py")
    produced_sha = sha256_file(ROOT / "audit_gloria_as_run.txt")
    assert manifest["script"]["sha256"] == committed_sha
    assert produced_sha != committed_sha
    author = json.loads((ROOT / "author_run_manifest.json").read_text(encoding="utf-8"))
    assert author["code_sha256"] == produced_sha
    assert manifest["extra"]["producing_script_sha256"] == produced_sha
    assert author["input_sha256"] == manifest["inputs_sha256"]["src.gloria-2022"]

    with (ROOT / "exclusions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_target: dict[str, int] = {}
    for row in rows:
        by_target[row["target"]] = by_target.get(row["target"], 0) + int(row["excluded"])
    for target, total in by_target.items():
        entry = manifest["counts"][target]
        assert sum(entry["exclusion_reasons"].values()) == entry["excluded"] == total
        assert entry["completed"] + entry["failed"] + entry["excluded"] == entry["attempted"]

    chla_optical = [
        int(row["excluded"])
        for row in rows
        if row["target"] == "Chla" and row["reason"] == "optically_derived_chla_circularity"
    ]
    assert chla_optical == [0]

    for name, digest in manifest["extra"]["output_sha256"].items():
        assert sha256_file(ROOT / name) == digest
