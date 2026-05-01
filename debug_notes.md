# CL Debug Notes — NACA 0012 alpha=6° Cl=0.1086 instead of ~0.65

**Date:** 2026-04-30  
**Case:** scripts/cases/naca0012_ap6_0  
**Expected:** Cl ≈ 0.65 at alpha=6°, Re=2×10⁵  
**Actual:**   Cl = 0.1086 (stably converged, NOT diverging)  
**Factor off:** 0.65 / 0.1086 ≈ 5.99 ≈ 6×

---

## 1. What We Found About Why Cl Is Wrong

### Confirmed NOT the cause:
- **liftDir/dragDir**: coefficient.dat header confirms liftDir=(-0.10453, 0.99452, 0) and
  dragDir=(0.99452, 0.10453, 0) — correct for alpha=6°. Fixed in case_builder.py.
- **Aref**: Confirmed 0.1 m² in forceCoeffs header. ✓
- **magUInf**: 2.4751 m/s confirmed in header. ✓
- **Column extraction**: parts[4]=Cl is correct per coefficient.dat column order. ✓
- **STL geometry**: Binary STL, 1192 triangles. Bounds confirmed:
    - X: [0.000000, 1.000000]  chord = 1.000000 m ✓
    - Y: [-0.060017, 0.060017] thick = 0.120034 m ✓
    - Z: [0.000000, 0.100000]  span  = 0.100000 m ✓
- **nNonOrthogonalCorrectors**: Fixed to 2 (was 0). ✓
- **Domain size**: Expanded to x=[-20,40], y=[-20,20] (was x=[-20,30], y=[-10,10]).
- **Convergence**: Cl is STABLE at 0.10859 from iteration ~200 to 3000. Not a divergence issue.

### Suspicious findings requiring investigation:
- **Cl oscillation early**: Cl starts at 0.2003 (t=1), drops to 0.0446 (t=7), then rises to 0.1086 (converged). This unusual trajectory may mean solver found a wrong stable branch.
- **Airfoil patch area**: 0.209055 m² with 3,182 faces. For NACA 0012 both sides: ~0.208 m². Looks correct, so the airfoil patch is properly covering the surface.
- **STL source**: The binary STL in the case (1192 triangles, "NACA watertight STL" header) is NOT from the current stl_generator.py (which writes ASCII ~796 triangles). It was copied from ~/OpenFOAM/airfoils/NACA0012.stl which is also binary. The geometry is correct but origin is unclear — this is worth noting.

---

## 2. What The Pressure Sampling Showed

**Attempt failed.** The postProcess probe command using bash process substitution (`/dev/fd/63`) is not supported by OpenFOAM's file reader. It exits with:
```
FOAM FATAL ERROR: cannot find file "/dev/fd/63"
```

**Only partial result obtained:**
```
areaAverage(naca0012) of p = -0.542685 Pa   (both sides averaged)
total area = 0.209055 m²
```

Averaging top and bottom pressure together is not diagnostic. Need to sample p along
lines above and below the airfoil at x=0.25, 0.5, 0.75 to see the actual ΔCp distribution.

**To get pressure sampling working:** Write a proper sampleDict file to disk, then run:
```bash
postProcess -func sample
```

---

## 3. What The Mesh Not-2D Warning Means

checkMesh output:
```
***Total number of faces on empty patches is not divisible by the number of cells in the mesh.
Hence this mesh is not 1D or 2D.
```

**What it means:** In a proper 2D OpenFOAM mesh, every cell has exactly one face on the
front empty patch (z=0) and one face on the back empty patch (z=0.1). So:
- front_faces = back_faces = N_cells
- Total empty faces = 2 × N_cells

Our mesh:
- N_cells = 19,324
- Expected empty faces = 38,648
- Actual empty faces ≈ 24,921 (28,543 total boundary − 3,182 airfoil − ~440 perimeter patches)
- Deficit = 13,727 faces

**Why the deficit?** snappyHexMesh splits base cells in ALL three directions (x, y, z).
Even though the base mesh has only 1 cell in z (z=0 to z=0.1), snappyHexMesh's
refinement near the airfoil surface splits those cells into 2 sub-cells in z (e.g.,
z=[0, 0.05] and z=[0.05, 0.1]). The new internal face at z=0.05 is NOT a boundary face.
So now 2 cells share the same front/back face count that 1 cell used to provide.

