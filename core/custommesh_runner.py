"""
custommesh_runner.py — Runs the full OpenFOAM meshing/solving pipeline for
CustomMesh cases, with per-step log scanning, automatic case cleanup on failure,
and automatic revert of custommesh_config.json to last_known_good.

This file is COMPLETELY INDEPENDENT from mesh_runner.py.
Do NOT import from, or modify, mesh_runner.py.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

FOAM_BASHRC = "/usr/lib/openfoam/openfoam2412/etc/bashrc"

# Patterns that indicate a fatal OpenFOAM error in a log file
_FATAL_PATTERNS = (
    "FOAM FATAL ERROR",
    "FOAM FATAL IO ERROR",
    "Segmentation fault",
    "Aborted",
    "Bus error",
    "Killed",
)

# ANSI codes for inline coloured output (no external import)
_R  = "\033[91m"   # red
_G  = "\033[92m"   # green
_Y  = "\033[93m"   # yellow
_RS = "\033[0m"    # reset
_USE_COLOR = sys.stdout.isatty()

def _cr(code, text): return f"{code}{text}{_RS}" if _USE_COLOR else text


# ---------------------------------------------------------------------------
# Log scanning
# ---------------------------------------------------------------------------

def _scan_log(log_path: Path) -> str | None:
    """Return the first fatal error line found in *log_path*, or None if clean."""
    if not log_path.exists():
        return None
    try:
        with open(log_path) as f:
            for line in f:
                stripped = line.strip()
                if any(pat in stripped for pat in _FATAL_PATTERNS):
                    return stripped
    except OSError:
        pass
    return None


def _hint_for_failure(step: str, error_line: str, cfg: dict) -> str | None:
    """Return a human-readable hint about which setting likely caused *step* to fail."""
    err = error_line.lower()
    lines = []

    if step == "blockMesh":
        if any(k in err for k in ("inconsistent", "invalid", "negative", "zero")):
            lines.append(
                f"  Domain geometry may be invalid: "
                f"inlet={cfg.get('inlet')}, outlet={cfg.get('outlet')}, "
                f"top_bottom={cfg.get('top_bottom')}."
            )
        else:
            lines.append(
                f"  Cell count ({cfg.get('nx')}×{cfg.get('ny')}×{cfg.get('nz')}) "
                f"or domain size may be causing blockMesh to fail."
            )

    elif step == "snappyHexMesh":
        if any(k in err for k in ("trisurface", "stl", "not found", "cannot open")):
            lines.append("  STL not found in constant/triSurface/. Re-import the airfoil STL.")
        elif cfg.get("refine_max", 0) > 2:
            lines.append(
                f"  refine_max={cfg.get('refine_max')} may be too high. "
                f"Try 0–2 for this geometry."
            )
        else:
            lines.append(
                "  Geometry may be outside the domain or not watertight. "
                "Check surfaceCheck output before running."
            )

    elif step == "simpleFoam":
        if cfg.get("end_time", 3000) < 500:
            lines.append(
                f"  end_time={cfg.get('end_time')} is very low — "
                f"solver may have diverged immediately."
            )
        else:
            lines.append(
                "  Mesh quality from snappyHexMesh may be too poor for simpleFoam. "
                "Try lowering refinement or using a cleaner STL."
            )

    return "\n".join(lines) if lines else None


# ---------------------------------------------------------------------------
# Config revert helper
# ---------------------------------------------------------------------------

def revert_config(config_path: Path):
    """Revert 'current' in custommesh_config.json back to 'last_known_good'."""
    if not config_path.exists():
        return
    try:
        with open(config_path) as f:
            data = json.load(f)
        data["current"] = dict(data.get("last_known_good", data.get("current", {})))
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        print(f"  [WARN] Could not revert config: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline_safe(
    case_dir: str,
    airfoil: str,
    config_path: Path,
) -> tuple[bool, str | None]:
    """
    Run surfaceFeatureExtract → blockMesh → snappyHexMesh → simpleFoam.

    Returns (True, None) on full success.
    On any failure:
      - Prints the offending log line in red
      - Prints a hint about which setting likely caused it
      - Deletes the corrupt case directory
      - Reverts config current → last_known_good
      - Prints green "Settings reverted…" message
      - Returns (False, error_message)
    """
    cwd  = str(Path(case_dir).resolve())
    ldir = Path(cwd) / "logs"
    ldir.mkdir(parents=True, exist_ok=True)

    # Load current config for hint messages
    cfg: dict = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = json.load(f).get("current", {})
        except Exception:
            pass

    steps = [
        ("surfaceFeatureExtract",    "surfaceFeatureExtract"),
        ("blockMesh",                "blockMesh"),
        ("snappyHexMesh -overwrite", "snappyHexMesh"),
        ("simpleFoam",               "simpleFoam"),
    ]

    for cmd, label in steps:
        log_path = ldir / f"{label}.log"
        full_cmd = (
            f'set -o pipefail && source "{FOAM_BASHRC}" && '
            f'{cmd} 2>&1 | tee "{log_path}"'
        )
        print(f"  [RUN] {label}  →  {log_path.name}", flush=True)
        result = subprocess.run(["bash", "-c", full_cmd], cwd=cwd)

        # Scan log regardless of returncode (some FOAM errors don't set exit code)
        error_line = _scan_log(log_path)

        if result.returncode != 0 or error_line:
            err_msg = error_line or f"{label} exited with code {result.returncode}"

            print(file=sys.stderr)
            print(_cr(_R, f"  [FAIL] {label}"), file=sys.stderr)
            print(_cr(_R, f"  Error: {err_msg}"), file=sys.stderr)

            hint = _hint_for_failure(label, err_msg, cfg)
            if hint:
                print(_cr(_Y, hint), file=sys.stderr)

            # Delete corrupt case
            case_path = Path(case_dir)
            if case_path.exists():
                try:
                    shutil.rmtree(case_path)
                    print(f"  Deleted corrupt case: {case_path.name}", file=sys.stderr)
                except Exception as exc:
                    print(f"  Could not delete case: {exc}", file=sys.stderr)

            # Revert config
            revert_config(config_path)
            print(_cr(_G, "  Settings reverted to default 100x80x1. You can try again now."))

            return False, err_msg

        print(f"  [OK] {label}", flush=True)

    return True, None
