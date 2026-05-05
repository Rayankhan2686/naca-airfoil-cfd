# NACA Airfoil CFD Research Tool

**Developer:** Rayan Khan | sleepyheadron2686  
**Institution:** [Your University Name]  
**Course:** Aerodynamics / Fluid Mechanics Research  
**Year:** 2026  

---

## Project Overview

This project is a fully automated computational fluid dynamics (CFD) 
pipeline built to investigate the aerodynamic performance of NACA 
four-digit airfoils at low Reynolds numbers. The tool automates the 
complete OpenFOAM workflow from geometry generation through to results 
extraction, eliminating manual setup errors and enabling systematic 
parametric studies.

The research focuses on quantifying how airfoil camber affects lift, 
drag, pitching moment, and stall characteristics — trade-offs that are 
critical for small UAV and low-speed aircraft design.

---

## Research Goals

- Compute lift (Cl), drag (Cd), and pitching moment (Cm) coefficients 
  for NACA 0012, 2412, and 4412 airfoils
- Investigate the effect of camber on stall angle and maximum lift
- Quantify drag penalty and L/D ratio as camber increases
- Identify optimal camber for a given lift requirement
- Produce publication-quality data for a journal or conference paper

---

## What I Built

A Python command-line tool that automates the full CFD pipeline:**Research Mode** — locked physics for systematic NACA study:
- Generates watertight ASCII STL geometry for any NACA 4-digit airfoil
- Builds structured background mesh with blockMesh
- Snaps mesh to airfoil surface with snappyHexMesh
- Runs simpleFoam RANS solver with kOmegaSST turbulence model
- Extracts Cl/Cd/Cm from postProcessing and saves to CSV
- Visualizes flow field in ParaView
- Runs full angle-of-attack sweeps automatically

**Custom Mesh Mode** — flexible mode for imported geometries:
- Imports STL files from SolidWorks or any CAD tool
- Custom mesh density settings with validation and auto-revert
- Same full pipeline as Research Mode
- Mesh quality statistics viewer by airfoil and angle

---

## Fixed Physics Parameters

| Parameter | Value |
|-----------|-------|
| Reynolds Number | 2 × 10⁵ |
| Freestream Velocity | 2.4751 m/s |
| Density | 1.225 kg/m³ |
| Dynamic Viscosity | 1.516 × 10⁻⁵ Pa·s |
| Chord Length | 1.0 m |
| Span | 0.1 m |
| Reference Area | 0.1 m² |
| Turbulence Model | kOmegaSST |
| Solver | simpleFoam (steady RANS) |
| Iterations | 3000 |

---

## Airfoils Studied

| Airfoil | Camber | Thickness |
|---------|--------|-----------|
| NACA 0012 | 0% | 12% |
| NACA 2412 | 2% at 40% chord | 12% |
| NACA 4412 | 4% at 40% chord | 12% |

---

## Requirements

- OpenFOAM 2412
- Python 3.10+
- numpy
- ParaView (optional, for visualization)
- Ubuntu 24 / WSL2

---

## Installation

```bash
git clone https://github.com/sleepyheadron2686/naca-airfoil-cfd.git
mkdir -p ~/OpenFOAM/{airfoils,run,results}
pip3 install numpy
echo 'alias foam-research="python3 ~/OpenFOAM/scripts/foam_research.py"' >> ~/.bashrc
source ~/.bashrc
```

---

## Usage

```bash
foam-research
```

**Menu Options:**
- **A. Research Mode** — systematic NACA airfoil study
- **B. Custom Mesh Mode** — import and simulate any STL geometry
- **C. Exit**

---

## Project Structurescripts/
├── foam_research.py        # Main launcher
├── custommesh.py           # Custom mesh tool
├── core/
│   ├── ui.py               # Terminal UI
│   ├── stl_generator.py    # NACA geometry generation
│   ├── case_builder.py     # OpenFOAM case writer
│   ├── mesh_runner.py      # Pipeline executor
│   └── results_extractor.py # Data extraction
└── results/                # CSV output---

## Expected Outcomes

- Lift curves (Cl vs α) for all three airfoils
- Drag polars (Cl vs Cd) showing drag penalty with camber
- L/D ratio comparison across airfoils
- Stall angle identification for each airfoil
- Flow visualizations showing separation behavior near stall
- Technical report suitable for journal or conference submission

---

## License

MIT License — © 2026 Rayan Khan

---

---

# ACTIVE DEBUG LOG — Cl Fix Session (2026-05-01)

> **For Codex / next session:** This section is the handoff. Read this, then resume from
> "STEP TO EXECUTE NEXT" below. Do not ask for context — it is all here.

