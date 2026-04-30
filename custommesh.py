#!/usr/bin/env python3
"""
custommesh.py — Standalone CustomMesh program for SolidWorks STL → OpenFOAM CFD.

Completely independent from foam_research.py and the research pipeline.
Never modifies case_builder.py, mesh_runner.py, or results_extractor.py.

Launch:  custommesh        (alias in ~/.bashrc)
      or  python3 ~/OpenFOAM/scripts/custommesh.py
"""

import csv
import datetime
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow imports from scripts/core/
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from core.custommesh_builder import build_case, DEFAULTS
from core.custommesh_runner  import run_pipeline_safe, revert_config

# ---------------------------------------------------------------------------
# Paths  (ALL separate from the research pipeline)
# ---------------------------------------------------------------------------
SCRIPTS_DIR    = Path(__file__).parent
CONFIG_PATH    = SCRIPTS_DIR / "custommesh_config.json"
CASES_DIR      = SCRIPTS_DIR / "cases"
CUSTOM_STL_DIR = Path.home() / "OpenFOAM" / "airfoils" / "custom"
RESULTS_DIR    = Path.home() / "OpenFOAM" / "results" / "custom"
RESULTS_CSV    = RESULTS_DIR / "custom_results.csv"
FOAM_BASHRC    = "/usr/lib/openfoam/openfoam2412/etc/bashrc"

STL_SCAN_DIRS = [
    Path("/mnt/c/Users/khanr/Downloads"),
    Path("/mnt/c/Users/khanr/Desktop"),
    Path("/mnt/c/Users/khanr/Documents"),
    Path.home() / "OpenFOAM" / "airfoils",
]

_NACA_KEYS        = {"naca0012", "naca2412", "naca4412"}
_NACA_DISPLAY_MAP = {"naca0012": "NACA 0012", "naca2412": "NACA 2412", "naca4412": "NACA 4412"}
_CASE_SCAN_ROOTS  = [CASES_DIR, Path.home() / "OpenFOAM" / "run"]
_NUM_RE_CM        = r"([\d]+\.[\d]+(?:[eE][+\-]?\d+)?)"

_SOLIDWORKS_TIPS = (
    "  SolidWorks STL Export Settings:\n"
    "    File → Save As → STL (*.stl) → Options\n"
    "      Format    : ASCII  (binary is auto-converted)\n"
    "      Units     : Meters\n"
    "      Chord     : 1.0 m   (leading edge at x=0, trailing edge at x=1)\n"
    "      Span      : 0.1 m   (Z from 0 to 0.1)\n"
    "      Resolution: Fine\n"
    "    Tick 'Save as closed solid' — geometry MUST be fully watertight.\n"
)

# ---------------------------------------------------------------------------
# Inline colour / UI  (no import from core.ui)
# ---------------------------------------------------------------------------
_G  = "\033[92m"
_C  = "\033[96m"
_Y  = "\033[93m"
_R  = "\033[91m"
_B  = "\033[1m"
_RS = "\033[0m"
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RS}" if _USE_COLOR else text


def _header(title: str):
    bar = "=" * 62
    print(f"\n{_c(_B + _C, bar)}")
    print(_c(_B + _C, f"  {title}"))
    print(_c(_B + _C, bar))


def _section(title: str):
    print(f"\n{_c(_B + _G, '--- ' + title + ' ---')}")


def _info(msg: str):
    print(f"  {_c(_C, '>')} {msg}")


def _success(msg: str):
    print(f"  {_c(_G, '[OK]')} {msg}")


def _warn(msg: str):
    print(f"  {_c(_Y, '[WARN]')} {msg}", file=sys.stderr)


def _error(msg: str):
    print(f"  {_c(_R, '[ERROR]')} {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"  {_c(_C, prompt + f' [{default}]')}: ").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            _warn("Enter a valid integer.")


def _ask_float(prompt: str, default: float) -> float:
    while True:
        raw = input(f"  {_c(_C, prompt + f' [{default}]')}: ").strip()
        if raw == "":
            return default
        try:
            return float(raw)
        except ValueError:
            _warn("Enter a valid number.")


def _fmt_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024.0:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:.1f} GB"


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

def _ensure_config():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        _save_config({"current": dict(DEFAULTS), "last_known_good": dict(DEFAULTS)})


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"current": dict(DEFAULTS), "last_known_good": dict(DEFAULTS)}


def _save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _get_cfg() -> dict:
    return _load_config()["current"]


def _revert_to_lkg():
    data = _load_config()
    data["current"] = dict(data.get("last_known_good", DEFAULTS))
    _save_config(data)


