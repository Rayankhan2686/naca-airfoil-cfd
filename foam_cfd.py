#!/usr/bin/env python3
"""
foam_cfd.py
===========
Unified OpenFOAM CFD launcher.
Combines the NACA research pipeline and SolidWorks import pipeline
into one clean menu-driven interface.

Usage:
    python3 foam_cfd.py
    alias foam-cfd="python3 ~/OpenFOAM/scripts/foam_cfd.py"

Modes:
    [1] foam airfoil (Research)   — Generate NACA 4-digit STLs & run CFD
    [2] foam helper  (SolidWorks) — Import any SolidWorks STL & run CFD
    [3] Exit
"""

import os
import sys
import math
import struct
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# Colours
# ─────────────────────────────────────────────
R    = "\033[91m"
G    = "\033[92m"
Y    = "\033[93m"
B    = "\033[94m"
C    = "\033[96m"
W    = "\033[97m"
DIM  = "\033[2m"
BOLD = "\033[1m"
RESET= "\033[0m"

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
HOME        = Path.home()
SCRIPTS_DIR = HOME / "OpenFOAM" / "scripts"
STL_DIR     = HOME / "OpenFOAM" / "stl"
RUN_DIR     = HOME / "OpenFOAM" / "run"
RESULTS_DIR = HOME / "OpenFOAM" / "results"


# ══════════════════════════════════════════════════════════════════
#  BANNERS
# ══════════════════════════════════════════════════════════════════

def banner_main():
    os.system("clear")
    print(f"""
{B}{BOLD}┌─────────────────────────────────────────────────────────────┐
│                                                             │
│        ███████╗ ██████╗  █████╗ ███╗   ███╗               │
│        ██╔════╝██╔═══██╗██╔══██╗████╗ ████║               │
│        █████╗  ██║   ██║███████║██╔████╔██║               │
│        ██╔══╝  ██║   ██║██╔══██║██║╚██╔╝██║               │
│        ██║     ╚██████╔╝██║  ██║██║ ╚═╝ ██║               │
│        ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝               │
│                                                             │
│              CFD Pipeline  ·  OpenFOAM 2412                │
│         Ubuntu 24  ·  k-ω SST  ·  simpleFoam              │
└─────────────────────────────────────────────────────────────┘{RESET}
""")


def banner_research():
    print(f"""
{C}{BOLD}┌─────────────────────────────────────────────────────────────┐
│   foam airfoil  ·  Research Mode                           │
│   NACA 4-digit  ·  STL Generator  ·  CFD Sweep            │
└─────────────────────────────────────────────────────────────┘{RESET}
""")


def banner_solidworks():
    print(f"""
{Y}{BOLD}┌─────────────────────────────────────────────────────────────┐
│   foam helper  ·  SolidWorks Mode                          │
│   STL Import  ·  Validation  ·  mm→m Scaling              │
└─────────────────────────────────────────────────────────────┘{RESET}
""")


# ══════════════════════════════════════════════════════════════════
#  SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════

def run_cmd(cmd, cwd=None, live=True):
    """Run shell command. live=True streams output."""
    print(f"{DIM}  $ {cmd}{RESET}")
    if live:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        return proc.returncode
    else:
        res = subprocess.run(cmd, shell=True, cwd=cwd,
                             capture_output=True, text=True)
        return res.returncode


def pause(msg="Press Enter to return to main menu..."):
    input(f"\n{DIM}{msg}{RESET}")


def section(title, colour=C):
    print(f"\n{colour}{BOLD}── {title} ──{RESET}\n")


# ══════════════════════════════════════════════════════════════════
#  NACA GEOMETRY  (self-contained, no external deps)
# ══════════════════════════════════════════════════════════════════

def naca4_points(designation: str, n_points: int = 200):
    des = designation.zfill(4)
    m = int(des[0]) / 100.0
    p = int(des[1]) / 10.0
    t = int(des[2:]) / 100.0

    beta = [math.pi * i / (n_points - 1) for i in range(n_points)]
    x    = [(1 - math.cos(b)) / 2 for b in beta]

    def thickness(xc):
        return (t / 0.2) * (
            0.2969 * math.sqrt(max(xc, 0))
            - 0.1260 * xc - 0.3516 * xc**2
            + 0.2843 * xc**3 - 0.1015 * xc**4
        )

    def camber(xc):
        if m == 0 or p == 0:
            return 0.0, 0.0
        if xc < p:
            yc  = (m / p**2) * (2*p*xc - xc**2)
            dyc = (2*m / p**2) * (p - xc)
        else:
            yc  = (m / (1-p)**2) * ((1-2*p) + 2*p*xc - xc**2)
            dyc = (2*m / (1-p)**2) * (p - xc)
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


