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

# Notes this function generates itself - re-derived from scratch each pass so a
# stale/since-fixed auto-flag is cleared, not preserved. Any other note is manual.
_AUTO_NOTES = {"post-stall-unreliable", "diverged-unreliable"}


def _is_single_point_anomaly(row: dict, prev: dict | None, nxt: dict | None) -> bool:
    """
    True if *row* is a lone diverged/garbage point: coefficients that are both
    a large spike relative to BOTH immediate neighbours AND beyond any
    physically plausible converged value.

    This guards the sequential post-stall detector below. A case can "converge"
    (residuals fall to ~1e-4) onto a non-physical state - the turbulence field
    goes unstable early, corrupts the solution, and the solver settles on a
    garbage steady state with huge Cl/Cd - so there is no solver crash to catch
    it (seen on NACA4412 alpha=0: Cl~1888, Cd~17.5). Left unquarantined, that
    one point's huge Cd trips the "abrupt Cd jump" criterion and cascades a
    false post-stall flag onto every downstream angle. Airfoil-agnostic: no
    real converged case at this Re has |Cl|>3 or Cd>1.
    """
    CL_MAX_PHYS = 3.0    # |Cl| beyond this is non-physical at Re~2e5
    CD_MAX_PHYS = 1.0    # Cd beyond this is non-physical (deep post-stall ~0.6)
    SPIKE       = 5.0    # x the larger neighbour magnitude
    cl, cd = abs(row["Cl"]), abs(row["Cd"])
    # Absolute implausibility is necessary in every case - a large-but-real
    # value on a smooth trend must never be quarantined.
    if cl <= CL_MAX_PHYS and cd <= CD_MAX_PHYS:
        return False
    nbrs = [n for n in (prev, nxt) if n is not None]
    if not nbrs:
        return True  # endpoint already beyond physical bounds
    nbr_cl = max(abs(n["Cl"]) for n in nbrs)
    nbr_cd = max(abs(n["Cd"]) for n in nbrs)
    return cl > SPIKE * max(nbr_cl, 1e-9) or cd > SPIKE * max(nbr_cd, 1e-9)


def auto_flag_airfoil(rows: list[dict]) -> list[dict]:
    """
    Apply reliability flags to rows for a single airfoil sorted by alpha.

    Flags assigned:
    - 'diverged-unreliable'   : Cd < 0, or a single-point anomaly (garbage
                                coefficients from a non-physically-converged
                                case - see _is_single_point_anomaly)
    - 'post-stall-unreliable' : Cl drops then rises again (second RANS branch)
                                OR abrupt Cd jump >3x previous clean point
                                (indicates sudden full separation onset)

    Single-point anomalies are quarantined BEFORE the post-stall detection so a
    lone garbage point cannot cascade-corrupt every flag after it.

    Already-flagged rows keep their existing note unless a stronger flag applies.
    """
    sorted_rows = sorted(rows, key=lambda r: r["alpha"])
    n = len(sorted_rows)

    # --- Pre-pass: quarantine single-point anomalies ---
    anomaly = [False] * n
    for i in range(n):
        prev = sorted_rows[i - 1] if i > 0 else None
        nxt  = sorted_rows[i + 1] if i < n - 1 else None
        anomaly[i] = _is_single_point_anomaly(sorted_rows[i], prev, nxt)

    # --- Detect post-stall start alpha (skipping quarantined points) ---
    peak_cl      = float("-inf")
    peak_alpha   = None
    drop_seen    = False
    drop_first   = None   # Cl at the FIRST point that dropped from peak
    post_stall_start = None
    prev_cl      = None
    prev_cd      = None

    for i, row in enumerate(sorted_rows):
        if anomaly[i]:
            continue   # quarantined - do not let it seed prev_cl/prev_cd or trip a criterion
        cl    = row["Cl"]
        cd    = row["Cd"]
        alpha = row["alpha"]

        # Criterion A — PARTIAL rise after stall drop:
        #   Cl climbs back above the first-drop level + 0.20, but stays BELOW
        #   the pre-drop peak. A genuine post-stall second branch only recovers
        #   partially - it never climbs back past CLmax. A dip that recovers
        #   ABOVE its pre-drop peak was a benign mid-range feature, not stall
        #   (e.g. NACA4412 alpha=4->5 dip recovering past its old peak on the
        #   way to a higher CLmax at alpha=11) - fall through and let the
        #   peak-update branch reset it. Using first-drop Cl (not running min)
        #   avoids false-positives when Cl spirals further down before
        #   recovering on a second RANS branch.
        if (drop_seen and drop_first is not None
                and cl > drop_first + 0.20 and cl < peak_cl):
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
    # Re-derive the flagger's OWN labels from scratch each pass: start from a
    # clean slate for any note this function itself produces (_AUTO_NOTES), so a
    # stale auto-flag from a previous pass - e.g. a since-fixed cascade - is
    # cleared rather than preserved. Any other (manual/research) note is kept.
    result = []
    for i, row in enumerate(sorted_rows):
        existing = row.get("note", "")
        note = "" if existing in _AUTO_NOTES else existing
        if anomaly[i] or row["Cd"] < 0:
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