**Implication:** The mesh is pseudo-3D near the airfoil. There are multiple z-layers
stacked on top of each other near the airfoil surface, connected by internal faces.
The empty BCs at z=0 and z=0.1 enforce dφ/dz=0 there, but NOT at the internal z=0.05
interface. If the flow is truly 2D (which it should be by symmetry), the z-gradient
should remain zero. However, this mesh topology VIOLATES the assumption that simpleFoam
makes for the empty BC treatment of the 2D pressure equation, potentially corrupting
the pressure field near the airfoil.

**Severity:** This is likely the primary root cause. The non-2D mesh means the pressure
solver is partially solving a 3D problem where it expects a 2D one.

---

## 4. Files Changed So Far

### core/case_builder.py (modified, NOT yet committed)
Four changes:
1. **Domain expanded**: x=[-20,30]→[-20,40], y=[-10,10]→[-20,20]
2. **Cell count increased**: 100×80→120×100
3. **front/back empty faces corrected**: front uses z=0 vertices (0,3,2,1), back uses z=0.1 vertices (4,5,6,7)
4. **liftDir/dragDir**: hardcoded (0 1 0)/(1 0 0) → computed (-sinα, cosα, 0)/(cosα, sinα, 0)
5. **nNonOrthogonalCorrectors**: 0 → 2

### results/airfoil_results.csv (modified)
One new row added from the test simulation (Cl=0.1086, which is wrong — this row should be deleted or marked invalid before publication).

### No other files changed in this debugging session.
Files confirmed correct (read-only in this session):
- core/results_extractor.py (column mapping confirmed correct)
- core/mesh_runner.py (pipeline confirmed correct)
- core/stl_generator.py (writes ASCII STL, but binary STL is being used in case — mismatch)

---

## 5. Root Cause Assessment

**Most likely root cause: snappyHexMesh creates non-2D mesh (z-cell splitting)**

For 2D external aerodynamics, snappyHexMesh is NOT a good choice with only 1 z-cell.
When it refines cells near the airfoil, it splits in all 3 directions. With z=0.1m and
1 cell in z, z-refinement creates 2 layers (z=0 to 0.05, z=0.05 to 0.1). This violates
the 2D mesh assumption in simpleFoam.

**Secondary possible causes (not yet ruled out):**
- Mesh too coarse near leading edge to capture leading-edge suction peak (main driver of lift)
- No wall layer addition (addLayers false) → y+ might be too large or too small → wall functions inaccurate
- kOmegaSST fully turbulent assumption at Re=200,000 (transitional flow) → but this should give Cl ~0.55-0.65, not 0.1086
- snappyHexMesh trailing edge topology (sharp trailing edge of NACA 0012 might create badly snapped cells)

**Why factor of ~6?** Not fully explained. If only 1/6 of the airfoil surface is seeing
correct pressure (e.g., only 1 z-layer out of 6 near-wall z-layers), that would do it.
But this is speculative.

---

## 6. Next Steps To Fix (In Order)

### Step 1: Fix the mesh — prevent snappyHexMesh from splitting in z

**Option A (Recommended): Switch to blockMesh-only structured C-mesh**
- Use a structured C-mesh around the airfoil built entirely in blockMesh
- No snappyHexMesh needed for a known 2D profile
- This is what the OpenFOAM airFoil2D tutorial uses
- Correct Cl values are well-documented for this approach
- Downside: significant refactor of case_builder.py

**Option B (Simpler): Increase span to 5 cells in z with thicker span**
- Use z=[0, 0.5] with 5 cells in z in blockMesh
- Set Aref = chord × 0.5 = 0.5 m²
- snappyHexMesh can now refine in z without breaking the 2D constraint (center cells remain 2D-like)
- STL also needs span=0.5m → stl_generator needs to be updated
- Run simulation and compare Cl

**Option C (Quick test): Add snappyHexMesh nCellsBetweenLevels to prevent z-split**
- Add a refinement region box that excludes the z-direction from refinement
- Complex and may not work reliably

### Step 2: Delete the wrong test result row from airfoil_results.csv

### Step 3: Re-run test simulation at alpha=6° and verify Cl ≈ 0.65