def generate_naca_stl(designation: str, output_path: str,
                      chord: float = 1.0, n_points: int = 200,
                      extrude_z: float = 0.001):
    """Generate a watertight NACA 4-digit binary STL."""
    (xu, yu), (xl, yl) = naca4_points(designation, n_points)

    upper   = list(zip(xu, yu))
    lower   = list(zip(xl, yl))
    profile = upper + list(reversed(lower[1:-1]))
    px = [chord * p[0] for p in profile]
    py = [chord * p[1] for p in profile]
    n  = len(px)

    triangles = []

    def add_tri(p0, p1, p2):
        v1 = (p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2])
        v2 = (p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2])
        nx = v1[1]*v2[2] - v1[2]*v2[1]
        ny = v1[2]*v2[0] - v1[0]*v2[2]
        nz = v1[0]*v2[1] - v1[1]*v2[0]
        ln = math.sqrt(nx**2+ny**2+nz**2)
        if ln < 1e-20:
            return
        triangles.append(((nx/ln, ny/ln, nz/ln), p0, p1, p2))

    z0, z1 = 0.0, extrude_z

    # Side walls
    for i in range(n):
        j = (i+1) % n
        A = (px[i], py[i], z0)
        B = (px[j], py[j], z0)
        C = (px[j], py[j], z1)
        D = (px[i], py[i], z1)
        add_tri(A, B, D)
        add_tri(B, C, D)

    # Caps
    cx = sum(px) / n
    cy = sum(py) / n
    for i in range(n):
        j = (i+1) % n
        add_tri((cx,cy,z0), (px[j],py[j],z0), (px[i],py[i],z0))
        add_tri((cx,cy,z1), (px[i],py[i],z1), (px[j],py[j],z1))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    header = f"NACA{designation}".encode().ljust(80, b'\x00')
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(triangles)))
        for (nx,ny,nz), p0, p1, p2 in triangles:
            f.write(struct.pack("<fff", nx, ny, nz))
            for p in (p0, p1, p2):
                f.write(struct.pack("<fff", *p))
            f.write(struct.pack("<H", 0))

    print(f"{G}  ✔  Wrote {len(triangles)} triangles → {output_path}{RESET}")
    return output_path


# ══════════════════════════════════════════════════════════════════
#  STL VALIDATION & SCALING
# ══════════════════════════════════════════════════════════════════

def read_binary_stl(path: str):
    triangles = []
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        for _ in range(n):
            f.read(12)
            verts = []
            for _ in range(3):
                x, y, z = struct.unpack("<fff", f.read(12))
                verts.append((round(x,9), round(y,9), round(z,9)))
            f.read(2)
            triangles.append(tuple(verts))
    return triangles


def check_watertight(path: str) -> bool:
    from collections import defaultdict
    try:
        triangles = read_binary_stl(path)
    except Exception as e:
        print(f"{R}  Could not read STL: {e}{RESET}")
        return False

    edge_count = defaultdict(int)
    for v0, v1, v2 in triangles:
        for e in [(v0,v1),(v1,v2),(v2,v0)]:
            edge_count[tuple(sorted(e))] += 1

    bad   = [e for e, c in edge_count.items() if c != 2]
    total = len(edge_count)

    if not bad:
        print(f"{G}  ✔  Watertight — {total} edges, all valid.{RESET}")
        return True
    else:
        print(f"{R}  ✘  Not watertight — {len(bad)}/{total} bad edges.{RESET}")
        return False


def detect_units(path: str) -> str:
    try:
        tris = read_binary_stl(path)
        all_v = [v for tri in tris for v in tri]
        xs = [v[0] for v in all_v]
        ys = [v[1] for v in all_v]
        span = max(max(xs)-min(xs), max(ys)-min(ys))
        if span > 10:   return "mm"
        if span > 0.01: return "m"
    except Exception:
        pass
    return "unknown"


