"""
custommesh_builder.py — Writes a complete OpenFOAM simpleFoam/kOmegaSST case
directory for any airfoil, with all mesh parameters read from a config dict
(loaded from custommesh_config.json).

This file is COMPLETELY INDEPENDENT from case_builder.py.
Do NOT import from, or modify, case_builder.py.

Physics (Re=2e5, chord=1 m) — identical to case_builder.py:
  V         = 2.4751 m/s
  nu        = 1.2375e-5 m2/s
  k_inf     = 2.297e-4 m2/s2
  omega_inf = 3.95 1/s
  chord     = 1.0 m
  span      = 0.1 m
  Aref      = 0.1 m2
"""

import math
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Physics constants
# ---------------------------------------------------------------------------
V         = 2.4751
NU        = 1.2375e-5
K_INF     = 2.297e-4
OMEGA_INF = 3.95
CHORD     = 1.0
SPAN      = 0.1
AREF      = 0.1
RHO       = 1.225

DEFAULTS = {
    "nx": 100, "ny": 80, "nz": 1,
    "inlet": 20, "outlet": 30, "top_bottom": 10,
    "refine_min": 0, "refine_max": 0,
    "end_time": 3000,
}


def _alpha_to_vec(alpha_deg: float) -> tuple[float, float]:
    a = math.radians(alpha_deg)
    return math.cos(a), math.sin(a)


# ---------------------------------------------------------------------------
# File content builders
# ---------------------------------------------------------------------------

def _header(cls: str, obj: str, location: str = "system") -> str:
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "{location}";
    object      {obj};
}}
"""


def _build_U(alpha_deg: float, patch: str) -> str:
    ux, uy = _alpha_to_vec(alpha_deg)
    Uvec = f"({ux*V:.6f} {uy*V:.6f} 0)"
    return f"""{_header("volVectorField", "U", "0")}
dimensions      [0 1 -1 0 0 0 0];

internalField   uniform {Uvec};

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform {Uvec};
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform {Uvec};
    }}
    top
    {{
        type            symmetry;
    }}
    bottom
    {{
        type            symmetry;
    }}
    {patch}
    {{
        type            noSlip;
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}
}}
"""


def _build_p(patch: str) -> str:
    return f"""{_header("volScalarField", "p", "0")}
dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform 0;
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform 0;
    }}
    top
    {{
        type            symmetry;
    }}
    bottom
    {{
        type            symmetry;
    }}
    {patch}
    {{
        type            zeroGradient;
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}
}}
"""


def _build_k(patch: str) -> str:
    return f"""{_header("volScalarField", "k", "0")}
dimensions      [0 2 -2 0 0 0 0];

internalField   uniform {K_INF};

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform {K_INF};
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform {K_INF};
    }}
    top
    {{
        type            symmetry;
    }}
    bottom
    {{
        type            symmetry;
    }}
    {patch}
    {{
        type            kqRWallFunction;
        value           uniform {K_INF};
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}
}}
"""


def _build_omega(patch: str) -> str:
    return f"""{_header("volScalarField", "omega", "0")}
dimensions      [0 0 -1 0 0 0 0];

internalField   uniform {OMEGA_INF};

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform {OMEGA_INF};
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform {OMEGA_INF};
    }}
    top
    {{
        type            symmetry;
    }}
    bottom
    {{
        type            symmetry;
    }}
    {patch}
    {{
        type            omegaWallFunction;
        value           uniform {OMEGA_INF};
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}
}}
"""


def _build_nut(patch: str) -> str:
    return f"""{_header("volScalarField", "nut", "0")}
dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    outlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    top
    {{
        type            symmetry;
    }}
    bottom
    {{
        type            symmetry;
    }}
    {patch}
    {{
        type            nutkWallFunction;
        value           uniform 0;
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}
}}
"""


def _build_transport_props() -> str:
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      transportProperties;
}}

transportModel  Newtonian;

nu              {NU};
"""


def _build_turbulence_props() -> str:
    return """FoamFile
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
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""


def _build_block_mesh(patch: str, cfg: dict) -> str:
    nx  = cfg["nx"]
    ny  = cfg["ny"]
    nz  = cfg["nz"]
    x0  = -cfg["inlet"]
    x1  =  cfg["outlet"]
    y0  = -cfg["top_bottom"]
    y1  =  cfg["top_bottom"]
    return f"""FoamFile
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
    ({x0}  {y0}  0   )   // 0
    ( {x1}  {y0}  0   )   // 1
    ( {x1}  {y1}  0   )   // 2
    ({x0}  {y1}  0   )   // 3
    ({x0}  {y0}  0.1 )   // 4
    ( {x1}  {y0}  0.1 )   // 5
    ( {x1}  {y1}  0.1 )   // 6
    ({x0}  {y1}  0.1 )   // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

