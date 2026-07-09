"""
Writes a complete OpenFOAM simpleFoam / kOmegaSST case directory
for any airfoil geometry at Re=2e5, chord=1 m.

The `airfoil` argument may be any identifier (e.g. 'naca0012', 'my_wing',
'delta_v2').  It is used as the OpenFOAM patch name and as the STL file
basename (upper-cased, e.g. MY_WING.stl).  No NACA-specific logic is applied.

Locked physics (Re=2e5, chord=1 m):
  V         = 2.4751 m/s
  rho       = 1.225  kg/m3
  mu        = 1.516e-5 Pa.s
  nu        = 1.2375e-5 m2/s
  k_inf     = 2.297e-4 m2/s2
  omega_inf = 3.95 1/s
  chord     = 1.0 m
  span      = 0.1 m
  Aref      = 0.1 m2
"""

import math
import os
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


def _build_U(alpha_deg: float, airfoil_patch: str) -> str:
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
    {airfoil_patch}
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




def _build_p_clean(airfoil_patch: str) -> str:
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
    {airfoil_patch}
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


def _build_k(airfoil_patch: str) -> str:
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
    {airfoil_patch}
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


def _build_omega(airfoil_patch: str) -> str:
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
    {airfoil_patch}
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


def _build_nut(airfoil_patch: str) -> str:
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
    {airfoil_patch}
    {{
        type            nutUSpaldingWallFunction;
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


def _build_block_mesh(airfoil_patch: str) -> str:
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
    (-20 -20  0   )   // 0
    ( 40 -20  0   )   // 1
    ( 40  20  0   )   // 2
    (-20  20  0   )   // 3
    (-20 -20  0.1 )   // 4
    ( 40 -20  0.1 )   // 5
    ( 40  20  0.1 )   // 6
    (-20  20  0.1 )   // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (120 100 1) simpleGrading (1 1 1)
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
        faces ( (0 3 2 1) );
    }}
    back
    {{
        type empty;
        faces ( (4 5 6 7) );
    }}
);
"""


def _build_block_mesh_cmesh(airfoil_patch: str, stl_name: str,
                            nx: int = 200, ny: int = 150) -> str:
    """
    C-mesh blockMeshDict using the blockMesh project feature.
    Produces a true 2D mesh (1 cell in z, no snappyHexMesh z-splitting).

    x=chord (0=LE,1=TE), y=lift/vertical, z=span (empty, 0→0.1).
    C-arc radius 20 centred at (0.3,0). Wake extends to x=40.
    6 blocks: lower/upper × (leading|middle|wake). 24 vertices total.

    nx = total chordwise cells (distributed proportionally across the 3 sections).
    ny = normal cells (from airfoil surface to far-field arc).
    Z is always 1 (2D empty direction, locked).
    """
    R        = 20.0
    xS       = 0.3
    yL       = -0.06
    yU       =  0.06
    xMax     = 40.0
    xMin_prj = -20.0   # projects onto cylinder → (-19.7, 0)

    # Distribute nx chordwise cells proportionally to the baseline 75:112:113 split
    _BASE = 300
    xUC = max(1, round(nx * 75  / _BASE))
    xMC = max(1, round(nx * 112 / _BASE))
    xDC = max(1, nx - xUC - xMC)
    nW  = ny

    lG  = 0.2
    xUG = 5.0
    xDG = 10.0
    wG  = 400

    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}

scale   1;

geometry
{{
    {airfoil_patch}
    {{
        type   triSurfaceMesh;
        file   "{stl_name}";
    }}
    inlet_arc
    {{
        type   cylinder;
        point1 ({xS} 0 -1e6);
        point2 ({xS} 0  1e6);
        radius {R};
    }}
}}

vertices
(
    // z=0.1 plane, vertices 0-11
    project ({xS}        {-R}  0.1) (inlet_arc)      // 0
    (1       {-R}        0.1)                         // 1
    ({xMax}  {-R}        0.1)                         // 2
    project ({xMin_prj}   0   0.1) (inlet_arc)       // 3
    project (0            0   0.1) ({airfoil_patch}) // 4  LE
    project (1            0   0.1) ({airfoil_patch}) // 5  TE
    ({xMax}  0            0.1)                        // 6
    project ({xS}        {yL}  0.1) ({airfoil_patch}) // 7  lower surface
    project ({xS}        {yU}  0.1) ({airfoil_patch}) // 8  upper surface
    project ({xS}        {R}   0.1) ({airfoil_patch}) // 9  snaps to upper surf
    project (1           {R}   0.1) ({airfoil_patch}) // 10 snaps to TE
    ({xMax}  {R}          0.1)                         // 11

    // z=0 plane, vertices 12-23
    project ({xS}        {-R}  0) (inlet_arc)       // 12
    (1       {-R}        0)                          // 13
    ({xMax}  {-R}        0)                          // 14
    project ({xMin_prj}   0   0) (inlet_arc)        // 15
    project (0            0   0) ({airfoil_patch})  // 16 LE
    project (1            0   0) ({airfoil_patch})  // 17 TE
    ({xMax}  0            0)                         // 18
    project ({xS}        {yL}  0) ({airfoil_patch}) // 19 lower surface
    project ({xS}        {yU}  0) ({airfoil_patch}) // 20 upper surface
    project ({xS}        {R}   0) ({airfoil_patch}) // 21 snaps to upper surf
    project (1           {R}   0) ({airfoil_patch}) // 22 snaps to TE
    ({xMax}  {R}          0)                         // 23
);

blocks
(
    hex ( 7  4 16 19  0  3 15 12) ({xUC} 1 {nW})
    edgeGrading
    (
        {lG}  {lG}  {xUG} {xUG}
        1 1 1 1
        {wG} {wG} {wG} {wG}
    )
    hex ( 5  7 19 17  1  0 12 13) ({xMC} 1 {nW}) simpleGrading (1 1 {wG})
    hex (17 18  6  5 13 14  2  1) ({xDC} 1 {nW}) simpleGrading ({xDG} 1 {wG})
    hex (20 16  4  8 21 15  3  9) ({xUC} 1 {nW})
    edgeGrading
    (
        {lG}  {lG}  {xUG} {xUG}
        1 1 1 1
        {wG} {wG} {wG} {wG}
    )
    hex (17 20  8  5 22 21  9 10) ({xMC} 1 {nW}) simpleGrading (1 1 {wG})
    hex ( 5  6 18 17 10 11 23 22) ({xDC} 1 {nW}) simpleGrading ({xDG} 1 {wG})
);

edges
(
    project  4  7 ({airfoil_patch})
    project  7  5 ({airfoil_patch})
    project  4  8 ({airfoil_patch})
    project  8  5 ({airfoil_patch})
    project 16 19 ({airfoil_patch})
    project 19 17 ({airfoil_patch})
    project 16 20 ({airfoil_patch})
    project 20 17 ({airfoil_patch})
    project  3  0 (inlet_arc)
    project  3  9 (inlet_arc)
    project 15 12 (inlet_arc)
    project 15 21 (inlet_arc)
);

boundary
(
    {airfoil_patch}
    {{
        type wall;
        faces
        (
            ( 4  7 19 16)
            ( 7  5 17 19)
            ( 5  8 20 17)
            ( 8  4 16 20)
        );
    }}
    inlet
    {{
        type patch;
        faces
        (
            ( 3  0 12 15)
            ( 0  1 13 12)
            ( 1  2 14 13)
            (11 10 22 23)
            (10  9 21 22)
            ( 9  3 15 21)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            ( 2  6 18 14)
            ( 6 11 23 18)
        );
    }}
    front
    {{
        type empty;
        faces
        (
            ( 3  4  7  0)
            ( 0  7  5  1)
            ( 1  5  6  2)
            ( 3  9  8  4)
            ( 9 10  5  8)
            (10 11  6  5)
        );
    }}
    back
    {{
        type empty;
        faces
        (
            (15 16 19 12)
            (12 19 17 13)
            (13 17 18 14)
            (15 21 20 16)
            (21 22 17 20)
            (22 23 18 17)
        );
    }}
);
"""


