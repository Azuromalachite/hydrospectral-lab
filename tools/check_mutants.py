#!/usr/bin/env python3
"""Mutation-testing guard proving core hydrospectral invariants can actually fail.

Reads surgical single-line mutants from `tools/mutants.tsv`, applies each one
to a temporary copy of `src/` (never modifying the working tree), runs the
mutant's targeted `pytest` module with `PYTHONPATH` pointing at the mutated
tree, and fails if any mutant survives (i.e., tests still pass).

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


def _run_pytest_against_src(src_dir: Path, test_rel: str, repo_root: Path) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "pythonpath=", str(repo_root / test_rel)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return proc.returncode


def run_mutant(row: dict[str, str], repo_root: Path) -> tuple[bool, str]:
    """Return (killed, detail). A mutant is killed iff pytest exits non-zero."""
    rel_file = row["file"].replace("\\", "/")
    if not rel_file.startswith("src/"):
        return False, f"mutant {row['name']!r} targets non-src file {rel_file!r}"
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
        tmp_src = Path(tmp) / "src"
        shutil.copytree(repo_root / "src", tmp_src)
        mutated_file = tmp_src / sub_rel
        mutated_file.write_text(
            text.replace(row["original"], row["mutant"], 1),
            encoding="utf-8",
            newline="\n",
        )
        rc = _run_pytest_against_src(tmp_src, row["test_file"], repo_root)
    if rc == 0:
        return False, f"SURVIVED: mutant {row['name']!r} passed {row['test_file']}!"
    return True, f"killed: {row['name']} ({row['test_file']})"


def self_test() -> int:
    failures: list[str] = []
    # 1. Verify an unmutated copy passes pytest (proving kills are not caused by import/env error).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_src = Path(tmp) / "src"
        shutil.copytree(REPO / "src", tmp_src)
        rc = _run_pytest_against_src(tmp_src, "tests/test_palette_and_provenance_keys.py", REPO)
        if rc != 0:
            failures.append(f"unmutated copy failed baseline pytest (exit={rc})")

    # 2. Verify a planted no-op mutant is detected as SURVIVED.
    noop_row = {
        "name": "planted_noop_comment",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_palette_and_provenance_keys.py",
        "original": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")',
        "mutant": 'AVAILABLE_PALETTES = ("batlow", "vik", "lajolla")  # noop',
    }
    killed, detail = run_mutant(noop_row, REPO)
    if killed:
        failures.append(f"planted no-op mutant was falsely reported killed: {detail}")

    # 3. Verify a real mutant IS killed.
    real_row = {
        "name": "planted_render_key_bypass",
        "file": "src/hydrospectral/palette.py",
        "test_file": "tests/test_palette_and_provenance_keys.py",
        "original": "if not isinstance(key_a, str) or not isinstance(key_b, str) or key_a != key_b:",
        "mutant": "if False:",
    }
    killed_real, detail_real = run_mutant(real_row, REPO)
    if not killed_real:
        failures.append(f"planted real mutant was not killed: {detail_real}")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("self-test passed: unmutated baseline passes, no-op mutant caught as survived, real mutant killed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, default=DEFAULT_MUTANTS_TSV)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    rows = load_mutants(args.mutants)
    problems: list[str] = []
    for row in rows:
        killed, detail = run_mutant(row, REPO)
        if not killed:
            problems.append(detail)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 1
    print(f"ok: all {len(rows)} planted mutant(s) killed by targeted tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