def scale_stl(input_path: str, output_path: str, scale: float = 0.001):
    triangles = read_binary_stl(input_path)
    header = b"Scaled by foam-cfd".ljust(80, b'\x00')
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(triangles)))
        for v0, v1, v2 in triangles:
            sv = [(v[0]*scale, v[1]*scale, v[2]*scale) for v in (v0,v1,v2)]
            v1v = tuple(sv[1][i]-sv[0][i] for i in range(3))
            v2v = tuple(sv[2][i]-sv[0][i] for i in range(3))
            nx = v1v[1]*v2v[2]-v1v[2]*v2v[1]
            ny = v1v[2]*v2v[0]-v1v[0]*v2v[2]
            nz = v1v[0]*v2v[1]-v1v[1]*v2v[0]
            ln = math.sqrt(nx**2+ny**2+nz**2) or 1.0
            f.write(struct.pack("<fff", nx/ln, ny/ln, nz/ln))
            for v in sv:
                f.write(struct.pack("<fff", *v))
            f.write(struct.pack("<H", 0))
    print(f"{G}  ✔  Scaled STL → {output_path}{RESET}")


# ══════════════════════════════════════════════════════════════════
#  STL FILE BROWSER
# ══════════════════════════════════════════════════════════════════

SEARCH_DIRS = [
    HOME / "OpenFOAM" / "stl",
    HOME / "Downloads",
    HOME / "Desktop",
    HOME,
    Path("/mnt/c/Users"),
]


def find_stl_files():
    found = []
    seen  = set()
    for base in SEARCH_DIRS:
        if base.exists():
            for pat in ["*.stl","*.STL"]:
                for f in base.rglob(pat):
                    if str(f) not in seen:
                        seen.add(str(f))
                        found.append(f)
    return found


def browse_stl(prompt="Select STL file") -> str | None:
    print(f"\n{C}Searching for STL files...{RESET}")
    files = find_stl_files()

    if not files:
        print(f"{Y}  No STL files found automatically.{RESET}")
        manual = input(f"{Y}  Enter STL path manually: {RESET}").strip()
        return manual if manual else None

    print(f"\n{G}  Found {len(files)} STL file(s):{RESET}\n")
    for i, f in enumerate(files):
        kb = f.stat().st_size / 1024
        print(f"  [{B}{i+1:2d}{RESET}]  {f.name:<38} {DIM}{kb:.1f} KB  {f.parent}{RESET}")

    choice = input(f"\n{Y}  {prompt} (number, or Enter to type path): {RESET}").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return str(files[idx])

    manual = input(f"{Y}  Enter full STL path: {RESET}").strip()
    return manual if manual else None


# ══════════════════════════════════════════════════════════════════
#  OPENFOAM CONFIG WRITERS
# ══════════════════════════════════════════════════════════════════

