#!/usr/bin/env python3
"""Verify that no tracked text file contains invalid UTF-8 or leftover conflict markers.

Markdown setext headings ('=======') are intentionally allowed; only the three
asymmetric conflict markers ('<<<<<<<', '>>>>>>>', '|||||||') at line start are
flagged. Tracked non-binary files that fail UTF-8 decoding are also reported so
locale-corrupted files cannot hide conflict markers. A minimum file-count floor
prevents an empty or broken worktree scan from silently passing.

Usage:
    python tools/check_conflict_markers.py
    python tools/check_conflict_markers.py --self-test
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIN_SCANNED = 15
MARKERS = re.compile(r"^(<{7}|>{7}|\|{7})(\s|$)", re.M)
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".pdf",
        ".gz",
        ".zip",
        ".nc",
        ".nc4",
        ".h5",
        ".hdf5",
        ".tif",
        ".tiff",
    }
)


def _is_declared_binary(path: Path, raw: bytes) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    return b"\x00" in raw[:8192]


def check(root: Path, *, min_scanned: int = MIN_SCANNED) -> tuple[list[str], dict[str, int]]:
    try:
        listing = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return ["not a git work tree; refusing to report clean on unknown scope"], {
            "files": 0,
            "markers": 0,
            "not_git": 1,
        }

    candidates = sorted({root / rel for rel in listing.splitlines() if (root / rel).is_file()})
    problems: list[str] = []
    markers = 0
    scanned_text = 0

    for path in candidates:
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(f"{rel}: unreadable tracked file: {exc}")
            continue

        if _is_declared_binary(path, raw):
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(
                f"{rel}: tracked text file is not valid UTF-8 ({exc.reason} at byte {exc.start})"
            )
            continue

        scanned_text += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            if MARKERS.match(line):
                markers += 1
                problems.append(f"{rel}:{lineno}: leftover conflict marker: {line[:40]!r}")

    if scanned_text < min_scanned:
        problems.append(
            f"scanned only {scanned_text} readable UTF-8 tracked text file(s), expected >= {min_scanned}; "
            "refusing vacuous pass"
        )
    return problems, {"files": scanned_text, "markers": markers, "not_git": 0}


def self_test() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        copy_root = Path(tmp) / "repo"
        listing = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.splitlines()
        tracked = sorted({rel for rel in listing if (REPO / rel).is_file()})
        if not tracked:
            print("SELF-TEST FAILED: host repository returned no tracked files", file=sys.stderr)
            return 1
        for rel in tracked:
            dst = copy_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dst)

        subprocess.run(["git", "init", "--quiet"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "add", "--"] + tracked,
            cwd=copy_root,
            check=True,
            capture_output=True,
        )

        if check(copy_root)[0]:
            failures.append(f"clean copy failed: {check(copy_root)[0][:2]}")

        readme = copy_root / "README.md"
        original = readme.read_text(encoding="utf-8")

        def plant(label: str, mutated: str, *, should_fail: bool) -> None:
            readme.write_text(mutated, encoding="utf-8")
            fired = bool(check(copy_root)[0])
            if fired != should_fail:
                failures.append(f"{'missed' if should_fail else 'false positive on'} {label}")
            readme.write_text(original, encoding="utf-8")

        plant("full conflict block", original + "\n<<<<<<< HEAD\na\n=======\nb\n>>>>>>> feat\n", should_fail=True)
        plant("orphan opener", original + "\n<<<<<<< HEAD\n", should_fail=True)
        plant("orphan closer", original + "\n>>>>>>> feat\n", should_fail=True)
        plant("diff3 base marker", original + "\n||||||| base\n", should_fail=True)
        plant("setext heading", original + "\nSection Heading\n===============\n", should_fail=False)
        plant("inline code mention", original + "\nCheck `<<<<<<<` markers.\n", should_fail=False)

        # Non-UTF-8 tracked text file must fail rather than be silently skipped.
        readme.write_bytes(b"# Corrupt encoding \xb0\xa1\n<<<<<<< HEAD\n")
        if not any("not valid UTF-8" in p for p in check(copy_root)[0]):
            failures.append("missed non-UTF-8 tracked text file")
        readme.write_text(original, encoding="utf-8")

        if not check(copy_root, min_scanned=10_000)[0]:
            failures.append("min_scanned floor failed to reject small tree")

    with tempfile.TemporaryDirectory() as empty_dir:
        if not check(Path(empty_dir))[0]:
            failures.append("empty non-git directory passed")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(
        "self-test passed: clean tree passes, empty tree refuses, non-UTF-8 caught, 4 markers caught, 2 look-alikes allowed"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    problems, stats = check(args.root)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 2 if stats.get("not_git") else 1
    print(f"ok: zero conflict markers across {stats['files']} tracked UTF-8 text file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
