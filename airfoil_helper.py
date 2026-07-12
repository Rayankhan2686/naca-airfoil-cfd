#!/usr/bin/env python3
"""
foam_helper.py
=================
File browser and NACA 4-digit STL generator for the 2D OpenFOAM pipeline.

Features:
  • Search Downloads / Desktop / Home for STL files
  • Generate watertight NACA 4-digit airfoil STL files
  • Validate STL watertightness (edge-manifold check)
  • Scale STL from mm → m (SolidWorks exports)

Usage:
    python3 airfoil_helper.py
    alias foam-helper="python3 ~/OpenFOAM/scripts/airfoil_helper.py"
"""

import os
import sys
import math
import struct
import argparse
from pathlib import Path

# ─────────────────────────────────────────────
# Colours
# ─────────────────────────────────────────────
R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"
B = "\033[94m"; C = "\033[96m"; DIM = "\033[2m"
RESET = "\033[0m"; BOLD = "\033[1m"


def banner():
    print(f"""
{C}{BOLD}╔══════════════════════════════════════════════════════╗
║          foam-helper  ·  Airfoil STL Utility         ║
║          NACA 4-digit  ·  2D Pipeline  ·  v1.0       ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


# ─────────────────────────────────────────────
# NACA 4-digit Geometry
# ─────────────────────────────────────────────

def naca4_points(designation: str, n_points: int = 200):
    """
    Return (x_upper, y_upper), (x_lower, y_lower) arrays for a
    NACA 4-digit airfoil, cosine-spaced.

    designation : e.g. '0012', '2412', '4412'
    n_points    : points per surface (total = 2*n_points - 1)
    """
    des = designation.zfill(4)
    m = int(des[0]) / 100.0   # max camber
    p = int(des[1]) / 10.0    # location of max camber
    t = int(des[2:]) / 100.0  # thickness

    # Cosine spacing for leading-edge clustering
    beta = [math.pi * i / (n_points - 1) for i in range(n_points)]
    x = [(1 - math.cos(b)) / 2 for b in beta]

    def thickness(xc):
        return (t / 0.2) * (
            0.2969 * math.sqrt(xc)
            - 0.1260 * xc
            - 0.3516 * xc**2
            + 0.2843 * xc**3
            - 0.1015 * xc**4
        )

    def camber(xc):
        if m == 0 or p == 0:
            return 0.0, 0.0
        if xc < p:
            yc = (m / p**2) * (2 * p * xc - xc**2)
            dyc = (2 * m / p**2) * (p - xc)
        else:
            yc = (m / (1 - p)**2) * ((1 - 2 * p) + 2 * p * xc - xc**2)
            dyc = (2 * m / (1 - p)**2) * (p - xc)
        return yc, dyc

    xu, yu, xl, yl = [], [], [], []
    for xc in x:
        th = thickness(xc)
        yc, dyc = camber(xc)
        theta = math.atan(dyc)
        xu.append(xc - th * math.sin(theta))
        yu.append(yc + th * math.cos(theta))
        xl.append(xc + th * math.sin(theta))
        yl.append(yc - th * math.cos(theta))

    return (xu, yu), (xl, yl)


def write_naca_stl(designation: str, output_path: str,
                   chord: float = 1.0, n_points: int = 200,
                   extrude_z: float = 0.001):
    """
    Write a watertight binary STL for a NACA 4-digit airfoil.

    The airfoil is extruded by extrude_z in the Z direction to create
    a closed solid (required by snappyHexMesh even for 2D cases).
    Chord length is normalised to `chord` metres.
    """
    (xu, yu), (xl, yl) = naca4_points(designation, n_points)

    # Build closed profile: upper surface LE→TE, lower surface TE→LE
    upper = list(zip(xu, yu))
    lower = list(zip(xl, yl))
    # profile[0] = LE, profile[-1] = TE
    profile_x = [chord * x for x, _ in upper] + [chord * x for x, _ in reversed(lower[:-1])]
    profile_y = [chord * y for _, y in upper] + [chord * y for _, y in reversed(lower[:-1])]

    n = len(profile_x)
    triangles = []

    def tri(p0, p1, p2):
        """Compute normal and append triangle."""
        v1 = (p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2])
        v2 = (p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2])
        nx = v1[1]*v2[2] - v1[2]*v2[1]
        ny = v1[2]*v2[0] - v1[0]*v2[2]
        nz = v1[0]*v2[1] - v1[1]*v2[0]
        length = math.sqrt(nx**2 + ny**2 + nz**2)
        if length < 1e-15:
            length = 1.0
        triangles.append(((nx/length, ny/length, nz/length), p0, p1, p2))

    z0, z1 = 0.0, extrude_z

    # Side walls (front z=0, back z=z1)
    for i in range(n):
        j = (i + 1) % n
        x0, y0 = profile_x[i], profile_y[i]
        x1, y1 = profile_x[j], profile_y[j]
        # Front face (z=0, normal pointing -Z)
        tri((x0,y0,z0), (x1,y1,z0), (x1,y1,z0))   # degenerate — skip side for 2D
        # Two triangles per quad for the extrusion
        tri((x0,y0,z0), (x1,y1,z0), (x0,y0,z1))
        tri((x1,y1,z0), (x1,y1,z1), (x0,y0,z1))

    # End-cap triangulation (fan from centroid)
    cx = sum(profile_x) / n
    cy = sum(profile_y) / n

    for i in range(n):
        j = (i + 1) % n
        x0, y0 = profile_x[i], profile_y[i]
        x1, y1 = profile_x[j], profile_y[j]
        # Front cap (z=0)
        tri((cx,cy,z0), (x1,y1,z0), (x0,y0,z0))
        # Back cap (z=z1)
        tri((cx,cy,z1), (x0,y0,z1), (x1,y1,z1))

    # Write binary STL
    header = f"NACA {designation} chord={chord}m n={n_points}".encode().ljust(80, b'\x00')
    n_tri = len(triangles)
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", n_tri))
        for (nx,ny,nz), p0, p1, p2 in triangles:
            f.write(struct.pack("<fff", nx, ny, nz))
            for p in (p0, p1, p2):
                f.write(struct.pack("<fff", *p))
            f.write(struct.pack("<H", 0))

    print(f"{G}✔  Wrote {n_tri} triangles → {output_path}{RESET}")
    return output_path


# ─────────────────────────────────────────────
# STL Validation (watertight edge-manifold check)
# ─────────────────────────────────────────────

def read_binary_stl_triangles(path: str):
    """Return list of (v0, v1, v2) tuples from binary STL."""
    triangles = []
    with open(path, "rb") as f:
        f.read(80)   # header
        n = struct.unpack("<I", f.read(4))[0]
        for _ in range(n):
            f.read(12)  # normal
            verts = []
            for _ in range(3):
                x, y, z = struct.unpack("<fff", f.read(12))
                verts.append((round(x,9), round(y,9), round(z,9)))
            f.read(2)   # attribute
            triangles.append(tuple(verts))
    return triangles


def check_watertight(path: str) -> bool:
    """
    Edge-manifold check: every edge must be shared by exactly 2 triangles.
    Returns True if the mesh is watertight.
    """
    from collections import defaultdict
    try:
        triangles = read_binary_stl_triangles(path)
    except Exception as e:
        # Try ASCII fallback
        print(f"{Y}Binary read failed ({e}), trying ASCII...{RESET}")
        return _check_ascii_stl(path)

    edge_count = defaultdict(int)
    for v0, v1, v2 in triangles:
        for e in [(v0,v1),(v1,v2),(v2,v0)]:
            key = tuple(sorted(e))
            edge_count[key] += 1

    bad = [e for e, c in edge_count.items() if c != 2]
    total = len(edge_count)

    if not bad:
        print(f"{G}✔  Watertight: all {total} edges shared by exactly 2 triangles.{RESET}")
        return True
    else:
        print(f"{R}✘  Not watertight: {len(bad)}/{total} edges have wrong valence.{RESET}")
        for e in bad[:5]:
            print(f"   {DIM}{e}{RESET}")
        if len(bad) > 5:
            print(f"   ... and {len(bad)-5} more.")
        return False


def _check_ascii_stl(path):
    """Fallback ASCII STL checker."""
    from collections import defaultdict
    edge_count = defaultdict(int)
    verts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("vertex"):
                parts = line.split()
                verts.append(tuple(round(float(v),9) for v in parts[1:4]))
                if len(verts) == 3:
                    v0, v1, v2 = verts
                    for e in [(v0,v1),(v1,v2),(v2,v0)]:
                        edge_count[tuple(sorted(e))] += 1
                    verts = []
    bad = [e for e, c in edge_count.items() if c != 2]
    if not bad:
        print(f"{G}✔  Watertight (ASCII STL).{RESET}")
        return True
    print(f"{R}✘  Not watertight: {len(bad)} bad edges.{RESET}")
    return False


# ─────────────────────────────────────────────
# STL Unit Scaling (mm → m)
# ─────────────────────────────────────────────

def detect_stl_scale(path: str) -> str:
    """Heuristic: read bounding box and guess units."""
    try:
        triangles = read_binary_stl_triangles(path)
    except Exception:
        return "unknown"

    all_verts = [v for tri in triangles for v in tri]
    if not all_verts:
        return "unknown"

    xs = [v[0] for v in all_verts]
    ys = [v[1] for v in all_verts]
    span = max(max(xs)-min(xs), max(ys)-min(ys))

    if span > 10:
        return "mm"    # SolidWorks default
    elif span > 0.01:
        return "m"
    else:
        return "unknown"


def scale_stl(input_path: str, output_path: str, scale: float = 0.001):
    """Write a new binary STL with all vertices multiplied by scale."""
    triangles = read_binary_stl_triangles(input_path)
    header = b"Scaled by foam-helper".ljust(80, b'\x00')
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(triangles)))
        for v0, v1, v2 in triangles:
            # Recompute normal
            v1v = tuple(v1[i]-v0[i] for i in range(3))
            v2v = tuple(v2[i]-v0[i] for i in range(3))
            nx = v1v[1]*v2v[2] - v1v[2]*v2v[1]
            ny = v1v[2]*v2v[0] - v1v[0]*v2v[2]
            nz = v1v[0]*v2v[1] - v1v[1]*v2v[0]
            length = math.sqrt(nx**2+ny**2+nz**2) or 1.0
            f.write(struct.pack("<fff", nx/length, ny/length, nz/length))
            for v in (v0, v1, v2):
                f.write(struct.pack("<fff", v[0]*scale, v[1]*scale, v[2]*scale))
            f.write(struct.pack("<H", 0))
    print(f"{G}✔  Scaled STL written to {output_path}{RESET}")


# ─────────────────────────────────────────────
# STL File Browser
# ─────────────────────────────────────────────

SEARCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home(),
    Path("/mnt/c/Users"),   # WSL Windows access
]


def find_stl_files():
    """Search common directories for .stl files."""
    found = []
    for base in SEARCH_DIRS:
        if base.exists():
            for stl in base.rglob("*.stl"):
                found.append(stl)
            for stl in base.rglob("*.STL"):
                found.append(stl)
    # Deduplicate
    seen = set()
    unique = []
    for f in found:
        if str(f) not in seen:
            seen.add(str(f)); unique.append(f)
    return unique


def browse_stl_files():
    """Interactive STL file browser."""
    print(f"\n{C}Searching for STL files...{RESET}")
    files = find_stl_files()

    if not files:
        print(f"{Y}No STL files found in standard locations.{RESET}")
        manual = input(f"{Y}Enter STL path manually (or Enter to skip): {RESET}").strip()
        if manual:
            return manual
        return None

    print(f"\n{G}Found {len(files)} STL file(s):{RESET}\n")
    for i, f in enumerate(files):
        size_kb = f.stat().st_size / 1024
        print(f"  {DIM}{i+1:3d}{RESET}  {f.name:<35} {DIM}{size_kb:.1f} KB  {f.parent}{RESET}")

    choice = input(f"\n{Y}Select file number (or Enter to cancel): {RESET}").strip()
    if not choice.isdigit():
        return None
    idx = int(choice) - 1
    if 0 <= idx < len(files):
        return str(files[idx])
    return None


# ─────────────────────────────────────────────
# Interactive Menu
# ─────────────────────────────────────────────

def menu_generate_naca():
    """Prompt user for NACA designation and generate STL."""
    print(f"\n{C}NACA 4-digit airfoils available in your project:{RESET}")
    print("  0012  —  symmetric,  0% camber")
    print("  2412  —  cambered,   2% camber at 40% chord")
    print("  4412  —  cambered,   4% camber at 40% chord")

    des = input(f"\n{Y}Enter NACA designation (e.g. 0012): {RESET}").strip()
    if len(des) != 4 or not des.isdigit():
        print(f"{R}Invalid designation.{RESET}")
        return

    out_dir = Path.home() / "OpenFOAM" / "stl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"NACA{des}.stl"

    n_pts = input(f"{Y}Points per surface (default 200): {RESET}").strip()
    n_pts = int(n_pts) if n_pts.isdigit() else 200

    write_naca_stl(des, str(out_path), chord=1.0, n_points=n_pts)
    print(f"\n{G}STL saved to: {out_path}{RESET}")

    validate = input(f"{Y}Run watertight check? (y/n): {RESET}").lower()
    if validate == "y":
        check_watertight(str(out_path))


def menu_validate_stl():
    stl = browse_stl_files()
    if stl:
        units = detect_stl_scale(stl)
        print(f"\n{C}Detected units: {BOLD}{units}{RESET}")
        check_watertight(stl)

        if units == "mm":
            scale_it = input(f"\n{Y}Scale from mm → m? (y/n): {RESET}").lower()
            if scale_it == "y":
                out = stl.replace(".stl", "_m.stl").replace(".STL", "_m.STL")
                scale_stl(stl, out, scale=0.001)


def menu_browse():
    stl = browse_stl_files()
    if stl:
        print(f"\n{G}Selected: {stl}{RESET}")
        units = detect_stl_scale(stl)
        print(f"{C}Detected units: {BOLD}{units}{RESET}")
        check = input(f"{Y}Run watertight check? (y/n): {RESET}").lower()
        if check == "y":
            check_watertight(stl)


MENU = [
    ("Generate NACA 4-digit STL",       menu_generate_naca),
    ("Browse & select STL file",        menu_browse),
    ("Validate STL (watertight check)", menu_validate_stl),
    ("Exit",                            None),
]


def main():
    banner()
    # CLI mode: python3 airfoil_helper.py --generate 0012
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--generate", metavar="NACA", help="Generate NACA STL directly")
    parser.add_argument("--check", metavar="PATH", help="Check STL watertightness")
    parser.add_argument("--scale", metavar="PATH", help="Scale STL mm→m")
    args, _ = parser.parse_known_args()

    if args.generate:
        out = Path.home() / "OpenFOAM" / "stl" / f"NACA{args.generate}.stl"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_naca_stl(args.generate, str(out))
        check_watertight(str(out))
        return

    if args.check:
        check_watertight(args.check)
        return

    if args.scale:
        out = args.scale.replace(".stl", "_m.stl")
        scale_stl(args.scale, out)
        return

    # Interactive menu
    while True:
        print(f"{BOLD}foam-helper Menu{RESET}")
        for i, (label, _) in enumerate(MENU):
            print(f"  [{B}{i+1}{RESET}] {label}")

        choice = input(f"\n{Y}Select: {RESET}").strip()
        if not choice.isdigit():
            continue
        idx = int(choice) - 1
        if idx < 0 or idx >= len(MENU):
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