def _write(case_dir: Path, rel_path: str, content: str):
    full = case_dir / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def setup_case(case_dir: Path, stl_path: str, alpha_deg: float,
               Re: float, U_inf: float, n_iter: int):
    """Write all OpenFOAM dictionaries for a 2D airfoil simulation."""
    stl_path  = Path(stl_path).resolve()
    stl_file  = stl_path.name
    stl_name  = stl_path.stem
    patch     = stl_name.lower()

    # Copy STL
    (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)
    shutil.copy(stl_path, case_dir / "constant" / "triSurface" / stl_file)

    # Chord from bounding box
    chord = 1.0
    try:
        tris = read_binary_stl(str(stl_path))
        all_v = [v for t in tris for v in t]
        xs = [v[0] for v in all_v]
        chord = max(xs) - min(xs)
        if chord < 1e-6: chord = 1.0
    except Exception:
        pass

    nu    = U_inf * chord / Re
    tu    = 0.01
    l     = 0.07 * chord
    k_val = 1.5 * (U_inf * tu) ** 2
    omega = math.sqrt(k_val) / (0.09**0.25 * l)
    alpha = math.radians(alpha_deg)
    Ux    = U_inf * math.cos(alpha)
    Uy    = U_inf * math.sin(alpha)

    # blockMeshDict
    U_dom, D_dom, H_dom = 20, 30, 10
    _write(case_dir, "system/blockMeshDict", f"""FoamFile
{{ version 2.0; format ascii; class dictionary;
  location "system"; object blockMeshDict; }}
scale 1;
vertices
(
    (-{U_dom*chord:.4f} -{H_dom*chord:.4f} 0)
    ( {D_dom*chord:.4f} -{H_dom*chord:.4f} 0)
    ( {D_dom*chord:.4f}  {H_dom*chord:.4f} 0)
    (-{U_dom*chord:.4f}  {H_dom*chord:.4f} 0)
    (-{U_dom*chord:.4f} -{H_dom*chord:.4f} 0.001)
    ( {D_dom*chord:.4f} -{H_dom*chord:.4f} 0.001)
    ( {D_dom*chord:.4f}  {H_dom*chord:.4f} 0.001)
    (-{U_dom*chord:.4f}  {H_dom*chord:.4f} 0.001)
);
blocks ( hex (0 1 2 3 4 5 6 7) (100 80 1) simpleGrading (1 1 1) );
edges ();
boundary
(
    inlet   {{ type patch;        faces ((0 3 7 4)); }}
    outlet  {{ type patch;        faces ((1 5 6 2)); }}
    top     {{ type symmetryPlane; faces ((3 2 6 7)); }}
    bottom  {{ type symmetryPlane; faces ((0 4 5 1)); }}
    front   {{ type empty;        faces ((4 7 6 5)); }}
    back    {{ type empty;        faces ((0 3 2 1)); }}
);
mergePatchPairs ();
""")

    # snappyHexMeshDict
    _write(case_dir, "system/snappyHexMeshDict", f"""FoamFile
{{ version 2.0; format ascii; class dictionary;
  location "system"; object snappyHexMeshDict; }}
castellatedMesh true; snap true; addLayers true;
geometry
{{
    {stl_file} {{ type triSurfaceMesh; name {patch}; }}
}}
castellatedMeshControls
{{
    maxLocalCells 1000000; maxGlobalCells 2000000;
    minRefinementCells 10; nCellsBetweenLevels 3;
    features ( {{ file "{stl_file}.eMesh"; level 4; }} );
    refinementSurfaces {{ {patch} {{ level (4 5); }} }}
    resolveFeatureAngle 30; refinementRegions {{}}
    locationInMesh (0.5 0.1 0.0005);
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 3; tolerance 4.0; nSolveIter 100;
    nRelaxIter 5; nFeatureSnapIter 10;
    implicitFeatureSnap false; explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}
addLayersControls
{{
    relativeSizes true;
    layers {{ {patch} {{ nSurfaceLayers 5; }} }}
    expansionRatio 1.3; finalLayerThickness 0.3;
    minThickness 0.1; nGrow 0; featureAngle 60;
    nRelaxIter 3; nSmoothSurfaceNormals 1;
    nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4;
    maxConcave 80; minVol 1e-13; minTetQuality 1e-15;
    minArea -1; minTwist 0.02; minDeterminant 0.001;
    minFaceWeight 0.05; minVolRatio 0.01; minTriangleTwist -1;
    nSmoothScale 4; errorReduction 0.75;
}}
debug 0; mergeTolerance 1e-6;
""")

    # surfaceFeatureExtractDict
    _write(case_dir, "system/surfaceFeatureExtractDict", f"""FoamFile
{{ version 2.0; format ascii; class dictionary;
  location "system"; object surfaceFeatureExtractDict; }}
{stl_file}
{{
    extractionMethod extractFromSurface;
    extractFromSurfaceCoeffs {{ includedAngle 150; }}
    writeObj yes;
}}
""")

    # fvSchemes
    _write(case_dir, "system/fvSchemes", """FoamFile
{ version 2.0; format ascii; class dictionary;
  location "system"; object fvSchemes; }
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes    { default corrected; }
wallDist         { method meshWave; }
""")

    # fvSolution
    _write(case_dir, "system/fvSolution", """FoamFile
{ version 2.0; format ascii; class dictionary;
  location "system"; object fvSolution; }
solvers
{
    p     { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    U     { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    k     { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    omega { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
}
SIMPLE
{
    nNonOrthogonalCorrectors 2;
    residualControl { p 1e-4; U 1e-4; k 1e-4; omega 1e-4; }
    pRefCell 0; pRefValue 0;
}
relaxationFactors
{
    fields    { p 0.3; }
    equations { U 0.7; k 0.7; omega 0.7; }
}
""")

    # controlDict
    _write(case_dir, "system/controlDict", f"""FoamFile
{{ version 2.0; format ascii; class dictionary;
  location "system"; object controlDict; }}
application     simpleFoam;
startFrom       startTime; startTime 0;
stopAt          endTime;   endTime {n_iter};
deltaT          1;
writeControl    timeStep;  writeInterval 500;
purgeWrite      3; writeFormat ascii; writePrecision 8;
writeCompression off; runTimeModifiable true;
functions
{{
    forces
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        writeControl    timeStep; writeInterval 10;
        patches         ("{patch}");
        rho             rhoInf; rhoInf 1.225;
        liftDir         (0 1 0); dragDir (1 0 0);
        CofR            (0.25 0 0); pitchAxis (0 0 1);
        magUInf         {U_inf}; lRef {chord:.6f}; Aref {chord:.6f};
    }}
}}
""")

    # transportProperties
    _write(case_dir, "constant/transportProperties", f"""FoamFile
{{ version 2.0; format ascii; class dictionary;
  location "constant"; object transportProperties; }}
transportModel Newtonian;
nu {nu:.6e};
""")

    # turbulenceProperties
    _write(case_dir, "constant/turbulenceProperties", """FoamFile
{ version 2.0; format ascii; class dictionary;
  location "constant"; object turbulenceProperties; }
simulationType RAS;
RAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }
""")

    # Boundary conditions
    def bc_field(fname, dims, internal, patches):
        lines = [f"""FoamFile
{{ version 2.0; format ascii; class volScalarField;
  location "0"; object {fname}; }}
dimensions {dims};
internalField uniform {internal};
boundaryField
{{"""]
        for pname, ptype in patches:
            lines.append(f"    {pname} {{ {ptype} }}")
        lines.append("}\n")
        return "\n".join(lines)

    slip = "type symmetryPlane;"
    emp  = "type empty;"

    # U
    _write(case_dir, "0/U", f"""FoamFile
{{ version 2.0; format ascii; class volVectorField;
  location "0"; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField uniform ({Ux:.6f} {Uy:.6f} 0);
boundaryField
{{
    inlet   {{ type freestream; freestreamValue uniform ({Ux:.6f} {Uy:.6f} 0); }}
    outlet  {{ type freestream; freestreamValue uniform ({Ux:.6f} {Uy:.6f} 0); }}
    top     {{ {slip} }}
    bottom  {{ {slip} }}
    {patch} {{ type noSlip; }}
    front   {{ {emp} }}
    back    {{ {emp} }}
}}
""")

    # p
    _write(case_dir, "0/p", f"""FoamFile
{{ version 2.0; format ascii; class volScalarField;
  location "0"; object p; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet   {{ type freestreamPressure; }}
    outlet  {{ type freestreamPressure; }}
    top     {{ {slip} }}
    bottom  {{ {slip} }}
    {patch} {{ type zeroGradient; }}
    front   {{ {emp} }}
    back    {{ {emp} }}
}}
""")

    # k
    _write(case_dir, "0/k", f"""FoamFile
{{ version 2.0; format ascii; class volScalarField;
  location "0"; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {k_val:.6e};
boundaryField
{{
    inlet   {{ type fixedValue; value uniform {k_val:.6e}; }}
    outlet  {{ type zeroGradient; }}
    top     {{ {slip} }}
    bottom  {{ {slip} }}
    {patch} {{ type kqRWallFunction; value uniform {k_val:.6e}; }}
    front   {{ {emp} }}
    back    {{ {emp} }}
}}
""")

    # omega
    _write(case_dir, "0/omega", f"""FoamFile
{{ version 2.0; format ascii; class volScalarField;
  location "0"; object omega; }}
dimensions [0 0 -1 0 0 0 0];
internalField uniform {omega:.6e};
boundaryField
{{
    inlet   {{ type fixedValue; value uniform {omega:.6e}; }}
    outlet  {{ type zeroGradient; }}
    top     {{ {slip} }}
    bottom  {{ {slip} }}
    {patch} {{ type omegaWallFunction; value uniform {omega:.6e}; }}
    front   {{ {emp} }}
    back    {{ {emp} }}
}}
""")

    # nut
    _write(case_dir, "0/nut", f"""FoamFile
{{ version 2.0; format ascii; class volScalarField;
  location "0"; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet   {{ type calculated; value uniform 0; }}
    outlet  {{ type calculated; value uniform 0; }}
    top     {{ {slip} }}
    bottom  {{ {slip} }}
    {patch} {{ type nutkWallFunction; value uniform 0; }}
    front   {{ {emp} }}
    back    {{ {emp} }}
}}
""")

    return patch, chord


