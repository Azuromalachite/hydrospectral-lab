#!/usr/bin/env python3
"""Verify that every Python/notebook text file read/write explicitly declares encoding=.

On Windows workstations (such as cp949 locales), bare `open(path)`, `io.open(path)`,
or `Path.read_text()` defaults to the OS codepage rather than UTF-8, silently
corrupting or crashing on non-ASCII scientific units and names while passing on
Linux CI. Binary modes ('rb', 'wb', etc.) and binary archive/image APIs are exempt.

Usage:
    python tools/check_declared_encoding.py
    python tools/check_declared_encoding.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".eggs",
        "node_modules",
        "build",
        "dist",
    }
)
TEXT_METHODS = {"read_text": 0, "write_text": 1}
MODULE_TEXT_OPENERS = {
    "io": (1, 3),
    "builtins": (1, 3),
    "codecs": (1, 2),
}
COMPRESSED_OPENERS = frozenset({"gzip", "bz2", "lzma"})
BINARY_ONLY_RECEIVERS = frozenset(
    {"Image", "tarfile", "zipfile", "ZipFile", "TarFile", "urllib", "fsspec", "h5py"}
)
VALID_MODE_RE = re.compile(r"^[rwax+btU]+$")


class Finding:
    __slots__ = ("path", "line", "call")

    def __init__(self, path: Path, line: int, call: str) -> None:
        self.path = path
        self.line = line
        self.call = call

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.call} missing explicit non-null encoding="


def _should_skip_dir(directory: Path, root: Path) -> bool:
    if directory.is_symlink():
        return True
    name = directory.name
    if name in SKIP_DIRS or name.endswith(".egg-info") or name.endswith(".zarr"):
        return True
    if (directory / "pyvenv.cfg").exists():
        return True
    if directory != root and (directory / ".git").exists():
        return True
    return False


def iter_source_files(root: Path) -> tuple[list[Path], list[Path]]:
    py_files: list[Path] = []
    nb_files: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not _should_skip_dir(entry, root):
                    stack.append(entry)
            elif entry.suffix == ".py":
                py_files.append(entry)
            elif entry.suffix == ".ipynb" and entry.name != ".ipynb_checkpoints":
                nb_files.append(entry)
    return sorted(py_files), sorted(nb_files)


def _extract_mode_str(node: ast.Call, mode_idx: int) -> str | None:
    mode_expr: ast.expr | None = None
    if mode_idx >= 0 and len(node.args) > mode_idx:
        mode_expr = node.args[mode_idx]
    for kw in node.keywords:
        if kw.arg == "mode":
            mode_expr = kw.value
    if (
        isinstance(mode_expr, ast.Constant)
        and isinstance(mode_expr.value, str)
        and VALID_MODE_RE.fullmatch(mode_expr.value)
    ):
        return mode_expr.value
    return None


def _has_valid_encoding(node: ast.Call, enc_arg_index: int) -> bool:
    enc_expr: ast.expr | None = None
    if enc_arg_index >= 0 and len(node.args) > enc_arg_index:
        enc_expr = node.args[enc_arg_index]
    for kw in node.keywords:
        if kw.arg == "encoding":
            enc_expr = kw.value
            break
    if enc_expr is None:
        return False
    if isinstance(enc_expr, ast.Constant):
        return isinstance(enc_expr.value, str) and bool(enc_expr.value.strip())
    return True


def _receiver_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def inspect_python_source(source: str, path: Path, *, label_prefix: str = "") -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        call_name: str | None = None
        mode_idx = -1
        enc_idx = -1
        default_binary = False

        if isinstance(node.func, ast.Name) and node.func.id == "open":
            call_name = "open()"
            mode_idx = 1
            enc_idx = 3
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            recv = _receiver_name(node.func.value)
            if attr in TEXT_METHODS:
                call_name = f".{attr}()"
                mode_idx = -1
                enc_idx = TEXT_METHODS[attr]
            elif attr == "open":
                if recv in BINARY_ONLY_RECEIVERS:
                    continue
                if recv in MODULE_TEXT_OPENERS:
                    call_name = f"{recv}.open()"
                    mode_idx, enc_idx = MODULE_TEXT_OPENERS[recv]
                elif recv in COMPRESSED_OPENERS:
                    call_name = f"{recv}.open()"
                    mode_idx = 1
                    enc_idx = 3
                    default_binary = True
                else:
                    # Path.open(mode='r', buffering=-1, encoding=None, ...)
                    # Note: if someone calls zip_var.open("file.csv"), args[0] is not a
                    # valid mode string and zip_var should use ZipFile / binary read; if
                    # args[0] is a non-mode string literal, skip only when clearly a
                    # non-Path archive member call? No: Path.open('r') passes a valid mode,
                    # Path.open() passes 0 args, whereas archive.open('member.csv') passes
                    # a filename at args[0]. Distinguish Path.open vs archive.open cleanly:
                    if (
                        len(node.args) >= 1
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and not VALID_MODE_RE.fullmatch(node.args[0].value)
                    ):
                        # Path.open's first positional parameter IS `mode`, so passing a
                        # filename literal at args[0] is never Path.open (it is e.g. zf.open("a.csv")).
                        continue
                    call_name = ".open()"
                    mode_idx = 0
                    enc_idx = 2

        if call_name is None:
            continue

        mode_str = _extract_mode_str(node, mode_idx)
        if default_binary:
            # gzip.open / bz2.open / lzma.open default to binary unless 't' is in mode
            if mode_str is None or "t" not in mode_str:
                continue
        elif mode_str is not None and "b" in mode_str:
            continue

        if _has_valid_encoding(node, enc_idx):
            continue

        findings.append(Finding(path, node.lineno, f"{label_prefix}{call_name}"))
    return findings


def _sanitize_notebook_cell(lines: list[str]) -> str:
    cleaned: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("%", "!")):
            indent = line[: len(line) - len(stripped)]
            cleaned.append(f"{indent}pass\n")
        else:
            cleaned.append(line if line.endswith("\n") else line + "\n")
    return "".join(cleaned)


def inspect_notebook(path: Path) -> list[Finding]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cells = raw.get("cells", [])
    if not isinstance(cells, list):
        return [Finding(path, 0, "malformed .ipynb cells")]
    findings: list[Finding] = []
    for idx, cell in enumerate(cells, start=1):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        src = cell.get("source", [])
        lines = src.splitlines(keepends=True) if isinstance(src, str) else list(src)
        code = _sanitize_notebook_cell(lines)
        try:
            findings.extend(inspect_python_source(code, path, label_prefix=f"cell[{idx}] "))
        except SyntaxError as exc:
            findings.append(Finding(path, exc.lineno or 0, f"cell[{idx}] syntax error"))
    return findings


def check(root: Path) -> tuple[list[Finding], int]:
    py_files, nb_files = iter_source_files(root)
    all_findings: list[Finding] = []
    for path in py_files:
        try:
            source = path.read_text(encoding="utf-8")
            all_findings.extend(inspect_python_source(source, path))
        except UnicodeDecodeError:
            all_findings.append(Finding(path, 0, "non-utf8 source file"))
        except SyntaxError as exc:
            all_findings.append(Finding(path, exc.lineno or 0, "syntax error"))

    for nb in nb_files:
        try:
            all_findings.extend(inspect_notebook(nb))
        except (UnicodeDecodeError, json.JSONDecodeError):
            all_findings.append(Finding(nb, 0, "invalid UTF-8/JSON notebook"))

    return all_findings, len(py_files) + len(nb_files)


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def self_test() -> int:
    failures: list[str] = []
    clean_sample = (
        "import gzip, io, zipfile\n"
        "from pathlib import Path\n"
        "def ok(p, zf):\n"
        "    with open(p, 'r', encoding='utf-8') as f:\n"
        "        _ = f.read()\n"
        "    with io.open('benchmark.csv', 'r', encoding='utf-8') as f2:\n"
        "        _ = f2.read()\n"
        "    with open(p, 'rb') as fb:\n"
        "        _ = fb.read()\n"
        "    with gzip.open('archive.gz') as gz:\n"
        "        _ = gz.read()\n"
        "    with zf.open('GLORIA_Rrs.csv') as zmember:\n"
        "        _ = zmember.read()\n"
        "    return Path(p).read_text(encoding='utf-8')\n"
    )
    bad_samples = {
        "bare_open.py": "def f(p):\n    return open(p).read()\n",
        "text_mode_open.py": "def f(p):\n    return open(p, 'w').write('x')\n",
        "io_open_b_in_name.py": "import io\ndef f():\n    return io.open('benchmark.csv').read()\n",
        "codecs_open_no_enc.py": "import codecs\ndef f():\n    return codecs.open('calib.txt', 'r').read()\n",
        "gzip_text_no_enc.py": "import gzip\ndef f():\n    return gzip.open('a.gz', 'rt').read()\n",
        "encoding_none.py": "def f(p):\n    return open(p, encoding=None).read()\n",
        "kwargs_bypass.py": "def f(p, kw):\n    return open(p, **kw).read()\n",
        "path_read_text.py": "from pathlib import Path\ndef f(p):\n    return Path(p).read_text()\n",
        "path_write_text.py": "from pathlib import Path\ndef f(p):\n    Path(p).write_text('x')\n",
        "path_open.py": "from pathlib import Path\ndef f(p):\n    return Path(p).open().read()\n",
    }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, count0 = check(root)
        if count0 != 0:
            failures.append("expected 0 scanned files on empty dir")

        _write(root, "clean.py", clean_sample)
        nb_clean = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title\n"]},
                {"cell_type": "code", "source": ["%matplotlib inline\n", "if True:\n", "    !echo ok\n", "from pathlib import Path\n", "Path('a.txt').read_text(encoding='utf-8')\n"]},
            ]
        }
        _write(root, "clean.ipynb", json.dumps(nb_clean))
        findings, count_clean = check(root)
        if findings or count_clean != 2:
            failures.append(f"clean samples failed: {[str(x) for x in findings]}")

        for filename, code in bad_samples.items():
            _write(root, filename, code)
        nb_bad = {
            "cells": [
                {"cell_type": "code", "source": ["open('notes.txt').read()\n"]},
            ]
        }
        _write(root, "bad_nb.ipynb", json.dumps(nb_bad))

        findings, _ = check(root)
        caught = {item.path.name for item in findings}
        for filename in list(bad_samples) + ["bad_nb.ipynb"]:
            if filename not in caught:
                failures.append(f"missed {filename}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, ".github/scripts/helper.py", bad_samples["bare_open.py"])
        _write(root, "venv-like/mod.py", bad_samples["path_read_text.py"])
        _write(root, "real_venv/mod_ignored.py", bad_samples["bare_open.py"])
        _write(root, "real_venv/pyvenv.cfg", "home = /usr/bin\n")
        findings, _ = check(root)
        names = {item.path.name for item in findings}
        if "helper.py" not in names:
            failures.append("skipped .github/ python file")
        if "mod.py" not in names:
            failures.append("skipped directory without pyvenv.cfg")
        if "mod_ignored.py" in names:
            failures.append("scanned real pyvenv.cfg environment")

    if failures:
        print("SELF-TEST FAILED: " + "; ".join(failures), file=sys.stderr)
        return 1
    print(
        f"self-test passed: empty refused, clean .py/.ipynb passed, {len(bad_samples) + 1} bad shapes caught (incl. io.open('benchmark.csv'), encoding=None, **kwargs, .ipynb)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    findings, scanned = check(args.root)
    if scanned == 0:
        print(f"ERROR: scanned zero Python/notebook files under {args.root}; refusing vacuous pass.", file=sys.stderr)
        return 2
    if findings:
        print(f"{len(findings)} text I/O call(s) missing explicit non-null encoding=:", file=sys.stderr)
        for item in findings:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"ok: all {scanned} Python/notebook file(s) declare explicit encoding= on text I/O")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