def _update_lkg():
    """Call after a successful end-to-end simulation."""
    data = _load_config()
    data["last_known_good"] = dict(data["current"])
    _save_config(data)


# ---------------------------------------------------------------------------
# Settings display / validation / estimation
# ---------------------------------------------------------------------------

def _show_settings(cfg: dict):
    w = 44
    print(f"  {_c(_B + _C, f'Setting{'':<{w-7}}Value')}")
    print("  " + "-" * (w + 10))
    rows = [
        ("Cells X (streamwise)",                  cfg["nx"]),
        ("Cells Y (normal to flow)",               cfg["ny"]),
        ("Cells Z (span, 1 = 2D)",                 cfg["nz"]),
        ("Inlet upstream distance (chord lengths)", cfg["inlet"]),
        ("Outlet downstream distance (chords)",     cfg["outlet"]),
        ("Top / bottom distance (chords)",          cfg["top_bottom"]),
        ("snappyHexMesh refinement min",            cfg["refine_min"]),
        ("snappyHexMesh refinement max",            cfg["refine_max"]),
        ("Solver iterations  (endTime)",            cfg["end_time"]),
    ]
    for label, val in rows:
        print(f"  {label:<{w}} {val:>6}")


def _validate_settings(cfg: dict) -> list[str]:
    warnings = []
    nx, ny = cfg["nx"], cfg["ny"]
    if nx < 50:
        warnings.append(f"X cells={nx} < 50: Too coarse — mesh may fail to capture airfoil geometry.")
    if nx > 300:
        warnings.append(f"X cells={nx} > 300: Very fine mesh — simulation will take several hours.")
    if ny < 40:
        warnings.append(f"Y cells={ny} < 40: Too coarse in Y — boundary layer may be inaccurate.")
    if ny > 200:
        warnings.append(f"Y cells={ny} > 200: Very fine — will be very slow.")
    if cfg["refine_max"] > 3:
        warnings.append(f"refine_max={cfg['refine_max']} > 3: High refinement — snappyHexMesh will take a long time.")
    if cfg["end_time"] < 500:
        warnings.append(f"endTime={cfg['end_time']} < 500: Results may not converge.")
    if cfg["refine_min"] > cfg["refine_max"]:
        warnings.append(f"refine_min ({cfg['refine_min']}) > refine_max ({cfg['refine_max']}): Invalid range.")
    if cfg["inlet"] < 5:
        warnings.append(f"inlet={cfg['inlet']} chord lengths is very short — upstream boundary effects likely.")
    if cfg["outlet"] < 5:
        warnings.append(f"outlet={cfg['outlet']} chord lengths is very short — wake may not be captured.")
    return warnings


def _estimate(cfg: dict) -> tuple[int, str]:
    base = cfg["nx"] * cfg["ny"] * cfg["nz"]
    ref_mult = max(1, 2 ** cfg["refine_max"])
    total = base * ref_mult
    iter_factor = cfg["end_time"] / 3000.0
    solve_min = max(1, round(total * iter_factor / 2000))
    mesh_min  = max(1, round(total / 40000) + cfg["refine_max"])
    total_min = 2 + mesh_min + solve_min
    if total_min < 60:
        time_str = f"~{total_min} minutes"
    else:
        hrs, mins = divmod(total_min, 60)
        time_str = f"~{hrs}h {mins}m"
    return total, time_str


def _pre_run_check() -> dict:
    """
    Show settings, validate, ask user to confirm.
    Returns the cfg dict to use (may be reverted to LKG if user declines).
    """
    cfg = _get_cfg()
    warnings = _validate_settings(cfg)
    cells, time_str = _estimate(cfg)

    print()
    _info("Mesh settings for this simulation:")
    _show_settings(cfg)
    print()
    _info(f"Estimated cells:           ~{cells:,}")
    _info(f"Estimated simulation time: {time_str}")

    if warnings:
        print()
        for w in warnings:
            _warn(w)
        print()
        ans = input(f"  {_c(_Y, 'Continue with these settings? [y/N]')}: ").strip().lower()
        if ans not in ("y", "yes"):
            _revert_to_lkg()
            cfg = _get_cfg()
            _info("Reverted to last_known_good settings:")
            _show_settings(cfg)

    return cfg


# ---------------------------------------------------------------------------
# Results (inline CSV — no import from results_extractor.py)
# ---------------------------------------------------------------------------
_CSV_COLS = ["airfoil", "alpha", "Cl", "Cd", "Cm"]