def read_force_coeffs(case_dir: Path):
    """Extract CL, CD, Cm from postProcessing."""
    for p in case_dir.rglob("forceCoeffs.dat"):
        try:
            with open(p) as f:
                lines = [l for l in f if not l.startswith("#") and l.strip()]
            if not lines: continue
            last = lines[-1].split()
            return float(last[3]), float(last[2]), float(last[1])
        except Exception:
            continue
    return None, None, None


def run_simulation(case_dir: Path, n_iter: int, paraview: bool = False):
    """Run the full mesh + solver sequence."""
    print(f"\n{C}  Running blockMesh...{RESET}")
    if run_cmd("blockMesh", cwd=case_dir) != 0:
        print(f"{R}  ✘ blockMesh failed{RESET}"); return False

    print(f"\n{C}  Running surfaceFeatureExtract...{RESET}")
    run_cmd("surfaceFeatureExtract", cwd=case_dir)

    print(f"\n{C}  Running snappyHexMesh...{RESET}")
    if run_cmd("snappyHexMesh -overwrite", cwd=case_dir) != 0:
        print(f"{R}  ✘ snappyHexMesh failed{RESET}"); return False

    print(f"\n{C}  Running simpleFoam ({n_iter} iterations)...{RESET}")
    run_cmd(f"simpleFoam | tee log.simpleFoam", cwd=case_dir)

    # .foam file for ParaView
    foam_file = case_dir / f"{case_dir.name}.foam"
    foam_file.touch()

    if paraview:
        subprocess.Popen(["paraview", str(foam_file)])

    return True


