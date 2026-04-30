#!/usr/bin/env python3
"""
openfoam_launcher.py
====================
Interactive CLI menu for OpenFOAM 2412 on Ubuntu 24 / WSL.
Handles: tutorial browsing, blockMesh, solver runs, case cleaning,
and real-time residual monitoring.

Usage:
    python3 openfoam_launcher.py
    alias foam-launch="python3 ~/OpenFOAM/scripts/openfoam_launcher.py"
"""

import os
import sys
import subprocess
import shutil
import time
from pathlib import Path

# ─────────────────────────────────────────────
# Colour helpers (no external deps)
# ─────────────────────────────────────────────
R  = "\033[91m"   # red
G  = "\033[92m"   # green
Y  = "\033[93m"   # yellow
B  = "\033[94m"   # blue
C  = "\033[96m"   # cyan
W  = "\033[97m"   # white
DIM = "\033[2m"
RESET = "\033[0m"
BOLD  = "\033[1m"

FOAM_SRC = "/usr/lib/openfoam/openfoam2412"
FOAM_TUTORIALS = os.path.join(FOAM_SRC, "tutorials")
USER_FOAM = os.path.expanduser("~/OpenFOAM")


def banner():
    print(f"""
{B}{BOLD}╔══════════════════════════════════════════════════════╗
║          OpenFOAM 2412  ·  Launcher v1.0             ║
║          Ubuntu 24  ·  WSL  ·  Python 3              ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def find_case_dir():
    """Return current directory if it looks like an OpenFOAM case."""
    cwd = Path.cwd()
    if (cwd / "system" / "controlDict").exists():
        return str(cwd)
    return None


def run_cmd(cmd, cwd=None, live=False):
    """
    Run a shell command.
    live=True  → stream stdout line-by-line (for solver monitoring).
    Returns (returncode, stdout_str).
    """
    if live:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        output_lines = []
        for line in proc.stdout:
            print(line, end="")
            output_lines.append(line)
        proc.wait()
        return proc.returncode, "".join(output_lines)
    else:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True
        )
        return result.returncode, result.stdout + result.stderr


# ─────────────────────────────────────────────
# Menu Actions
# ─────────────────────────────────────────────

def browse_tutorials():
    """List available tutorial categories and let user copy one."""
    if not os.path.isdir(FOAM_TUTORIALS):
        print(f"{R}Tutorials not found at {FOAM_TUTORIALS}{RESET}")
        print("Run: source /usr/lib/openfoam/openfoam2412/etc/bashrc")
        return

    categories = sorted([
        d for d in os.listdir(FOAM_TUTORIALS)
        if os.path.isdir(os.path.join(FOAM_TUTORIALS, d))
    ])

    print(f"\n{C}Available tutorial categories:{RESET}")
    for i, cat in enumerate(categories):
        print(f"  {DIM}{i+1:2d}{RESET}  {cat}")

    cat_idx = input(f"\n{Y}Enter category number (or Enter to cancel): {RESET}").strip()
    if not cat_idx.isdigit():
        return
    cat = categories[int(cat_idx) - 1]
    cat_path = os.path.join(FOAM_TUTORIALS, cat)

    cases = sorted([
        d for d in os.listdir(cat_path)
        if os.path.isdir(os.path.join(cat_path, d))
    ])

    print(f"\n{C}Cases in '{cat}':{RESET}")
    for i, case in enumerate(cases):
        print(f"  {DIM}{i+1:2d}{RESET}  {case}")

    case_idx = input(f"\n{Y}Enter case number to copy (or Enter to cancel): {RESET}").strip()
    if not case_idx.isdigit():
        return
    case = cases[int(case_idx) - 1]
    src = os.path.join(cat_path, case)
    dst = os.path.join(USER_FOAM, "run", case)

    if os.path.exists(dst):
        overwrite = input(f"{Y}Destination {dst} exists. Overwrite? (y/n): {RESET}").lower()
        if overwrite != "y":
            return
        shutil.rmtree(dst)

    shutil.copytree(src, dst)
    print(f"{G}✔  Copied to {dst}{RESET}")
    print(f"   cd {dst}")


def run_blockmesh():
    """Run blockMesh in the current or specified case directory."""
    case = find_case_dir() or input(f"{Y}Case directory path: {RESET}").strip()
    if not case:
        return
    print(f"\n{C}Running blockMesh in {case}{RESET}")
    rc, out = run_cmd("blockMesh", cwd=case, live=True)
    if rc == 0:
        print(f"\n{G}✔  blockMesh completed successfully.{RESET}")
    else:
        print(f"\n{R}✘  blockMesh failed (exit {rc}).{RESET}")


def run_solver():
    """Detect solver from controlDict and run it."""
    case = find_case_dir() or input(f"{Y}Case directory path: {RESET}").strip()
    if not case:
        return

    control = os.path.join(case, "system", "controlDict")
    solver = "simpleFoam"   # default
    try:
        with open(control) as f:
            for line in f:
                line = line.strip()
                if line.startswith("application"):
                    solver = line.split()[1].rstrip(";")
                    break
    except FileNotFoundError:
        print(f"{R}controlDict not found.{RESET}")
        return

    print(f"\n{C}Solver detected: {BOLD}{solver}{RESET}")
    cores = input(f"{Y}Number of cores (1 = serial, >1 = parallel): {RESET}").strip()
    cores = int(cores) if cores.isdigit() else 1

    if cores > 1:
        cmd = f"decomposePar -force && mpirun -np {cores} {solver} -parallel | tee log.{solver} && reconstructPar"
    else:
        cmd = f"{solver} | tee log.{solver}"

    print(f"\n{C}Launching: {cmd}{RESET}\n")
    rc, _ = run_cmd(cmd, cwd=case, live=True)
    status = f"{G}✔  Solver finished." if rc == 0 else f"{R}✘  Solver exited with code {rc}."
    print(f"\n{status}{RESET}")


def clean_case():
    """Remove processor*, time directories, and log files."""
    case = find_case_dir() or input(f"{Y}Case directory path: {RESET}").strip()
    if not case:
        return

    case_path = Path(case)
    removed = []

    # Processor directories
    for d in case_path.glob("processor*"):
        shutil.rmtree(d); removed.append(str(d))

    # Numeric time directories (keep 0/)
    for d in case_path.iterdir():
        if d.is_dir():
            try:
                val = float(d.name)
                if val > 0:
                    shutil.rmtree(d); removed.append(str(d))
            except ValueError:
                pass

    # Log files
    for f in case_path.glob("log.*"):
        f.unlink(); removed.append(str(f))

    # foam file
    for f in case_path.glob("*.foam"):
        f.unlink(); removed.append(str(f))

    if removed:
        print(f"\n{G}Removed:{RESET}")
        for r in removed:
            print(f"  {DIM}{r}{RESET}")
    else:
        print(f"{Y}Nothing to clean.{RESET}")


def monitor_residuals():
    """Tail solver log and show latest residuals for U, p, k, omega."""
    case = find_case_dir() or input(f"{Y}Case directory path: {RESET}").strip()
    if not case:
        return

    logs = list(Path(case).glob("log.*"))
    if not logs:
        print(f"{R}No log files found.{RESET}")
        return

    log = max(logs, key=lambda f: f.stat().st_mtime)
    print(f"\n{C}Monitoring {log.name} — Ctrl+C to stop{RESET}\n")

    residuals = {}
    try:
        with open(log) as f:
            f.seek(0, 2)  # seek to end
            while True:
                line = f.readline()
                if line:
                    # Parse lines like: "smoothSolver: Solving for Ux, ..."
                    if "Solving for" in line:
                        parts = line.split()
                        try:
                            field_idx = parts.index("for") + 1
                            field = parts[field_idx].rstrip(",")
                            # find residual after "Initial residual ="
                            if "Initial residual =" in line:
                                res_val = line.split("Initial residual =")[1].split(",")[0].strip()
                                residuals[field] = res_val
                        except (ValueError, IndexError):
                            pass
                    if "Time =" in line and residuals:
                        t = line.split("=")[1].strip()
                        res_str = "  ".join(f"{k}={v}" for k, v in residuals.items())
                        print(f"\r{G}t={t:<8}{RESET}  {res_str}", end="", flush=True)
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n\n{Y}Monitoring stopped.{RESET}")


def check_environment():
    """Verify OpenFOAM environment is sourced."""
    print(f"\n{C}Checking OpenFOAM environment...{RESET}\n")
    foam_var = os.environ.get("FOAM_INST_DIR") or os.environ.get("WM_PROJECT_DIR")
    if foam_var:
        print(f"{G}✔  FOAM environment detected: {foam_var}{RESET}")
    else:
        print(f"{R}✘  OpenFOAM not sourced.{RESET}")
        print(f"   Run: source {FOAM_SRC}/etc/bashrc")

    for tool in ["blockMesh", "simpleFoam", "snappyHexMesh", "paraFoam"]:
        path = shutil.which(tool)
        if path:
            print(f"{G}✔  {tool:<22}{DIM}{path}{RESET}")
        else:
            print(f"{R}✘  {tool} not found{RESET}")


# ─────────────────────────────────────────────
# Main Menu Loop
# ─────────────────────────────────────────────

MENU = [
    ("Browse & copy tutorials",     browse_tutorials),
    ("Run blockMesh",               run_blockmesh),
    ("Run solver (auto-detected)",  run_solver),
    ("Clean case directory",        clean_case),
    ("Monitor residuals (live)",    monitor_residuals),
    ("Check OpenFOAM environment",  check_environment),
    ("Exit",                        None),
]


def main():
    banner()
    while True:
        print(f"{BOLD}Main Menu{RESET}")
        for i, (label, _) in enumerate(MENU):
            marker = f"{B}{i+1}{RESET}"
            print(f"  [{marker}] {label}")

        choice = input(f"\n{Y}Select option: {RESET}").strip()
        if not choice.isdigit():
            continue
        idx = int(choice) - 1
        if idx < 0 or idx >= len(MENU):
            print(f"{R}Invalid choice.{RESET}")
            continue

        label, fn = MENU[idx]
        if fn is None:
            print(f"\n{G}Goodbye.{RESET}\n")
            sys.exit(0)

        print(f"\n{DIM}─── {label} ───{RESET}\n")
        fn()
        print()


if __name__ == "__main__":
    main()
