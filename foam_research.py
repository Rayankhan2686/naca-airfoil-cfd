#!/usr/bin/env python3
"""
foam_research.py – Main entry point for OpenFOAM airfoil CFD research.

Mode A: Research Mode    — NACA 0012 / 2412 / 4412 pipeline (options 1-5)
Mode B: Custom Mesh Mode — import any SolidWorks STL and run CFD
Mode C: Exit
"""

import csv
import datetime
import json
import os
import re
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
SCRIPTS_DIR           = Path(__file__).parent
CASES_DIR             = SCRIPTS_DIR / "cases"
STL_DIR               = SCRIPTS_DIR / "stl"
RESULTS_CSV           = SCRIPTS_DIR / "results" / "airfoil_results.csv"
CUSTOM_AIRFOILS_DIR   = Path.home() / "OpenFOAM" / "airfoils"
MESH_STATS_DIR        = Path.home() / "OpenFOAM" / "results"
RESEARCH_MESH_CONFIG  = SCRIPTS_DIR / "research_mesh_config.json"

# Directories scanned automatically when importing a SolidWorks STL
_STL_SCAN_DIRS = [
    Path("/mnt/c/Users/khanr/Downloads"),
    Path("/mnt/c/Users/khanr/Desktop"),
    Path("/mnt/c/Users/khanr/Documents"),
    CUSTOM_AIRFOILS_DIR,
]


def _fmt_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024.0:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:.1f} GB"


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

# ---------------------------------------------------------------------------
# Option 6 — Research mesh configuration
# ---------------------------------------------------------------------------
_MESH_DEFAULTS = {"nx": 200, "ny": 150}


def _load_research_mesh_config() -> dict:
    """Load nx/ny from research_mesh_config.json; fall back to defaults."""
    try:
        with open(RESEARCH_MESH_CONFIG) as f:
            data = json.load(f)
        return {
            "nx": max(100, min(500, int(data.get("nx", 200)))),
            "ny": max(80,  min(400, int(data.get("ny", 150)))),
        }
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return dict(_MESH_DEFAULTS)


def _save_research_mesh_config(cfg: dict):
    with open(RESEARCH_MESH_CONFIG, "w") as f:
        json.dump({"nx": cfg["nx"], "ny": cfg["ny"]}, f, indent=2)


def task_mesh_settings():
    ui.section("Mesh Settings")
    cfg = _load_research_mesh_config()

    while True:
        nx, ny = cfg["nx"], cfg["ny"]
        print(f"\n  Current research mesh settings:")
        print(f"    Cells in X (streamwise/chordwise) : {nx}  [100–500]")
        print(f"    Cells in Y (normal to flow)       : {ny}  [80–400]")
        print(f"    Cells in Z (span)                 : 1    [LOCKED]")

        if nx < 150 or ny < 100:
            ui.warn("Below minimum for publication quality results")
        if nx > 400 or ny > 300:
            ui.warn("Very fine mesh — each simulation will take over 30 minutes")

        print()
        print("    1) Change X cells (streamwise/chordwise)  [100–500]")
        print("    2) Change Y cells (normal to flow)         [80–400]")
        print("    3) Reset to publication defaults (200 × 150)")
        print("    0) Back")
        print()

        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip()

        if choice == "1":
            new_nx = ui.ask_int("Cells in X (streamwise/chordwise) [100-500]", default=nx)
            if not 100 <= new_nx <= 500:
                ui.warn(f"Value must be between 100 and 500. Got {new_nx}.")
                continue
            cfg["nx"] = new_nx
            _save_research_mesh_config(cfg)
            ui.success(f"Saved: X cells = {new_nx}")

        elif choice == "2":
            new_ny = ui.ask_int("Cells in Y (normal to flow) [80-400]", default=ny)
            if not 80 <= new_ny <= 400:
                ui.warn(f"Value must be between 80 and 400. Got {new_ny}.")
                continue
            cfg["ny"] = new_ny
            _save_research_mesh_config(cfg)
            ui.success(f"Saved: Y cells = {new_ny}")

        elif choice == "3":
            cfg = dict(_MESH_DEFAULTS)
            _save_research_mesh_config(cfg)
            ui.success("Reset to publication defaults: 200 × 150")

        elif choice == "0":
            break
        else:
            ui.warn("Enter 1, 2, 3, or 0.")


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

    mesh_cfg = _load_research_mesh_config()
    ui.info(f"Building case: {case_dir}  (mesh {mesh_cfg['nx']}×{mesh_cfg['ny']}×1)")
    try:
        build_case(case_dir, airfoil, alpha_deg, stl_src=str(stl_path),
                   nx=mesh_cfg["nx"], ny=mesh_cfg["ny"])
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


