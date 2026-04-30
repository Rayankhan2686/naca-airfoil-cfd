#!/usr/bin/env python3
"""
airfoil_pipeline.py
===================
Full end-to-end 2D airfoil CFD pipeline for OpenFOAM 2412.

Takes an STL file path and simulation parameters, auto-generates all
OpenFOAM configuration files, runs blockMesh → surfaceFeatureExtract →
snappyHexMesh → simpleFoam, and optionally launches ParaView.

Usage:
    python3 airfoil_pipeline.py
    python3 airfoil_pipeline.py --stl ~/OpenFOAM/stl/NACA0012.stl --alpha 0 --Re 200000
    alias foam-airfoil="python3 ~/OpenFOAM/scripts/airfoil_pipeline.py"
"""

import os
import sys
import math
import shutil
import struct
import subprocess
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
{B}{BOLD}╔══════════════════════════════════════════════════════╗
║       foam-airfoil  ·  2D CFD Pipeline  v1.0         ║
║       OpenFOAM 2412  ·  simpleFoam  ·  k-ω SST       ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def run(cmd, cwd=None, live=True):
    """Run shell command, optionally streaming output."""
    print(f"{DIM}$ {cmd}{RESET}")
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
        if res.returncode != 0:
            print(res.stdout[-2000:])
            print(res.stderr[-1000:])
        return res.returncode


# ─────────────────────────────────────────────
# STL helpers
# ─────────────────────────────────────────────

def get_stl_bounding_box(stl_path):
    """Return (xmin, xmax, ymin, ymax, zmin, zmax) from binary STL."""
    xs, ys, zs = [], [], []
    try:
        with open(stl_path, "rb") as f:
            f.read(80)
            n = struct.unpack("<I", f.read(4))[0]
            for _ in range(n):
                f.read(12)
                for _ in range(3):
                    x, y, z = struct.unpack("<fff", f.read(12))
                    xs.append(x); ys.append(y); zs.append(z)
                f.read(2)
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
    except Exception:
        return -0.5, 1.5, -0.5, 0.5, 0.0, 0.001   # safe defaults


def get_patch_name_from_boundary(case_dir):
    """Read polyMesh/boundary and return the airfoil patch name."""
    boundary = Path(case_dir) / "constant" / "polyMesh" / "boundary"
    if not boundary.exists():
        return "airfoil"
    with open(boundary) as f:
        content = f.read()
    # Return first patch that isn't inlet/outlet/top/bottom/front/back/defaultFaces
    import re
    patches = re.findall(r'^\s+(\w+)\s*\n\s*\{', content, re.MULTILINE)
    skip = {"inlet","outlet","top","bottom","front","back","defaultFaces","empty"}
    for p in patches:
        if p.lower() not in skip:
            return p
    return "airfoil"


# ─────────────────────────────────────────────
# Physics helpers
# ─────────────────────────────────────────────

def compute_nu(Re, U_inf, chord):
    """Kinematic viscosity from Re = U*c/nu."""
    return U_inf * chord / Re


def turbulence_ics(U_inf, intensity=0.01, length_scale_ratio=0.07, chord=1.0):
    """
    Compute k and omega freestream initial conditions.
    intensity       : turbulence intensity (fraction, e.g. 0.01 = 1%)
    length_scale_ratio : mixing length / chord
    """
    l = length_scale_ratio * chord
    k = 1.5 * (U_inf * intensity) ** 2
    omega = math.sqrt(k) / (0.09 ** 0.25 * l)
    return k, omega


# ─────────────────────────────────────────────
# File Writers
# ─────────────────────────────────────────────

def write_controlDict(case_dir, airfoil_patch, n_iter=3000):
    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| OpenFOAM 2412  ·  airfoil_pipeline.py auto-generated                       |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {n_iter};
deltaT          1;
writeControl    timeStep;
writeInterval   500;
purgeWrite      3;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   8;
runTimeModifiable true;

functions
{{
    forces
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        writeControl    timeStep;
        writeInterval   10;
        patches         ("{airfoil_patch}");
        rho             rhoInf;
        rhoInf          1.225;
        liftDir         (0 1 0);
        dragDir         (1 0 0);
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
        magUInf         1;       // overwritten at runtime
        lRef            1;
        Aref            1;
    }}
}}
"""
    _write(case_dir, "system/controlDict", content)


def write_fvSchemes(case_dir):
    content = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

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
"""
    _write(case_dir, "system/fvSchemes", content)


def write_fvSolution(case_dir):
    content = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}

