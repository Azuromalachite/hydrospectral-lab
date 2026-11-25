#!/usr/bin/env python3
"""Enforce repository data-hygiene, lane-promotion, and source-manifest invariants.

Checks four invariants that `.gitignore` comments alone cannot guarantee (for
instance if someone runs `git add -f`):

1. `config/local_paths.yaml`, staging dirs (`data/raw/`, `data/interim/`,
   `data/external/`, `data/processed/`, `papers/`, `literature/`), and credential
   files (`.env*`, `.netrc`, `*credentials*.json`, `*service-account*.json`,
   `*client_secret*.json`) are never tracked.
2. Forbidden binary archive/granule suffixes (`.zip`, `.nc`, `.h5`, `.tif`, etc.),
   `.zarr/` directory stores, and third-party PDFs outside `docs/figures/` or
   `results/figures/` are never tracked.
3. No `sprint/*` branch merge appears anywhere in Git merge history
   (`docs/lanes-and-promotion.md`).
4. Every file in `manifests/sources/` conforms to `<root>/schemas/source_manifest.schema.json`,
   at least one active source exists, and `example-source.yaml` carries `example: true`
   and is refused by the active-source loader.

Usage:
    python tools/check_repo_hygiene.py
    python tools/check_repo_hygiene.py --self-test
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hydrospectral.manifests import (  # noqa: E402
    SourceManifestError,
    load_active_sources,
    load_source_manifest,
)

FORBIDDEN_PATH_LOWER = frozenset({"config/local_paths.yaml"})
FORBIDDEN_DIR_PREFIXES = (
    "data/raw/",
    "data/interim/",
    "data/external/",
    "data/processed/",
    "papers/",
    "literature/",
)
FORBIDDEN_CREDENTIAL_BASENAMES = frozenset({".env", ".netrc", "_netrc"})
FORBIDDEN_CREDENTIAL_GLOBS = (
    "*credentials*.json",
    "*service-account*.json",
    "*client_secret*.json",
)
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".7z",
        ".rar",
        ".nc",
        ".nc4",
        ".cdf",
        ".hdf",
        ".h4",
        ".h5",
        ".hdf5",
        ".he5",
        ".tif",
        ".tiff",
        ".geotiff",
        ".grib",
        ".grib2",
        ".parquet",
        ".feather",
        ".arrow",
        ".pkl",
        ".pickle",
        ".joblib",
        ".npy",
        ".npz",
        ".pt",
        ".pth",
        ".ckpt",
        ".onnx",
        ".safetensors",
    }
)
ALLOWED_PDF_PREFIXES = ("docs/figures/", "results/figures/")
SPRINT_MERGE_RE = re.compile(r"\bsprint/[a-z0-9._-]+", re.I)


def _is_forbidden_credential_file(basename_lower: str) -> bool:
    if basename_lower in FORBIDDEN_CREDENTIAL_BASENAMES:
        return True
    if basename_lower.startswith(".env.") and basename_lower != ".env.example":
        return True
    return any(fnmatch.fnmatch(basename_lower, pat) for pat in FORBIDDEN_CREDENTIAL_GLOBS)


def check_repo(root: Path) -> tuple[list[str], dict[str, int]]:
    try:
        tracked_out = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return ["not a git repository; refusing"], {"tracked": 0, "active_sources": 0}

    tracked = [line.strip() for line in tracked_out.splitlines() if line.strip()]
    if not tracked:
        return ["zero tracked files in git index; refusing vacuous pass"], {
            "tracked": 0,
            "active_sources": 0,
        }

    problems: list[str] = []
    for rel in tracked:
        norm = rel.replace("\\", "/")
        lower = norm.lower()
        segments = lower.split("/")
        basename_lower = segments[-1]

        if lower in FORBIDDEN_PATH_LOWER or _is_forbidden_credential_file(basename_lower):
            problems.append(f"forbidden local/credential file tracked in git: {norm}")
            continue
        if lower.startswith(FORBIDDEN_DIR_PREFIXES):
            problems.append(f"forbidden local staging/literature path tracked in git: {norm}")
            continue
        if any(seg.endswith(".zarr") for seg in segments[:-1]):
            problems.append(f"forbidden .zarr directory store tracked in git: {norm}")
            continue
        if lower.endswith(".pdf") and not lower.startswith(ALLOWED_PDF_PREFIXES):
            problems.append(
                f"PDF tracked outside docs/figures/ or results/figures/ (keep publisher PDFs out of git): {norm}"
            )
            continue
        for suffix in FORBIDDEN_SUFFIXES:
            if lower.endswith(suffix):
                problems.append(f"forbidden binary/archive file tracked in git ({suffix}): {norm}")
                break

    has_head = (
        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).returncode
        == 0
    )
    if has_head:
        try:
            merges_out = subprocess.run(
                ["git", "log", "--merges", "--pretty=%s"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError) as exc:
            problems.append(f"failed to inspect git merge history: {exc}")
            merges_out = ""

        for subject in merges_out.splitlines():
            if SPRINT_MERGE_RE.search(subject):
                problems.append(f"sprint branch merged into history (violates lanes policy): {subject!r}")

    schema_path = root / "schemas" / "source_manifest.schema.json"
    sources_dir = root / "manifests" / "sources"
    example_path = sources_dir / "example-source.yaml"
    if not schema_path.is_file():
        problems.append(f"source manifest schema missing: {schema_path}")
    if not example_path.is_file():
        problems.append("manifests/sources/example-source.yaml missing")
    elif schema_path.is_file():
        try:
            load_source_manifest(example_path, allow_example=True, schema_path=schema_path)
        except SourceManifestError as exc:
            problems.append(f"example-source.yaml failed schema validation: {exc}")
        else:
            try:
                load_source_manifest(example_path, allow_example=False, schema_path=schema_path)
                problems.append(
                    "example-source.yaml was accepted as an active source (must carry example: true and be rejected)"
                )
            except SourceManifestError:
                pass

    active_count = 0
    if schema_path.is_file():
        try:
            active = load_active_sources(sources_dir, schema_path=schema_path)
            active_count = len(active)
        except SourceManifestError as exc:
            problems.append(f"source manifest validation failed: {exc}")

    return problems, {"tracked": len(tracked), "active_sources": active_count}


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

        copied_rels: list[str] = []
        for rel in sorted(set(listing)):
            src = REPO / rel
            if not src.is_file():
                continue
            dst = copy_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied_rels.append(rel)

        subprocess.run(["git", "init", "-b", "main", "--quiet"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "tag.gpgsign", "false"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "add", "--"] + copied_rels, cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "base", "--quiet"], cwd=copy_root, check=True, capture_output=True)

        clean_problems, _ = check_repo(copy_root)
        if clean_problems:
            failures.append(f"clean copy failed: {clean_problems}")

        # 1. Force-added local_paths.yaml, nested .env.*, and GCP service-account JSON must fail.
        planted_secrets = [
            "config/local_paths.yaml",
            "notebooks/.env.local",
            "gcp-service-account-key.json",
            "data/processed/cohort.csv",
            "cube.zarr/.zarray",
        ]
        for rel in planted_secrets:
            p = copy_root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("placeholder\n", encoding="utf-8")
        (copy_root / ".env.example").write_text("EE_PROJECT=\n", encoding="utf-8")

        subprocess.run(
            ["git", "add", "-f", "--"] + planted_secrets + [".env.example"],
            cwd=copy_root,
            check=True,
            capture_output=True,
        )
        probs = check_repo(copy_root)[0]
        for rel in planted_secrets:
            if not any(rel in item for item in probs):
                failures.append(f"missed forbidden path {rel}")
        if any(".env.example" in item for item in probs):
            failures.append("false positive on allowed .env.example")
        subprocess.run(
            ["git", "rm", "-f", "--quiet", "--"] + planted_secrets + [".env.example"],
            cwd=copy_root,
            check=True,
            capture_output=True,
        )

        # 2. Force-added publisher PDF at root and NetCDF granule must fail; results/figures/*.pdf allowed.
        pdf = copy_root / "paper.pdf"
        nc = copy_root / "granule.nc"
        fig_pdf = copy_root / "results" / "figures" / "plot.pdf"
        fig_pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4\n")
        nc.write_bytes(b"CDF\x01")
        fig_pdf.write_bytes(b"%PDF-1.4\n")
        subprocess.run(
            ["git", "add", "-f", "paper.pdf", "granule.nc", "results/figures/plot.pdf"],
            cwd=copy_root,
            check=True,
            capture_output=True,
        )
        probs = check_repo(copy_root)[0]
        if not any("paper.pdf" in p for p in probs):
            failures.append("missed tracked root paper.pdf")
        if not any("granule.nc" in p for p in probs):
            failures.append("missed tracked granule.nc")
        if any("results/figures/plot.pdf" in p for p in probs):
            failures.append("false positive on allowed results/figures/plot.pdf")
        subprocess.run(
            ["git", "rm", "-f", "--quiet", "paper.pdf", "granule.nc", "results/figures/plot.pdf"],
            cwd=copy_root,
            check=True,
            capture_output=True,
        )

        # 3. Example manifest with example: false AND local schema mutation must both be checked.
        ex = copy_root / "manifests" / "sources" / "example-source.yaml"
        orig_ex = ex.read_text(encoding="utf-8")
        ex.write_text(orig_ex.replace("example: true", "example: false"), encoding="utf-8")
        if not any("example-source.yaml" in p for p in check_repo(copy_root)[0]):
            failures.append("missed example-source.yaml losing example: true")
        ex.write_text(orig_ex, encoding="utf-8")

        # Mutate copy_root's schema to verify check_repo reads <root>/schemas/source_manifest.schema.json.
        schema_copy = copy_root / "schemas" / "source_manifest.schema.json"
        orig_schema = schema_copy.read_text(encoding="utf-8")
        schema_copy.write_text(orig_schema.replace('"id",', '"id", "nonexistent_required_field",'), encoding="utf-8")
        if not any("source manifest" in p.lower() for p in check_repo(copy_root)[0]):
            failures.append("check_repo ignored <root>/schemas/source_manifest.schema.json")
        schema_copy.write_text(orig_schema, encoding="utf-8")

        # 4. Merging a sprint/* branch (even with unquoted custom subject) must fail.
        subprocess.run(["git", "switch", "-c", "sprint/band-hunt-2026-11", "--quiet"], cwd=copy_root, check=True, capture_output=True)
        (copy_root / "README.md").write_text(
            (copy_root / "README.md").read_text(encoding="utf-8") + "\nsprint note\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "README.md"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "sprint commit", "--quiet"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(["git", "switch", "main", "--quiet"], cwd=copy_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "merge", "--no-ff", "--no-gpg-sign", "sprint/band-hunt-2026-11", "-m", "Merge sprint/band-hunt-2026-11 into main", "--quiet"],
            cwd=copy_root,
            check=True,
            capture_output=True,
        )
        if not any("sprint branch merged" in p for p in check_repo(copy_root)[0]):
            failures.append("missed unquoted sprint/* merge commit")

    with tempfile.TemporaryDirectory() as empty_dir:
        if not check_repo(Path(empty_dir))[0]:
            failures.append("empty non-git directory passed")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(
        "self-test passed: clean repo passes, empty dir refuses, secrets/.zarr/PDF/.nc/schema-root/example-bypass/sprint-merge all caught"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    problems, stats = check_repo(args.root)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 2 if stats["tracked"] == 0 else 1
    print(
        f"ok: hygiene verified ({stats['tracked']} tracked files, {stats['active_sources']} active source manifest(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
