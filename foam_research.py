#!/usr/bin/env python3
"""
foam_research.py – Main entry point for NACA airfoil CFD research.

Menu A: FOAM Airfoil Research
  1. Generate STL
  2. Run single simulation
  3. Run angle sweep
  4. View results
B. Exit
"""

import os
import subprocess
import sys
from pathlib import Path

# Allow imports from scripts/core/ regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from core import ui
from core.stl_generator   import generate_stl, SUPPORTED
from core.case_builder    import build_case
from core.mesh_runner     import run_pipeline_verbose
from core.results_extractor import (
    extract_results, append_result, load_csv, filter_results, print_results
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR  = Path(__file__).parent
CASES_DIR    = SCRIPTS_DIR / "cases"
STL_DIR      = SCRIPTS_DIR / "stl"
RESULTS_CSV  = SCRIPTS_DIR / "results" / "airfoil_results.csv"


# ---------------------------------------------------------------------------
# Helper: resolve airfoil display name
# ---------------------------------------------------------------------------
_DISPLAY = {
    "naca0012": "NACA 0012",
    "naca2412": "NACA 2412",
    "naca4412": "NACA 4412",
}


def _display(key: str) -> str:
    return _DISPLAY.get(key, key.upper())


# ---------------------------------------------------------------------------
# Sub-tasks
# ---------------------------------------------------------------------------

def task_generate_stl():
    ui.section("Generate STL")
    airfoil = ui.choose_airfoil()
    n_pts   = ui.ask_int("Profile points per surface", default=100)
    ui.info(f"Generating STL for {_display(airfoil)} …")
    STL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        path = generate_stl(airfoil, str(STL_DIR), n_pts=n_pts, span=0.1)
        ui.success(f"STL written to: {path}")
    except Exception as exc:
        ui.error(str(exc))


def task_run_single():
    ui.section("Run Single Simulation")
    airfoil   = ui.choose_airfoil()
    alpha_deg = ui.ask_float("Angle of attack (degrees)", default=0.0)
    _run_one(airfoil, alpha_deg)


def _run_one(airfoil: str, alpha_deg: float) -> bool:
    """Build case, run pipeline, extract and save results. Returns True on success."""
    stl_path = STL_DIR / f"{airfoil.upper()}.stl"
    if not stl_path.exists():
        ui.warn(f"STL not found at {stl_path}. Generating …")
        STL_DIR.mkdir(parents=True, exist_ok=True)
        try:
            generate_stl(airfoil, str(STL_DIR), n_pts=100, span=0.1)
        except Exception as exc:
            ui.error(f"STL generation failed: {exc}")
            return False

    case_name = f"{airfoil}_a{alpha_deg:+.1f}".replace("+", "p").replace("-", "m").replace(".", "_")
    case_dir  = str(CASES_DIR / case_name)

    ui.info(f"Building case: {case_dir}")
    try:
        build_case(case_dir, airfoil, alpha_deg, stl_src=str(stl_path))
    except Exception as exc:
        ui.error(f"Case build failed: {exc}")
        return False

    ui.info("Running meshing and solver pipeline …")
    success = run_pipeline_verbose(case_dir, airfoil)
    if not success:
        ui.error("Pipeline failed. Check logs/ inside the case directory.")
        return False

    ui.info("Extracting results …")
    result = extract_results(case_dir, airfoil, alpha_deg)
    if result is None:
        ui.warn("Could not extract coefficients from postProcessing output.")
        return False

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    append_result(str(RESULTS_CSV), result)
    ui.success(
        f"α={alpha_deg:.1f}°  Cl={result['Cl']:.4f}  "
        f"Cd={result['Cd']:.4f}  Cm={result['Cm']:.4f}"
    )
    return True


def task_angle_sweep():
    ui.section("Angle Sweep")
    airfoil   = ui.choose_airfoil()
    alpha_min = ui.ask_float("Start angle (deg)", default=-5.0)
    alpha_max = ui.ask_float("End angle   (deg)", default=10.0)
    step      = ui.ask_float("Step size   (deg)", default=1.0)

    alphas = []
    a = alpha_min
    while a <= alpha_max + 1e-9:
        alphas.append(round(a, 6))
        a += step

    ui.info(f"Running {len(alphas)} angles for {_display(airfoil)} …")
    failed = []
    for alpha in alphas:
        ui.info(f"  α = {alpha:+.1f}°")
        ok = _run_one(airfoil, alpha)
        if not ok:
            failed.append(alpha)

    if failed:
        ui.warn(f"Failed angles: {failed}")
    else:
        ui.success("Sweep complete.")


def task_view_results():
    ui.section("View Results")
    rows = load_csv(str(RESULTS_CSV))
    if not rows:
        ui.warn("No results found. Run simulations first.")
        return

    print("  Filter by airfoil? (leave blank for all)")
    airfoils = sorted({r["airfoil"] for r in rows})
    for i, a in enumerate(airfoils, 1):
        print(f"    {i}) {_display(a)}")
    print(f"    0) All")

    raw = input("  Choice: ").strip()
    selected = None
    if raw.isdigit() and int(raw) != 0:
        idx = int(raw) - 1
        if 0 <= idx < len(airfoils):
            selected = airfoils[idx]

    filtered = filter_results(rows, selected)
    print_results(filtered)

    # Offer to print as table
    if ui.ask_yes_no("Print L/D ratio table?", default=False):
        table_rows = [
            [r["airfoil"], r["alpha"], r["Cl"], r["Cd"],
             r["Cl"] / r["Cd"] if r["Cd"] != 0 else float("nan"),
             r["Cm"]]
            for r in filtered
        ]
        ui.print_table(["airfoil", "alpha", "Cl", "Cd", "L/D", "Cm"], table_rows, col_width=14)


# ---------------------------------------------------------------------------
# ParaView visualisation
# ---------------------------------------------------------------------------

# Both the scripts/cases/ directory and the legacy ~/OpenFOAM/run/ directory
_CASE_ROOTS = [CASES_DIR, Path.home() / "OpenFOAM" / "run"]


def _find_cases() -> list[Path]:
    """Return all case directories that contain a constant/polyMesh subdirectory."""
    cases = []
    for root in _CASE_ROOTS:
        if root.exists():
            for entry in sorted(root.iterdir()):
                if entry.is_dir() and (entry / "constant" / "polyMesh").exists():
                    cases.append(entry)
    return cases


def task_visualize_paraview():
    ui.section("Visualize in ParaView")

    cases = _find_cases()
    if not cases:
        ui.warn("No completed case directories found. Run a simulation first.")
        return

    for i, c in enumerate(cases, 1):
        print(f"    {i}) {c.name}  ({c.parent.name}/)")
    print(f"    0) Back")

    while True:
        raw = input(f"  {ui._c(ui._C, 'Select case')}: ").strip()
        if raw == "0":
            return
        if raw.isdigit() and 1 <= int(raw) <= len(cases):
            case_path = cases[int(raw) - 1]
            break
        ui.warn(f"Enter a number between 0 and {len(cases)}.")

    # Always create/overwrite the .foam trigger file
    foam_file = case_path / "case.foam"
    with open(foam_file, "w") as f:
        pass
    ui.success(f"Created {foam_file}")

    ui.info(f"Launching ParaView for {case_path.name} …")
    try:
        result = subprocess.run(
            ["paraview", str(foam_file)],
            timeout=None,
        )
        if result.returncode != 0:
            ui.warn(f"ParaView exited with code {result.returncode}.")
    except FileNotFoundError:
        ui.error("ParaView is not installed.")
        ui.info("Install it with:  sudo apt install paraview")
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("display", "xcb", "x server", "wayland", "cannot connect")):
            ui.error("ParaView could not open a window.")
            ui.info("You need Windows 11 with WSLg, or an X server such as VcXsrv on Windows 10.")
            ui.info("With VcXsrv running: export DISPLAY=:0  before launching this script.")
        else:
            ui.error(f"Unexpected error launching ParaView: {exc}")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def menu_foam_research():
    while True:
        ui.section("FOAM Airfoil Research")
        print("    1) Generate STL")
        print("    2) Run single simulation")
        print("    3) Run angle sweep  (-5° to +10° default)")
        print("    4) View results")
        print("    5) Visualize in ParaView")
        print("    0) Back")

        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip()
        if choice == "1":
            task_generate_stl()
        elif choice == "2":
            task_run_single()
        elif choice == "3":
            task_angle_sweep()
        elif choice == "4":
            task_view_results()
        elif choice == "5":
            task_visualize_paraview()
        elif choice == "0":
            break
        else:
            ui.warn("Invalid choice.")


def main():
    ui.header("OpenFOAM NACA Airfoil Research  |  Re = 2×10⁵")
    while True:
        print()
        print(f"  {ui._c(ui._Y, 'A')}) FOAM Airfoil Research")
        print(f"  {ui._c(ui._Y, 'B')}) Exit")
        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip().upper()
        if choice == "A":
            menu_foam_research()
        elif choice == "B":
            ui.info("Goodbye.")
            break
        else:
            ui.warn("Enter A or B.")


if __name__ == "__main__":
    main()