### Step 4: Commit with message 'fix: domain size and CL normalization for publication quality results'

### Step 5 (If Option A chosen for Step 1):
- Update stl_generator.py if needed
- Update case_builder.py blockMesh to generate C-mesh around airfoil
- Update snappyHexMesh section to be disabled or removed

---

## Working Commands For Next Session

**Check OpenFOAM airFoil2D tutorial location:**
```bash
source /usr/lib/openfoam/openfoam2412/etc/bashrc
find $FOAM_TUTORIALS -name "airFoil2D" -type d 2>/dev/null
ls $FOAM_TUTORIALS/incompressible/simpleFoam/
```

**Sample pressure along line (write sampleDict to disk first):**
```bash
cd ~/OpenFOAM/scripts/cases/naca0012_ap6_0
cat > system/sampleDict << 'EOF'
... (probes or sample dict)
EOF
postProcess -func sample -latestTime
```

**Check number of z-layers in refined mesh:**
```bash
source /usr/lib/openfoam/openfoam2412/etc/bashrc
cd ~/OpenFOAM/scripts/cases/naca0012_ap6_0
checkMesh 2>&1 | grep -i "empty\|front\|back"
```

**Check the airFoil2D tutorial approach:**
```bash
source /usr/lib/openfoam/openfoam2412/etc/bashrc
cat $FOAM_TUTORIALS/incompressible/simpleFoam/airFoil2D/system/blockMeshDict
```

---

## 7. Session 2 Findings — C-Mesh Analysis (2026-05-01)

### 7.1 Tutorial reference found

The correct reference is NOT `incompressible/simpleFoam/airFoil2D` (that tutorial uses a
pre-built binary polyMesh with no blockMeshDict). The correct reference is:

```
/usr/lib/openfoam/openfoam2412/tutorials/compressible/rhoSimpleFoam/aerofoilNACA0012/
```

Its `Allrun.pre` pipeline:
```bash
mkdir -p constant/geometry
cp NACA0012.obj.gz constant/geometry/
restore0Dir
blockMesh                          # build 2D mesh using project feature
transformPoints -scale '(1 0 1)'  # collapse y to 0 (flatten to x-z plane)
extrudeMesh                        # extrude 1 cell in -y direction, thickness 0.1
```

The `extrudeMeshDict` (in system/) configures:
```
constructFrom    patch;
sourceCase       "<case>";
sourcePatches    (back);
exposedPatchName front;
extrudeModel     linearDirection;
direction        (0 -1 0);
thickness        0.1;
```

### 7.2 Tutorial coordinate system

**CRITICAL:** The tutorial uses a DIFFERENT coordinate system than our case:

| Direction | Tutorial blockMeshDict | Our case |
|-----------|----------------------|----------|
| chord     | x (0=LE, 1=TE)       | x (same) |
| lift/vert | **z** (zMin=-2, zMax=2) | **y** (yMin=-20, yMax=20) |
| span/empty| **y** (-0.1 to +0.1) | **z** (0 to 0.1) |

In the tutorial, the airfoil profile lies in the **x-z plane** (chord × lift).
In our case, the airfoil profile lies in the **x-y plane** (chord × lift).

The NACA0012.obj resource file confirms this:
- Vertices at y=±0.5 (span direction), x=0→1 (chord), z=−0.06→+0.06 (lift/thickness)
- The airfoil profile is in the x-z plane with y as the extruded span direction

### 7.3 Tutorial blockMeshDict structure

The blockMeshDict uses the `geometry` + `project` feature:

```
geometry {
    aerofoil { type triSurfaceMesh; file "NACA0012.obj"; }
    cylinder {
        type   cylinder;
        point1 (0.3 -1e3 0);   // axis through (xSample, *, zLead=0) in y direction
        point2 (0.3  1e3 0);
        radius 2;               // = domain.zMax = far-field radius
    }
}
```

**24 vertices total** (12 at y=-0.1, 12 at y=+0.1, the span direction):

