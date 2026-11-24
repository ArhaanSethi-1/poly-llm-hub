"""Build a one-file desktop executable on native Windows or macOS."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if sys.platform not in ("win32", "darwin"):
        raise SystemExit("Build on Windows or macOS; PyInstaller does not cross-compile between these systems.")
    datas = [
        f"{ROOT / 'web'}{os.pathsep}web",
        f"{ROOT / 'catalog'}{os.pathsep}catalog",
    ]
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "Poly-LLM-Hub", "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyinstaller-work"),
        "--specpath", str(ROOT / "build" / "pyinstaller-spec"),
    ]
    for entry in datas:
        command.extend(("--add-data", entry))
    command.append(str(ROOT / "app.py"))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
