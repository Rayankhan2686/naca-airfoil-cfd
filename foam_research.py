#!/usr/bin/env python3
"""
foam_research.py – Main entry point for OpenFOAM airfoil CFD research.

Mode A: Research Mode    — NACA 0012 / 2412 / 4412 pipeline (options 1-5)
Mode B: Custom Mesh Mode — import any SolidWorks STL and run CFD
Mode C: Exit
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Allow imports from scripts/core/ regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from core import ui
from core.stl_generator   import generate_stl, SUPPORTED
from core.case_builder    import build_case
from core.mesh_runner     import run_pipeline_verbose, FOAM_BASHRC
from core.results_extractor import (
    extract_results, append_result, load_csv, filter_results, print_results
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR         = Path(__file__).parent
CASES_DIR           = SCRIPTS_DIR / "cases"
STL_DIR             = SCRIPTS_DIR / "stl"
RESULTS_CSV         = SCRIPTS_DIR / "results" / "airfoil_results.csv"
CUSTOM_AIRFOILS_DIR = Path.home() / "OpenFOAM" / "airfoils"


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


# ===========================================================================
# MODE A — Research Mode  (NACA 0012 / 2412 / 4412)
# ===========================================================================

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


# Exact research sweep — 0.5° resolution through 8°–12° stall region
_RESEARCH_ALPHAS = [
    -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7,
    8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12,
    13, 14, 15, 16, 17, 18, 19, 20,
]


def task_angle_sweep():
    ui.section("Angle Sweep")
    airfoil = ui.choose_airfoil()

    ui.info(f"Default research sweep ({len(_RESEARCH_ALPHAS)} angles, 0.5° steps at 8°–12°):")
    ui.info("  " + "  ".join(f"{a:g}°" for a in _RESEARCH_ALPHAS))

    use_default = ui.ask_yes_no("Use this exact list?", default=True)

    if use_default:
        alphas = _RESEARCH_ALPHAS
    else:
        alpha_min = ui.ask_float("Start angle (deg)", default=-4.0)
        alpha_max = ui.ask_float("End angle   (deg)", default=20.0)
        step      = ui.ask_float("Step size   (deg)", default=1.0)
        alphas = []
        a = alpha_min
        while a <= alpha_max + 1e-9:
            alphas.append(round(a, 6))
            a = round(a + step, 6)

    ui.info(f"Running {len(alphas)} angles for {_display(airfoil)} …")

    failed = []
    for alpha in alphas:
        ui.info(f"  α = {alpha:+g}°")
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

    if ui.ask_yes_no("Print L/D ratio table?", default=False):
        table_rows = [
            [r["airfoil"], r["alpha"], r["Cl"], r["Cd"],
             r["Cl"] / r["Cd"] if r["Cd"] != 0 else float("nan"),
             r["Cm"]]
            for r in filtered
        ]
        ui.print_table(["airfoil", "alpha", "Cl", "Cd", "L/D", "Cm"], table_rows, col_width=14)


# ---------------------------------------------------------------------------
# ParaView visualisation (shared by both modes)
# ---------------------------------------------------------------------------

_CASE_ROOTS = [CASES_DIR, Path.home() / "OpenFOAM" / "run"]


def _find_cases() -> list[Path]:
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

    foam_file = case_path / "case.foam"
    with open(foam_file, "w") as f:
        pass
    ui.success(f"Created {foam_file}")

    ui.info(f"Launching ParaView for {case_path.name} …")
    try:
        result = subprocess.run(["paraview", str(foam_file)], timeout=None)
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


def menu_foam_research():
    while True:
        ui.section("Research Mode  —  NACA Airfoils")
        print("    1) Generate STL")
        print("    2) Run single simulation")
        print("    3) Run angle sweep  (29 angles: -4° to 20°, 0.5° steps at 8°–12°)")
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


# ===========================================================================
# MODE B — Custom Mesh Mode  (any SolidWorks STL)
# ===========================================================================

_SOLIDWORKS_TIPS = (
    "  SolidWorks STL Export Settings:\n"
    "    File → Save As → STL (*.stl) → Options\n"
    "      Format   : ASCII  (binary is auto-converted, but ASCII is preferred)\n"
    "      Units    : Meters\n"
    "      Chord    : 1.0 m\n"
    "      Span     : 0.1 m\n"
    "      Resolution: Fine\n"
    "    Tick 'Save as closed solid' — the geometry MUST be watertight.\n"
    "    Recommended coordinate system:\n"
    "      X → chord direction (LE at x=0, TE at x=1)\n"
    "      Y → thickness / lift direction\n"
    "      Z → span direction (0 → 0.1 m)\n"
)


def task_import_stl():
    ui.section("Import Custom STL from SolidWorks")
    print()
    print(_SOLIDWORKS_TIPS)

    raw_path = input(f"  {ui._c(ui._C, 'STL file path')}: ").strip()
    if not raw_path:
        ui.warn("No path entered.")
        return
    src_path = Path(raw_path).expanduser().resolve()
    if not src_path.exists():
        ui.error(f"File not found: {src_path}")
        return

    name = input(f"  {ui._c(ui._C, 'Airfoil name (e.g. my_wing, delta_v2)')}: ").strip()
    if not name:
        ui.error("Airfoil name cannot be empty.")
        return
    name_key   = name.lower().replace(" ", "_")
    name_upper = name_key.upper()

    CUSTOM_AIRFOILS_DIR.mkdir(parents=True, exist_ok=True)
    dst_path = CUSTOM_AIRFOILS_DIR / f"{name_upper}.stl"

    # ---- Convert to ASCII STL with surfaceConvert -------------------------
    ui.info("Converting to ASCII STL with surfaceConvert …")
    conv_cmd = f'source "{FOAM_BASHRC}" && surfaceConvert "{src_path}" "{dst_path}"'
    try:
        conv = subprocess.run(
            ["bash", "-c", conv_cmd],
            capture_output=True, text=True, timeout=120,
        )
        if conv.returncode == 0:
            ui.success(f"Converted → {dst_path}")
        else:
            ui.warn("surfaceConvert returned non-zero; copying file directly.")
            detail = (conv.stderr or conv.stdout).strip()
            if detail:
                ui.warn(detail[:200])
            shutil.copy2(src_path, dst_path)
    except subprocess.TimeoutExpired:
        ui.warn("surfaceConvert timed out; copying file directly.")
        shutil.copy2(src_path, dst_path)
    except Exception as exc:
        ui.warn(f"surfaceConvert unavailable ({exc}); copying file directly.")
        shutil.copy2(src_path, dst_path)

    # ---- Check geometry with surfaceCheck --------------------------------
    ui.info("Checking geometry with surfaceCheck …")
    check_cmd = f'source "{FOAM_BASHRC}" && surfaceCheck "{dst_path}"'
    try:
        chk = subprocess.run(
            ["bash", "-c", check_cmd],
            capture_output=True, text=True, timeout=120,
        )
        output = (chk.stdout + chk.stderr).lower()
        bad_kws = (
            "open edge", "open edges", "open boundary",
            "non-closed", "not closed", "hole",
            "multiply connected",
        )
        found = [kw for kw in bad_kws if kw in output]
        if found:
            ui.warn("surfaceCheck detected potential geometry issues:")
            for kw in found:
                ui.warn(f"    '{kw}' found in surfaceCheck output")
            ui.warn("Meshing may fail. Repair the geometry in SolidWorks:")
            ui.warn("  – Ensure the body is a fully closed solid (no open edges or holes).")
            ui.warn("  – Use Tools → Check → Check Geometry before exporting.")
        else:
            ui.success("surfaceCheck: no open edges or holes detected.")
    except subprocess.TimeoutExpired:
        ui.warn("surfaceCheck timed out; skipping geometry check.")
    except Exception as exc:
        ui.warn(f"surfaceCheck unavailable ({exc}); skipping geometry check.")

    ui.success(f"Custom airfoil '{name}' saved as: {dst_path}")
    ui.info(f"Use options 2 or 3 in the Custom Mesh menu to run simulations.")


def _choose_custom_airfoil() -> str | None:
    """List STLs in CUSTOM_AIRFOILS_DIR and ask user to pick one. Returns key or None."""
    CUSTOM_AIRFOILS_DIR.mkdir(parents=True, exist_ok=True)
    stl_files = sorted(CUSTOM_AIRFOILS_DIR.glob("*.stl"))
    if not stl_files:
        ui.warn(f"No custom airfoils found in {CUSTOM_AIRFOILS_DIR}")
        ui.info("Import a SolidWorks STL first (Option 1).")
        return None

    ui.section("Select Custom Airfoil")
    for i, f in enumerate(stl_files, 1):
        print(f"    {i}) {f.stem}")

    while True:
        raw = input(f"  {ui._c(ui._C, f'Choice [1-{len(stl_files)}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(stl_files):
            chosen = stl_files[int(raw) - 1]
            airfoil_key = chosen.stem.lower()
            ui.success(f"Selected {chosen.stem}")
            return airfoil_key
        ui.warn(f"Enter a number between 1 and {len(stl_files)}.")


def _run_custom(airfoil: str, alpha_deg: float) -> bool:
    """Build case and run pipeline for a custom STL airfoil. Returns True on success."""
    stl_path = CUSTOM_AIRFOILS_DIR / f"{airfoil.upper()}.stl"
    if not stl_path.exists():
        ui.error(f"STL not found: {stl_path}")
        ui.info("Import the STL first using Option 1.")
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


def task_custom_run_single():
    ui.section("Run Single Simulation — Custom Airfoil")
    airfoil = _choose_custom_airfoil()
    if airfoil is None:
        return
    alpha_deg = ui.ask_float("Angle of attack (degrees)", default=0.0)
    _run_custom(airfoil, alpha_deg)


def task_custom_angle_sweep():
    ui.section("Angle Sweep — Custom Airfoil")
    airfoil = _choose_custom_airfoil()
    if airfoil is None:
        return

    alpha_min = ui.ask_float("Start angle (deg)", default=-4.0)
    alpha_max = ui.ask_float("End angle   (deg)", default=20.0)
    step      = ui.ask_float("Step size   (deg)", default=1.0)

    alphas: list[float] = []
    a = alpha_min
    while a <= alpha_max + 1e-9:
        alphas.append(round(a, 6))
        a = round(a + step, 6)

    ui.info(f"Running {len(alphas)} angles for {airfoil.upper()} …")

    failed = []
    for alpha in alphas:
        ui.info(f"  α = {alpha:+g}°")
        ok = _run_custom(airfoil, alpha)
        if not ok:
            failed.append(alpha)

    if failed:
        ui.warn(f"Failed angles: {failed}")
    else:
        ui.success("Sweep complete.")


def menu_custom_mesh():
    while True:
        ui.section("Custom Mesh Mode  —  SolidWorks STL")
        print("    1) Import Custom STL from SolidWorks")
        print("    2) Run Single Simulation on custom airfoil")
        print("    3) Run Angle Sweep on custom airfoil")
        print("    4) View Results")
        print("    5) Visualize in ParaView")
        print("    0) Back")

        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip()
        if choice == "1":
            task_import_stl()
        elif choice == "2":
            task_custom_run_single()
        elif choice == "3":
            task_custom_angle_sweep()
        elif choice == "4":
            task_view_results()
        elif choice == "5":
            task_visualize_paraview()
        elif choice == "0":
            break
        else:
            ui.warn("Invalid choice.")


# ===========================================================================
# Main entry point
# ===========================================================================

def main():
    ui.header("OpenFOAM Airfoil CFD Research  |  Re = 2×10⁵")
    while True:
        print()
        print(f"  {ui._c(ui._Y, 'A')}) Research Mode       — NACA 0012 / 2412 / 4412")
        print(f"  {ui._c(ui._Y, 'B')}) Custom Mesh Mode    — SolidWorks STL import & CFD")
        print(f"  {ui._c(ui._Y, 'C')}) Exit")
        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip().upper()
        if choice == "A":
            menu_foam_research()
        elif choice == "B":
            menu_custom_mesh()
        elif choice == "C":
            ui.info("Goodbye.")
            break
        else:
            ui.warn("Enter A, B, or C.")


if __name__ == "__main__":
    main()