solvers
{
    p
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }
    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }
    k
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }
    omega
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors  2;
    residualControl
    {
        p       1e-4;
        U       1e-4;
        k       1e-4;
        omega   1e-4;
    }
    pRefCell    0;
    pRefValue   0;
}

relaxationFactors
{
    fields  { p 0.3; }
    equations { U 0.7; k 0.7; omega 0.7; }
}
"""
    _write(case_dir, "system/fvSolution", content)


def write_blockMeshDict(case_dir, chord, alpha_deg):
    """
    Domain: 20c upstream, 30c downstream, 10c top and bottom.
    Angle of attack imposed by rotating inlet velocity vector.
    """
    U = 20   # cells upstream
    D = 30   # cells downstream
    H = 10   # half-height

    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}

scale   1;

vertices
(
    (-{U*chord:.4f}  -{H*chord:.4f}  0)      // 0
    ( {D*chord:.4f}  -{H*chord:.4f}  0)      // 1
    ( {D*chord:.4f}   {H*chord:.4f}  0)      // 2
    (-{U*chord:.4f}   {H*chord:.4f}  0)      // 3
    (-{U*chord:.4f}  -{H*chord:.4f}  0.001)  // 4
    ( {D*chord:.4f}  -{H*chord:.4f}  0.001)  // 5
    ( {D*chord:.4f}   {H*chord:.4f}  0.001)  // 6
    (-{U*chord:.4f}   {H*chord:.4f}  0.001)  // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (100 80 1) simpleGrading (1 1 1)
);

edges ();

boundary
(
    inlet
    {{
        type patch;
        faces ((0 3 7 4));
    }}
    outlet
    {{
        type patch;
        faces ((1 5 6 2));
    }}
    top
    {{
        type symmetryPlane;
        faces ((3 2 6 7));
    }}
    bottom
    {{
        type symmetryPlane;
        faces ((0 4 5 1));
    }}
    front
    {{
        type empty;
        faces ((4 7 6 5));
    }}
    back
    {{
        type empty;
        faces ((0 3 2 1));
    }}
);

mergePatchPairs ();
"""
    _write(case_dir, "system/blockMeshDict", content)


def write_snappyHexMeshDict(case_dir, stl_name, airfoil_patch):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       true;

geometry
{{
    {stl_name}
    {{
        type triSurfaceMesh;
        name {airfoil_patch};
    }}
}}

castellatedMeshControls
{{
    maxLocalCells       1000000;
    maxGlobalCells      2000000;
    minRefinementCells  10;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels 3;

    features
    (
        {{
            file "{stl_name}.eMesh";
            level 4;
        }}
    );

    refinementSurfaces
    {{
        {airfoil_patch}
        {{
            level (4 5);
        }}
    }}

    resolveFeatureAngle 30;
    refinementRegions {{}}

    locationInMesh (0.5 0.1 0.0005);
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch    3;
    tolerance       4.0;
    nSolveIter      100;
    nRelaxIter      5;
    nFeatureSnapIter 10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
        {airfoil_patch}
        {{
            nSurfaceLayers 5;
        }}
    }}
    expansionRatio          1.3;
    finalLayerThickness     0.3;
    minThickness            0.1;
    nGrow                   0;
    featureAngle            60;
    slipFeatureAngle        30;
    nRelaxIter              3;
    nSmoothSurfaceNormals   1;
    nSmoothNormals          3;
    nSmoothThickness        10;
    maxFaceThicknessRatio   0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle      90;
    nBufferCellsNoExtrude   0;
    nLayerIter              50;
}}

meshQualityControls
{{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minVol              1e-13;
    minTetQuality       1e-15;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.05;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
}}

debug 0;
mergeTolerance 1e-6;
"""
    _write(case_dir, "system/snappyHexMeshDict", content)


def write_surfaceFeatureExtractDict(case_dir, stl_name):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      surfaceFeatureExtractDict;
}}

{stl_name}
{{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {{
        includedAngle   150;
    }}
    writeObj            yes;
}}
"""
    _write(case_dir, "system/surfaceFeatureExtractDict", content)


def write_U(case_dir, U_inf, alpha_deg, airfoil_patch):
    alpha = math.radians(alpha_deg)
    Ux = U_inf * math.cos(alpha)
    Uy = U_inf * math.sin(alpha)
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}}

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform ({Ux:.6f} {Uy:.6f} 0);

