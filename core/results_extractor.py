"""
Reads Cl, Cd, Cm from OpenFOAM postProcessing/forceCoeffs/*/coefficient.dat
and manages a CSV results database.

CSV schema: airfoil, alpha, Cl, Cd, Cm, note
"""

import csv
import os
from pathlib import Path


_CSV_COLUMNS = ["airfoil", "alpha", "Cl", "Cd", "Cm", "note"]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_coefficient_dat(dat_path: str) -> dict[str, float] | None:
    """
    Read the last non-comment, non-header data line of coefficient.dat.
    Returns {"Cl": ..., "Cd": ..., "Cm": ...} or None on failure.

    OpenFOAM coefficient.dat columns (v2412):
      Time  Cm  Cd  Cl  CmFront  CmBack
    index:   0   1   2   3   4   5
    """
    path = Path(dat_path)
    if not path.exists():
        return None

    last_line = None
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                continue
            last_line = stripped

    if last_line is None:
        return None

    try:
        parts = last_line.split()
        # columns: Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) CmPitch CmRoll CmYaw ...
        return {
            "Cl": float(parts[4]),
            "Cd": float(parts[1]),
            "Cm": float(parts[7]),
        }
    except (IndexError, ValueError):
        return None


def _find_dat(case_dir: str) -> str | None:
    """Locate the coefficient.dat file inside postProcessing/forceCoeffs/."""
    base = Path(case_dir) / "postProcessing" / "forceCoeffs"
    if not base.exists():
        return None
    # Walk subdirectories (e.g. 0/)
    for sub in sorted(base.iterdir()):
        dat = sub / "coefficient.dat"
        if dat.exists():
            return str(dat)
    return None


def extract_results(case_dir: str, airfoil: str, alpha_deg: float) -> dict | None:
    """
    Extract Cl/Cd/Cm from a completed case directory.
    Returns a dict with keys airfoil, alpha, Cl, Cd, Cm or None on failure.
    """
    dat = _find_dat(case_dir)
    if dat is None:
        return None
    coeffs = _parse_coefficient_dat(dat)
    if coeffs is None:
        return None
    return {
        "airfoil": airfoil.lower().replace(" ", ""),
        "alpha":   float(alpha_deg),
        "note":    "",
        **coeffs,
    }


# ---------------------------------------------------------------------------
# Auto-flagging
# ---------------------------------------------------------------------------

def auto_flag_airfoil(rows: list[dict]) -> list[dict]:
    """
    Apply reliability flags to rows for a single airfoil sorted by alpha.

    Flags assigned:
    - 'diverged-unreliable'   : Cd < 0
    - 'post-stall-unreliable' : Cl drops then rises again (second RANS branch)
                                OR abrupt Cd jump >3x previous clean point
                                (indicates sudden full separation onset)

    Already-flagged rows keep their existing note unless a stronger flag applies.
    """
    sorted_rows = sorted(rows, key=lambda r: r["alpha"])

    # --- Detect post-stall start alpha ---
    peak_cl      = float("-inf")
    peak_alpha   = None
    drop_seen    = False
    drop_first   = None   # Cl at the FIRST point that dropped from peak
    post_stall_start = None
    prev_cl      = None
    prev_cd      = None

    for row in sorted_rows:
        cl    = row["Cl"]
        cd    = row["Cd"]
        alpha = row["alpha"]

        # Criterion A — rise after stall drop:
        #   Cl climbs back above the first-drop level + 0.20.
        #   Using first-drop Cl (not running min) avoids false-positives when
        #   Cl spirals further down before recovering on a second RANS branch.
        if drop_seen and drop_first is not None and cl > drop_first + 0.20:
            post_stall_start = peak_alpha
            break

        if cl > peak_cl:
            # Criterion B — abrupt Cd jump → full separation at this alpha
            if prev_cd is not None and prev_cd > 0 and cd > 3.0 * prev_cd:
                post_stall_start = alpha
                break
            peak_cl    = cl
            peak_alpha = alpha
            drop_seen  = False
            drop_first = None
        else:
            # Criterion C — single-step Cl drop > 0.5 → solver jumped branch.
            # Physical stall declines gradually; a 0.5+ drop in one step is a
            # branch change (e.g. NACA0012 α=11.5→12: Cl 0.693→−0.135 = −0.828).
            if prev_cl is not None and prev_cl - cl > 0.50:
                post_stall_start = alpha
                break
            if peak_cl - cl > 0.05 and not drop_seen:
                drop_seen  = True
                drop_first = cl   # lock in the first-drop level

        prev_cl = cl
        if not drop_seen:
            prev_cd = cd

    # --- Assign notes ---
    result = []
    for row in sorted_rows:
        note = row.get("note", "")
        if row["Cd"] < 0:
            note = "diverged-unreliable"
        elif post_stall_start is not None and row["alpha"] >= post_stall_start:
            note = "post-stall-unreliable"
        result.append({**row, "note": note})
    return result


