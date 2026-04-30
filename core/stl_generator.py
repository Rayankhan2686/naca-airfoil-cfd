"""
Watertight ASCII STL generator for NACA 4-digit airfoils.
Supports: 0012, 2412, 4412
Uses cosine spacing, fan triangulation for end caps, outward normals.
"""

import math
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# NACA 4-digit geometry
# ---------------------------------------------------------------------------

def _naca4(code: str, n_pts: int = 100) -> list[tuple[float, float]]:
    """
    Return (x, y) points along the FULL closed airfoil contour (upper then lower),
    starting and ending at the trailing edge.
    n_pts: number of points on each surface (total = 2*n_pts - 1 open trailing edge).
    """
    code = code.lower().replace("naca", "").strip()
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:]) / 100.0

    def thickness(x):
        return 5 * t * (0.2969 * math.sqrt(x)
                        - 0.1260 * x
                        - 0.3516 * x**2
                        + 0.2843 * x**3
                        - 0.1015 * x**4)

    def camber_and_slope(x):
        if m == 0 or p == 0:
            return 0.0, 0.0
        if x < p:
            yc = m / p**2 * (2 * p * x - x**2)
            dyc = 2 * m / p**2 * (p - x)
        else:
            yc = m / (1 - p)**2 * (1 - 2 * p + 2 * p * x - x**2)
            dyc = 2 * m / (1 - p)**2 * (p - x)
        return yc, dyc

    # cosine-spaced x stations
    betas = [math.pi * i / (n_pts - 1) for i in range(n_pts)]
    xs = [(1 - math.cos(b)) / 2 for b in betas]

    upper, lower = [], []
    for x in xs:
        yt = thickness(x)
        yc, dyc = camber_and_slope(x)
        theta = math.atan(dyc)
        xu = x  - yt * math.sin(theta)
        yu = yc + yt * math.cos(theta)
        xl = x  + yt * math.sin(theta)
        yl = yc - yt * math.cos(theta)
        upper.append((xu, yu))
        lower.append((xl, yl))

    # Close trailing edge precisely
    upper[-1] = (1.0, 0.0)
    lower[-1] = (1.0, 0.0)

    # Full contour: upper LE→TE, then lower TE→LE (skip shared TE and LE)
    contour = upper + lower[-2::-1]
    return contour


# ---------------------------------------------------------------------------
# STL helpers
# ---------------------------------------------------------------------------

def _normal(v0, v1, v2):
    ax, ay, az = v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2]
    bx, by, bz = v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2]
    nx = ay*bz - az*by
    ny = az*bx - ax*bz
    nz = ax*by - ay*bx
    mag = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
    return nx/mag, ny/mag, nz/mag


def _tri(f, v0, v1, v2):
    nx, ny, nz = _normal(v0, v1, v2)
    f.write(f"  facet normal {nx:.6e} {ny:.6e} {nz:.6e}\n")
    f.write("    outer loop\n")
    for v in (v0, v1, v2):
        f.write(f"      vertex {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
    f.write("    endloop\n")
    f.write("  endfacet\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED = {"naca0012", "naca2412", "naca4412"}


def generate_stl(airfoil: str, out_dir: str, n_pts: int = 100, span: float = 0.1) -> str:
    """
    Generate a watertight ASCII STL for *airfoil* (e.g. 'naca0012').
    Returns the path to the written STL file.
    """
    key = airfoil.lower().replace(" ", "")
    if key not in SUPPORTED:
        raise ValueError(f"Unsupported airfoil '{airfoil}'. Choose from {SUPPORTED}.")

    code = key.replace("naca", "")
    contour = _naca4(code, n_pts)
    n = len(contour)

    z0, z1 = 0.0, span

    # 3-D contour rings at z=0 (back) and z=span (front)
    back  = [(x, y, z0) for x, y in contour]
    front = [(x, y, z1) for x, y in contour]

    out_path = Path(out_dir) / f"{key.upper()}.stl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    name = key.upper()
    with open(out_path, "w") as f:
        f.write(f"solid {name}\n")

        # --- Side (extrusion) quads as two triangles each ---
        for i in range(n - 1):
            b0, b1 = back[i],  back[i+1]
            fr0, fr1 = front[i], front[i+1]
            # outward normal is determined by winding; _tri computes it
            _tri(f, b0, fr0, fr1)
            _tri(f, b0, fr1, b1)

        # Close the loop (last→first)
        _tri(f, back[-1],  front[-1], front[0])
        _tri(f, back[-1],  front[0],  back[0])

        # --- Back cap (z=0, normal pointing -z) ---
        # Fan from centroid; for outward normal at z=0 → -z, winding must be CW when viewed from -z
        cx = sum(p[0] for p in contour) / n
        cy = sum(p[1] for p in contour) / n
        centroid_back = (cx, cy, z0)
        for i in range(n - 1):
            _tri(f, centroid_back, back[i+1], back[i])
        _tri(f, centroid_back, back[0], back[-1])

        # --- Front cap (z=span, normal pointing +z) ---
        centroid_front = (cx, cy, z1)
        for i in range(n - 1):
            _tri(f, centroid_front, front[i], front[i+1])
        _tri(f, centroid_front, front[-1], front[0])

        f.write(f"endsolid {name}\n")

    return str(out_path)


if __name__ == "__main__":
    import sys
    af = sys.argv[1] if len(sys.argv) > 1 else "naca0012"
    path = generate_stl(af, "/tmp", span=0.1)
    print(f"Written: {path}")