```
Back face (y=-0.1), vertex 0-11:
v0:  project (0.3, -0.1, -2) → cylinder  = bottom of C-arc at x=0.3
v1:  (1, -0.1, -2)                        = lower corner at TE
v2:  (4, -0.1, -2)                        = lower right corner (outlet)
v3:  project (-4, -0.1, 0) → cylinder    = left of C-arc (-1.7, -0.1, 0) [snapped]
v4:  project (0, -0.1, 0) → aerofoil     = LE on airfoil
v5:  project (1, -0.1, 0) → aerofoil     = TE on airfoil
v6:  (4, -0.1, 0)                         = right middle (outlet)
v7:  project (0.3, -0.1, -0.06) → aerofoil = lower surface at x=0.3
v8:  project (0.3, -0.1, 0.06) → aerofoil  = upper surface at x=0.3
v9:  project (0.3, -0.1, 2) → aerofoil     = snaps to upper surface at x=0.3 (= v8 position)
v10: project (1, -0.1, 2) → aerofoil       = snaps to TE (= v5 position)
v11: (4, -0.1, 2)                           = upper right corner (outlet)

Front face (y=+0.1), vertex 12-23: identical with y=+0.1
```

**v9=v8 and v10=v5 intentional** — the block at the upper/outer edge of the C-mesh
is an inlet boundary face that goes from the airfoil upper surface (v9, v21)
diagonally out to the far-field cylinder (v3, v15). The "outer" face of block 4 is:
face (v9, v3, v15, v21) = from airfoil upper surface to far-field arc — this IS the
inlet patch face. The projected edge `project 3 9 (cylinder)` creates the arc along
the inlet C-boundary between the left-most point (v3) and the upper point where
the C-mesh boundary meets the upper side of the airfoil.

**6 blocks** (3 on lower side, 3 on upper side):
```
hex ( 7  4 16 19  0  3 15 12)  (xUCells 1 zCells)  // lower leading area (LE to x=0.3)
hex ( 5  7 19 17  1  0 12 13)  (xMCells 1 zCells)  // lower middle (x=0.3 to TE)
hex (17 18  6  5 13 14  2  1)  (xDCells 1 zCells)  // lower wake (TE to outlet)
hex (20 16  4  8 21 15  3  9)  (xUCells 1 zCells)  // upper leading area (LE to x=0.3)
hex (17 20  8  5 22 21  9 10)  (xMCells 1 zCells)  // upper middle (x=0.3 to TE)
hex ( 5  6 18 17 10 11 23 22)  (xDCells 1 zCells)  // upper wake (TE to outlet)
```

Cell counts: xUCells=30, xMCells=30, xDCells=40, zCells=80 (wall-normal), 1 (span)

**Projected edges** (these make block edges follow the airfoil surface):
```
project 4 7 (aerofoil)   // lower surface, LE to x=0.3 (at y=-0.1)
project 7 5 (aerofoil)   // lower surface, x=0.3 to TE (at y=-0.1)
project 4 8 (aerofoil)   // upper surface, LE to x=0.3 (at y=-0.1)
project 8 5 (aerofoil)   // upper surface, x=0.3 to TE (at y=-0.1)
project 16 19 (aerofoil) // lower surface at y=+0.1
project 19 17 (aerofoil)
project 16 20 (aerofoil) // upper surface at y=+0.1
project 20 17 (aerofoil)
project 3  0  (cylinder) // C-arc from left to bottom (at y=-0.1)
project 3  9  (cylinder) // C-arc from left to upper (inlet boundary edge at y=-0.1)
project 15 12 (cylinder) // C-arc at y=+0.1
project 15 21 (cylinder)
```

**Boundary patches in tutorial:**
```
aerofoil: (4 7 19 16) (7 5 17 19) (5 8 20 17) (8 4 16 20)
inlet:    (3 0 12 15) (0 1 13 12) (1 2 14 13)  [lower half + left arc]
          (11 10 22 23) (10 9 21 22) (9 3 15 21) [upper half + left arc]
outlet:   (2 6 18 14) (6 11 23 18)
back:     (empty, 6 faces at y=-0.1)
front:    (empty, 6 faces at y=+0.1)
```

### 7.4 Tutorial mesh result

Running `Allrun.pre` on the tutorial:
```
checkMesh output:
  cells:         16,000
  faces:         64,240
  internal faces: 31,760
  boundary patches: 5
  Overall domain bounding box: (-1.7, -0.1, -2) to (4, 0, 2)
  Max non-orthogonality: 30.2°
  Max aspect ratio: 81.3
  Mesh OK. (No 2D warning, no non-orthogonality errors)
```