def _extract_results(case_dir: str, airfoil: str, alpha_deg: float) -> dict | None:
    base = Path(case_dir) / "postProcessing" / "forceCoeffs"
    if not base.exists():
        return None
    dat = None
    for sub in sorted(base.iterdir()):
        candidate = sub / "coefficient.dat"
        if candidate.exists():
            dat = candidate
            break
    if dat is None:
        return None
    last = None
    with open(dat) as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                last = s
    if last is None:
        return None
    try:
        parts = last.split()
        return {
            "airfoil": airfoil.lower(),
            "alpha":   float(alpha_deg),
            "Cl":      float(parts[4]),
            "Cd":      float(parts[1]),
            "Cm":      float(parts[7]),
        }
    except (IndexError, ValueError):
        return None


def _load_results() -> list[dict]:
    if not RESULTS_CSV.exists():
        return []
    try:
        with open(RESULTS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                rows.append({
                    "airfoil": row["airfoil"],
                    "alpha":   float(row["alpha"]),
                    "Cl":      float(row["Cl"]),
                    "Cd":      float(row["Cd"]),
                    "Cm":      float(row["Cm"]),
                })
        return rows
    except Exception:
        return []


def _save_results(rows: list[dict]):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLS)
        writer.writeheader()
        writer.writerows(rows)


def _append_result(result: dict):
    rows = _load_results()
    key  = (result["airfoil"], float(result["alpha"]))
    rows = [r for r in rows if (r["airfoil"], r["alpha"]) != key]
    rows.append(result)
    rows.sort(key=lambda r: (r["airfoil"], r["alpha"]))
    _save_results(rows)


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def _run_one(airfoil: str, alpha_deg: float, cfg: dict) -> bool:
    stl_path = CUSTOM_STL_DIR / f"{airfoil.upper()}.stl"
    if not stl_path.exists():
        _error(f"STL not found: {stl_path}")
        _info("Import the airfoil STL first (Option A).")
        return False

    case_name = (
        f"{airfoil}_a{alpha_deg:+.1f}"
        .replace("+", "p").replace("-", "m").replace(".", "_")
    )
    case_dir = CASES_DIR / case_name
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    _info(f"Building case: {case_dir.name}")
    try:
        build_case(str(case_dir), airfoil, alpha_deg, stl_src=str(stl_path), cfg=cfg)
    except Exception as exc:
        _error(f"Case build failed: {exc}")
        return False

    _info("Running meshing and solver pipeline …")
    success, err_msg = run_pipeline_safe(str(case_dir), airfoil, CONFIG_PATH)
    if not success:
        return False

    _info("Extracting results …")
    result = _extract_results(str(case_dir), airfoil, alpha_deg)
    if result is None:
        _warn("Could not extract coefficients from postProcessing output.")
        return False

    _append_result(result)
    _update_lkg()
    _success(
        f"α={alpha_deg:.1f}°  Cl={result['Cl']:.4f}  "
        f"Cd={result['Cd']:.4f}  Cm={result['Cm']:.4f}"
    )
    _info(f"Results saved to: {RESULTS_CSV}")
    return True


# ---------------------------------------------------------------------------
# Airfoil picker (from CUSTOM_STL_DIR)
# ---------------------------------------------------------------------------

