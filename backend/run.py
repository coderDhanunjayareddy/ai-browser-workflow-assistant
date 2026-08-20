"""Compatibility entry point for the one canonical local runtime.

Historically this file started a reload supervisor plus worker with local-dev
identity. That allowed it to compete with the validated runtime on port 8000 and
made an independently built extension appear falsely compatible. Keep the familiar
``python run.py`` command, but route it through the same launcher used for validation.
"""

from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    launcher = repo_root / "scripts" / "start-stabilization-runtime.ps1"
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
        ],
        cwd=repo_root,
        check=False,
    )
    sys.exit(completed.returncode)