After extrudeMesh, the final mesh has:
- Span in y direction: y=[-0.1, 0] (from extrudeMesh direction (0,-1,0), thickness=0.1)
- x: [-1.7, 4] (chord + far field left and right)
- z: [-2, 2] (vertical/lift far field)

This is a **perfect 2D mesh** — no z-splitting, all cells have exactly 1 face on each empty patch.

### 7.5 Adaptation plan for our coordinate system

To use the same approach but in our coordinate system (x=chord, y=lift, z=span=empty):

**Coordinate swap needed:** In tutorial coords (x=chord, z=lift, y=span):
- Swap y ↔ z compared to tutorial
- Our "front/back" patches are at z=0 and z=0.1 (tutorial uses y=-0.1/+0.1)
- Our far-field is in x-y plane; cylinder axis must be in z direction

**Adapted vertex layout (our coordinates, at z=0 then z=0.1):**

```
Domain parameters (to match our existing domain size):
  xSample = 0.3    # chord-wise split point
  R = 20.0         # far-field radius, centered at (0.3, 0)
  xMax = 40.0      # wake extension
  yMax = 20.0      # = R (far field top/bottom)
  zSpan = 0.1      # span (empty direction)

Cylinder: centered at (0.3, 0, z_any), axis in z, radius=20
  → left point: (0.3-20, 0) = (-19.7, 0)
  → bottom: (0.3, -20)
  → top: (0.3, +20)

At z=0 (vertices 0-11), at z=0.1 (vertices 12-23):
v0:  project (0.3, -20, 0) → cylinder   = bottom of C-arc
v1:  (1, -20, 0)                          = lower corner at TE
v2:  (40, -20, 0)                         = lower outlet corner
v3:  project (-20, 0, 0) → cylinder     = left of C-arc → snaps to (-19.7, 0, 0)
v4:  project (0, 0, 0) → aerofoil       = LE = (0, 0, 0)
v5:  project (1, 0, 0) → aerofoil       = TE = (1, 0, 0)
v6:  (40, 0, 0)                           = right middle (outlet)
v7:  project (0.3, -0.06, 0) → aerofoil = lower surface at x=0.3
v8:  project (0.3, 0.06, 0) → aerofoil  = upper surface at x=0.3
v9:  project (0.3, 20, 0) → aerofoil    = snaps to upper surface (same as v8)
v10: project (1, 20, 0) → aerofoil      = snaps to TE (same as v5)
v11: (40, 20, 0)                          = upper outlet corner

v12-v23: same but at z=0.1
```

**Adapted geometry section:**
```
geometry {
    NACA0012 {        // must match STL file name
        type triSurfaceMesh;
        file "NACA0012.stl";
    }
    cylinder {
        type   cylinder;
        point1 (0.3 0 -1e3);   // cylinder axis in z direction
        point2 (0.3 0  1e3);
        radius 20;
    }
}
```

**Block connectivity** (same 6 blocks, adapting vertex indices):
```
// zCells = wall-normal cells (from airfoil surface to far field)
// xUCells = cells from LE to x=0.3 (leading portion)
// xMCells = cells from x=0.3 to TE (trailing portion)
// xDCells = cells in wake (TE to xMax)
// 1 cell in span (z direction)

hex ( 7  4 16 19  0  3 15 12)  (xUCells 1 zCells)  // lower leading
hex ( 5  7 19 17  1  0 12 13)  (xMCells 1 zCells)  // lower middle
hex (17 18  6  5 13 14  2  1)  (xDCells 1 zCells)  // lower wake
hex (20 16  4  8 21 15  3  9)  (xUCells 1 zCells)  // upper leading
hex (17 20  8  5 22 21  9 10)  (xMCells 1 zCells)  // upper middle
hex ( 5  6 18 17 10 11 23 22)  (xDCells 1 zCells)  // upper wake
```

**Adapted projected edges:**
```
// Airfoil surface edges (at z=0)
project 4 7 (NACA0012)    // lower surface LE to x=0.3
project 7 5 (NACA0012)    // lower surface x=0.3 to TE
project 4 8 (NACA0012)    // upper surface LE to x=0.3
project 8 5 (NACA0012)    // upper surface x=0.3 to TE
// Same edges at z=0.1 (vertices 12-23)
project 16 19 (NACA0012)
project 19 17 (NACA0012)
project 16 20 (NACA0012)
project 20 17 (NACA0012)
// C-arc inlet edges
project 3  0  (cylinder)  // arc from left to bottom at z=0
project 3  9  (cylinder)  // arc from left to upper at z=0
project 15 12 (cylinder)  // arc at z=0.1
project 15 21 (cylinder)
```