boundaryField
{{
    inlet
    {{
        type        freestream;
        freestreamValue uniform ({Ux:.6f} {Uy:.6f} 0);
    }}
    outlet
    {{
        type        freestream;
        freestreamValue uniform ({Ux:.6f} {Uy:.6f} 0);
    }}
    top
    {{
        type        symmetryPlane;
    }}
    bottom
    {{
        type        symmetryPlane;
    }}
    {airfoil_patch}
    {{
        type        noSlip;
    }}
    front
    {{
        type        empty;
    }}
    back
    {{
        type        empty;
    }}
}}
"""
    _write(case_dir, "0/U", content)


def write_p(case_dir, airfoil_patch):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      p;
}}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type        freestreamPressure;
    }}
    outlet
    {{
        type        freestreamPressure;
    }}
    top
    {{
        type        symmetryPlane;
    }}
    bottom
    {{
        type        symmetryPlane;
    }}
    {airfoil_patch}
    {{
        type        zeroGradient;
    }}
    front
    {{
        type        empty;
    }}
    back
    {{
        type        empty;
    }}
}}
"""
    _write(case_dir, "0/p", content)


def write_k(case_dir, k_val, airfoil_patch):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      k;
}}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform {k_val:.6e};

boundaryField
{{
    inlet
    {{
        type        fixedValue;
        value       uniform {k_val:.6e};
    }}
    outlet
    {{
        type        zeroGradient;
    }}
    top
    {{
        type        symmetryPlane;
    }}
    bottom
    {{
        type        symmetryPlane;
    }}
    {airfoil_patch}
    {{
        type        kqRWallFunction;
        value       uniform {k_val:.6e};
    }}
    front
    {{
        type        empty;
    }}
    back
    {{
        type        empty;
    }}
}}
"""
    _write(case_dir, "0/k", content)


def write_omega(case_dir, omega_val, airfoil_patch):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      omega;
}}

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform {omega_val:.6e};

boundaryField
{{
    inlet
    {{
        type        fixedValue;
        value       uniform {omega_val:.6e};
    }}
    outlet
    {{
        type        zeroGradient;
    }}
    top
    {{
        type        symmetryPlane;
    }}
    bottom
    {{
        type        symmetryPlane;
    }}
    {airfoil_patch}
    {{
        type        omegaWallFunction;
        value       uniform {omega_val:.6e};
    }}
    front
    {{
        type        empty;
    }}
    back
    {{
        type        empty;
    }}
}}
"""
    _write(case_dir, "0/omega", content)


def write_nut(case_dir, airfoil_patch):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nut;
}}

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type        calculated;
        value       uniform 0;
    }}
    outlet
    {{
        type        calculated;
        value       uniform 0;
    }}
    top
    {{
        type        symmetryPlane;
    }}
    bottom
    {{
        type        symmetryPlane;
    }}
    {airfoil_patch}
    {{
        type        nutkWallFunction;
        value       uniform 0;
    }}
    front
    {{
        type        empty;
    }}
    back
    {{
        type        empty;
    }}
}}
"""
    _write(case_dir, "0/nut", content)


def write_turbulenceProperties(case_dir):
    content = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      turbulenceProperties;
}

simulationType  RAS;

RAS
{
    RASModel    kOmegaSST;
    turbulence  on;
    printCoeffs on;
}
"""
    _write(case_dir, "constant/turbulenceProperties", content)


def write_transportProperties(case_dir, nu):
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      transportProperties;
}}

