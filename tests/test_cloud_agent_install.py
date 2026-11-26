"""The Cloud Agent install script must not sync an unrelated directory."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT_CHECKOUT = Path("/agent/repos/hydrospectral-lab")


def _install_script() -> str:
    payload = json.loads((ROOT / ".cursor" / "environment.json").read_text(encoding="utf-8"))
    script = payload["install"]
    assert script.startswith("set -euo pipefail\n")
    return script


def _run(tmp_path: Path, cwd: Path, repo_root: str | None) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    bindir = tmp_path / "bin"
    home.mkdir()
    bindir.mkdir()
    mock = bindir / "uv"
    mock.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$PWD\" >> \"$HOME/uv-invocations\"\n"
        "printf '%s\\n' \"$*\" >> \"$HOME/uv-invocations\"\nexit 0\n",
        encoding="utf-8",
    )
    mock.chmod(0o755)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    if repo_root is None:
        env.pop("HYDROSPECTRAL_REPO_ROOT", None)
    else:
        env["HYDROSPECTRAL_REPO_ROOT"] = repo_root
    return subprocess.run(
        ["bash", "-c", _install_script()],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invocations(tmp_path: Path) -> str:
    stamp = tmp_path / "home" / "uv-invocations"
    if not stamp.exists():
        return ""
    return stamp.read_text(encoding="utf-8")


def test_install_script_parses() -> None:
    subprocess.run(["bash", "-n", "-c", _install_script()], check=True)


def test_refuses_unrelated_directory_before_any_uv_call(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "pyproject.toml").write_text('name = "other"\n', encoding="utf-8")
    missing = tmp_path / "missing-agent-checkout"

    result = _run(tmp_path, unrelated, str(missing))

    assert result.returncode == 1
    assert "refusing install" in result.stderr
    assert _invocations(tmp_path) == ""


def test_refuses_the_current_directory_when_the_agent_checkout_is_absent(tmp_path: Path) -> None:
    if AGENT_CHECKOUT.is_dir():
        pytest.skip("the agent checkout exists, so the default path is this repository")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    result = _run(tmp_path, unrelated, None)

    assert result.returncode == 1
    assert "refusing install" in result.stderr
    assert _invocations(tmp_path) == ""


def test_syncs_only_after_the_checkout_identifies_as_hydrospectral(tmp_path: Path) -> None:
    checkout = tmp_path / "hydrospectral-lab"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "hydrospectral"\n',
        encoding="utf-8",
    )
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    result = _run(tmp_path, unrelated, str(checkout))

    assert result.returncode == 0, result.stderr
    assert _invocations(tmp_path).splitlines() == [
        str(checkout),
        "sync --locked --group dev --python 3.12",
    ]