def _build_snappy(airfoil_patch: str, stl_name: str) -> str:
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
        name {airfoil_patch};
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
            level 4;
        }}
    );

    refinementSurfaces
    {{
        {airfoil_patch}
        {{
            level (4 6);
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


def _build_control_dict(airfoil_patch: str, alpha_deg: float, n_iter: int = 3000) -> str:
    alpha_rad = math.radians(alpha_deg)
    lx = -math.sin(alpha_rad)
    ly =  math.cos(alpha_rad)
    dx =  math.cos(alpha_rad)
    dy =  math.sin(alpha_rad)
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
endTime         {n_iter};
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

        patches         ({airfoil_patch});
        rho             rhoInf;
        rhoInf          1.225;
        liftDir         ({lx:.6f} {ly:.6f} 0);
        dragDir         ({dx:.6f} {dy:.6f} 0);
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


def _build_fv_solution(relax_U: float = 0.3, relax_p: float = 0.2) -> str:
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}}

solvers
{{
    p
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }}
    U
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }}
    k
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }}
    omega
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }}
}}

SIMPLE
{{
    nNonOrthogonalCorrectors 2;
    consistent      yes;
}}

relaxationFactors
{{
    fields
    {{
        p               {relax_p};
    }}
    equations
    {{
        U               {relax_U};
        k               0.3;
        omega           0.3;
    }}
}}
"""


def _build_decomposeParDict() -> str:
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

def build_case(case_dir: str, airfoil: str, alpha_deg: float, stl_src: str | None = None,
               nx: int = 200, ny: int = 150,
               relax_U: float = 0.3, relax_p: float = 0.2,
               n_iter: int = 3000):
    """
    Write a complete OpenFOAM case to *case_dir*.

    Parameters
    ----------
    case_dir  : path to the case (created if absent)
    airfoil   : e.g. 'naca0012'
    alpha_deg : angle of attack in degrees
    stl_src   : path to the STL file to copy into constant/triSurface/
                (optional; if None the file must already be there)
    """
    key   = airfoil.lower().replace(" ", "")
    patch = key          # e.g. naca0012
    stl_name = key.upper() + ".stl"

    case = Path(case_dir)
    dirs = [
        case / "0",
        case / "constant" / "geometry",
        case / "system",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Copy STL into constant/geometry/ — blockMesh project feature looks there
    if stl_src and Path(stl_src).exists():
        dst = case / "constant" / "geometry" / stl_name
        shutil.copy2(stl_src, dst)

    # 0/
    (case / "0" / "U").write_text(_build_U(alpha_deg, patch))
    (case / "0" / "p").write_text(_build_p_clean(patch))
    (case / "0" / "k").write_text(_build_k(patch))
    (case / "0" / "omega").write_text(_build_omega(patch))
    (case / "0" / "nut").write_text(_build_nut(patch))

    # constant/
    (case / "constant" / "transportProperties").write_text(_build_transport_props())
    (case / "constant" / "turbulenceProperties").write_text(_build_turbulence_props())

    # system/
    (case / "system" / "blockMeshDict").write_text(_build_block_mesh_cmesh(patch, key.upper() + ".stl", nx=nx, ny=ny))
    (case / "system" / "controlDict").write_text(_build_control_dict(patch, alpha_deg, n_iter=n_iter))
    (case / "system" / "fvSchemes").write_text(_build_fv_schemes())
    (case / "system" / "fvSolution").write_text(_build_fv_solution(relax_U=relax_U, relax_p=relax_p))
    (case / "system" / "decomposeParDict").write_text(_build_decomposeParDict())

    return str(case)