---

## Problem

NACA 0012 at alpha=6°, Re=2×10⁵ gives **Cl=0.1086** (stable, converged). Should be ~0.65.
Factor off: ~6×. Root cause confirmed: **snappyHexMesh z-cell splitting**.

With only 1 z-cell in the base mesh (z=0 to 0.1), snappyHexMesh refines all 3 directions
near the airfoil, creating 2 sub-cells in z (z=0–0.05, z=0.05–0.1). This breaks the 2D
assumption in simpleFoam. checkMesh confirms: "Total number of faces on empty patches is
not divisible by the number of cells in the mesh. Hence this mesh is not 1D or 2D."

---

## Solution Chosen

Replace snappyHexMesh with a **blockMesh C-mesh** using OpenFOAM's `project` feature
(snaps vertices/edges onto a triSurface geometry file). This is the same approach used
in the `rhoSimpleFoam/aerofoilNACA0012` tutorial. No snappyHexMesh needed.

Reference tutorial path:
```
/usr/lib/openfoam/openfoam2412/tutorials/compressible/rhoSimpleFoam/aerofoilNACA0012/
```

---

## What Has Been Done

### 1. mesh_runner.py — COMPLETE

`run_pipeline()` and `run_pipeline_verbose()` both now run only:
```python
steps = [
    ("blockMesh",  "blockMesh"),
    ("simpleFoam", "simpleFoam"),
]
```
`surfaceFeatureExtract` and `snappyHexMesh -overwrite` have been removed.

### 2. case_builder.py — PARTIALLY DONE, ONE BUG REMAINING

**Done:**
- `_build_block_mesh_cmesh(airfoil_patch, stl_name)` added after `_build_block_mesh()` (line ~339)
- `top` and `bottom` symmetry BC blocks removed from all 5 BC builders:
  `_build_U`, `_build_p_clean`, `_build_k`, `_build_omega`, `_build_nut`
- `outlet` freestream/calculated BC added to all 5 builders
- `build_case()` updated:
  - STL copied to `constant/geometry/` (not `constant/triSurface/`)
  - Calls `_build_block_mesh_cmesh(patch, key.upper()+".stl")` instead of `_build_block_mesh(patch)`
  - No longer writes `snappyHexMeshDict` or `surfaceFeatureExtractDict`

**BUG (not yet fixed):**
blockMesh fails with:
```
Block hex (7 4 16 19 0 3 15 12) (40 1 80) ... is inside-out
```
Root cause: In our coordinate system (x=chord, y=lift, z=span), the j-direction of the
hex block goes from z=0 → z=0.1 (+z direction). This makes det(i, j, k) negative, producing
an inside-out block.

---

## STEP TO EXECUTE NEXT — Fix Inside-Out Block

### What to change

In `core/case_builder.py`, function `_build_block_mesh_cmesh()`, in the `vertices` section:

**CURRENT (wrong):**
```
// z=0 plane, vertices 0-11
project ({xS} {-R}  0) (inlet_arc)      // 0
(1    {-R}    0)                         // 1
({xMax} {-R}  0)                         // 2
...all 12 vertices at z=0...

// z=0.1 plane, vertices 12-23
project ({xS} {-R}  0.1) (inlet_arc)    // 12
...all 12 vertices at z=0.1...
```

**REQUIRED (correct):**
```
// z=0.1 plane, vertices 0-11  ← swap! 0-11 go to z=0.1
project ({xS} {-R}  0.1) (inlet_arc)    // 0
(1    {-R}    0.1)                       // 1
({xMax} {-R}  0.1)                       // 2
...all 12 vertices at z=0.1...

// z=0 plane, vertices 12-23  ← swap! 12-23 go to z=0
project ({xS} {-R}  0) (inlet_arc)      // 12
...all 12 vertices at z=0...
```

This makes the j-direction of each hex go from z=0.1 → z=0 (−z direction), giving
positive Jacobian det(i, j, k) > 0.

### Also swap the front/back face lists in the boundary section

**CURRENT back (z=0, vertices 0-11):**
```openfoam
back
{
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
}
front
{
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
}
```

**REQUIRED (after swap, front=z=0.1 stays as 0-11 faces, back=z=0 stays as 12-23 faces):**
```openfoam
front
{
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
}
back
{
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
}
```

In other words:
- The faces `(3 4 7 0)` etc. (vertices 0-11, now at z=0.1) → these are the **front** patch
- The faces `(15 16 19 12)` etc. (vertices 12-23, now at z=0) → these are the **back** patch

---

## Full Corrected `_build_block_mesh_cmesh` Vertex Section