transportModel  Newtonian;
nu              {nu:.6e};
"""
    _write(case_dir, "constant/transportProperties", content)


def _write(case_dir, rel_path, content):
    """Write content to case_dir/rel_path, creating dirs as needed."""
    full = Path(case_dir) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    print(f"{G}✔  Wrote {rel_path}{RESET}")


# ─────────────────────────────────────────────
# Force Coefficient Extraction
# ─────────────────────────────────────────────

def extract_force_coefficients(case_dir):
    """
    Read the last line of postProcessing/forces/0/forceCoeffs.dat
    and return (CL, CD, Cm).
    """
    fc_path = Path(case_dir) / "postProcessing" / "forces" / "0" / "forceCoeffs.dat"
    if not fc_path.exists():
        # Try alternate path used in newer OpenFOAM
        for p in Path(case_dir).rglob("forceCoeffs.dat"):
            fc_path = p
            break

    if not fc_path.exists():
        print(f"{Y}forceCoeffs.dat not found — check postProcessing directory.{RESET}")
        return None, None, None

    with open(fc_path) as f:
        lines = [l for l in f if not l.startswith("#") and l.strip()]

    if not lines:
        return None, None, None

    last = lines[-1].split()
    try:
        # Columns: Time  Cm  Cd  Cl  CmFront  CmBack
        Cm = float(last[1])
        CD = float(last[2])
        CL = float(last[3])
        return CL, CD, Cm
    except (IndexError, ValueError):
        return None, None, None


# ─────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────

def run_pipeline(stl_path, alpha_deg, Re, U_inf, case_name, n_iter, paraview):

    print(f"\n{C}{BOLD}Pipeline Parameters{RESET}")
    print(f"  STL         : {stl_path}")
    print(f"  Alpha       : {alpha_deg}°")
    print(f"  Re          : {Re:.2e}")
    print(f"  U_inf       : {U_inf} m/s")
    print(f"  Iterations  : {n_iter}")
    print(f"  Case dir    : {case_name}\n")

    stl_path = Path(stl_path).resolve()
    stl_name = stl_path.stem                         # e.g. "NACA0012"
    stl_file = stl_path.name                         # e.g. "NACA0012.stl"
    case_dir = Path(case_name).resolve()

    # ── 1. Setup case directory ──────────────────
    print(f"{C}[1/7]  Setting up case directory...{RESET}")
    if case_dir.exists():
        overwrite = input(f"{Y}  Case '{case_dir}' exists. Overwrite? (y/n): {RESET}").lower()
        if overwrite != "y":
            print(f"{R}Aborted.{RESET}"); return
        shutil.rmtree(case_dir)

    for d in ["system","constant/triSurface","0"]:
        (case_dir / d).mkdir(parents=True, exist_ok=True)

    # Copy STL into constant/triSurface
    stl_dest = case_dir / "constant" / "triSurface" / stl_file
    shutil.copy(stl_path, stl_dest)
    print(f"{G}  ✔  STL copied → constant/triSurface/{stl_file}{RESET}")

    # ── 2. Compute physics ───────────────────────
    print(f"\n{C}[2/7]  Computing flow parameters...{RESET}")
    xmin, xmax, ymin, ymax, zmin, zmax = get_stl_bounding_box(str(stl_dest))
    chord = xmax - xmin
    if chord < 1e-6:
        chord = 1.0
    print(f"  Chord detected : {chord:.4f} m")

    nu = compute_nu(Re, U_inf, chord)
    k_val, omega_val = turbulence_ics(U_inf)
    print(f"  nu             : {nu:.3e} m²/s")
    print(f"  k              : {k_val:.3e} m²/s²")
    print(f"  omega          : {omega_val:.3e} 1/s")

    airfoil_patch = stl_name.lower()   # patch name = STL filename lowercase

    # ── 3. Write config files ────────────────────
    print(f"\n{C}[3/7]  Writing OpenFOAM dictionaries...{RESET}")
    write_blockMeshDict(case_dir, chord, alpha_deg)
    write_snappyHexMeshDict(case_dir, stl_file, airfoil_patch)
    write_surfaceFeatureExtractDict(case_dir, stl_file)
    write_fvSchemes(case_dir)
    write_fvSolution(case_dir)
    write_controlDict(case_dir, airfoil_patch, n_iter)
    write_turbulenceProperties(case_dir)
    write_transportProperties(case_dir, nu)
    write_U(case_dir, U_inf, alpha_deg, airfoil_patch)
    write_p(case_dir, airfoil_patch)
    write_k(case_dir, k_val, airfoil_patch)
    write_omega(case_dir, omega_val, airfoil_patch)
    write_nut(case_dir, airfoil_patch)

    # ── 4. blockMesh ─────────────────────────────
    print(f"\n{C}[4/7]  Running blockMesh...{RESET}")
    rc = run("blockMesh", cwd=case_dir)
    if rc != 0:
        print(f"{R}✘  blockMesh failed. Check log above.{RESET}"); return

    # ── 5. Feature extraction + snappyHexMesh ────
        rc = run("surfaceFeatureExtract", cwd=case_dir)
        if rc != 0:
            print(f"{Y}⚠ surfaceFeatureExtract failed.{RESET}")


    rc = run("snappyHexMesh -overwrite", cwd=case_dir)
    if rc != 0:
        print(f"{R}✘  snappyHexMesh failed.{RESET}"); return

    # Re-read patch name from actual boundary file
    airfoil_patch = get_patch_name_from_boundary(case_dir)
    print(f"{G}  ✔  Airfoil patch name: '{airfoil_patch}'{RESET}")

    # Rewrite boundary condition files with correct patch name
    write_U(case_dir, U_inf, alpha_deg, airfoil_patch)
    write_p(case_dir, airfoil_patch)
    write_k(case_dir, k_val, airfoil_patch)
    write_omega(case_dir, omega_val, airfoil_patch)
    write_nut(case_dir, airfoil_patch)
    write_controlDict(case_dir, airfoil_patch, n_iter)

    # ── 6. simpleFoam ─────────────────────────────
    print(f"\n{C}[6/7]  Running simpleFoam ({n_iter} iterations)...{RESET}")
    rc = run(f"simpleFoam | tee log.simpleFoam", cwd=case_dir)
    if rc != 0:
        print(f"{R}✘  simpleFoam failed. Check log.simpleFoam{RESET}"); return

    # ── 7. Results ────────────────────────────────
    print(f"\n{C}[7/7]  Extracting results...{RESET}")
    CL, CD, Cm = extract_force_coefficients(case_dir)

    if CL is not None:
        LD = CL / CD if CD and abs(CD) > 1e-10 else float("nan")
        print(f"""
{G}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NACA Airfoil Results  ·  α = {alpha_deg}°
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
  CL         = {G}{CL:+.4f}{RESET}
  CD         = {Y}{CD:+.6f}{RESET}
  Cm (c/4)   = {CD:+.4f}
  L/D        = {B}{LD:.2f}{RESET}
{G}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
""")
    else:
        print(f"{Y}Could not extract CL/CD — check postProcessing directory.{RESET}")

    # Create .foam file for ParaView
    foam_file = case_dir / f"{case_dir.name}.foam"
    foam_file.touch()
    print(f"{G}✔  Created {foam_file.name} for ParaView{RESET}")

    if paraview:
        print(f"\n{C}Launching ParaView...{RESET}")
        subprocess.Popen(["paraview", str(foam_file)])

    print(f"\n{G}✔  Pipeline complete. Case: {case_dir}{RESET}\n")


# ─────────────────────────────────────────────
# Interactive prompt
# ─────────────────────────────────────────────

def interactive_mode():
    print(f"{Y}No STL path provided.{RESET}")
    print(f"{Y}Tip: use --stl flag directly, e.g:{RESET}")
    print(f"  foam-airfoil --stl ~/OpenFOAM/stl/NACA0012.stl --alpha 0 --Re 200000")
    stl = input(f"\n{Y}Enter full STL path: {RESET}").strip()
    if not stl:
        stl = input(f"{Y}Enter STL file path: {RESET}").strip()
    if not stl or not Path(stl).exists():
        print(f"{R}STL file not found.{RESET}"); return

    alpha = input(f"{Y}Angle of attack (degrees, default 0): {RESET}").strip()
    alpha = float(alpha) if alpha else 0.0

    Re_in = input(f"{Y}Reynolds number (default 200000): {RESET}").strip()
    Re = float(Re_in) if Re_in else 2e5

    U_in = input(f"{Y}Freestream velocity m/s (default 50): {RESET}").strip()
    U = float(U_in) if U_in else 50.0

    n_in = input(f"{Y}Solver iterations (default 3000): {RESET}").strip()
    n_iter = int(n_in) if n_in.isdigit() else 3000

    stl_name = Path(stl).stem
    case_default = str(Path.home() / "OpenFOAM" / "run" / f"{stl_name}_alpha{int(alpha)}")
    case_in = input(f"{Y}Case directory (default {case_default}): {RESET}").strip()
    case = case_in or case_default

    pv = input(f"{Y}Launch ParaView after simulation? (y/n): {RESET}").lower() == "y"

    run_pipeline(stl, alpha, Re, U, case, n_iter, pv)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    banner()
    parser = argparse.ArgumentParser(
        description="foam-airfoil: 2D airfoil CFD pipeline"
    )
    parser.add_argument("--stl",     help="Path to STL file")
    parser.add_argument("--alpha",   type=float, default=0.0,    help="Angle of attack (deg)")
    parser.add_argument("--Re",      type=float, default=2e5,    help="Reynolds number")
    parser.add_argument("--U",       type=float, default=50.0,   help="Freestream velocity (m/s)")
    parser.add_argument("--niter",   type=int,   default=3000,   help="Solver iterations")
    parser.add_argument("--case",    default=None,               help="Output case directory")
    parser.add_argument("--paraview", action="store_true",       help="Launch ParaView when done")
    args = parser.parse_args()

    if not args.stl:
        interactive_mode()
        return

    stl = Path(args.stl)
    if not stl.exists():
        print(f"{R}STL file not found: {stl}{RESET}"); sys.exit(1)

    case = args.case or str(
        Path.home() / "OpenFOAM" / "run" / f"{stl.stem}_alpha{int(args.alpha)}"
    )

    run_pipeline(str(stl), args.alpha, args.Re, args.U, case, args.niter, args.paraview)


if __name__ == "__main__":
    main()