def apply_flags_all_airfoils(rows: list[dict]) -> list[dict]:
    """Run auto_flag_airfoil on every airfoil group and return the combined list."""
    airfoils = sorted({r["airfoil"] for r in rows})
    out = []
    for af in airfoils:
        group = [r for r in rows if r["airfoil"] == af]
        out.extend(auto_flag_airfoil(group))
    out.sort(key=lambda r: (r["airfoil"], r["alpha"]))
    return out


# ---------------------------------------------------------------------------
# CSV database
# ---------------------------------------------------------------------------

def load_csv(csv_path: str) -> list[dict]:
    """Load results CSV; returns [] if file does not exist."""
    path = Path(csv_path)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            if not row["Cl"] or not row["Cd"] or not row["Cm"]:
                continue  # skip diverged rows with no numeric data
            rows.append({
                "airfoil": row["airfoil"],
                "alpha":   float(row["alpha"]),
                "Cl":      float(row["Cl"]),
                "Cd":      float(row["Cd"]),
                "Cm":      float(row["Cm"]),
                "note":    row.get("note", ""),
            })
    return rows


def save_csv(csv_path: str, rows: list[dict]):
    """Write rows to CSV, overwriting any existing file."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "airfoil": row["airfoil"],
                "alpha":   row["alpha"],
                "Cl":      row.get("Cl", ""),
                "Cd":      row.get("Cd", ""),
                "Cm":      row.get("Cm", ""),
                "note":    row.get("note", ""),
            })


def append_result(csv_path: str, result: dict):
    """
    Append (or update) a single result row to the CSV, then re-apply
    auto-flagging across the whole airfoil group.
    """
    rows = load_csv(csv_path)
    key  = (result["airfoil"], float(result["alpha"]))
    rows = [r for r in rows if (r["airfoil"], r["alpha"]) != key]
    rows.append({**result, "note": result.get("note", "")})
    rows = apply_flags_all_airfoils(rows)
    rows.sort(key=lambda r: (r["airfoil"], r["alpha"]))
    save_csv(csv_path, rows)


def filter_results(rows: list[dict], airfoil: str | None = None) -> list[dict]:
    """Filter rows by airfoil (None = all)."""
    if airfoil is None:
        return rows
    key = airfoil.lower().replace(" ", "")
    return [r for r in rows if r["airfoil"] == key]


def print_results(rows: list[dict]):
    """Pretty-print results to stdout."""
    if not rows:
        print("  No results available.")
        return
    header = f"{'Airfoil':<12} {'Alpha':>7} {'Cl':>10} {'Cd':>10} {'Cm':>10}  Note"
    sep    = "-" * (len(header) + 10)
    print(f"\n  {header}")
    print(f"  {sep}")
    for r in rows:
        note = r.get("note", "")
        flag = f"  [{note}]" if note else ""
        print(f"  {r['airfoil']:<12} {r['alpha']:>7.2f} {r['Cl']:>10.4f} {r['Cd']:>10.4f} {r['Cm']:>10.4f}{flag}")
    print()
