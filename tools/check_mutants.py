#!/usr/bin/env python3
"""Mutation-testing guard proving core hydrospectral invariants can actually fail.

Reads surgical single-line mutants from `tools/mutants.tsv`, verifies that every
referenced test module passes UNMUTATED in an isolated temporary slice (`src/`,
`config/`, `schemas/`), applies each mutant to a fresh temp copy without
modifying the working tree, and requires pytest to exit with `rc == 1` (actual
test failure — never usage/collection/import errors `rc in {2, 3, 4, 5}`).

Usage:
    python tools/check_mutants.py
    python tools/check_mutants.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MUTANTS_TSV = REPO / "tools" / "mutants.tsv"


def load_mutants(tsv_path: Path) -> list[dict[str, str]]:
    if not tsv_path.is_file():
        raise FileNotFoundError(f"mutants table not found: {tsv_path}")
    with tsv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
    required = {"name", "file", "test_file", "original", "mutant"}
    if not rows:
        raise ValueError(f"mutants table is empty: {tsv_path}")
    for row in rows:
        missing = required - set(row.keys())
        if missing:
            raise ValueError(f"mutants table missing columns: {sorted(missing)}")
    return rows


def _prepare_temp_slice(repo_root: Path, tmp_dir: Path) -> Path:
    """Copy src/, config/, and schemas/ so relative repo lookups match the real checkout."""
    tmp_src = tmp_dir / "src"
    shutil.copytree(repo_root / "src", tmp_src)
    for aux in ("config", "schemas"):
        aux_src = repo_root / aux
        if aux_src.is_dir():
            shutil.copytree(aux_src, tmp_dir / aux)
    return tmp_src


def _run_pytest_against_src(src_dir: Path, test_rel: str, repo_root: Path) -> tuple[int, str]:
    test_path = repo_root / test_rel
    if not test_path.is_file():
        return 4, f"test file does not exist: {test_rel}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "pythonpath=", str(test_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out


def check_baselines(test_files: list[str], repo_root: Path) -> list[str]:
    """Verify every targeted test file passes (rc == 0) in an unmutated isolated copy."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_src = _prepare_temp_slice(repo_root, Path(tmp))
        for test_rel in sorted(set(test_files)):
            rc, out = _run_pytest_against_src(tmp_src, test_rel, repo_root)
            if rc != 0:
                snippet = out.splitlines()[-1] if out else ""
                problems.append(
                    f"UNMUTATED BASELINE FAILED (rc={rc}) for {test_rel}: {snippet}"
                )
    return problems


def run_mutant(row: dict[str, str], repo_root: Path) -> tuple[bool, str]:
    """Return (killed, detail). A mutant is killed iff pytest exits specifically with rc == 1."""
    rel_file = row["file"].replace("\\", "/")
    if not rel_file.startswith("src/"):
        return False, f"mutant {row['name']!r} targets non-src file {rel_file!r}"
    test_rel = row["test_file"].replace("\\", "/")
    if not (repo_root / test_rel).is_file():
        return False, f"mutant {row['name']!r} references missing test_file {test_rel!r}"
    sub_rel = rel_file[len("src/") :]
    orig_path = repo_root / rel_file
    if not orig_path.is_file():
        return False, f"mutant {row['name']!r} target file missing: {rel_file}"
    text = orig_path.read_text(encoding="utf-8")
    count = text.count(row["original"])
    if count != 1:
        return (
            False,
            f"mutant {row['name']!r} expected original snippet exactly once in {rel_file}, found {count}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_src = _prepare_temp_slice(repo_root, Path(tmp))
        mutated_file = tmp_src / sub_rel
        mutated_file.write_text(
            text.replace(row["original"], row["mutant"], 1),
            encoding="utf-8",
            newline="\n",
        )
        rc, out = _run_pytest_against_src(tmp_src, test_rel, repo_root)
    if rc == 0:
        return False, f"SURVIVED (rc=0): mutant {row['name']!r} passed {test_rel}!"
    if rc != 1:
        snippet = out.splitlines()[-1] if out else ""
        return (
            False,
            f"INVALID KILL (rc={rc}, expected 1): mutant {row['name']!r} errored in {test_rel}: {snippet}",
        )
    return True, f"killed (rc=1): {row['name']} ({test_rel})"


def self_test() -> int:
    failures: list[str] = []
    # 1. Verify unmutated baselines pass across both threshold-dependent and standalone test modules.
    base_probs = check_baselines(
        ["tests/test_gloria_and_splits.py", "tests/test_palette_and_provenance_keys.py"],
        REPO,
    )
    if base_probs:
        failures.extend(base_probs)

    # 2. Missing test file (rc=4) must be rejected, NEVER counted as killed!
    missing_row = {
        "name": "planted_missing_test_file",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_does_not_exist.py",
        "original": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")',
        "mutant": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")  # noop',
    }
    killed_missing, _ = run_mutant(missing_row, REPO)
    if killed_missing:
        failures.append("missing test_file was falsely counted as killed")

    # 3. Syntax-error mutant (rc=2 collection error) must be rejected, NEVER counted as killed!
    syntax_row = {
        "name": "planted_syntax_error",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_palette_and_provenance_keys.py",
        "original": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")',
        "mutant": "AVAILABLE_PALETTES = (((( syntax error",
    }
    killed_syn, _ = run_mutant(syntax_row, REPO)
    if killed_syn:
        failures.append("syntax/collection error (rc=2) was falsely counted as killed")

    # 4. Planted no-op mutant (rc=0) must be caught as SURVIVED.
    noop_row = {
        "name": "planted_noop_comment",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_palette_and_provenance_keys.py",
        "original": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")',
        "mutant": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")  # noop',
    }
    killed_noop, detail_noop = run_mutant(noop_row, REPO)
    if killed_noop:
        failures.append(f"planted no-op mutant was falsely reported killed: {detail_noop}")

    # 5. Real invariant bypass mutant (rc=1) must be killed.
    real_row = {
        "name": "planted_render_key_bypass",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_palette_and_provenance_keys.py",
        "original": "if not valid_pair:",
        "mutant": "if False:",
    }
    killed_real, detail_real = run_mutant(real_row, REPO)
    if not killed_real:
        failures.append(f"planted real mutant was not killed: {detail_real}")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(
        "self-test passed: unmutated baselines pass (incl. config/schemas), missing test_file & syntax errors rejected, no-op survived, real mutant killed (rc=1)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, default=DEFAULT_MUTANTS_TSV)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    rows = load_mutants(args.mutants)
    baseline_problems = check_baselines([row["test_file"] for row in rows], REPO)
    if baseline_problems:
        for item in baseline_problems:
            print(item, file=sys.stderr)
        return 1

    problems: list[str] = []
    for row in rows:
        killed, detail = run_mutant(row, REPO)
        if not killed:
            problems.append(detail)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 1
    print(f"ok: all {len(rows)} planted mutant(s) killed (rc=1) after verifying clean baselines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