# ===========================================================================
# Option 6 — Mesh Statistics  (Research Mode)
# ===========================================================================

_NACA_AIRFOILS = [
    ("naca0012", "NACA 0012"),
    ("naca2412", "NACA 2412"),
    ("naca4412", "NACA 4412"),
]

# Regex fragment that matches a floating-point / scientific number
_NUM_RE = r"([\d]+\.[\d]+(?:[eE][+\-]?\d+)?)"


def _case_to_alpha(case_name: str) -> float | None:
    """
    Decode the angle of attack from a case directory name.
    Format: {airfoil}_a{p|m}{integer}_{decimal}
      naca0012_ap1_0  →  +1.0
      naca0012_am2_0  →  -2.0
      naca0012_ap8_5  →  +8.5
    """
    m = re.search(r"_a([pm])(\d+)_(\d+)$", case_name)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "m" else 1.0
    return sign * float(f"{m.group(2)}.{m.group(3)}")


def _find_mesh_cases(af_key: str) -> list[tuple[float, Path]]:
    """Return sorted (alpha, path) pairs for all completed cases of *af_key*."""
    prefix = af_key + "_a"
    found: list[tuple[float, Path]] = []
    for root in _CASE_ROOTS:
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or not d.name.startswith(prefix):
                continue
            if not (d / "constant" / "polyMesh").exists():
                continue
            alpha = _case_to_alpha(d.name)
            if alpha is not None:
                found.append((alpha, d))
    found.sort(key=lambda x: x[0])
    return found


def _parse_checkmesh(output: str, alpha: float) -> dict | None:
    """Extract mesh metrics from checkMesh stdout. Returns None if cells missing."""
    mc  = re.search(r"^\s+cells:\s+(\d+)",   output, re.M)
    mf  = re.search(r"^\s+faces:\s+(\d+)",   output, re.M)
    mp  = re.search(r"^\s+points:\s+(\d+)",  output, re.M)
    no  = re.search(r"Mesh non-orthogonality Max:\s*" + _NUM_RE, output)
    sk  = re.search(r"Max skewness\s*=\s*"   + _NUM_RE, output)
    mv  = re.search(r"Min volume\s*=\s*"     + _NUM_RE, output)
    asp = re.search(r"Max aspect ratio\s*=\s*" + _NUM_RE, output)

    if re.search(r"Mesh OK\.", output):
        quality = "PASS"
    else:
        fm = re.search(r"Failed\s+(\d+)\s+mesh check", output)
        quality = f"FAIL ({fm.group(1)})" if fm else "UNKNOWN"

    if not mc:
        return None

    return {
        "alpha":        alpha,
        "cells":        int(mc.group(1)),
        "faces":        int(mf.group(1))  if mf  else None,
        "points":       int(mp.group(1))  if mp  else None,
        "max_nonortho": float(no.group(1))  if no  else None,
        "max_skewness": float(sk.group(1))  if sk  else None,
        "min_volume":   float(mv.group(1))  if mv  else None,
        "max_aspect":   float(asp.group(1)) if asp else None,
        "quality":      quality,
    }