**Adapted boundary patches:**
```
aerofoil {
    type wall;
    faces ( (4 7 19 16) (7 5 17 19) (5 8 20 17) (8 4 16 20) );
}
inlet {
    type patch;
    faces (
        (3 0 12 15)   // left C-arc
        (0 1 13 12)   // lower straight
        (1 2 14 13)   // lower bottom (outlet area bottom)
        (11 10 22 23) // upper top
        (10 9 21 22)  // upper straight
        (9 3 15 21)   // upper C-arc
    );
}
outlet {
    type patch;
    faces ( (2 6 18 14) (6 11 23 18) );
}
front {
    type empty;
    faces ( (15 16 19 12) (19 17 13 12) (17 18 14 13) ... );  // z=0.1 faces
}
back {
    type empty;
    faces ( (3 4 7 0) (7 5 1 0) ... );  // z=0 faces
}
```

**Grading (recommended starting values):**
```
xUCells = 40    // LE to x=0.3 (leading portion)
xMCells = 60    // x=0.3 to TE (trailing portion)
xDCells = 60    // wake
nWall   = 80    // wall-normal cells (airfoil to far field)
wallGrading = 200  // expand outward from wall (very fine near wall)
leadGrading = 0.2  // cluster toward LE
xDGrading  = 10    // expand downstream in wake
```

### 7.6 Pipeline changes needed

**mesh_runner.py**: Remove `surfaceFeatureExtract` and `snappyHexMesh -overwrite` steps.
New pipeline: `blockMesh` only (no STL needed since project uses STL from triSurface/).
OR use `blockMesh → extrudeMesh` like the tutorial (then need extrudeMeshDict too).

**Simpler option for our pipeline**: Use the direct blockMeshDict approach (no extrudeMesh)
because we already have z=0 and z=0.1 vertices explicitly in the blockMeshDict. No need
for transformPoints + extrudeMesh. The tutorial uses that pattern only because its
blockMeshDict was originally in the x-z plane and needed extrusion.

**case_builder.py changes needed:**
1. Replace `_build_block_mesh()` with new `_build_block_mesh_cmesh()` that outputs
   the 6-block C-mesh topology with project vertices and projected edges
2. Replace `_build_snappy()` call in `build_case()` with nothing (delete it)
3. Remove `_build_surface_feature_extract()` call  
4. The STL file is still needed (for the `project` feature in blockMeshDict)
5. Keep `stl_generator.py` as-is — the STL is used for projection, not for snappyHexMesh
6. Update boundary patch names: replace 'top'/'bottom' symmetry with 'inlet' freestream
   (top and bottom are now part of the inlet in C-mesh topology)
7. Update 0/U, 0/p, 0/k, 0/omega, 0/nut to use `inlet` instead of `top`/`bottom`

### 7.7 NEXT STEP

**Write `_build_block_mesh_cmesh(airfoil_patch, stl_name)` in case_builder.py.**

The function returns a complete blockMeshDict string with:
- The geometry section (triSurface STL + cylinder)
- 24 vertices (12 at z=0, 12 at z=0.1)
- 6 blocks (hex definitions as above)
- Projected edges for airfoil surface and C-arc
- Boundary patches: aerofoil (wall), inlet (freestream), outlet (patch), front/back (empty)

Then:
1. Update `build_case()` to call `_build_block_mesh_cmesh()` instead of `_build_block_mesh()` + `_build_snappy()`
2. Update `_build_U()`, `_build_p_clean()`, `_build_k()`, `_build_omega()`, `_build_nut()` 
   to replace `top`/`bottom` symmetry blocks with `inlet` freestream block
3. Update `mesh_runner.py` `run_pipeline()` to drop surfaceFeatureExtract and snappyHexMesh steps
4. Test on naca0012 alpha=6°, verify checkMesh gives "Mesh OK" with no 2D warning
5. Run simpleFoam, verify Cl ≈ 0.65