boundary
(
    inlet
    {{
        type patch;
        faces ( (0 4 7 3) );
    }}
    outlet
    {{
        type patch;
        faces ( (1 2 6 5) );
    }}
    bottom
    {{
        type symmetry;
        faces ( (0 1 5 4) );
    }}
    top
    {{
        type symmetry;
        faces ( (3 7 6 2) );
    }}
    front
    {{
        type empty;
        faces ( (4 5 6 7) );
    }}
    back
    {{
        type empty;
        faces ( (0 3 2 1) );
    }}
);
"""


def _build_snappy(patch: str, stl_name: str, cfg: dict) -> str:
    rmin = cfg["refine_min"]
    rmax = cfg["refine_max"]
    feat_level = max(rmax, 1)
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       false;

geometry
{{
    {stl_name}
    {{
        type triSurfaceMesh;
        name {patch};
    }}
}}

castellatedMeshControls
{{
    maxLocalCells       2000000;
    maxGlobalCells      4000000;
    minRefinementCells  10;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels 3;
    resolveFeatureAngle 30;

    features
    (
        {{
            file "{stl_name[:-4]}.eMesh";
            level {feat_level};
        }}
    );

    refinementSurfaces
    {{
        {patch}
        {{
            level ({rmin} {rmax});
            patchInfo
            {{
                type wall;
            }}
        }}
    }}

    refinementRegions
    {{
    }}

    locationInMesh (0.5 0.1 0.0005);
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch        3;
    tolerance           2.0;
    nSolveIter          30;
    nRelaxIter          5;
    nFeatureSnapIter    10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
    }}
    expansionRatio      1.0;
    finalLayerThickness 0.3;
    minThickness        0.1;
    nGrow               0;
    featureAngle        60;
    nRelaxIter          3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle  90;
    nBufferCellsNoExtrude 0;
    nLayerIter          50;
}}

meshQualityControls
{{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minVol              1e-13;
    minTetQuality       1e-30;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.05;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
    relaxed
    {{
        maxNonOrtho     75;
    }}
}}

debug           0;
mergeTolerance  1e-6;
"""


def _build_surface_feature_extract(stl_name: str) -> str:
    return f"""FoamFile
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


def _build_control_dict(patch: str, alpha_deg: float, cfg: dict) -> str:
    alpha_rad = math.radians(alpha_deg)
    lx = -math.sin(alpha_rad)
    ly =  math.cos(alpha_rad)
    dx =  math.cos(alpha_rad)
    dy =  math.sin(alpha_rad)
    end_time = cfg["end_time"]
    return f"""FoamFile
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
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   500;
purgeWrite      3;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    forceCoeffs
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        writeControl    timeStep;
        writeInterval   1;
        log             true;

        patches         ({patch});
        rho             rhoInf;
        rhoInf          1.225;
        liftDir         (0 1 0);
        dragDir         (1 0 0);
        CofR            (0.25 0 0.05);
        pitchAxis       (0 0 1);
        magUInf         {V};
        lRef            {CHORD};
        Aref            {AREF};
    }}
}}
"""


def _build_fv_schemes() -> str:
    return """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
}

divSchemes
{
    default                         none;
    div(phi,U)                      bounded Gauss linearUpwindV grad(U);
    div(phi,k)                      bounded Gauss upwind;
    div(phi,omega)                  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U)))))   Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

wallDist
{
    method meshWave;
}
"""


def _build_fv_solution() -> str:
    return """FoamFile
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
    nNonOrthogonalCorrectors 0;
    consistent      yes;
}

relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
        k               0.7;
        omega           0.7;
    }
}
"""


def _build_decompose_par() -> str:
    return """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      decomposeParDict;
}

numberOfSubdomains  1;
method              simple;
simpleCoeffs
{
    n               (1 1 1);
    delta           0.001;
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_case(case_dir: str, airfoil: str, alpha_deg: float,
               stl_src: str | None = None, cfg: dict | None = None) -> str:
    """
    Write a complete OpenFOAM case to *case_dir* using *cfg* for mesh parameters.

    Parameters
    ----------
    case_dir  : destination directory (created if absent)
    airfoil   : any identifier, e.g. 'my_wing' or 'naca6412'
    alpha_deg : angle of attack in degrees
    stl_src   : path to the STL to copy into constant/triSurface/ (optional)
    cfg       : mesh settings dict; defaults to DEFAULTS if None
    """
    if cfg is None:
        cfg = dict(DEFAULTS)

    key      = airfoil.lower().replace(" ", "")
    patch    = key
    stl_name = key.upper() + ".stl"

    case = Path(case_dir)
    for d in [case / "0", case / "constant" / "triSurface", case / "system"]:
        d.mkdir(parents=True, exist_ok=True)

    if stl_src and Path(stl_src).exists():
        shutil.copy2(stl_src, case / "constant" / "triSurface" / stl_name)

    (case / "0" / "U").write_text(_build_U(alpha_deg, patch))
    (case / "0" / "p").write_text(_build_p(patch))
    (case / "0" / "k").write_text(_build_k(patch))
    (case / "0" / "omega").write_text(_build_omega(patch))
    (case / "0" / "nut").write_text(_build_nut(patch))

    (case / "constant" / "transportProperties").write_text(_build_transport_props())
    (case / "constant" / "turbulenceProperties").write_text(_build_turbulence_props())

    (case / "system" / "blockMeshDict").write_text(_build_block_mesh(patch, cfg))
    (case / "system" / "snappyHexMeshDict").write_text(_build_snappy(patch, stl_name, cfg))
    (case / "system" / "surfaceFeatureExtractDict").write_text(_build_surface_feature_extract(stl_name))
    (case / "system" / "controlDict").write_text(_build_control_dict(patch, alpha_deg, cfg))
    (case / "system" / "fvSchemes").write_text(_build_fv_schemes())
    (case / "system" / "fvSolution").write_text(_build_fv_solution())
    (case / "system" / "decomposeParDict").write_text(_build_decompose_par())

    return str(case)