def _run_checkmesh_on_case(alpha: float, case_path: Path) -> dict | None:
    """Run (or re-use cached) checkMesh for one case and return parsed stats."""
    log_path = case_path / "logs" / "checkMesh.log"

    if log_path.exists():
        ui.info(f"  Using cached log: {log_path.relative_to(CASES_DIR.parent)}")
        output = log_path.read_text()
    else:
        ui.info(f"  Running checkMesh for {case_path.name} …")
        cmd = f'source "{FOAM_BASHRC}" && checkMesh -latestTime 2>&1'
        try:
            res = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(case_path),
                capture_output=True, text=True, timeout=120,
            )
            output = res.stdout
            if output.strip():
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(output)
        except subprocess.TimeoutExpired:
            ui.error(f"  checkMesh timed out for {case_path.name}")
            return None
        except Exception as exc:
            ui.error(f"  checkMesh error: {exc}")
            return None

    return _parse_checkmesh(output, alpha)


def _ansi_len(s: str) -> int:
    """Return visible length of a string, ignoring ANSI escape codes."""
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


def _pad_ansi(s: str, width: int) -> str:
    """Left-pad s to *width* visible characters, respecting ANSI escape codes."""
    return s + ' ' * max(0, width - _ansi_len(s))


def _print_mesh_stats_table(rows: list[dict]):
    """Print a formatted, colour-coded mesh statistics table."""
    cols   = ["Alpha",  "Cells", "Faces",  "Points", "NonOrtho", "Skewness", "MinVol",    "Aspect"]
    widths = [8,        8,       8,        8,        10,         10,         12,          10]

    def _fmt(r: dict) -> list:
        no_val = r["max_nonortho"]
        if no_val is not None:
            no_str = f"{no_val:.2f}"
            no_col = ui._G if no_val < 70.0 else ui._R
            no_cell = ui._c(no_col, no_str)
        else:
            no_cell = "N/A"
        return [
            f"{r['alpha']:+.1f}°",
            str(r["cells"])   if r["cells"]   is not None else "N/A",
            str(r["faces"])   if r["faces"]   is not None else "N/A",
            str(r["points"])  if r["points"]  is not None else "N/A",
            no_cell,
            f"{r['max_skewness']:.4f}"   if r["max_skewness"] is not None else "N/A",
            f"{r['min_volume']:.2e}"     if r["min_volume"]   is not None else "N/A",
            f"{r['max_aspect']:.2f}"     if r["max_aspect"]   is not None else "N/A",
        ]

    hdr = "  " + "  ".join(f"{h:<{w}}" for h, w in zip(cols, widths)) + "  Quality"
    sep = "  " + "-" * (len(hdr) - 2 + 14)
    print(f"\n{ui._c(ui._B + ui._C, hdr)}")
    print(sep)

    for r in rows:
        cells = _fmt(r)
        body = "  " + "  ".join(_pad_ansi(v, w) for v, w in zip(cells, widths))
        q = r.get("quality", "UNKNOWN")
        qcol = ui._G if q == "PASS" else (ui._R if "FAIL" in q else ui._Y)
        print(body + "  " + ui._c(qcol, q))
    print()


def _print_mesh_stats_explanation():
    """Print a plain-English explanation of each mesh quality metric."""
    print(ui._c(ui._B + ui._C, "\n  Mesh Quality Metrics Explained:"))
    print()
    print("    Non-Orthogonality  — angle (°) between the cell-centre-to-face vector")
    print("      and the face normal. Values under 70 = PASS (solver is stable).")
    print("      Over 70 = FAIL; high non-orthogonality causes numerical diffusion")
    print("      and can prevent the solver from converging.")
    print()
    print("    Skewness  — how distorted a cell face is from its ideal shape.")
    print("      Values below 4 are good. Higher skewness near the trailing edge")
    print("      or in tight corners can cause the solver to diverge.")
    print()
    print("    Min Volume  — the smallest cell volume in the mesh. Must be positive.")
    print("      A negative value means at least one cell is inside-out; the")
    print("      simulation cannot run until this is fixed.")
    print()
    print("    Max Aspect Ratio  — longest cell edge divided by shortest cell edge.")
    print("      High values (>1000) are normal in boundary-layer cells near the")
    print("      airfoil wall but should be low in the freestream region.")
    print()
    print("    Overall Quality  — OpenFOAM's built-in mesh check result.")
    print("      PASS = all internal checks passed. FAIL(n) = n checks failed;")
    print("      inspect the checkMesh log for details before running simulations.")
    print()


