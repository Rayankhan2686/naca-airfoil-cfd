"""
Reads Cl, Cd, Cm from OpenFOAM postProcessing/forceCoeffs/*/coefficient.dat
and manages a CSV results database.

CSV schema: airfoil, alpha, Cl, Cd, Cm
"""

import csv
import os
from pathlib import Path


_CSV_COLUMNS = ["airfoil", "alpha", "Cl", "Cd", "Cm"]


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
        **coeffs,
    }


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
            rows.append({
                "airfoil": row["airfoil"],
                "alpha":   float(row["alpha"]),
                "Cl":      float(row["Cl"]),
                "Cd":      float(row["Cd"]),
                "Cm":      float(row["Cm"]),
            })
    return rows


def save_csv(csv_path: str, rows: list[dict]):
    """Write rows to CSV, overwriting any existing file."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def append_result(csv_path: str, result: dict):
    """
    Append (or update) a single result row to the CSV.
    If a row with the same airfoil+alpha exists it is replaced.
    """
    rows = load_csv(csv_path)
    key = (result["airfoil"], float(result["alpha"]))
    rows = [r for r in rows if (r["airfoil"], r["alpha"]) != key]
    rows.append(result)
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
    header = f"{'Airfoil':<12} {'Alpha':>7} {'Cl':>10} {'Cd':>10} {'Cm':>10}"
    sep    = "-" * len(header)
    print(f"\n  {header}")
    print(f"  {sep}")
    for r in rows:
        print(f"  {r['airfoil']:<12} {r['alpha']:>7.2f} {r['Cl']:>10.4f} {r['Cd']:>10.4f} {r['Cm']:>10.4f}")
    print()