def _choose_airfoil() -> str | None:
    CUSTOM_STL_DIR.mkdir(parents=True, exist_ok=True)
    stl_files = sorted(CUSTOM_STL_DIR.glob("*.stl"))
    if not stl_files:
        _warn(f"No custom airfoils found in {CUSTOM_STL_DIR}")
        _info("Import an STL first (Option A).")
        return None
    _section("Select Airfoil")
    for i, f in enumerate(stl_files, 1):
        print(f"    {i}) {f.stem}")
    while True:
        raw = input(f"  {_c(_C, f'Choice [1-{len(stl_files)}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(stl_files):
            chosen = stl_files[int(raw) - 1]
            key = chosen.stem.lower()
            _success(f"Selected {chosen.stem}")
            return key
        _warn(f"Enter 1–{len(stl_files)}.")


# ===========================================================================
# Menu tasks  (A–G)
# ===========================================================================

# ---------------------------------------------------------------------------
# A — Import Custom STL from SolidWorks
# ---------------------------------------------------------------------------

def task_import_stl():
    _section("Import Custom STL from SolidWorks")
    print()
    print(_SOLIDWORKS_TIPS)

    # Scan for STL files
    _info("Scanning for STL files …")
    found: list[Path] = []
    for scan_dir in STL_SCAN_DIRS:
        if scan_dir.exists():
            hits = sorted(scan_dir.glob("*.stl"))
            if hits:
                _info(f"  {scan_dir}  ({len(hits)} file(s))")
            found.extend(hits)

    print()
    if found:
        name_w = max(max(len(p.name) for p in found), 24)
        hdr = f"  {'#':<4}  {'File':<{name_w}}  {'Size':>9}  {'Modified':<17}  Location"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for i, stl in enumerate(found, 1):
            st    = stl.stat()
            sz    = _fmt_size(st.st_size)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {i:<4}  {stl.name:<{name_w}}  {sz:>9}  {mtime:<17}  {stl.parent}")
        print()
        manual_idx = len(found) + 1
        print(f"  {manual_idx})  Enter path manually")
    else:
        _warn("No STL files found in the default scan locations.")
        manual_idx = 1
        print(f"  1)  Enter path manually")

    print()
    while True:
        raw = input(f"  {_c(_C, f'Choice [1-{manual_idx}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= manual_idx:
            break
        _warn(f"Enter a number between 1 and {manual_idx}.")

    choice = int(raw)
    if choice <= len(found):
        src_path = found[choice - 1]
    else:
        raw_path = input(f"  {_c(_C, 'Full path to STL file')}: ").strip()
        if not raw_path:
            _warn("No path entered.")
            return
        src_path = Path(raw_path).expanduser().resolve()
        if not src_path.exists():
            _error(f"File not found: {src_path}")
            return

    # Confirm file details
    st    = src_path.stat()
    mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d  %H:%M")
    print()
    print(f"  File     : {src_path.name}")
    print(f"  Full path: {src_path}")
    print(f"  Size     : {_fmt_size(st.st_size)}")
    print(f"  Modified : {mtime}")
    print()

    name = input(f"  {_c(_C, 'Airfoil name (e.g. NACA6412, CUSTOM01)')}: ").strip()
    if not name:
        _error("Airfoil name cannot be empty.")
        return
    name_key   = name.lower().replace(" ", "_")
    name_upper = name_key.upper()

    CUSTOM_STL_DIR.mkdir(parents=True, exist_ok=True)
    dst_path = CUSTOM_STL_DIR / f"{name_upper}.stl"

    # Convert to ASCII with surfaceConvert
    _info("Converting to ASCII STL with surfaceConvert …")
    conv_cmd = f'source "{FOAM_BASHRC}" && surfaceConvert "{src_path}" "{dst_path}"'
    try:
        conv = subprocess.run(
            ["bash", "-c", conv_cmd],
            capture_output=True, text=True, timeout=120,
        )
        if conv.returncode == 0:
            _success(f"Converted → {dst_path}")
        else:
            _warn("surfaceConvert returned non-zero; copying file directly.")
            detail = (conv.stderr or conv.stdout).strip()
            if detail:
                _warn(detail[:200])
            shutil.copy2(src_path, dst_path)
    except subprocess.TimeoutExpired:
        _warn("surfaceConvert timed out; copying file directly.")
        shutil.copy2(src_path, dst_path)
    except Exception as exc:
        _warn(f"surfaceConvert unavailable ({exc}); copying file directly.")
        shutil.copy2(src_path, dst_path)

    # Geometry check with surfaceCheck
    _info("Checking geometry with surfaceCheck …")
    check_cmd = f'source "{FOAM_BASHRC}" && surfaceCheck "{dst_path}"'
    try:
        chk = subprocess.run(
            ["bash", "-c", check_cmd],
            capture_output=True, text=True, timeout=120,
        )
        output = (chk.stdout + chk.stderr).lower()
        bad_kws = (
            "open edge", "open edges", "open boundary",
            "non-closed", "not closed", "hole", "multiply connected",
        )
        issues = [kw for kw in bad_kws if kw in output]
        if issues:
            _warn("surfaceCheck detected potential geometry issues:")
            for kw in issues:
                _warn(f"    '{kw}' found in output")
            _warn("Meshing may fail. Fix the geometry in SolidWorks:")
            _warn("  – Ensure the body is a fully closed solid.")
            _warn("  – Use Tools → Check → Check Geometry before exporting.")
        else:
            _success("surfaceCheck: no open edges or holes detected.")
    except subprocess.TimeoutExpired:
        _warn("surfaceCheck timed out; skipping geometry check.")
    except Exception as exc:
        _warn(f"surfaceCheck unavailable ({exc}); skipping geometry check.")

    final_st = dst_path.stat()
    print()
    _success(f"'{name_upper}' is now available for simulation.")
    _info(f"  Saved to : {dst_path}")
    _info(f"  Size     : {_fmt_size(final_st.st_size)}")
    _info("Use Option C or D to run simulations.")


# ---------------------------------------------------------------------------
# B — Custom Mesh Settings
# ---------------------------------------------------------------------------

def task_mesh_settings():
    _section("Custom Mesh Settings")
    cfg = _get_cfg()

    print()
    _info("Current settings:")
    _show_settings(cfg)
    print()
    _info("Press Enter to keep the current value, or type a new one.")
    print()

    new_cfg = {
        "nx":         _ask_int("Cells in X (streamwise)",                   cfg["nx"]),
        "ny":         _ask_int("Cells in Y (normal to flow)",                cfg["ny"]),
        "nz":         _ask_int("Cells in Z (span — keep 1 for 2D)",          cfg["nz"]),
        "inlet":      _ask_int("Inlet distance upstream   (chord lengths)",  cfg["inlet"]),
        "outlet":     _ask_int("Outlet distance downstream (chord lengths)", cfg["outlet"]),
        "top_bottom": _ask_int("Top/bottom distance        (chord lengths)", cfg["top_bottom"]),
        "refine_min": _ask_int("snappyHexMesh refinement min  (0–3)",        cfg["refine_min"]),
        "refine_max": _ask_int("snappyHexMesh refinement max  (0–3)",        cfg["refine_max"]),
        "end_time":   _ask_int("Solver iterations  (endTime)",               cfg["end_time"]),
    }

    warnings = _validate_settings(new_cfg)
    cells, time_str = _estimate(new_cfg)

    print()
    _info(f"Estimated cells:           ~{cells:,}")
    _info(f"Estimated simulation time: {time_str}")

    if warnings:
        print()
        for w in warnings:
            _warn(w)
        print()
        ans = input(f"  {_c(_Y, 'Save these settings anyway? [y/N]')}: ").strip().lower()
    else:
        print()
        ans = input(f"  {_c(_C, 'Save these settings? [Y/n]')}: ").strip().lower()

    if ans in ("y", "yes") or (not ans and not warnings):
        data = _load_config()
        data["current"] = new_cfg
        _save_config(data)
        _success("Settings saved.")
        _info(f"Config: {CONFIG_PATH}")
    else:
        _revert_to_lkg()
        _info("Settings NOT saved — reverted to last_known_good.")
        _show_settings(_get_cfg())


# ---------------------------------------------------------------------------
# C — Run Single Simulation
# ---------------------------------------------------------------------------

def task_run_single():
    _section("Run Single Simulation")
    airfoil = _choose_airfoil()
    if airfoil is None:
        return
    alpha_deg = _ask_float("Angle of attack (degrees)", default=0.0)
    cfg = _pre_run_check()
    _run_one(airfoil, alpha_deg, cfg)


# ---------------------------------------------------------------------------
# D — Run Angle Sweep
# ---------------------------------------------------------------------------

def task_run_sweep():
    _section("Run Angle Sweep")
    airfoil = _choose_airfoil()
    if airfoil is None:
        return

    alpha_min = _ask_float("Start angle (deg)", default=-4.0)
    alpha_max = _ask_float("End angle   (deg)", default=20.0)
    step      = _ask_float("Step size   (deg)", default=1.0)

    alphas: list[float] = []
    a = alpha_min
    while a <= alpha_max + 1e-9:
        alphas.append(round(a, 6))
        a = round(a + step, 6)

    _info(f"Will run {len(alphas)} angles: {alphas[0]:g}° → {alphas[-1]:g}°  (step {step:g}°)")
    cfg = _pre_run_check()

    failed = []
    for alpha in alphas:
        _info(f"α = {alpha:+g}°")
        ok = _run_one(airfoil, alpha, cfg)
        if not ok:
            failed.append(alpha)

    if failed:
        _warn(f"Failed angles: {failed}")
    else:
        _success("Sweep complete.")


# ---------------------------------------------------------------------------
# E — View Results
# ---------------------------------------------------------------------------

def task_view_results():
    _section("View Results")
    rows = _load_results()
    if not rows:
        _warn("No results yet. Run a simulation first (Option C or D).")
        _info(f"Results file: {RESULTS_CSV}")
        return

    airfoils = sorted({r["airfoil"] for r in rows})
    print("  Filter by airfoil?")
    for i, a in enumerate(airfoils, 1):
        print(f"    {i}) {a.upper()}")
    print("    0) All")

    raw = input("  Choice: ").strip()
    selected = None
    if raw.isdigit() and int(raw) != 0:
        idx = int(raw) - 1
        if 0 <= idx < len(airfoils):
            selected = airfoils[idx]

    filtered = [r for r in rows if selected is None or r["airfoil"] == selected]
    if not filtered:
        _warn("No results for that selection.")
        return

    hdr = f"{'Airfoil':<16} {'Alpha':>7} {'Cl':>10} {'Cd':>10} {'L/D':>10} {'Cm':>10}"
    sep = "-" * len(hdr)
    print(f"\n  {_c(_B + _C, hdr)}")
    print(f"  {sep}")
    for r in filtered:
        ld = r["Cl"] / r["Cd"] if r["Cd"] != 0 else float("nan")
        print(
            f"  {r['airfoil']:<16} {r['alpha']:>7.2f} "
            f"{r['Cl']:>10.4f} {r['Cd']:>10.4f} {ld:>10.4f} {r['Cm']:>10.4f}"
        )
    print()
    _info(f"Results file: {RESULTS_CSV}")


# ---------------------------------------------------------------------------
# F — Visualize in ParaView
# ---------------------------------------------------------------------------

def task_visualize_paraview():
    _section("Visualize in ParaView")
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        d for d in sorted(CASES_DIR.iterdir())
        if d.is_dir() and (d / "constant" / "polyMesh").exists()
    ]
    if not cases:
        _warn("No completed cases found. Run a simulation first (Option C).")
        return

    for i, c in enumerate(cases, 1):
        print(f"    {i}) {c.name}")
    print("    0) Back")

    while True:
        raw = input(f"  {_c(_C, 'Select case')}: ").strip()
        if raw == "0":
            return
        if raw.isdigit() and 1 <= int(raw) <= len(cases):
            case_path = cases[int(raw) - 1]
            break
        _warn(f"Enter 0–{len(cases)}.")

    foam_file = case_path / "case.foam"
    foam_file.write_text("")
    _success(f"Created {foam_file}")
    _info(f"Launching ParaView for {case_path.name} …")
    try:
        result = subprocess.run(["paraview", str(foam_file)], timeout=None)
        if result.returncode != 0:
            _warn(f"ParaView exited with code {result.returncode}.")
    except FileNotFoundError:
        _error("ParaView is not installed.  sudo apt install paraview")
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("display", "xcb", "wayland", "x server")):
            _error("ParaView could not open a window.")
            _info("Needs WSLg (Windows 11) or VcXsrv with  export DISPLAY=:0")
        else:
            _error(f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Mesh statistics helpers
# ---------------------------------------------------------------------------

def _extract_airfoil_key(case_name: str) -> str | None:
    m = re.match(r'^(.+)_a[pm]\d+_\d+$', case_name)
    return m.group(1) if m else None


def _case_to_alpha_cm(case_name: str) -> float | None:
    m = re.search(r"_a([pm])(\d+)_(\d+)$", case_name)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "m" else 1.0
    return sign * float(f"{m.group(2)}.{m.group(3)}")


def _discover_all_airfoils() -> tuple[list[str], list[str]]:
    naca_set:   set[str] = set()
    custom_set: set[str] = set()
    for root in _CASE_SCAN_ROOTS:
        if not root.exists():
            continue
        for d in root.iterdir():
            if not d.is_dir():
                continue
            if not (d / "constant" / "polyMesh").exists():
                continue
            key = _extract_airfoil_key(d.name)
            if key is None:
                continue
            if key in _NACA_KEYS:
                naca_set.add(key)
            else:
                custom_set.add(key)
    return sorted(naca_set), sorted(custom_set)


def _find_cases_for_airfoil(af_key: str) -> list[tuple[float, Path]]:
    results = []
    for root in _CASE_SCAN_ROOTS:
        if not root.exists():
            continue
        for d in root.iterdir():
            if not d.is_dir():
                continue
            if not (d / "constant" / "polyMesh").exists():
                continue
            if _extract_airfoil_key(d.name) != af_key:
                continue
            alpha = _case_to_alpha_cm(d.name)
            if alpha is None:
                continue
            results.append((alpha, d))
    results.sort(key=lambda x: x[0])
    return results


def _parse_checkmesh_cm(output: str, alpha: float) -> dict | None:
    def _find_int(pattern: str) -> str:
        m = re.search(pattern, output, re.M)
        return m.group(1) if m else "N/A"

    def _find_float(pattern: str) -> str:
        m = re.search(pattern, output, re.I)
        return m.group(1) if m else "N/A"

    cells   = _find_int(r'^\s*cells:\s*(\d+)')
    faces   = _find_int(r'^\s*faces:\s*(\d+)')
    points  = _find_int(r'^\s*points:\s*(\d+)')

    nonortho = _find_float(
        r'[Mm]ax(?:imum)?\s+non-orthogonality\s*[=:]\s*' + _NUM_RE_CM)
    skewness = _find_float(
        r'[Mm]ax(?:imum)?\s+skewness\s*[=:]\s*' + _NUM_RE_CM)
    min_vol  = _find_float(
        r'[Mm]in(?:imum)?\s+(?:cell\s+)?volume\s*[=:]\s*' + _NUM_RE_CM)
    max_asp  = _find_float(
        r'[Mm]ax(?:imum)?\s+(?:cell\s+)?aspect\s+ratio\s*[=:]\s*' + _NUM_RE_CM)

    qual_m  = re.search(r'(PASS|FAIL\s*\(\d+\))', output, re.I)
    quality = qual_m.group(1).strip() if qual_m else "N/A"

    return {
        "alpha":        alpha,
        "cells":        cells,
        "faces":        faces,
        "points":       points,
        "max_nonortho": nonortho,
        "max_skewness": skewness,
        "min_volume":   min_vol,
        "max_aspect":   max_asp,
        "quality":      quality,
    }


def _run_checkmesh_cm(alpha: float, case_path: Path) -> dict | None:
    log_dir  = case_path / "logs"
    log_path = log_dir / "checkMesh.log"
    if log_path.exists():
        return _parse_checkmesh_cm(log_path.read_text(), alpha)
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = (
        f'set -o pipefail && source "{FOAM_BASHRC}" && '
        f'checkMesh -latestTime 2>&1 | tee "{log_path}"'
    )
    try:
        subprocess.run(["bash", "-c", cmd], cwd=str(case_path.resolve()), timeout=300)
    except subprocess.TimeoutExpired:
        _warn(f"checkMesh timed out for {case_path.name}")
        return None
    except Exception as exc:
        _warn(f"checkMesh error for {case_path.name}: {exc}")
        return None
    if not log_path.exists():
        return None
    return _parse_checkmesh_cm(log_path.read_text(), alpha)


def _print_mesh_stats_table_cm(rows: list[dict]):
    header = (
        f"  {'Alpha':>7}  {'Cells':>9}  {'Faces':>10}  {'Points':>10}  "
        f"{'NonOrtho':>12}  {'Skewness':>10}  {'MinVol':>14}  {'Aspect':>9}  Quality"
    )
    sep = "  " + "-" * (len(header) - 2)
    print(f"\n{_c(_B + _C, header)}")
    print(sep)
    for r in rows:
        try:
            no_val = float(r["max_nonortho"])
            no_flag = "OK" if no_val <= 70.0 else "!!"
            nonortho_str = f"{no_val:.1f} {no_flag}"
        except (ValueError, TypeError):
            nonortho_str = str(r["max_nonortho"])

        body = (
            f"  {r['alpha']:>7.2f}  {str(r['cells']):>9}  {str(r['faces']):>10}  "
            f"{str(r['points']):>10}  {nonortho_str:>12}  {str(r['max_skewness']):>10}  "
            f"{str(r['min_volume']):>14}  {str(r['max_aspect']):>9}  "
        )
        q = str(r["quality"])
        if q.upper().startswith("PASS"):
            quality_str = _c(_G, q)
        elif q.upper().startswith("FAIL"):
            quality_str = _c(_R, q)
        else:
            quality_str = q
        print(body + quality_str)
    print()


def _save_mesh_stats_csv_cm(csv_path: Path, rows: list[dict]):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["alpha", "cells", "faces", "points",
              "max_nonortho", "max_skewness", "min_volume", "max_aspect", "quality"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


_MESH_LEGEND = """\
  What these metrics mean:
  NonOrtho  — angle (degrees) between the cell-centre-to-face vector and the face normal.
              Keep below 70°. Values above 70° are marked !! and cause solver instability.
  Skewness  — face distortion relative to an ideal face. Below 4 is acceptable for simpleFoam.
  MinVol    — smallest cell volume in the mesh. Must be positive; negative means inverted cells.
  Aspect    — longest-to-shortest edge ratio. Below 100 near the wall is acceptable.
  Quality   — PASS = all mesh checks within OpenFOAM thresholds. FAIL(N) = N checks failed.
"""


# ---------------------------------------------------------------------------
# H — View Mesh Statistics
# ---------------------------------------------------------------------------

def task_mesh_stats():
    _section("View Mesh Statistics")
    naca_keys, custom_keys = _discover_all_airfoils()

    if not naca_keys and not custom_keys:
        _warn("No completed cases found.")
        _info(f"Scan roots: {[str(r) for r in _CASE_SCAN_ROOTS]}")
        return

    entries: list[tuple[str, str]] = []
    print()
    idx = 1
    if naca_keys:
        print(f"  {_c(_B, 'Research Airfoils (NACA)')}")
        for key in naca_keys:
            label = _NACA_DISPLAY_MAP.get(key, key.upper())
            print(f"    {idx}) {label}")
            entries.append((key, "naca"))
            idx += 1
    if custom_keys:
        print(f"  {_c(_B, 'Custom Airfoils')}")
        for key in custom_keys:
            print(f"    {idx}) {key.upper()}")
            entries.append((key, "custom"))
            idx += 1

    print()
    while True:
        raw = input(f"  {_c(_C, f'Select airfoil [1-{len(entries)}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(entries):
            af_key, category = entries[int(raw) - 1]
            break
        _warn(f"Enter 1–{len(entries)}.")

    cases = _find_cases_for_airfoil(af_key)
    if not cases:
        _warn(f"No completed cases found for '{af_key}'.")
        return

    _section(f"Select Angle — {af_key.upper()}")
    for i, (alpha, case_path) in enumerate(cases, 1):
        print(f"    {i}) α = {alpha:+.2f}°  ({case_path.name})")
    print(f"    0) ALL angles")

    while True:
        raw = input(f"  {_c(_C, f'Choice [0-{len(cases)}]')}: ").strip()
        if raw == "0":
            selected = cases
            break
        if raw.isdigit() and 1 <= int(raw) <= len(cases):
            selected = [cases[int(raw) - 1]]
            break
        _warn(f"Enter 0–{len(cases)}.")

    _section("Running checkMesh")
    rows = []
    for alpha, case_path in selected:
        _info(f"α = {alpha:+.2f}°  ({case_path.name})")
        row = _run_checkmesh_cm(alpha, case_path)
        if row is not None:
            rows.append(row)
        else:
            _warn(f"Could not get mesh stats for {case_path.name}")

    if not rows:
        _warn("No mesh statistics could be extracted.")
        return

    display_name = _NACA_DISPLAY_MAP.get(af_key, af_key.upper())
    _section(f"Mesh Statistics — {display_name}")
    _print_mesh_stats_table_cm(rows)
    print(_MESH_LEGEND)

    if category == "naca":
        csv_path = Path.home() / "OpenFOAM" / "results" / f"{af_key}_mesh_stats.csv"
    else:
        csv_path = Path.home() / "OpenFOAM" / "results" / "custom" / f"{af_key}_mesh_stats.csv"

    _save_mesh_stats_csv_cm(csv_path, rows)
    _success(f"Mesh stats saved to: {csv_path}")


# ---------------------------------------------------------------------------
# G — Reset all settings to default
# ---------------------------------------------------------------------------

def task_reset_defaults():
    _section("Reset All Settings to Default")
    _info("This will restore the proven defaults:")
    _show_settings(DEFAULTS)
    print()
    ans = input(f"  {_c(_Y, 'Confirm reset? [y/N]')}: ").strip().lower()
    if ans in ("y", "yes"):
        _save_config({"current": dict(DEFAULTS), "last_known_good": dict(DEFAULTS)})
        _success(
            "All settings reset to default: "
            "100×80×1 cells, domain ±20/30/10 chords, 3000 iterations."
        )
    else:
        _info("Reset cancelled — settings unchanged.")


# ===========================================================================
# Main menu
# ===========================================================================

_MENU = {
    "A": ("Import Custom STL from SolidWorks",          task_import_stl),
    "B": ("Custom Mesh Settings",                       task_mesh_settings),
    "C": ("Run Single Simulation with custom settings", task_run_single),
    "D": ("Run Angle Sweep with custom settings",       task_run_sweep),
    "E": ("View Results",                               task_view_results),
    "F": ("Visualize in ParaView",                      task_visualize_paraview),
    "G": ("Reset all settings to default",              task_reset_defaults),
    "H": ("View Mesh Statistics",                       task_mesh_stats),
    "I": ("Exit",                                       None),
}


def main():
    _ensure_config()
    _header("CustomMesh  |  SolidWorks STL → OpenFOAM CFD  |  Re = 2×10⁵")
    while True:
        print()
        for key, (label, _) in _MENU.items():
            print(f"  {_c(_Y, key)}) {label}")
        choice = input(f"\n  {_c(_C, 'Select')}: ").strip().upper()
        if choice == "I":
            _info("Goodbye.")
            break
        if choice in _MENU:
            _, fn = _MENU[choice]
            fn()
        else:
            _warn("Enter A–I.")


if __name__ == "__main__":
    main()