Replace lines ~394–421 of `core/case_builder.py` with:

```python
    // z=0.1 plane, vertices 0-11
    project ({xS}        {-R}  0.1) (inlet_arc)        // 0
    (1       {-R}        0.1)                            // 1
    ({xMax}  {-R}        0.1)                            // 2
    project ({xMin_prj}   0   0.1) (inlet_arc)          // 3
    project (0            0   0.1) ({airfoil_patch})    // 4  LE
    project (1            0   0.1) ({airfoil_patch})    // 5  TE
    ({xMax}  0            0.1)                           // 6
    project ({xS}        {yL}  0.1) ({airfoil_patch})  // 7  lower surface
    project ({xS}        {yU}  0.1) ({airfoil_patch})  // 8  upper surface
    project ({xS}        {R}   0.1) ({airfoil_patch})  // 9  snaps to upper surf
    project (1           {R}   0.1) ({airfoil_patch})  // 10 snaps to TE
    ({xMax}  {R}          0.1)                           // 11

    // z=0 plane, vertices 12-23
    project ({xS}        {-R}  0) (inlet_arc)           // 12
    (1       {-R}        0)                              // 13
    ({xMax}  {-R}        0)                              // 14
    project ({xMin_prj}   0   0) (inlet_arc)            // 15
    project (0            0   0) ({airfoil_patch})      // 16 LE
    project (1            0   0) ({airfoil_patch})      // 17 TE
    ({xMax}  0            0)                             // 18
    project ({xS}        {yL}  0) ({airfoil_patch})    // 19 lower surface
    project ({xS}        {yU}  0) ({airfoil_patch})    // 20 upper surface
    project ({xS}        {R}   0) ({airfoil_patch})    // 21 snaps to upper surf
    project (1           {R}   0) ({airfoil_patch})    // 22 snaps to TE
    ({xMax}  {R}          0)                             // 23
```

Then in the boundary section (lines ~496–521): swap the `back` and `front` labels
so that 0-11 face lists → `front`, and 12-23 face lists → `back`.

**Block hex definitions, edges, and all other boundary faces stay UNCHANGED.**

---

## Steps After the Fix

Once the inside-out error is resolved:

1. **Verify blockMesh runs cleanly:**
   ```bash
   source /usr/lib/openfoam/openfoam2412/etc/bashrc
   cd ~/OpenFOAM/scripts/cases/naca0012_ap6_0
   blockMesh 2>&1 | tail -20
   ```

2. **Run checkMesh and confirm no 2D warning:**
   ```bash
   checkMesh 2>&1 | grep -E "Mesh OK|2D|1D|empty"
   ```
   Expected: `Mesh OK.` and empty face count = 2 × cell count.

3. **Run simpleFoam and verify Cl ≈ 0.65:**
   ```bash
   simpleFoam 2>&1 | tail -5
   cat postProcessing/forceCoeffs/0/coefficient.dat | tail -1
   ```

4. **Delete the invalid result row** from `results/airfoil_results.csv`
   (the row with Cl=0.1086 from the snappyHexMesh run).

5. **Commit:**
   ```bash
   git add core/case_builder.py core/mesh_runner.py
   git commit -m "fix: replace snappyHexMesh with blockMesh C-mesh for true 2D NACA simulation"
   ```

6. **Run full alpha sweep** for NACA 0012 (alpha = 0, 2, 4, 6, 8, 10, 12°) to produce
   the lift curve. Expected: Cl ≈ 0.11·alpha (per degree) up to stall ~12°.

---

## Key File Locations

| File | Purpose | Status |
|------|---------|--------|
| `core/case_builder.py` | OpenFOAM case writer | Modified, bug at line ~394–421 |
| `core/mesh_runner.py` | Pipeline executor | Done |
| `debug_notes.md` | Full investigation notes (Sections 1–8) | Up to date |
| `results/airfoil_results.csv` | Simulation results | Has invalid row (Cl=0.1086) |
| `~/OpenFOAM/airfoils/NACA0012.stl` | Binary STL geometry | Correct, use as-is |

---

## Coordinate System Reference

Our case: `x=chord (0=LE, 1=TE)`, `y=lift/vertical`, `z=span (empty, 0→0.1)`

Tutorial (`rhoSimpleFoam/aerofoilNACA0012`): `x=chord`, `z=lift`, `y=span` — DIFFERENT.
All tutorial vertex coordinates must be adapted: swap y↔z.

The cylinder geometry in blockMeshDict has its axis in z:
```
point1 (0.3 0 -1e6);  point2 (0.3 0 1e6);  radius 20;
```