def print_results(CL, CD, Cm, alpha, airfoil_name):
    if CL is None:
        print(f"{Y}  No force coefficients found — check postProcessing.{RESET}")
        return
    LD = CL / CD if CD and abs(CD) > 1e-10 else float("nan")
    print(f"""
{G}{BOLD}  ┌─────────────────────────────────────────┐
  │  {airfoil_name:<20}  α = {alpha:+.1f}°          │
  ├─────────────────────────────────────────┤
  │  CL        =  {CL:+.4f}                    │
  │  CD        =  {CD:.6f}                  │
  │  Cm (c/4)  =  {Cm:+.4f}                    │
  │  L/D       =  {LD:.2f}                      │
  └─────────────────────────────────────────┘{RESET}""")


# ══════════════════════════════════════════════════════════════════
#  MODE 1 — foam airfoil (Research)
# ══════════════════════════════════════════════════════════════════

NACA_PRESETS = {
    "1": ("0012", "Symmetric  — 0% camber  (your Month 2 baseline)"),
    "2": ("2412", "Cambered   — 2% camber at 40% chord (Month 3)"),
    "3": ("4412", "Cambered   — 4% camber at 40% chord (Month 4)"),
    "4": ("custom", "Custom NACA 4-digit"),
}


def mode_research():
    while True:
        os.system("clear")
        banner_research()

        print(f"{BOLD}  What would you like to do?{RESET}\n")
        print(f"  [{B}1{RESET}]  Generate NACA STL file")
        print(f"  [{B}2{RESET}]  Run single simulation (one angle)")
        print(f"  [{B}3{RESET}]  Validate STL (watertight check)")
        print(f"  [{B}4{RESET}]  Back to main menu")

        choice = input(f"\n{Y}  Select: {RESET}").strip()

        if choice == "1":
            research_generate_stl()
        elif choice == "2":
            research_run_single()
        elif choice == "3":
            research_validate()
        elif choice == "4":
            return


def research_pick_naca() -> str | None:
    print(f"\n{C}  Select airfoil:{RESET}\n")
    for k, (code, desc) in NACA_PRESETS.items():
        print(f"  [{B}{k}{RESET}]  NACA {code if code != 'custom' else '????'}  —  {desc}")

    choice = input(f"\n{Y}  Select: {RESET}").strip()
    if choice not in NACA_PRESETS:
        return None

    code, _ = NACA_PRESETS[choice]
    if code == "custom":
        code = input(f"{Y}  Enter 4-digit code: {RESET}").strip()
    if len(code) != 4 or not code.isdigit():
        print(f"{R}  Invalid code.{RESET}")
        return None
    return code


