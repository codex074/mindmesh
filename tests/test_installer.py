from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_installer_registers_command_and_updates_path(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    install_dir = tmp_path / "commands with spaces"
    env = {
        **os.environ,
        "HOME": str(fake_home),
        "SHELL": "/bin/zsh",
        "MINDMESH_BIN_DIR": str(install_dir),
    }
    env["PATH"] = "/usr/bin:/bin"

    result = subprocess.run(
        [str(root / "install.sh"), "--help"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    command = install_dir / "mindmesh"
    assert command.is_symlink()
    assert command.resolve() == root / "mindmesh"
    profile = (fake_home / ".zshrc").read_text()
    assert "commands\\ with\\ spaces" in profile
    assert "usage: mindmesh [--deep]" in result.stdout
