#!/usr/bin/env python3
"""Release-evidence gate: verifies a vX.Y.Z tag's evidence matches that tag's code.

Adapted from public `espmap`'s `bench/check_release.py` (`docs/decisions.md` D-009):
- Reads `results/releases/acceptance_v<version>.json` (`hydrospectral.acceptance/1`).
- Verifies clean non-dev release version parity across the acceptance record,
  `hydrospectral.__version__`, `CITATION.cff`, and `CONTRACT_BY_RELEASE`.
- Verifies the full test suite and mutation-testing harness exited 0 on the
  exact accepted commit (never dirty or unknown).
- Verifies that `git diff --name-only <accepted_commit> <tag>` touches ONLY
  non-numerical files (`*.md`, `CITATION.cff`, and the acceptance JSON itself).

Usage:
    python tools/check_release.py v0.4.0
    python tools/check_release.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hydrospectral import __version__ as DECLARED_VERSION  # noqa: E402
from hydrospectral.provenance import CONTRACT_BY_RELEASE, MEASUREMENT_CONTRACTS  # noqa: E402

ACCEPTANCE_SCHEMA = "hydrospectral.acceptance/1"
SEMVER_RELEASE_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAY_DIFFER = (
    re.compile(r"(?:.*/)?[^/]*\.md$"),
    re.compile(r"^CITATION\.cff$"),
    re.compile(r"^results/releases/acceptance_v[^/]+\.json$"),
)


def commit_of(code: Any) -> str | None:
    """Extract commit SHA or exact tag from a clean git-describe string or 40-char SHA."""
    if not isinstance(code, str) or not code or code == "unknown" or code.endswith("-dirty"):
        return None
    if re.fullmatch(r"[0-9a-f]{40}", code):
        return code
    m = re.fullmatch(r"(v\d+\.\d+\.\d+)(?:-\d+-g([0-9a-f]{7,40}))?", code)
    if m is None:
        return None
    return m[2] or m[1]


def check_acceptance(
    acc: Any,
    version: str,
    changed: Sequence[str],
    *,
    code_version: str,
    citation_version: str | None,
    contract_by_release: Mapping[str, str],
) -> list[str]:
    """Return every reason `acc` does not license tagging `v<version>`."""
    if not isinstance(acc, Mapping) or acc.get("schema") != ACCEPTANCE_SCHEMA:
        return [f"not a {ACCEPTANCE_SCHEMA} record"]

    problems: list[str] = []
    if not SEMVER_RELEASE_RE.fullmatch(version):
        problems.append(f"release version {version!r} must be clean X.Y.Z (no .dev suffix)")
    if code_version != version:
        problems.append(f"hydrospectral.__version__ is {code_version!r}, not {version!r}")
    if citation_version != version:
        problems.append(f"CITATION.cff version is {citation_version!r}, not {version!r}")
    if version not in contract_by_release:
        problems.append(f"release {version!r} is not registered in CONTRACT_BY_RELEASE")
    elif contract_by_release[version] not in MEASUREMENT_CONTRACTS:
        problems.append(
            f"CONTRACT_BY_RELEASE[{version!r}] = {contract_by_release[version]!r} is unknown"
        )

    if acc.get("target_release") != version:
        problems.append(f"accepts {acc.get('target_release')!r}, not {version!r}")
    if acc.get("declared_code_version") != version:
        problems.append(
            f"accepted code declared {acc.get('declared_code_version')!r}, not {version!r}"
        )

    code = acc.get("acceptance_code")
    if commit_of(code) is None:
        problems.append(f"accepted code {code!r} is unknown or dirty")
    if acc.get("all_pass") is not True:
        problems.append("not every acceptance gate passed (all_pass != true)")

    suite = acc.get("suite")
    if not isinstance(suite, Mapping):
        problems.append("missing suite summary")
    else:
        if suite.get("code") != code:
            problems.append(f"suite ran on {suite.get('code')!r}, not accepted {code!r}")
        if suite.get("returncode") != 0:
            problems.append(f"suite exited {suite.get('returncode')!r}, not 0")
        if suite.get("failed") != 0 or suite.get("errors") != 0 or not suite.get("passed"):
            problems.append(
                f"suite did not pass cleanly: passed={suite.get('passed')}, "
                f"failed={suite.get('failed')}, errors={suite.get('errors')}"
            )

    mutants = acc.get("mutants")
    if not isinstance(mutants, Mapping):
        problems.append("missing mutation-testing summary")
    else:
        if mutants.get("returncode") != 0:
            problems.append(f"mutation check exited {mutants.get('returncode')!r}, not 0")
        killed = mutants.get("killed")
        total = mutants.get("total")
        if not isinstance(total, int) or total <= 0 or killed != total:
            problems.append(f"not all mutants killed: {killed}/{total}")

    moved = [p.replace("\\", "/") for p in changed if not any(rx.fullmatch(p.replace("\\", "/")) for rx in MAY_DIFFER)]
    if moved:
        problems.append("code/data changed after acceptance: " + ", ".join(sorted(moved)))
    return problems


def _read_citation_version(repo_root: Path) -> str | None:
    cff = repo_root / "CITATION.cff"
    if not cff.is_file():
        return None
    data = yaml.safe_load(cff.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        return None
    val = data.get("version")
    return None if val is None else str(val)


def self_test() -> int:
    failures: list[str] = []
    good_sha = "a" * 40
    good_acc = {
        "schema": ACCEPTANCE_SCHEMA,
        "target_release": "0.4.0",
        "declared_code_version": "0.4.0",
        "acceptance_code": good_sha,
        "all_pass": True,
        "suite": {"code": good_sha, "returncode": 0, "passed": 55, "failed": 0, "errors": 0},
        "mutants": {"returncode": 0, "killed": 10, "total": 10},
    }
    contracts = {"0.4.0": MEASUREMENT_CONTRACTS[0]}

    # 1. Clean release with only prose / CITATION / acceptance JSON changed must pass.
    clean = check_acceptance(
        good_acc,
        "0.4.0",
        ["README.md", "docs/decisions.md", "CITATION.cff", "results/releases/acceptance_v0.4.0.json"],
        code_version="0.4.0",
        citation_version="0.4.0",
        contract_by_release=contracts,
    )
    if clean:
        failures.append(f"clean acceptance failed: {clean}")

    # 2. Planted code change after acceptance must fail.
    if not check_acceptance(
        good_acc,
        "0.4.0",
        ["src/hydrospectral/gloria.py"],
        code_version="0.4.0",
        citation_version="0.4.0",
        contract_by_release=contracts,
    ):
        failures.append("missed code change after acceptance")

    # 3. Planted .dev0 code version, dirty commit, surviving mutant, and non-zero suite rc must fail.
    for label, acc_mut, cv, civ, cbr in [
        ("dev0_code", good_acc, "0.4.0.dev0", "0.4.0", contracts),
        ("citation_mismatch", good_acc, "0.4.0", "0.3.0", contracts),
        ("missing_contract", good_acc, "0.4.0", "0.4.0", {}),
        ("dirty_commit", dict(good_acc, acceptance_code="v0.4.0-1-gabcdef0-dirty"), "0.4.0", "0.4.0", contracts),
        ("nonzero_suite", dict(good_acc, suite=dict(good_acc["suite"], returncode=1)), "0.4.0", "0.4.0", contracts),
        ("survived_mutant", dict(good_acc, mutants={"returncode": 0, "killed": 9, "total": 10}), "0.4.0", "0.4.0", contracts),
    ]:
        if not check_acceptance(acc_mut, "0.4.0", [], code_version=cv, citation_version=civ, contract_by_release=cbr):
            failures.append(f"missed planted release defect: {label}")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(
        "self-test passed: clean acceptance passes; post-acceptance code diff, .dev0, CITATION drift, missing contract, dirty SHA, suite failure, and surviving mutant all caught"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", nargs="?", help="Release tag to verify, e.g. v0.4.0")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.tag:
        print("error: provide a release tag (e.g. v0.4.0) or --self-test", file=sys.stderr)
        return 2

    tag = args.tag
    version = tag[1:] if tag.startswith("v") else tag
    path = REPO / "results" / "releases" / f"acceptance_v{version}.json"
    if not path.is_file():
        print(f"{tag}: missing {path.relative_to(REPO)}", file=sys.stderr)
        return 1
    acc = json.loads(path.read_text(encoding="utf-8"))
    base = commit_of(acc.get("acceptance_code"))
    changed: list[str] = []
    if base:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--name-only", base, tag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if proc.returncode != 0:
            print(f"{tag}: cannot diff accepted commit {base}: {proc.stderr.strip()}", file=sys.stderr)
            return 1
        changed = proc.stdout.splitlines()

    bad = check_acceptance(
        acc,
        version,
        changed,
        code_version=DECLARED_VERSION,
        citation_version=_read_citation_version(REPO),
        contract_by_release=CONTRACT_BY_RELEASE,
    )
    for item in bad:
        print(f"{tag}: {item}", file=sys.stderr)
    print(f"{tag}: {'NOT releasable' if bad else 'evidence matches tag code'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