def research_generate_stl():
    section("Generate NACA STL", C)
    code = research_pick_naca()
    if not code: pause(); return

    out = STL_DIR / f"NACA{code}.stl"
    STL_DIR.mkdir(parents=True, exist_ok=True)
    generate_naca_stl(code, str(out))

    run_check = input(f"\n{Y}  Run watertight check? (y/n): {RESET}").lower()
    if run_check == "y":
        check_watertight(str(out))

    pause()


def research_run_single():
    section("Run Single Simulation", C)

    # Pick airfoil
    code = research_pick_naca()
    if not code: pause(); return

    stl = STL_DIR / f"NACA{code}.stl"
    if not stl.exists():
        print(f"{Y}  STL not found. Generating NACA{code} now...{RESET}")
        STL_DIR.mkdir(parents=True, exist_ok=True)
        generate_naca_stl(code, str(stl))

    # Parameters
    alpha = input(f"\n{Y}  Angle of attack in degrees (default 0): {RESET}").strip()
    alpha = float(alpha) if alpha else 0.0

    Re_in = input(f"{Y}  Reynolds number (default 200000): {RESET}").strip()
    Re    = float(Re_in) if Re_in else 2e5

    U_in  = input(f"{Y}  Freestream velocity m/s (default 50): {RESET}").strip()
    U     = float(U_in) if U_in else 50.0

    n_in  = input(f"{Y}  Solver iterations (default 3000): {RESET}").strip()
    n_iter = int(n_in) if n_in.isdigit() else 3000

    pv = input(f"{Y}  Launch ParaView when done? (y/n): {RESET}").lower() == "y"

    case_name = f"NACA{code}_alpha{alpha:+.1f}".replace("+","p").replace("-","m").replace(".","d")
    case_dir  = RUN_DIR / case_name
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    if case_dir.exists():
        ow = input(f"{Y}  Case exists. Overwrite? (y/n): {RESET}").lower()
        if ow != "y": pause(); return
        shutil.rmtree(case_dir)

    print(f"\n{C}  Setting up case: {case_dir}{RESET}")
    patch, chord = setup_case(case_dir, str(stl), alpha, Re, U, n_iter)

    ok = run_simulation(case_dir, n_iter, pv)
    if ok:
        CL, CD, Cm = read_force_coeffs(case_dir)
        print_results(CL, CD, Cm, alpha, f"NACA {code}")

    pause()


def research_validate():
    section("Validate STL", C)
    files = list(STL_DIR.glob("*.stl")) if STL_DIR.exists() else []

    if not files:
        print(f"{Y}  No STL files in ~/OpenFOAM/stl/ — generate one first.{RESET}")
        pause(); return

    print(f"\n{G}  STL files in ~/OpenFOAM/stl/:{RESET}\n")
    for i, f in enumerate(files):
        print(f"  [{B}{i+1}{RESET}]  {f.name}")

    choice = input(f"\n{Y}  Select file: {RESET}").strip()
    if not choice.isdigit(): pause(); return
    idx = int(choice) - 1
    if 0 <= idx < len(files):
        check_watertight(str(files[idx]))

    pause()


# ══════════════════════════════════════════════════════════════════
#  MODE 2 — foam helper (SolidWorks)
# ══════════════════════════════════════════════════════════════════

def mode_solidworks():
    while True:
        os.system("clear")
        banner_solidworks()

        print(f"{BOLD}  What would you like to do?{RESET}\n")
        print(f"  [{Y}1{RESET}]  Import SolidWorks STL & run simulation")
        print(f"  [{Y}2{RESET}]  Validate STL (watertight check)")
        print(f"  [{Y}3{RESET}]  Scale STL from mm to metres")
        print(f"  [{Y}4{RESET}]  Back to main menu")

        choice = input(f"\n{Y}  Select: {RESET}").strip()

        if choice == "1":
            solidworks_run()
        elif choice == "2":
            solidworks_validate()
        elif choice == "3":
            solidworks_scale()
        elif choice == "4":
            return


