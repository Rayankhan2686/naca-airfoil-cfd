"""
Creates ~/OpenFOAM/paraview_organized/ with human-readable symlinks:
  NACA0012/
    NACA0012 (12°)  ->  ../../scripts/cases/naca0012_ap12_0
    ...
  NACA2412/
    NACA2412 (-5°)  ->  ../../scripts/cases/naca2412_am5_0
    ...
"""

import os
import re

CASES_DIR = os.path.expanduser("~/OpenFOAM/scripts/cases")
OUT_DIR   = os.path.expanduser("~/OpenFOAM/paraview_organized")

EXCLUDED_PROFILES = {"naca2412"}


def decode_name(dirname):
    """
    Returns (naca_label, alpha_float) or None if not a recognised NACA case.
    Pattern: naca{digits}_{ap|am}{int}_{frac}
      ap = positive alpha, am = negative alpha
      last segment is tenths: ap8_5 -> 8.5, ap12_0 -> 12.0
    """
    m = re.fullmatch(r"(naca\d+)_(ap|am)(\d+)_(\d+)", dirname)
    if not m:
        return None
    naca_raw, sign, integer, frac = m.groups()
    naca_label = naca_raw.upper()          # naca0012 -> NACA0012
    alpha = float(f"{integer}.{frac}")
    if sign == "am":
        alpha = -alpha
    return naca_label, alpha


def alpha_label(alpha):
    """Format alpha as a clean degree string: -5.0 -> '-5°', 8.5 -> '8.5°'"""
    val = int(alpha) if alpha == int(alpha) else alpha
    return f"{val}°"


def main():
    cases = sorted(os.listdir(CASES_DIR))

    # Group by NACA profile
    groups: dict[str, list[tuple[float, str]]] = {}
    for name in cases:
        result = decode_name(name)
        if result is None:
            continue
        naca_label, alpha = result
        groups.setdefault(naca_label, []).append((alpha, name))

    os.makedirs(OUT_DIR, exist_ok=True)

    for naca_label, entries in sorted(groups.items()):
        if naca_label.lower() in EXCLUDED_PROFILES:
            continue
        naca_dir = os.path.join(OUT_DIR, naca_label)
        os.makedirs(naca_dir, exist_ok=True)

        for alpha, dirname in sorted(entries, key=lambda x: x[0]):
            link_name = f"{naca_label} ({alpha_label(alpha)})"
            link_path = os.path.join(naca_dir, link_name)
            target    = os.path.join(CASES_DIR, dirname)

            # Ensure a case.foam sentinel exists so ParaView can open it
            foam_file = os.path.join(target, "case.foam")
            if not os.path.exists(foam_file):
                open(foam_file, "w").close()
                print(f"  created {dirname}/case.foam")

            # Remove stale link then create fresh
            if os.path.islink(link_path):
                os.unlink(link_path)

            os.symlink(target, link_path)
            print(f"  {naca_label}/{link_name}  ->  {dirname}")

    print(f"\nDone. Organized view at: {OUT_DIR}")


if __name__ == "__main__":
    main()