def _save_mesh_stats_csv(csv_path: Path, rows: list[dict]):
    fields = ["alpha", "cells", "faces", "points",
              "max_nonortho", "max_skewness", "min_volume", "max_aspect", "quality"]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def task_mesh_stats():
    ui.section("Mesh Statistics by Airfoil and Angle")

    # 1. Select airfoil
    for i, (_, name) in enumerate(_NACA_AIRFOILS, 1):
        print(f"    {i}) {name}")
    while True:
        raw = input(f"  {ui._c(ui._C, 'Select airfoil [1-3]')}: ").strip()
        if raw in ("1", "2", "3"):
            af_key, af_display = _NACA_AIRFOILS[int(raw) - 1]
            break
        ui.warn("Enter 1, 2, or 3.")

    # 2. Find completed cases
    cases = _find_mesh_cases(af_key)
    if not cases:
        ui.warn(f"No completed cases found for {af_display}.")
        ui.info(f"Cases are searched in: {' and '.join(str(r) for r in _CASE_ROOTS)}")
        return

    # 3. Let user pick one angle or ALL
    print()
    ui.info(f"{len(cases)} completed case(s) for {af_display}:")
    for i, (alpha, path) in enumerate(cases, 1):
        print(f"    {i}) α = {alpha:+.1f}°   [{path.name}]")
    print(f"    0) ALL angles — single summary table")
    print()

    while True:
        raw = input(f"  {ui._c(ui._C, f'Select [0-{len(cases)}]')}: ").strip()
        if raw.isdigit() and 0 <= int(raw) <= len(cases):
            break
        ui.warn(f"Enter a number between 0 and {len(cases)}.")

    selected = cases if int(raw) == 0 else [cases[int(raw) - 1]]

    # 4. Run checkMesh on each selected case
    print()
    stats: list[dict] = []
    for alpha, case_path in selected:
        row = _run_checkmesh_on_case(alpha, case_path)
        if row:
            stats.append(row)
        else:
            ui.warn(f"  Skipping {case_path.name} — could not extract stats.")

    if not stats:
        ui.error("No mesh statistics could be extracted.")
        return

    # 5. Print table
    _print_mesh_stats_table(stats)

    # 6. Save CSV
    csv_path = MESH_STATS_DIR / f"{af_key.upper()}_mesh_stats.csv"
    _save_mesh_stats_csv(csv_path, stats)
    ui.success(f"Saved mesh stats CSV → {csv_path}")

    # 7. Plain-English explanation
    _print_mesh_stats_explanation()


# ---------------------------------------------------------------------------
# ParaView visualisation (shared by both modes)
# ---------------------------------------------------------------------------

_CASE_ROOTS = [CASES_DIR, Path.home() / "OpenFOAM" / "run"]


def _decode_case_label(dirname: str) -> tuple[str, float] | None:
    """Parse nacaXXXX_ap/_am naming into (NACAXXXX, alpha). Returns None if unrecognised."""
    import re
    m = re.fullmatch(r"(naca\d+)_(ap|am)(\d+)_(\d+)", dirname)
    if not m:
        return None
    naca_raw, sign, integer, frac = m.groups()
    alpha = float(f"{integer}.{frac}")
    if sign == "am":
        alpha = -alpha
    return naca_raw.upper(), alpha


def _case_display_name(path: Path) -> str:
    """Return a human-readable label like 'NACA0012 (12°)' or the raw dirname."""
    decoded = _decode_case_label(path.name)
    if decoded is None:
        return path.name
    naca, alpha = decoded
    val = int(alpha) if alpha == int(alpha) else alpha
    return f"{naca} ({val}°)"