def solidworks_run():
    section("SolidWorks STL → CFD Simulation", Y)

    stl = browse_stl("Select your SolidWorks STL")
    if not stl or not Path(stl).exists():
        print(f"{R}  STL not found.{RESET}"); pause(); return

    print(f"\n{G}  ✔  Selected: {stl}{RESET}")

    # Auto-detect and scale mm → m
    units = detect_units(stl)
    print(f"{C}  Detected units: {BOLD}{units}{RESET}")
    if units == "mm":
        scale_q = input(f"{Y}  Scale mm → m automatically? (y/n): {RESET}").lower()
        if scale_q == "y":
            scaled = stl.replace(".stl", "_m.stl").replace(".STL", "_m.STL")
            scale_stl(stl, scaled)
            stl = scaled

    # Validate
    check_q = input(f"{Y}  Run watertight check? (y/n): {RESET}").lower()
    if check_q == "y":
        ok = check_watertight(stl)
        if not ok:
            cont = input(f"{Y}  STL not watertight. Continue anyway? (y/n): {RESET}").lower()
            if cont != "y": pause(); return

    # Simulation parameters
    alpha = input(f"\n{Y}  Angle of attack in degrees (default 0): {RESET}").strip()
    alpha = float(alpha) if alpha else 0.0

    Re_in = input(f"{Y}  Reynolds number (default 200000): {RESET}").strip()
    Re    = float(Re_in) if Re_in else 2e5

    U_in  = input(f"{Y}  Freestream velocity m/s (default 50): {RESET}").strip()
    U     = float(U_in) if U_in else 50.0

    n_in  = input(f"{Y}  Solver iterations (default 3000): {RESET}").strip()
    n_iter = int(n_in) if n_in.isdigit() else 3000

    pv = input(f"{Y}  Launch ParaView when done? (y/n): {RESET}").lower() == "y"

    name     = Path(stl).stem
    case_dir = RUN_DIR / f"{name}_alpha{alpha:+.1f}".replace("+","p").replace("-","m").replace(".","d")
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    if case_dir.exists():
        ow = input(f"{Y}  Case exists. Overwrite? (y/n): {RESET}").lower()
        if ow != "y": pause(); return
        shutil.rmtree(case_dir)

    print(f"\n{C}  Setting up case: {case_dir}{RESET}")
    patch, chord = setup_case(case_dir, stl, alpha, Re, U, n_iter)

    ok = run_simulation(case_dir, n_iter, pv)
    if ok:
        CL, CD, Cm = read_force_coeffs(case_dir)
        print_results(CL, CD, Cm, alpha, name)

    pause()


def solidworks_validate():
    section("Validate STL", Y)
    stl = browse_stl("Select STL to validate")
    if not stl: pause(); return

    units = detect_units(stl)
    print(f"\n{C}  Detected units: {BOLD}{units}{RESET}")
    check_watertight(stl)
    pause()


def solidworks_scale():
    section("Scale STL mm → m", Y)
    stl = browse_stl("Select STL to scale")
    if not stl: pause(); return

    out = stl.replace(".stl","_m.stl").replace(".STL","_m.STL")
    scale_stl(stl, out)
    pause()


# ══════════════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════════════

def main():
    while True:
        banner_main()

        print(f"  {C}{BOLD}Choose your workflow:{RESET}\n")
        print(f"  [{C}1{RESET}]  {BOLD}foam airfoil{RESET}  {DIM}(Research){RESET}")
        print(f"       Generate NACA 0012 / 2412 / 4412 STLs and run CFD simulations")
        print(f"       Designed for your camber study at Re = 2×10⁵\n")
        print(f"  [{Y}2{RESET}]  {BOLD}foam helper{RESET}   {DIM}(SolidWorks){RESET}")
        print(f"       Import any SolidWorks STL, validate, scale mm→m, and run CFD")
        print(f"       For custom geometries exported from SolidWorks 2026\n")
        print(f"  [{R}3{RESET}]  Exit\n")

        choice = input(f"{Y}  Select: {RESET}").strip()

        if choice == "1":
            mode_research()
        elif choice == "2":
            mode_solidworks()
        elif choice == "3":
            print(f"\n{G}  Goodbye.\n{RESET}")
            sys.exit(0)


if __name__ == "__main__":
    main()
