"""
Runs the full OpenFOAM meshing and solving pipeline for one case directory.

Pipeline:
  1. blockMesh  (C-mesh via project feature, no snappyHexMesh)
  2. simpleFoam

All commands source /usr/lib/openfoam/openfoam2412/etc/bashrc first.
"""

import subprocess
import sys
from pathlib import Path

FOAM_BASHRC = "/usr/lib/openfoam/openfoam2412/etc/bashrc"


def _run(cmd: str, cwd: str, label: str) -> bool:
    """Source OpenFOAM bashrc then run *cmd* in *cwd*. Returns True on success."""
    full = f'source "{FOAM_BASHRC}" && {cmd}'
    print(f"  [RUN] {label}", flush=True)
    result = subprocess.run(
        ["bash", "-c", full],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            print(f"    | {line}", flush=True)
    if result.returncode != 0:
        print(f"  [FAIL] {label} exited with code {result.returncode}", file=sys.stderr)
        return False
    print(f"  [OK] {label}", flush=True)
    return True


def run_pipeline(case_dir: str, airfoil: str) -> bool:
    """
    Execute the full mesh + solve pipeline inside *case_dir*.
    Returns True if every step succeeded.
    """
    cwd = str(Path(case_dir).resolve())
    steps = [
        ("blockMesh",  "blockMesh"),
        ("simpleFoam", "simpleFoam"),
    ]
    for cmd, label in steps:
        if not _run(cmd, cwd, label):
            return False
    return True


def run_pipeline_verbose(case_dir: str, airfoil: str, log_dir: str | None = None) -> bool:
    """
    Like run_pipeline but writes per-step log files to *log_dir* (defaults to case_dir/logs/).
    Uses pipefail so a crashing OpenFOAM command is not masked by tee's exit code.
    """
    cwd  = str(Path(case_dir).resolve())
    ldir = Path(log_dir) if log_dir else Path(cwd) / "logs"
    ldir.mkdir(parents=True, exist_ok=True)

    steps = [
        ("blockMesh",  "blockMesh"),
        ("simpleFoam", "simpleFoam"),
    ]

    for cmd, label in steps:
        log_path = ldir / f"{label}.log"
        # set -o pipefail: propagate the OpenFOAM exit code through the tee pipe
        full_cmd = (
            f'set -o pipefail && source "{FOAM_BASHRC}" && '
            f'{cmd} 2>&1 | tee "{log_path}"'
        )
        print(f"  [RUN] {label}  →  {log_path}", flush=True)
        result = subprocess.run(["bash", "-c", full_cmd], cwd=cwd)
        if result.returncode != 0:
            print(f"  [FAIL] {label} — exit code {result.returncode} (see {log_path})", file=sys.stderr)
            return False
        print(f"  [OK] {label}", flush=True)

    return True