_EXCLUDED_PROFILES = {"naca2412"}


def _find_cases() -> list[Path]:
    cases = []
    for root in _CASE_ROOTS:
        if root.exists():
            for entry in sorted(root.iterdir()):
                if not entry.is_dir() or not (entry / "constant" / "polyMesh").exists():
                    continue
                decoded = _decode_case_label(entry.name)
                if decoded and decoded[0].lower() in _EXCLUDED_PROFILES:
                    continue
                cases.append(entry)

    def sort_key(p: Path):
        decoded = _decode_case_label(p.name)
        if decoded:
            naca, alpha = decoded
            return (0, naca, alpha)
        return (1, p.name, 0.0)

    return sorted(cases, key=sort_key)


def task_visualize_paraview():
    ui.section("Visualize in ParaView")

    cases = _find_cases()
    if not cases:
        ui.warn("No completed case directories found. Run a simulation first.")
        return

    prev_naca = None
    for i, c in enumerate(cases, 1):
        label = _case_display_name(c)
        decoded = _decode_case_label(c.name)
        if decoded:
            naca = decoded[0]
            if naca != prev_naca:
                print(f"\n  --- {naca} ---")
                prev_naca = naca
        print(f"    {i}) {label}")
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

    import os
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"      # force software rendering — required on WSLg
    env["MESA_GL_VERSION_OVERRIDE"] = "4.5" # advertise GL 4.5 so ParaView's pipeline loads

    ui.info(f"Launching ParaView for {_case_display_name(case_path)} …")
    ui.info("ParaView is opening in the background — may take 30–60 s on first load.")
    try:
        subprocess.Popen(["paraview", str(foam_file)], env=env)
        ui.success("ParaView launched.")
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
        print("    6) Mesh Settings  (cell counts for Research simulations)")
        print("    7) View Mesh Statistics by Airfoil and Angle")
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
        elif choice == "6":
            task_mesh_settings()
        elif choice == "7":
            task_mesh_stats()
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

    # ---- Auto-scan for STL files -----------------------------------------
    ui.info("Scanning for STL files …")
    found: list[Path] = []
    for scan_dir in _STL_SCAN_DIRS:
        if scan_dir.exists():
            hits = sorted(scan_dir.glob("*.stl"))
            if hits:
                ui.info(f"  {scan_dir}  ({len(hits)} file(s))")
            found.extend(hits)

    print()
    if found:
        name_w = max(len(p.name) for p in found)
        name_w = max(name_w, 24)
        hdr = f"  {'#':<4}  {'File':<{name_w}}  {'Size':>9}  Location"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for i, stl in enumerate(found, 1):
            stat    = stl.stat()
            sz      = _fmt_size(stat.st_size)
            loc     = str(stl.parent)
            print(f"  {i:<4}  {stl.name:<{name_w}}  {sz:>9}  {loc}")
        print()
        manual_idx = len(found) + 1
        print(f"  {manual_idx})  Enter path manually")
    else:
        ui.warn("No STL files found in the default scan locations.")
        manual_idx = 1
        print(f"  1)  Enter path manually")

    print()

    # ---- User selects a file ---------------------------------------------
    while True:
        raw = input(f"  {ui._c(ui._C, f'Choice [1-{manual_idx}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= manual_idx:
            break
        ui.warn(f"Enter a number between 1 and {manual_idx}.")

    choice = int(raw)
    if choice <= len(found):
        src_path = found[choice - 1]
    else:
        raw_path = input(f"  {ui._c(ui._C, 'Full path to STL file')}: ").strip()
        if not raw_path:
            ui.warn("No path entered.")
            return
        src_path = Path(raw_path).expanduser().resolve()
        if not src_path.exists():
            ui.error(f"File not found: {src_path}")
            return

    # ---- Confirm file details --------------------------------------------
    stat  = src_path.stat()
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d  %H:%M")
    print()
    print(f"  File     : {src_path.name}")
    print(f"  Full path: {src_path}")
    print(f"  Size     : {_fmt_size(stat.st_size)}")
    print(f"  Modified : {mtime}")
    print()

    # ---- Airfoil name ----------------------------------------------------
    name = input(f"  {ui._c(ui._C, 'Airfoil name (e.g. NACA6412, CUSTOM01)')}: ").strip()
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
        issues = [kw for kw in bad_kws if kw in output]
        if issues:
            ui.warn("surfaceCheck detected potential geometry issues:")
            for kw in issues:
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

    # ---- Final confirmation -----------------------------------------------
    final_stat = dst_path.stat()
    print()
    ui.success(f"'{name_upper}' is now available for simulation.")
    ui.info(f"  Saved to : {dst_path}")
    ui.info(f"  Size     : {_fmt_size(final_stat.st_size)}")
    ui.info("Use Option 2 or 3 in the Custom Mesh menu to run simulations.")


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
# Project Information
# ===========================================================================

def task_project_info():
    from core.case_builder import V, NU, RHO, CHORD, SPAN, AREF, K_INF, OMEGA_INF

    ui.header("Project Information")

    # ── Physics ──────────────────────────────────────────────────────────────
    ui.section("Flow Physics")
    RE = RHO * V * CHORD / (RHO * NU)
    MU = RHO * NU
    print(f"    {'Reynolds Number':<30} Re  = 2.00 × 10⁵")
    print(f"    {'Freestream Velocity':<30} U∞  = {V} m/s")
    print(f"    {'Air Density':<30} ρ   = {RHO} kg/m³")
    print(f"    {'Dynamic Viscosity':<30} μ   = {MU:.4e} Pa·s")
    print(f"    {'Kinematic Viscosity':<30} ν   = {NU:.4e} m²/s")
    print(f"    {'Chord Length':<30} c   = {CHORD} m")
    print(f"    {'Span':<30} b   = {SPAN} m")
    print(f"    {'Reference Area':<30} Aref= {AREF} m²  (chord × span)")

    # ── Turbulence ────────────────────────────────────────────────────────────
    ui.section("Turbulence Model  (kOmegaSST)")
    print(f"    {'Model':<30} kOmegaSST  (steady RANS)")
    print(f"    {'Freestream TKE':<30} k∞  = {K_INF:.3e} m²/s²")
    print(f"    {'Freestream Omega':<30} ω∞  = {OMEGA_INF} 1/s")
    print(f"    {'Turbulence Intensity':<30} ~0.1%  (low, typical wind-tunnel)")

    # ── Solver ────────────────────────────────────────────────────────────────
    ui.section("Solver Settings")
    print(f"    {'Solver':<30} simpleFoam  (steady incompressible)")
    print(f"    {'Max Iterations':<30} 3000")
    print(f"    {'nNonOrthogonalCorrectors':<30} 2")
    print(f"    {'Pressure solver':<30} GAMG + GaussSeidel")
    print(f"    {'Velocity solver':<30} smoothSolver + symGaussSeidel")
    print(f"    {'Default relaxation  U':<30} 0.3  (0.7 for difficult cases)")
    print(f"    {'Default relaxation  p':<30} 0.2  (0.3 for difficult cases)")
    print(f"    {'OpenFOAM version':<30} OpenFOAM 2412")

    # ── Mesh ─────────────────────────────────────────────────────────────────
    ui.section("Mesh (blockMesh C-mesh)")
    cfg = {}
    if RESEARCH_MESH_CONFIG.exists():
        import json
        with open(RESEARCH_MESH_CONFIG) as f:
            cfg = json.load(f)
    nx = cfg.get("nx", 200)
    ny = cfg.get("ny", 150)
    print(f"    {'Topology':<30} Structured C-mesh  (no snappyHexMesh)")
    print(f"    {'Far-field radius':<30} R = 20 m  (20 chord lengths)")
    print(f"    {'Wake extension':<30} x = 40 m  (40 chord lengths)")
    print(f"    {'Span cells':<30} 1  (true 2-D, empty BC)")
    print(f"    {'Chord-wise cells (nx)':<30} {nx}")
    print(f"    {'Wall-normal cells (ny)':<30} {ny}")
    print(f"    {'Wall grading':<30} 400× expansion to far-field")

    # ── Airfoils ──────────────────────────────────────────────────────────────
    ui.section("Airfoils in Study")
    airfoils = [
        ("NACA 0012", "0% camber,  12% thickness  — symmetric baseline"),
        ("NACA 2412", "2% camber at 40% chord,  12% thickness  — light camber"),
        ("NACA 4412", "4% camber at 40% chord,  12% thickness  — high camber"),
    ]
    for name, desc in airfoils:
        print(f"    {ui._c(ui._Y, name)}  {desc}")

    # ── Dataset status ────────────────────────────────────────────────────────
    ui.section("Dataset Status")
    if RESULTS_CSV.exists():
        import csv as _csv
        rows = list(_csv.DictReader(open(RESULTS_CSV)))
        airfoil_counts: dict[str, dict] = {}
        for r in rows:
            af = r["airfoil"]
            if af not in airfoil_counts:
                airfoil_counts[af] = {"total": 0, "reliable": 0}
            airfoil_counts[af]["total"] += 1
            if not r.get("note", "").strip():
                airfoil_counts[af]["reliable"] += 1
        if airfoil_counts:
            for af, counts in sorted(airfoil_counts.items()):
                print(f"    {_display(af):<12}  {counts['reliable']:>2} reliable  /  {counts['total']:>2} total data points")
        else:
            print("    No results yet.")
    else:
        print("    Results CSV not found.")

    # ── Paths ─────────────────────────────────────────────────────────────────
    ui.section("File Locations")
    print(f"    {'Cases directory':<30} {CASES_DIR}")
    print(f"    {'STL files':<30} {CUSTOM_AIRFOILS_DIR}")
    print(f"    {'Results CSV':<30} {RESULTS_CSV}")
    print(f"    {'Mesh config':<30} {RESEARCH_MESH_CONFIG}")

    # ── Git ───────────────────────────────────────────────────────────────────
    ui.section("Repository")
    try:
        import subprocess as _sp
        branch = _sp.check_output(
            ["git", "-C", str(SCRIPTS_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True, stderr=_sp.DEVNULL).strip()
        commit = _sp.check_output(
            ["git", "-C", str(SCRIPTS_DIR), "log", "-1", "--format=%h  %s"],
            text=True, stderr=_sp.DEVNULL).strip()
        print(f"    {'Branch':<30} {branch}")
        print(f"    {'Last commit':<30} {commit}")
    except Exception:
        print("    (git info unavailable)")

    print()
    input(f"  {ui._c(ui._C, 'Press Enter to return')} ")


# ===========================================================================
# Main entry point
# ===========================================================================

def main():
    ui.header("OpenFOAM Airfoil CFD Research  |  Re = 2×10⁵")
    while True:
        print()
        print(f"  {ui._c(ui._Y, 'A')}) Research Mode       — NACA 0012 / 2412 / 4412")
        print(f"  {ui._c(ui._Y, 'B')}) Custom Mesh Mode    — SolidWorks STL import & CFD")
        print(f"  {ui._c(ui._Y, 'I')}) Project Information — physics, solver, mesh, dataset status")
        print(f"  {ui._c(ui._Y, 'C')}) Exit")
        choice = input(f"  {ui._c(ui._C, 'Select')}: ").strip().upper()
        if choice == "A":
            menu_foam_research()
        elif choice == "B":
            menu_custom_mesh()
        elif choice == "I":
            task_project_info()
        elif choice == "C":
            ui.info("Goodbye.")
            break
        else:
            ui.warn("Enter A, B, I, or C.")


if __name__ == "__main__":
    main()
