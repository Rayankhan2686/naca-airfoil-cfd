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

---

## 8. Session 3 Status — Interrupted Before Writing Any Code (2026-05-01)

### 8.1 What was done this session

- Confirmed Section 7 analysis is complete and correct
- Set up task list:
  1. Add `_build_block_mesh_cmesh()` to case_builder.py  ← **NEXT**
  2. Remove top/bottom from BC files, add inlet freestream
  3. Update `build_case()` to use C-mesh and drop snappy
  4. Update `mesh_runner.py` pipeline
  5. Test blockMesh on naca0012

- **No code was written.** Session was interrupted before starting task 1.

### 8.2 Exact next step

**START HERE:** Open [core/case_builder.py](core/case_builder.py) and add the following
function after the existing `_build_block_mesh()` function (around line 376):

```python
def _build_block_mesh_cmesh(airfoil_patch: str, stl_name: str) -> str:
    """
    C-mesh blockMeshDict using OpenFOAM project feature.
    Replaces blockMesh+snappyHexMesh. Produces a true 2D mesh (1 cell in z).

    Coordinate system: x=chord (0=LE, 1=TE), y=lift/vertical, z=span (empty, 0 to 0.1)
    Domain: C-arc of radius 20 centred at (0.3, 0), wake extends to x=40.
    6 blocks: lower/upper × (leading|middle|wake).
    24 vertices: 0-11 at z=0, 12-23 at z=0.1 (same xy layout).
    """
    R        = 20.0   # far-field radius
    xS       = 0.3    # chord split point
    yL       = -0.06  # approx lower surface y at xS (project corrects this)
    yU       =  0.06  # approx upper surface y at xS
    xMax     = 40.0
    xMin_prj = -20.0  # projects onto cylinder → (-19.7, 0)

    xUC = 40    # cells: LE to xS
    xMC = 60    # cells: xS to TE
    xDC = 60    # cells: TE to xMax (wake)
    nW  = 80    # cells: wall-normal

    lG  = 0.2   # grading toward LE along chord
    xUG = 5.0   # grading toward LE upstream
    xDG = 10.0  # grading expanding downstream
    wG  = 400   # grading expanding wall to far field

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
    // z=0 plane (back), vertices 0-11
    project ({xS}       {-R}  0) (inlet_arc)       // 0
    (1       {-R}       0)                          // 1
    ({xMax}  {-R}       0)                          // 2
    project ({xMin_prj}  0   0) (inlet_arc)        // 3
    project (0           0   0) ({airfoil_patch})  // 4  LE
    project (1           0   0) ({airfoil_patch})  // 5  TE
    ({xMax}  0           0)                         // 6
    project ({xS}       {yL}  0) ({airfoil_patch}) // 7  lower surface
    project ({xS}       {yU}  0) ({airfoil_patch}) // 8  upper surface
    project ({xS}       {R}   0) ({airfoil_patch}) // 9  snaps to upper surf
    project (1          {R}   0) ({airfoil_patch}) // 10 snaps to TE
    ({xMax}  {R}         0)                         // 11

    // z=0.1 plane (front), vertices 12-23
    project ({xS}       {-R}  0.1) (inlet_arc)      // 12
    (1       {-R}       0.1)                         // 13
    ({xMax}  {-R}       0.1)                         // 14
    project ({xMin_prj}  0   0.1) (inlet_arc)       // 15
    project (0           0   0.1) ({airfoil_patch}) // 16 LE
    project (1           0   0.1) ({airfoil_patch}) // 17 TE
    ({xMax}  0           0.1)                        // 18
    project ({xS}       {yL}  0.1) ({airfoil_patch}) // 19 lower surface
    project ({xS}       {yU}  0.1) ({airfoil_patch}) // 20 upper surface
    project ({xS}       {R}   0.1) ({airfoil_patch}) // 21 snaps to upper surf
    project (1          {R}   0.1) ({airfoil_patch}) // 22 snaps to TE
    ({xMax}  {R}         0.1)                         // 23
);

blocks
(
    // lower leading: LE to xS, lower surface outward to far field
    hex ( 7  4 16 19  0  3 15 12)
    ({xUC} 1 {nW})
    edgeGrading
    (
        {lG}  {lG}  {xUG} {xUG}
        1 1 1 1
        {wG} {wG} {wG} {wG}
    )

    // lower middle: xS to TE, lower surface outward
    hex ( 5  7 19 17  1  0 12 13)
    ({xMC} 1 {nW})
    simpleGrading (1 1 {wG})

    // lower wake: TE to outlet
    hex (17 18  6  5 13 14  2  1)
    ({xDC} 1 {nW})
    simpleGrading ({xDG} 1 {wG})

    // upper leading: LE to xS, upper surface outward to far field
    hex (20 16  4  8 21 15  3  9)
    ({xUC} 1 {nW})
    edgeGrading
    (
        {lG}  {lG}  {xUG} {xUG}
        1 1 1 1
        {wG} {wG} {wG} {wG}
    )

    // upper middle: xS to TE, upper surface outward
    hex (17 20  8  5 22 21  9 10)
    ({xMC} 1 {nW})
    simpleGrading (1 1 {wG})

    // upper wake: TE to outlet
    hex ( 5  6 18 17 10 11 23 22)
    ({xDC} 1 {nW})
    simpleGrading ({xDG} 1 {wG})
);

edges
(
    // Airfoil surface edges at z=0
    project  4  7 ({airfoil_patch})
    project  7  5 ({airfoil_patch})
    project  4  8 ({airfoil_patch})
    project  8  5 ({airfoil_patch})
    // Airfoil surface edges at z=0.1
    project 16 19 ({airfoil_patch})
    project 19 17 ({airfoil_patch})
    project 16 20 ({airfoil_patch})
    project 20 17 ({airfoil_patch})
    // C-arc inlet edges
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
    back
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
    front
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
```

### 8.3 BC file changes (task 2 — after task 1)

In every BC builder (`_build_U`, `_build_p_clean`, `_build_k`, `_build_omega`, `_build_nut`):
- **Remove** the `top` and `bottom` blocks entirely
- **Add** an `outlet` block with the same type/value as `inlet`
  (both use `freestream` for U/p/k/omega; `calculated` for nut)

Concrete diff for `_build_U`:
```
REMOVE:
    top
    {
        type            symmetry;
    }
    bottom
    {
        type            symmetry;
    }

ADD (outlet block, same BC as inlet):
    outlet
    {
        type            freestream;
        freestreamValue uniform {Uvec};
    }
```

### 8.4 build_case() changes (task 3)

In `build_case()`:
- Replace `_build_block_mesh(patch)` → `_build_block_mesh_cmesh(patch, key.upper() + ".stl")`
- Delete the line writing `snappyHexMeshDict`
- Delete the line writing `surfaceFeatureExtractDict`

### 8.5 mesh_runner.py changes (task 4)

In `run_pipeline()` and `run_pipeline_verbose()`, change the `steps` list to:
```python
steps = [
    ("blockMesh", "blockMesh"),
    ("simpleFoam", "simpleFoam"),
]
```
(Remove `surfaceFeatureExtract` and `snappyHexMesh -overwrite` entries.)

---

# 9. Mesh Independence Study & Near-Stall Non-Convergence (2026-07-12)

## 9.1 Setup

5 mesh tiers, all NACA0012, all aspect-ratio-preserving scalings of the C-mesh
(nx,ny scaled together, not independently) around the then-current default
(nx=200, ny=150, "medium", ~60k cells):

| tier | nx | ny | cells (checkMesh) | scale vs. medium |
|---|---|---|---|---|
| coarse | 141 | 106 | 29,892 | 0.5x |
| medium | 200 | 150 | 60,000 | 1x (old default) |
| fine | 283 | 212 | 119,992 | 2x |
| extra-fine | 400 | 300 | 240,000 | 4x |

Run at alpha=5° (attached flow) and alpha=9° (near stall / near CLmax for
this airfoil at Re=2e5). Data: `results/mesh_independence.csv`.

## 9.2 alpha=5° (attached flow) — converges normally

| step | Cl | Cd |
|---|---|---|
| coarse->medium | -2.15% | -4.71% |
| medium->fine | **+0.25%** | -3.56% |

Cl is converged at the fine tier. Cd is still moving ~3.6% medium->fine —
not fully converged, but shrinking, well-behaved, monotonic. No sign of a
deeper problem here. This is why the production default moved to fine
(nx=283, ny=212) — see the `feat:` commit updating case_builder.py defaults.

## 9.3 alpha=9° (near stall) — genuinely non-convergent, NOT slow convergence

| step | Cl | Cd | Cm |
|---|---|---|---|
| coarse->medium | +51.6% | +130.6% | sign flip (+ -> -) |
| medium->fine | +11.4% | -26.6% | sign flip (- -> -, but -0.159 -> -0.040, not shrinking toward 0 monotonically) |
| fine->extra-fine | **-8.35%** | **-29.5%** | sign flip (- -> +) |

**This is the key result.** If this were slow convergence, every row's %
change should keep the same sign and shrink in magnitude as the mesh gets
finer. Instead:
- Cl changes sign of its *trend* between steps (+51% -> +11% -> **-8%**) —
  it overshoots and comes back down, it doesn't monotonically approach a
  limit.
- Cd's magnitude does NOT shrink: -26.6% (medium->fine) vs. **-29.5%**
  (fine->extra-fine) — going from 120k to 240k cells changed Cd by *more*
  than going from 60k to 120k did. Quadrupling the resolution from the old
  default made no progress on Cd at all.
- Cm flips sign three times across four tiers (+0.0085 -> -0.1591 ->
  -0.0404 -> +0.0068) with no visible trend.

**Conclusion: alpha=9° is a mesh-sensitive / bistable steady-RANS solution,
not a case that "just needs a finer mesh."** Stopped here per plan (evidence
is already unambiguous — an ultra-fine, ~480k-cell tier was not run, since
the fine->extra-fine step already shows the same-magnitude oscillation
pattern that would justify skipping further refinement). Most likely
explanation: alpha=9° sits at/near this airfoil's actual stall point at this
Re, where the real flow is physically unsteady (periodic separation /
vortex shedding). A steady-state solver has no true steady solution to
converge to there; whatever fixed point it lands on is an artifact of that
particular mesh's truncation error, which is why it moves around
unpredictably as the mesh changes instead of converging to a limit.

## 9.4 Proposed reliability flag (NOT implemented yet — proposal only)

Current `results/airfoil_results.csv` flags rows `post-stall-unreliable` only
by a fixed alpha cutoff (>=12° for NACA0012 in the existing dataset). Section
9.3 shows this is too permissive: alpha=9° looks perfectly smooth (converged
solver residuals, no divergence) but is not mesh-independent at all — the
current fixed-cutoff approach would report it as good data.

**Proposed criterion:** flag any (airfoil, alpha) row as unreliable based on
the *mesh-independence delta* at that specific alpha, not a hardcoded angle
threshold:

```
flag row as "mesh-unreliable" if:
    |ΔCl(medium->fine)| > T_Cl   OR   |ΔCd(medium->fine)| > T_Cd
```

where `T_Cl`, `T_Cd` are percent thresholds (candidates: 2-3%, per the
1-2% "adequately converged" bar used in this study, with some margin).
Reference points from this study to calibrate the threshold:
  - alpha=5 (should NOT be flagged): ΔCl=+0.25%, ΔCd=-3.56%
  - alpha=9 (SHOULD be flagged): ΔCl=+11.4%, ΔCd=-26.6%

A single fixed-alpha cutoff can't distinguish these because the mesh
sensitivity is airfoil- and alpha-specific (it's tied to how close that
point is to the actual stall/separation onset, which shifts with camber —
compare NACA0012 vs NACA2412's different stall behavior in
`results/airfoil_results.csv`), not a universal angle.

**Practical implementation note:** this requires running the medium/fine
pair (or fine/extra-fine, if fine is adopted as the new "medium" baseline
now that the default moved to 283x212) for every alpha in a production
sweep, not just spot checks — i.e., every angle would need its own 2-tier
mesh check to compute ΔCl/ΔCd before being trusted. That's a real cost
(roughly doubles the compute per angle) worth weighing against just
manually widening the fixed cutoff (e.g. dropping it to alpha>=8 based on
this one data point) as a cheaper, cruder interim fix.

Exact threshold (T_Cl, T_Cd) left for a follow-up decision once more alphas
are spot-checked this way — 9.3's numbers are illustrative, not a full
calibration.

## 9.5 pimpleFoam investigation at alpha=9 — SUPERSEDED, see 9.7 (2026-07-13)

**Goal:** determine whether NACA0012 alpha=9's non-convergence (9.3) is genuine
physical unsteadiness (periodic vortex shedding near stall, which steady
simpleFoam cannot represent) or a numerics artifact of the steady solver
setup, by switching to unsteady pimpleFoam and checking whether Cl/Cd settle
into stable periodic oscillation.

**What was tried:** pimpleFoam at alpha=9, both at the fine tier (120k cells)
and the medium tier (60k cells), same wall functions/physics as the steady
pipeline, backward ddtScheme, 3 PIMPLE outer correctors, started from a
uniform freestream IC. Both attempts **diverged** (floating-point exception
in the GAMG pressure solve) before completing even one flow-through time.
The medium-tier attempt's crash followed an adjustTimeStep overshoot (Courant
spiked to 500-960 after `maxCo` was raised from 50 to 150 to speed up an
impractically slow run) that the solver never recovered from even after
`maxCo` was reverted back down.

**Root cause NOT conclusively determined.** Two live hypotheses, not
distinguished:
  1. The flow at alpha=9 is genuinely unsteady/separated in a way that
     needs a more careful transient setup (e.g. more outer correctors,
     smaller Courant ceiling held constant throughout rather than adjusted
     up, a gentler/ramped initial condition instead of an impulsive uniform
     start) to integrate stably — i.e. a solver-robustness problem, fixable.
  2. The flow is bistable/violently transient in a way that makes ANY
     steady-start unsteady RANS integration fragile here regardless of
     solver settings — i.e. a genuine physics finding in its own right.

**Decision:** stop investigating for now rather than keep spending time
narrowing this down. This is explicitly an **open question**, not a settled
one - revisit if/when it becomes necessary (e.g. if the placeholder flag
below turns out to be materially wrong once real data exists to check it
against, or if the same non-convergence pattern shows up on NACA2412/4412
and a real answer becomes worth the cost).

## 9.6 Interim reliability flag adopted for NACA0012 — SUPERSEDED, see 9.7

(Historical record: this section originally described a conservative
placeholder flag adopted before the conclusion in 9.7 was reached. See 9.7
for the current, final flag and rationale.)

## 9.7 FINAL CONCLUSION — NACA0012 alpha>=8 has no steady RANS solution (2026-07-16)

**This closes the investigation started in 9.3-9.6. Not an open question
anymore - no further mesh or solver tuning is planned for NACA0012 on the
strength of this.**

**Validated range: alpha = -5 deg to 7 deg.** Clean, converged, mesh-checked
(9.2) results. Use this data with confidence.

**alpha >= 8 deg: no steady-state solution exists for this flow, full stop.**
Three independent lines of evidence, gathered across three separate
investigations, all point the same direction:

1. **Mesh-independence bistability (9.3).** At alpha=9, Cl and Cd do not
   converge with mesh refinement - they overshoot and reverse trend
   direction across coarse->medium->fine->extra-fine (Cl: +51.6% -> +11.4%
   -> -8.35%; Cd's swing does not shrink with refinement: -26.6% ->
   -29.5%). A real discretization error shrinks monotonically; this does not.

2. **pimpleFoam divergence, twice (9.5).** Unsteady solving was tried
   specifically to check whether the flow settles into ordinary periodic
   vortex shedding (which would still be a usable, if more expensive,
   answer). Both the fine-tier and medium-tier attempts diverged
   (floating-point exception) before completing even one flow-through time,
   starting from a plain uniform-freestream IC. Inconclusive on its own,
   but consistent with the flow being violent enough that even a transient
   solver can't integrate through it cleanly.

3. **Residual-synced Cl oscillation at extended iteration count (2026-07-16,
   this investigation).** Steady simpleFoam runs for alpha=14 and alpha=16
   were extended from 3000 to 6000 iterations to settle whether the
   still-climbing Cl at iteration 3000 (9.3's dataset) was slow convergence
   or something else. Neither case converged in either direction. Instead,
   both show a huge, non-monotonic swing: Cl climbs to an even less
   plausible peak (~2.1-2.4) around iteration 3200-3400, crashes through
   zero to strongly negative (-0.50 to -0.74) around iteration 4800-4900,
   then partially recovers - still moving at iteration 6000, nowhere near
   settled. Critically, the initial pressure residual spikes by 2-4 orders
   of magnitude (e.g. ~1e-6 -> 0.017) at exactly the iterations where Cl is
   swinging, then subsides again - this is the solution field undergoing
   real, discrete transitions, not numerical noise around a converged mean.

   This is the decisive piece: it directly demonstrates, inside the plain
   steady solver (no pimpleFoam needed), that there is no fixed point for
   simpleFoam's pseudo-time iteration to converge to at these angles. The
   the iteration count acts like a distorted pseudo-time axis, and what's
   visible is one incomplete cycle of a much larger oscillation - consistent
   with genuine, large-amplitude unsteady separation (deep-stall-type
   behavior) at Re=2e5, not a bug or a mesh/solver-tuning problem.

**Practical conclusion:** alpha>=8 deg for NACA0012 does not have a
steady-RANS answer to converge to, regardless of mesh density, iteration
count, or (based on the pimpleFoam attempts) a naive switch to unsteady
solving. More mesh refinement, more iterations, or more solver tuning are
not expected to fix this and are not planned.

**Flag applied:** `results/airfoil_results.csv` rows with alpha >= 8 for
NACA0012 (previously `near-stall-unreliable-placeholder`) are now labeled
`no-steady-solution-unsteady-separation` - the label change matters: this is
not "an uncertain number," it is "not a number." Rows alpha >= 16 keep the
separate, pre-existing `post-stall-unreliable` label from
`auto_flag_airfoil()`'s algorithmic branch-jump detection (not renamed here -
that detection is a different, narrower mechanism, though it stems from the
same underlying breakdown).

**Does NOT automatically apply to NACA2412/4412.** Stall onset shifts with
camber. Each airfoil's breakdown angle needs its own check via the same
method (mesh-independence spot-check + extended-iteration residual/Cl trend)
rather than assuming NACA0012's alpha=8 cutoff transfers directly - see the
NACA2412 sweep/breakdown-angle analysis for the first test of this.

---

# 10. NACA2412 full sweep and breakdown-angle analysis (2026-07-19)

## 10.1 Setup

Full 30-angle sweep, alpha=-5 to 20 (1 deg steps, 0.5 deg steps 8.5-11.5),
current finalized pipeline (fine-tier C-mesh ~120k cells,
nutUSpaldingWallFunction, simpleFoam/kOmegaSST, Re=2e5) - identical settings
to the NACA0012 dataset in section 9.7, so the two are directly comparable.
30/30 succeeded, 0 failures. The prior 6 NACA2412 rows (alpha=-5..0) were
deleted first and rerun as part of this sweep - confirmed via checkMesh that
they'd been built on the old medium-tier mesh (60000 cells) despite already
having the correct wall function, so were not valid to keep alongside a
fine-tier dataset.

## 10.2 Where the curve stops looking physically plausible

Per-degree Cl slope (dCl/dalpha):

| range | slope |
|---|---|
| alpha=-5 to 6 | ~0.095-0.115/deg, flat, normal attached-flow behavior |
| alpha=7 -> 8 | 0.148/deg - first jump |
| alpha=8 -> 11 | climbs further to ~0.25/deg at its peak (more than double baseline) |
| alpha=14 -> 15 | first outright non-monotonic reversal (Cl drops), already caught by auto_flag_airfoil()'s post-stall-unreliable |

The slope-acceleration onset lines up almost exactly with NACA0012's own
breakdown signature (section 9.3), which also showed the pre-breakdown
region as a flat, constant slope followed by a sudden increase rather than
the slope easing off toward a real CLmax.

## 10.3 Extended-iteration diagnostic (3000 -> 6000 iterations)

Ran at alpha=8, 11, 14 (chosen to bracket the slope acceleration and the
first non-monotonic jump). Results:

| alpha | Cl @ 3000 (original) | Cl @ 6000 | trajectory |
|---|---|---|---|
| 8  | 0.926 | 0.779 | rises to a peak (~0.946, iter ~2400), then declines steadily, NOT plateaued at iter 6000 |
| 11 | 1.615 | 0.00005 | rises to a peak (~1.81, iter ~3600), crashes through zero, ends essentially at zero, still moving |
| 14 | 2.115 | 0.151  | rises to a peak (~2.18, iter ~3300), crashes through zero to negative (~-0.058), partially recovers |

alpha=11 and alpha=14 show the unmistakable NACA0012 signature: large
climb-crash-through-zero-partial-recovery, with the pressure residual
spiking 2-4 orders of magnitude (e.g. alpha=14: ~1e-6 -> 0.015) exactly in
sync with the Cl crash. **Confirmed genuine breakdown, not slow
convergence**, same as NACA0012 section 9.3/9.7.

alpha=8 is the one ambiguous case: Cl is clearly NOT converged (still
declining ~16% off its peak with no plateau by iteration 6000), but unlike
alpha=11/14 it has not (yet, within 6000 iterations) crashed through zero,
and its residuals stay comparatively well-behaved (small, mostly
decreasing, no late-stage spike). Read most plausibly as the *early stage*
of the same breakdown on a slower timescale, rather than a separate,
milder phenomenon - but this is inference, not as airtight as the
alpha=11/14 evidence. Not independently confirmed via mesh-independence
cross-check (which is how NACA0012's alpha=9 case was first nailed down in
section 9.3) - a real gap if this boundary matters a lot later.

## 10.4 Turbulence-model decision: staying on kOmegaSST, no transition model (2026-07-23)

**Decision made: all three airfoils (0012, 2412, 4412) stay on plain
kOmegaSST with no laminar-turbulent transition model.** Not switching to
kOmegaSSTLM or similar. NACA0012's dataset is unaffected by this section -
no redo.

**Root cause of the Cl-vs-XFOIL mismatch identified.** A dedicated
diagnostic (mesh/y+ split upper-vs-lower, Cp distribution vs. a validated
NeuralFoil/XFOIL reference, both at NACA2412 alpha=4) found:

- y+ is asymmetric between surfaces (upper mean 4.91, lower mean 6.82) but
  both stay inside the 1-13 range `nutUSpaldingWallFunction` handles
  robustly - not the main driver.
- Mesh quality is modestly worse than NACA0012 (58 vs 38 severely
  non-orthogonal faces) and concentrated at the leading edge - a secondary
  contributor at most.
- **The Cp comparison is the decisive evidence.** The upper (suction)
  surface is under-predicted almost everywhere, peaking at x/c~0.14-0.22
  (|Cp error| up to 0.61) - just aft of the leading edge, in the region
  where the suction peak should be transitioning into recovery. This is a
  fully-turbulent boundary layer (no transition model) smearing out the
  suction peak, and it is *much* more pronounced here than the mild,
  symmetric slope deficit already known on NACA0012.

**Why NACA2412 shows this so much more than NACA0012:** NACA0012 is
symmetric with a comparatively weak, broad suction peak - the fully-turbulent
assumption still smears it, but mildly, since there is not much peak to
smear. NACA2412's camber produces a stronger, more concentrated suction
peak, which the same fully-turbulent assumption under-resolves far more
aggressively. **This bias should be expected to grow with camber**: more
camber means a stronger, more concentrated suction peak for the model to
under-resolve, not less. NACA4412 (4% camber, double NACA2412's) should be
expected to show an even larger version of this same effect - this is a
prediction to check once NACA4412 data exists, not just a possibility.

**Implication for the write-up: any camber-vs-lift conclusion in the final
analysis is a probable *underestimate* of the true camber effect, not an
absolute measurement.** Since the suction-peak under-prediction gets worse
as camber increases, the *relative* lift benefit of camber that this
dataset shows is itself biased low relative to reality - the real
aerodynamic benefit of camber is likely larger than what this pipeline will
report. **This limitation must be stated plainly in the paper's
methods/limitations section**, not left implicit in a data table footnote.

## 10.5 Mesh-seam fix at the block-transition point (xS=0.3) (2026-07-23)

**Independent of the turbulence-model decision above - a real, separate
mesh-quality bug, now fixed.** The Cp diagnostic in 10.4 also turned up a
sharp, localized anomaly on *both* surfaces at x/c~0.3, coincident with
`xS=0.3` - the C-mesh's block-transition/arc-center point in
`core/case_builder.py`'s `_build_block_mesh_cmesh()`.

**Confirmed by direct measurement**, not just suspicion: parsed the actual
generated mesh's surface-point spacing (not the code, the real
`constant/polyMesh` output) approaching and leaving the xS seam on a built
NACA2412 case. Found cell size growing smoothly from ~0.0052 to ~0.0084
across the leading block (LE->xS) as designed, then **abruptly dropping to
a flat 0.0066 for the entire length of the middle block (xS->TE)** - a
~15-25% cell-size discontinuity right at the block face, on both upper and
lower surfaces, at the exact x-station where the Cp anomaly showed up. Root
cause: the middle block used `simpleGrading (1 1 {wG})` - chordwise ratio
of exactly 1, i.e. perfectly uniform cells - which does not know or care
what cell size the leading block arrives with.

**Fix:** added a new grading parameter `mG = 1.3` and changed both middle
blocks (upper and lower) from `simpleGrading (1 1 {wG})` to
`simpleGrading ({mG} 1 {wG})`, so the middle block's cells start at roughly
the leading block's ending size and taper down gradually across the block
instead of resetting to uniform. This is an empirically-tuned value (I
rebuilt a test mesh and re-measured the actual point spacing rather than
trusting the grading math by hand, since the blocks are curved/projected
onto the airfoil surface and hand-deriving exact cell sizes isn't
reliable). **Verified fixed**: post-fix spacing goes 0.00838 -> 0.00799 ->
0.00750 -> 0.00748 -> ... smoothly decreasing by a fraction of a percent
per cell, no jump anywhere near the seam.

**This changes the shared `_build_block_mesh_cmesh()` function, so it
technically affects the mesh recipe for all three airfoils, not just
NACA2412** (same xS=0.3 block topology is used for NACA0012 and NACA4412
too). Per explicit instruction: NACA2412 gets rerun to reflect this fix;
**NACA0012's already-finalized dataset is deliberately left as-is and NOT
rerun**, even though the code it was generated from has since moved on
slightly. If NACA0012 is ever revisited, note that its dataset predates
this mesh-seam fix.

## 10.6 Conclusion: NACA2412 breakdown angle

**Validated range: alpha = -5 to 7 deg** (same bound as NACA0012, based on
the same standard: flat/consistent Cl slope, no evidence tested to the
contrary - alpha=7 itself was not independently extended-iteration-tested,
same caveat that applied to NACA0012's alpha=7 boundary).

**alpha >= 8 deg: flagged `no-steady-solution-unsteady-separation`**,
matching NACA0012's convention and label exactly. Confirmed unambiguously
for alpha=11 and 14; alpha=8 itself is flagged conservatively based on slope
evidence + non-plateaued Cl trend, not as airtight as 11/14 - treat alpha=8
specifically as "probably broken, not proven to the same standard" if this
distinction ever matters. Rows alpha>=14 additionally carry the pre-existing
algorithmic `post-stall-unreliable` label from `auto_flag_airfoil()`,
unchanged, same treatment as NACA0012.

**Comparison to NACA0012:** breakdown angle is the same, alpha>=8 for both
airfoils, despite NACA2412's 2% camber. This is somewhat unexpected -
classical thin-airfoil-theory intuition says camber shifts stall onset
(usually earlier for this direction of camber), but that intuition is about
*real* stall, and what's being measured here is not real stall - it's the
angle where steady RANS stops having a solution to converge to at all. That
breakdown may be governed more by Reynolds number, mesh, and turbulence
model (no transition model, fully-turbulent kOmegaSST) common to both
airfoils than by camber-specific aerodynamics. Should not be assumed to
hold for NACA4412 (4% camber, double NACA2412's) without its own check.

---

## 11. Airfoil-surface geometry bug: `project`-edge undershoot, polyLine fix,
## full NACA0012 redo (2026-08-03)

**Everything in section 9 (NACA0012) and section 10 (NACA2412) above was run
on an incorrect airfoil shape.** This section documents the bug, the fix,
and the full NACA0012 redo. NACA2412's redo is a separate, later phase.

### 11.1 The bug

The rendered NACA0012 pressure plots looked like a faceted diamond, not a
smooth aerofoil, even after fixing an unrelated ParaView camera-reset
rendering bug. Pulling the actual airfoil-patch points directly out of a
solved case's `constant/polyMesh` (not the STL - the real simulation mesh)
and comparing against the analytical `yt(x)` formula confirmed this was a
real geometry bug, not a rendering artifact: thickness error reached -95%
near the leading edge, was exactly 0% at the single vertex explicitly
projected at x=0.3, and ran -30% to -40% through mid-aft chord.

Root cause: `_build_block_mesh_cmesh()`'s airfoil-surface edges used
`project (edge) (airfoil_patch)` between three anchor vertices (LE, x=0.3,
TE). blockMesh's edge-projection does not trace the true curve between
those anchors - it interpolates a straight line then nearest-point-snaps
onto the STL, which undershoots a convex airfoil surface everywhere except
exactly at the anchors. Every simulation in this project prior to this
section (both airfoils, full sweeps, mesh independence, near-stall
diagnostics, XFOIL/NeuralFoil comparisons) used this wrong shape.

### 11.2 The fix

Replaced the 8 buggy `project`-edges (LE<->x=0.3<->TE, both z-planes) with
explicit `polyLine` edges built from densely-sampled analytical NACA4
points (cosine-spaced over the full chord, ~0.5-0.9% chord spacing
mid-chord, far denser at the LE/TE cusps) - see `_naca4_params`,
`_naca4_surface_point`, `_naca4_polyline_points` in `core/case_builder.py`.
Falls back to the old project-edge behavior for any non-NACA4 airfoil
identifier (Custom Mesh Mode / `core/custommesh_builder.py` untouched).

Verified by rebuilding a NACA0012 test case and re-pulling actual
`constant/polyMesh` patch points: mean thickness error across all 353
patch points dropped to 0.32%, and the old worst region (x in [0,0.3])
dropped to a 0.10% mean / 4.9% max - the only points over 1% error are the
TE vertex (compares against the NACA4 thickness formula's known nonzero
value at x=1; both old and new meshes force-close the TE to exactly (1,0),
unaffected by this fix) and the two points nearest the LE (absolute error
~1e-4, inflated in percentage terms by tiny local thickness). checkMesh
clean, same 354-face patch topology as before.

### 11.3 Effect on Cl/Cd: geometry bug vs. turbulence model

Comparing old (buggy-geometry) vs. new (corrected) at the two angles that
happened to be sampled early in the redo:

| alpha | Cl (old) | Cl (new) | Cl (XFOIL) | Cd (old) | Cd (new) | Cd (XFOIL) |
|---|---|---|---|---|---|---|
| 0 | ~0 | ~0 | 0.000 | 0.0178 | 0.0233 | 0.0102 |
| 4 | 0.395 | 0.388 | 0.536 | 0.0274 | 0.0253 | 0.0118 |

Cl is essentially unchanged (arguably fractionally worse) and Cd improved
only modestly at alpha=4, got *worse* at alpha=0. This is expected in
hindsight: NACA0012 is symmetric, so a thickness-undershoot bug does not
strongly bias lift the way it would for a cambered section. This means the
Cl-vs-XFOIL gap documented in section 10.4 (attributed to the fully-
turbulent kOmegaSST boundary layer smearing the suction peak, no
transition model) is probably still the right explanation for NACA0012,
and is NOT invalidated by this geometry fix. Whether the geometry bug
explains more of NACA2412's camber-related Cl gap is the open question for
the Phase 4 redo (cambered sections have nonzero yc, so the old bug's
undershoot was NOT symmetric top/bottom there).

### 11.4 Mesh independence on the corrected geometry - fine tier no longer clearly adequate

Re-ran coarse/medium/fine/extra-fine at alpha=5,9 on the corrected shape:

| alpha | tier | nx | ny | Cl | Cd |
|---|---|---|---|---|---|
| 5 | coarse | 141 | 106 | 0.5432 | 0.02779 |
| 5 | medium | 200 | 150 | 0.5156 | 0.02688 |
| 5 | fine | 283 | 212 | 0.4731 | 0.02636 |
| 5 | extra-fine | 400 | 300 | 0.4292 | 0.02589 |
| 9 | coarse | 141 | 106 | 0.8634 | 0.04037 |
| 9 | medium | 200 | 150 | 0.8354 | 0.03555 |
| 9 | fine | 283 | 212 | 0.7637 | 0.03322 |
| 9 | extra-fine | 400 | 300 | 0.6606 | 0.03020 |

Unlike the pre-fix mesh-independence study (fine->extra-fine changed
Cl<1%), Cl is still changing 8-13% from fine to extra-fine on the corrected
geometry (alpha=5: -9.3%, alpha=9: -13.5%). Reading: the old bug was
undershooting the true leading-edge curvature, so the old mesh only had to
resolve an artificially blunted shape; now that the LE is properly sharp,
"fine" (283x212, the current production default) may no longer be enough
to resolve it, especially at higher incidence where the LE suction peak
matters more. **Not resolved as of this section** - production mesh
settings may need to move up a tier, which is a comparable compute cost to
redoing the full sweep again. Flagged for a decision before treating any
NACA0012 dataset as final; not blocking the near-stall investigation below
since that uses the existing "fine" tier consistent with all other rows.

### 11.5 Near-stall breakdown re-investigation - new threshold is alpha>=14, NOT alpha>=8

The corrected-geometry Cl-vs-alpha curve (full 29-angle resweep,
`results/airfoil_results.csv`) is smooth and monotonic through alpha=12,
unlike the old dataset which broke down by alpha=8. Cd starts escalating
disproportionately from alpha=12 onward (0.0472 -> 0.0627 -> 0.1586 ->
0.3028 at alpha=12/13/14/15) while Cl keeps climbing to physically
implausible values (2.05-2.13 by alpha=17-19, well above any real NACA0012
stall Cl at this Re) - the same qualitative signature as the old
breakdown, just starting much later.

Ran the extended-iteration diagnostic (3000 -> 6000 iterations) at
alpha=9, 12, 13, 14 to locate the real onset rather than assume it moved
by the same 6 degrees as a guess:

- **alpha=9, 12: cleanly converged.** Cl approaches its 6000-iteration
  value asymptotically (alpha=9: 0.764->0.772, +1.1%; alpha=12: 0.915->
  0.927, +1.4%, with a small bounded overshoot/settle around
  iteration 1000-2000, not a divergence). Reliable.
- **alpha=13: converges, but slowly.** Cl overshoots to 1.042 by
  iteration 1000, declines to a genuine plateau of ~0.898-0.902 by
  iteration 4500-6000 (final 1500 iterations flat to 3 sig figs). The
  standard 3000-iteration sweep value (Cl=0.936) is ~3.7% high relative to
  its own converged value - a real but bounded iteration-count error, not
  a sign of no steady solution. Treated as the last validated angle, with
  this caveat noted rather than re-running the whole dataset at 6000
  iterations.
- **alpha=14: confirmed no steady solution.** Cl swings wildly and is
  still moving by tens of percent at iteration 6000 - not plateaued:
  0.955 (i=500) -> 1.138 (i=1000) -> 1.223 (i=3500) -> 1.305 (i=4000) ->
  0.999 (i=5000) -> 0.587 (i=5500) -> **0.183 (i=6000, still falling)**.
  Cd and Cm swing correspondingly (Cd peaks ~0.276 around i=4500 then
  falls to 0.119; Cm swings from +0.033 to -0.156 and back to +0.018).
  Same climb/crash/partial-recovery signature documented for the old
  geometry's breakdown cases and for NACA2412 alpha=11/14 (section 10.6).

alpha=15-20 were not independently extended-iteration-tested (same
convention as prior sections - representative points characterize the
regime), but share alpha=14's qualitative signature (Cl climbing past any
physical bound, Cd escalating) and are flagged on that basis.

**`auto_flag_airfoil()` did not catch any of this** - its heuristics
(single-step Cl drop >0.5, Cd jump >3x previous, or climb-back-above-
first-drop) were tuned to the *old* dataset's failure shape (a sharp Cl
drop then partial recovery). The new dataset's failure shape is a smooth
monotonic climb into unphysical territory with no single-step trigger
large enough to fire any of the three criteria - every alpha>=14 row would
have sailed through with an empty note if this extended-iteration check
hadn't been run by hand. Worth hardening later (e.g. an implausible-Cl-
magnitude or Cd-escalating-trend criterion) but not done here - flagged as
a known gap, not fixed as part of this phase.

### 11.6 Conclusion: NACA0012 validated range (corrected geometry)

**Validated range: alpha = -4 to 13 deg** (13 carries the slow-convergence
caveat from 11.5 above; -4 to 12 fully clean).

**alpha >= 14 deg: flagged `no-steady-solution-unsteady-separation`** in
`results/airfoil_results.csv`, same label as the old dataset's convention.
Confirmed by direct extended-iteration evidence at alpha=14; alpha=15-20
inferred from matching qualitative signature, not independently confirmed
to the same standard.

**Comparison to the old (buggy-geometry) conclusion:** the breakdown angle
moved from alpha>=8 to alpha>=14, a 6-degree shift. The corrected,
properly-sharp leading edge sustains a steady attached-flow RANS solution
across a much wider incidence range than the old undershoot-blunted shape
did. This is the clearest evidence so far that the geometry bug was not
just a cosmetic/thickness-accuracy issue but was materially degrading the
solver's ability to find a steady solution at moderate incidence.

---

## 12. Mesh-seam analytical fix, 6000-iter reruns, and full near-stall
## diagnostics for both airfoils (2026-08-09)

### 12.1 Context: two more mesh-construction defects fixed before this

Investigating why NACA2412's mesh-independence study (section 11-era) showed
a non-monotonic +/-26% Cl spread across tiers even after ruling out under-
convergence turned up two more hardcoded-constant bugs in
`_build_block_mesh_cmesh()`, both camber-specific and both invisible on
NACA0012 (symmetric) by coincidence:

- **mG (middle-block xS->TE chordwise grading)** was a hardcoded 1.3, tuned
  by eye against one NACA2412 fine-tier mesh. Measured directly (cell-size
  jump ratio at the x/c=0.3 seam): fine for NACA0012 (~0.86-0.88, flat across
  all 4 tiers) but an 80-95% cell-size collapse for NACA2412 (0.05 coarse ->
  0.20 fine, worse at coarser resolution). Replaced with an analytically
  solved per-surface ratio (geometric simpleGrading sequence) matching the
  leading block's xS-adjacent cell to the middle block's, using each block's
  true arc length - independently for upper/lower (mG_upper != mG_lower for
  cambered airfoils).

- **yU/yL (seed y for the xS vertices 7/8/19/20)** were hardcoded +-0.06,
  which matches NACA0012's actual thickness at x=0.3 (yt(0.3)~0.060) almost
  exactly - the reason it was invisible there. For NACA2412 the true surface
  is (0.0787 upper, -0.0412 lower), ~31% off. blockMesh's single-vertex
  project landed at essentially the raw unprojected seed (0.300000, 0.060000)
  instead of the true curve, planting a wrong point right at the seam. Fixed
  by computing yU/yL from the analytical surface at xS.

After both fixes, seam jump ratio is ~1.0 for BOTH airfoils across all 4
tiers (naca2412 upper went 0.2373 -> ~0.995). Audited every other
project(x,y,z) vertex: LE/TE are exact by NACA4 construction; far-field-arc
vertices are geometry-independent; vertices 9/10/21/22 ("snaps to
upper surf"/"snaps to TE") were empirically confirmed to NOT project onto
the airfoil at all - they stay at the far-field radius (y=20), which is the
correct far-field boundary shape, so the "snaps to..." comments are stale/
wrong but harmless. Commit 93922b9.

### 12.2 6000-iteration reruns (both airfoils, full 29-angle sweep)

Separately confirmed (section 11-era + NACA2412 mesh-independence work): the
fixed 3000-iteration budget under-converges the denser meshes. Both airfoils'
full sweeps were re-run at 6000 iterations on the corrected mesh (commit
c7d4084). Both now show physically realistic stall - Cl peaks then declines,
unlike the pre-fix data which climbed into unphysical territory. NACA2412
holds attached flow ~2-3 deg longer than NACA0012 and has a higher CLmax:
camber delaying stall and raising peak lift, the physically expected result,
and a clean contrast to the old buggy-geometry data where both broke down at
the SAME angle (which was flagged as suspicious at the time).

### 12.3 Near-stall extended-iteration diagnostics (12000 iterations)

Ran the standard extended-iteration check (double to 12000 iters, full
Cl/Cd/Cm trajectory + per-iteration pressure residual, same standard used
throughout) on the angles that matter for the research conclusions.

**Breakdown / no-steady-solution (both confirmed by direct evidence):**
- NACA0012 alpha=14: Cl swings violently the whole run (climbs to 1.24,
  crashes through zero to -0.059, partially recovers), never plateaus (Cl
  span in final quarter = 0.12), pressure residual spikes in sync with each
  Cl swing and never settles below ~1e-4. No steady solution.
- NACA2412 alpha=16: same signature (Cl through zero to -0.038, span in
  final quarter = 0.37, residual spikes to ~4e-3 synced with swings). No
  steady solution.

**Last reliable point below breakdown (both converge to clean plateaus):**
- NACA0012 alpha=13: settles to Cl=0.894 (final-6% span 0.0002, residual to
  5.6e-6). Converged. ~1% above its 6000-iter sweep value (0.884).
- NACA2412 alpha=15: settles to Cl=0.899 (final-6% span 0.001, residual to
  2.7e-6). Converged - but see 12.5, its 6000-iter sweep value was badly
  under-converged (0.830).

### 12.4 The alpha=6/7 dip is a REAL, reproducible feature (not noise)

NACA2412 showed a ~7% Cl drop from alpha=6 (0.812) to alpha=7 (0.755) with
Cm swinging sharply toward zero (-0.043 -> -0.0075) at an otherwise
unremarkable early angle - flagged during the sweep as worth checking rather
than dismissing. Both re-ran at 12000 iters converged ROCK-SOLID:
- alpha=6: Cl=0.81319, last-25% span = 0.00007, residual to 9.3e-7.
- alpha=7: Cl=0.75460, last-25% span = 0.00000, residual to 1.4e-6.
Both reproduce their 6000-iter sweep values to 4 decimal places. This is a
genuine, converged, repeatable aerodynamic feature - likely a real
separation/loading-distribution shift the RANS model captures at that
incidence for the cambered section (the sharp Cm-toward-zero swing is
consistent with a center-of-pressure shift from trailing-edge separation
onset). Not a numerical artifact.

### 12.5 The alpha=15 under-convergence is alpha=15-SPECIFIC, not broad

NACA2412 alpha=15 read 0.830 in the 6000-iter sweep but converges to 0.899
at 12000 iters (+8.3% gap) - far larger than NACA0012 alpha=13's 1% gap.
To scope this before trusting CLmax, re-ran the whole near-peak region
(alpha=11,12,13,14) at 12000 iters:

| alpha | 6000-iter sweep Cl | 12000-iter converged Cl | gap |
|-------|--------------------|-------------------------|-----|
| 11    | 1.0424             | 1.0427                  | +0.03% |
| 12    | 1.0707             | 1.0714                  | +0.06% |
| 13    | 1.0457             | 1.0447                  | -0.10% |
| 14    | 0.9951             | 0.9990                  | +0.4%  |
| 15    | 0.830              | 0.899                   | +8.3%  |

Every near-peak angle (11-14) matches its sweep value within 0.4% and
converges cleanly. **The under-convergence is isolated to alpha=15.** Its
trajectory overshoots to 1.33, dips to 0.77, then recovers to a plateau at
0.90 - the 6000-iter sweep caught it mid-recovery. alpha=15 sits just past
the peak in the early separation-growth region, where the larger separated
zone settles more slowly than the attached/near-peak points; those don't
have a big separated region so they converge fast.

Only alpha=14 and alpha=15 sweep rows were patched to their converged values
in results/airfoil_results.csv (alpha=15 carries a note). Everything
alpha<=13 is already correct as-swept.

### 12.6 Conclusion: validated ranges and CLmax (fully-corrected pipeline)

- **NACA0012: validated alpha = -4 to 13 deg. Breakdown (no steady RANS
  solution) at alpha >= 14 deg.** CLmax ~0.907 at alpha=12.
- **NACA2412: validated alpha = -4 to 15 deg. Breakdown at alpha >= 16 deg.**
  **CLmax = 1.071 at alpha=12** (confirmed unchanged - alpha=12 was already
  well-converged at 6000 iters, gap 0.06%).
- Camber delays breakdown by 2 deg (13->15 last-reliable) and raises CLmax
  (0.907 -> 1.071) - both physically expected, and a clean contrast to the
  old buggy-geometry data where both airfoils broke down at the same angle.

### 12.7 Cp comparison re-run: geometry bug, NOT the turbulence model, drove
### most of the section 10.4 suction-side discrepancy (2026-08-09)

Re-ran the NACA2412 alpha=4 surface-Cp comparison against the NeuralFoil/
XFOIL reference (Re=2e5), same methodology as section 10.4, now on the
corrected geometry+mesh (6000-iter case naca2412_ap4_0). OpenFOAM wall Cp
extracted by mapping the zeroGradient airfoil-patch faces to their owner
cells (Cp = p_kinematic / (0.5 V^2); stagnation Cp came out 0.998, sign/
reference confirmed). NeuralFoil Cp reconstructed from its ue/vinf edge-
velocity output as 1 - (ue/vinf)^2. NeuralFoil CL=0.706 matches real XFOIL
(0.708), reference validated.

**Result (upper/suction surface, the section-10.4 hotspot):**

| metric | section 10.4 (buggy geom) | now (corrected) |
|--------|---------------------------|-----------------|
| \|Cp err\| peak at x/c 0.10-0.25 | **~0.61** | **0.064** |
| \|Cp err\| at suction peak (x/c~0.016) | (not isolated) | 0.146 |
| upper-surface mean \|Cp err\| | (large) | 0.066 |
| lower-surface mean \|Cp err\| | - | 0.030 |

**The suction-side discrepancy collapsed ~10x (0.61 -> 0.064) in the same
region.** Section 10.4 attributed that error to the fully-turbulent
kOmegaSST boundary layer smearing the suction peak. That was wrong - the
bulk of it was the geometry bug (section 11): a wrong airfoil shape produces
a wholesale-wrong pressure distribution vs the correct-shape reference. With
the geometry/mesh fixed, only a small, genuine turbulence-model effect
remains: OpenFOAM still under-predicts the suction peak by ~0.05-0.15 Cp
(largest right at the LE), consistent with a fully-turbulent BL mildly
smearing the peak - but ~10x smaller than section 10.4 claimed. The
pressure (lower) surface matches the reference to ~0.03 mean.

**Revises section 10.4's headline caution.** 10.4 argued the pipeline's
camber-vs-lift conclusions are a "probable underestimate" and "the real
benefit of camber is likely larger than what this pipeline will report,"
because it believed the turbulence model was under-resolving the (camber-
driven) suction peak by up to 0.61. The true turbulence-model bias is ~10x
smaller, so that caution is largely retracted: the camber conclusions are far
more trustworthy than 10.4 feared. 10.4's *direction* still holds (fully-
turbulent RANS does mildly under-predict the suction peak, and more camber =
stronger peak = more smearing), but the *magnitude* it feared was almost
entirely the geometry bug, not the physics model. The NACA4412 Cp check
(stronger camber) is the remaining test of the residual, now-small effect.

Plot: results/NACA2412_Cp_alpha4_corrected.png. Script: compare_naca2412_cp.py
(committed - reconstructs the surface-Cp comparison capability, which the
section-10.4-era version was an ephemeral scratch script and had been lost).

---

## 13. XFOIL Cl/Cd validation and an HONEST correction to the
## "consistent offset" claim (2026-08-10)

Written before the NACA4412 result is in, deliberately - this is the record
of where confidence actually stands, not a story told after the answer is
known.

### 13.1 The premature conclusion

Ran the full Cl/Cd polar validation of the corrected-mesh, 6000-iter
NACA0012 and NACA2412 sweeps against the XFOIL Re=2e5 Ncrit=9 references
(compare_naca0012.py, compare_naca2412.py). Summary metrics over the
reliable range:

| airfoil | mean \|Cl err\| | mean \|Cd err\| |
|---------|-----------------|-----------------|
| NACA0012 | 0.134 | 0.011 |
| NACA2412 | 0.153 | 0.015 |

Cd agrees well (OpenFOAM slightly high, expected from the fully-turbulent
BL). The Cl error is a systematic deficit - OpenFOAM sits below XFOIL - and
on the strength of the two mean values being close (0.134 vs 0.153) I
concluded the offset was "systematic and consistent across airfoils, so the
relative camber comparison is trustworthy because the bias cancels."

**That conclusion was premature.** It rested on mean \|Cl error\| alone and
never checked the actual per-angle *shape* of the offset. Two means being in
the same ballpark says nothing about whether the offset tracks together as a
function of alpha.

### 13.2 What the per-angle ΔCl(α) overlay actually shows

Computed ΔCl(α) = Cl_XFOIL(α) - Cl_OpenFOAM(α) at every matching angle for
both airfoils and overlaid them directly
(results/deltaCl_overlay_0012_2412.png). The two curves do NOT overlay
closely - the similar means are coincidental, averaging over compensating
divergences:

| alpha range | behavior | gap (2412 - 0012) |
|-------------|----------|-------------------|
| -4 to +1    | track closely (both rise from ~-0.13 through 0) | within +-0.05 |
| 2 to 6      | NACA0012 deficit LARGER (0012 ~0.11-0.14, 2412 ~0.05) | up to -0.09 at a=3 |
| 6.5 to 7    | NACA2412 steps up sharply (0.055 -> 0.22), crosses above | - |
| 7 to 9      | NACA2412 deficit LARGER | up to +0.10 at a=7 |
| 9.5 to 11.5 | reconverge, both ~0.18-0.21 | +-0.03 |
| 12 to 13+   | NACA2412 diverges upward steeply (0.20->0.27->0.39) toward its own stall; 0012 turns down | growing, +0.10 at a=13 |

**Largest divergence: +0.104 at alpha=7**, and it is not random - it
coincides with the confirmed real alpha=6/7 NACA2412 Cl-dip feature
(section 12.4: converged, reproducible). OpenFOAM captures a genuine flow
event there that XFOIL does not show the same way, so the local deficit
jumps. The other structured divergence is approaching each airfoil's own
stall, where the two codes differ in stall onset.

So the offset is a real alpha-AND-camber-dependent function, not a flat
systematic bias. 0012's deficit dominates at low-moderate alpha; 2412's
dominates at 7-9 and again near stall.

### 13.3 Honest current confidence level

- **Qualitative camber conclusion (higher CLmax and delayed stall with
  camber): likely still directionally valid.** The offset is often smaller
  than the camber-driven Cl differences, and the curves do track in the
  -4..1 and 9.5..11.5 bands.
- **Precise quantitative magnitudes (exact CLmax deltas, exact stall-angle
  deltas between airfoils): NOT yet certified.** Some portion of a measured
  camber-to-camber Cl difference could be turbulence-model artifact rather
  than pure camber effect, because the offset itself varies with camber and
  does not cleanly cancel.

### 13.4 Pending resolution: the three-way overlay

The deciding test is the same ΔCl(α) overlay extended to NACA4412 (4%
camber), once its sweep and XFOIL validation are done:

- If NACA4412's ΔCl(α) lands as an ORDERED third curve (monotonically spaced
  relative to 0012 and 2412), the offset is a characterizable - if not flat -
  camber-dependent correction, and quantitative camber claims can be made
  with a stated correction/uncertainty.
- If NACA4412 BREAKS the ordering (lands out of sequence), that is evidence
  the offset is not reliably correctable, and the paper should either heavily
  caveat precise quantitative claims or report the qualitative trend as the
  finding instead of exact deltas.

This is the actual evidence the relative-camber comparison should be
certified (or rejected) on - not the fact that two mean-error numbers were in
the same ballpark. Supporting plot: results/deltaCl_overlay_0012_2412.png.

---

## 14. NACA4412: full sweep, alpha=0 divergence fix, near-stall diagnostic,
## and the three-way certification test (2026-08-13)

### 14.1 alpha=0 divergence (see also commit 3a840f1)

NACA4412 alpha=0 diverged to a NON-physical "converged" state - turbulence
field unstable early (k bounded to ~10,845), garbage forces (Cl~1888) with
misleadingly clean residuals (~1e-4), no solver crash. Diagnosed as a
numerical/turbulence instability, NOT a setup degeneracy (BC/IC structurally
identical to alpha=+-0.5; (V,0,0) is a valid axial vector; 0/k byte-identical).
Fixed with conservative relaxation (U/p/k/omega 0.2/0.15/0.2/0.2): zero
k-bounding, converged. 12000-iter final Cl=0.5672 (mild under-convergence at
6000). CSV row carries a provenance note.

Three flagger-robustness fixes in core/results_extractor.py so one bad point
can't cascade-corrupt flags: (1) single-point-anomaly quarantine pre-pass,
(2) stale-auto-note clearing, (3) Criterion A only fires when the post-drop
recovery stays BELOW the pre-drop peak (a dip recovering to a higher CLmax is
a benign feature, not stall). Verified no regression on NACA0012/2412.

### 14.2 Near-stall diagnostic (12000 iters at alpha=4,5,16,17,18)

- **alpha=4, 5: CONVERGED** (Cl=0.939, 0.744; last-25% span ~0; reproduce the
  6000-iter sweep to 3-4 decimals). The **alpha=4->5 dip is REAL**, not
  under-convergence - the NACA4412 analog of NACA2412's confirmed alpha=6/7
  dip. Camber moves the feature EARLIER and makes it BIGGER: 0012 none, 2412
  dips at 6/7, 4412 dips at 4/5 more strongly. The Criterion-A fix correctly
  treats it as benign, not stall.
- **alpha=16: oscillating onset** (span 0.027, not settled - sweep value 1.013
  was a mid-swing snapshot).
- **alpha=17, 18: no steady solution** (Cl span 0.116/0.131 in the last
  quarter; pressure residual spikes to 2e-3 / 1.6e-2 synced with the swings -
  the confirmed breakdown signature).

**NACA4412 validated range: alpha = -4 to 15, breakdown at alpha >= 16**
(flagged no-steady-solution-unsteady-separation). Breakdown ordering across
the series: **0012 at 14, 2412 and 4412 both at 16** - camber delays breakdown,
but 4412's extra camber does NOT push it past 2412's. (CLmax still orders
cleanly: 0.907 < 1.071 < 1.156.)

Because the Criterion-A fix stops the auto-flagger from firing on the benign
alpha=4/5 dip, the flagger also no longer catches NACA4412's GRADUAL post-stall
decline (no single >0.5 drop, no Cd<0) - so alpha>=16 was flagged MANUALLY from
this diagnostic, same as the near-stall angles for the other two airfoils.

### 14.3 Three-way ΔCl(α) certification: BROKEN ORDERING

Extended the section-13 ΔCl(α) overlay to all three airfoils to test whether
the turbulence-model offset scales cleanly with camber (section 13.4's
pre-registered decision test). Reference is NeuralFoil for ALL three
(consistent source - airfoiltools XFOIL for 4412 was unreachable; the
NeuralFoil-based 0012-vs-2412 curves reproduce section-13's real-XFOIL
conclusion, confirming NeuralFoil is a faithful stand-in). Plot:
results/deltaCl_overlay_threeway.png.

**Verdict: the offset does NOT order cleanly by camber - it lands in the
BROKEN-ORDERING branch.** The mean offset does rise with camber (0012 0.103,
2412 0.124, 4412 0.139), but the per-angle ordering 0012<=2412<=4412 holds at
only 6 of 22 angles, and the curves cross repeatedly:
- alpha=-4..4: NACA4412 is the LOWEST curve, going NEGATIVE (OpenFOAM
  OVER-predicts 4412's lift vs reference) - more camber -> smaller deficit,
  the reverse of the expected direction.
- alpha=5..9: flips to the "expected" 0012<2412<4412, but only because each
  airfoil's dip spikes its own curve at a different angle (4412 at 5, 2412 at 7).
- alpha=10..12: all three bunch and cross.
- alpha=13..15: 0012 turns down toward its earlier stall while 2412/4412 climb
  together toward theirs.

The structure is dominated by each airfoil's OWN dip angle and OWN
stall-approach angle, not a smooth camber scaling.

**Implication for the paper:** the turbulence-model offset is NOT a reliably
correctable, camber-scaled quantity, so precise quantitative camber-deltas
("4% camber adds exactly X to CLmax") must NOT be claimed. The QUALITATIVE
camber trends ARE robust and reportable: CLmax orders cleanly
(0.907 < 1.071 < 1.156), camber raises peak lift and shifts the zero-lift angle
negative, and camber delays breakdown (14 -> 16). Correcting for the offset
would only RAISE the true values while preserving these orderings, so the
qualitative conclusions stand; the exact magnitudes do not.

Caveat stated plainly: the alpha<4 reversal for 4412 uses NeuralFoil
(validated against real XFOIL for 2412, not independently at 4% camber), so
that specific sign-flip could partly reflect the surrogate - but the overall
broken-ordering conclusion does not depend on that region (the crossings and
dip-driven structure carry it).


## 15. Post-processing close-out: definitions, methods, and traceability
## (2026-08-13)

Final study post-processing before the report. All quantities below are computed
from the VALIDATED polar ONLY. "Validated" = every row in
results/airfoil_results.csv whose `note` is NOT one of
{post-stall-unreliable, diverged-unreliable, no-steady-solution-unsteady-separation}.
Provenance notes are KEPT and treated as validated data (they mark corrected/
re-run points, not bad points):
- naca2412 alpha=15: "corrected: 12000-iter converged" (6000-iter sweep read 0.830).
- naca4412 alpha=0: "conservative-relaxation 12000-iter converged" (default 6000-iter
  run diverged to a non-physical state, Cl~1888).
Validated ranges: 0012 alpha=-4..13, 2412 alpha=-4..15, 4412 alpha=-4..15.

Scripts (in scratchpad, run via WSL): aero_postproc.py (parts 1-4),
part5_extract.py (part 5), compile_summary.py (compiled outputs).

### 15.1 alpha_stall (distinct from "breakdown angle")
Definition requested: the first angle at which CL drops by more than 2% from
CL,max, i.e. the first alpha > alpha(CLmax) where CL < 0.98*CL,max. CL,max is the
max CL over the validated polar (argmax). If the 0.98*CL,max crossing lands
between two sampled angles, alpha_stall is LINEARLY INTERPOLATED between them and
the bracketing sampled pair is reported. Results (all bracketed by sampled [12,13]):
0012 = 12.81, 2412 = 12.86, 4412 = 12.28.

This is a SEPARATE quantity from the "breakdown angle" (the angle at which the
steady RANS solution ceases to exist / points get flagged
no-steady-solution-unsteady-separation or post-stall-unreliable). Breakdown =
first flagged/excluded angle above alpha(CLmax): 0012 = 14, 2412 = 16, 4412 = 16.
Both are reported in the summary table. alpha_stall (~12.3-12.9) sits below
breakdown (14-16) for every airfoil, as expected (the 2%-lift-loss onset precedes
full loss of a steady solution).

### 15.2 CD and Cm at target CL (0.6 and 1.0)
CD, Cm, and alpha are interpolated at CL=0.6 and CL=1.0 by LINEAR interpolation
along the ASCENDING (pre-CL,max) branch of the polar only (slice 0..argmax(CL),
so the CL->quantity map is monotonic/single-valued). If a target CL lies outside
the ascending-branch CL range it is reported "not reached" and NOT extrapolated.
NACA0012 (CL,max=0.907) never reaches CL=1.0 -> reported "not reached". Cm here is
Cm about the quarter chord (forceCoeffs CofR = (0.25 0 0)), i.e. Cm,c/4. L/D at
target = CL_target / CD_interp.

### 15.3 max L/D
max over the validated polar of CL/CD, with the alpha at which it occurs:
0012 = 23.00 @ 9.0 deg, 2412 = 26.25 @ 8.5 deg, 4412 = 27.93 @ 4.0 deg. See the
NACA4412 caveat in 15.6.

### 15.4 Cm,c/4 at alpha_stall
Cm interpolated (np.interp over the full validated alpha,Cm arrays) at the
interpolated alpha_stall: 0012 = 0.0467, 2412 = 0.0110, 4412 = -0.0274. Cm at
CL=0.6 and CL=1.0 are in 15.2 / summary table 2.

### 15.5 Skin friction Cf and separation point vs alpha
Angles: representative set alpha = 0,4,8,10,11,12,13 per airfoil (pre-stall
through alpha_stall). Case mapping matches the validated CSV value: base
6000-iter case naca<af>_ap<N>_0, EXCEPT naca4412 alpha=0 -> naca4412_ap0_0_crelax
(the base 6000-iter run is the non-physical one; crelax @ t=12000 is the
validated solution).

Method:
- wallShearStress computed on the existing converged fields with
  `simpleFoam -postProcess -func wallShearStress -latestTime` (the plain
  `postProcess` utility FAILS with "Unable to find turbulence model in the
  database" - the solver's -postProcess mode is required so the kOmegaSST model
  is constructed to give nuEff).
- The airfoil wall patch is named after the airfoil (naca0012/naca2412/naca4412),
  nFaces=354. Wall-shear vectors are read from the patch boundaryField
  (nonuniform List<vector>, 354 entries) in patch-face order; face centres are
  computed from constant/polyMesh (points + faces, mean of each face's vertices).
- Cf_x = tau_x / (0.5 * V^2), V = 2.4751 m/s. wallShearStress is kinematic for the
  incompressible solver (already divided by rho), consistent with the kinematic
  pressure used for Cp, so no rho factor is applied.
- Upper surface = faces with y > camber-line y_c(x) (for the symmetric 0012,
  y_c=0 so upper = y>0). Faces sorted LE->TE by x.
- SIGN CONVENTION (determined empirically, not assumed): on the upper surface
  ATTACHED flow gives Cf_x < 0 and REVERSED/separated flow gives Cf_x > 0.
  Verified on alpha=4 (Cf_x<0 everywhere aft of the LE = attached) vs alpha=13
  (Cf_x flips to >0 at x/c~0.40 and stays positive to ~0.98 = large TE
  separation).
- Separation onset x/c = the first SUSTAINED negative->positive zero-crossing,
  searched in x/c in [0.05, 0.99] (front 5% excluded to avoid LE-stagnation sign
  complexity; last 1% excluded to avoid TE-closure numerical noise). "Sustained"
  = the region downstream of the candidate crossing is >=50% positive, which
  rejects isolated single-face blips. Crossing x/c is linearly interpolated. If no
  sustained crossing exists, the surface is reported "attached".

Outputs: results/separation_vs_alpha.csv (airfoil, alpha, x_c_separation,
status) and results/cf_profiles_<af>.csv (full upper-surface Cf_x(x/c) per angle,
raw traceable data).

### 15.6 Cross-checks against the established trends (consistency audit)
Everything is consistent with the previously established results; the two items
worth flagging are nuances of definition, NOT contradictions:

Consistent:
- CL,max orders cleanly with camber: 0.907 < 1.071 < 1.156 (matches section 14).
- Breakdown 14/16/16 (matches sections 9-14).
- max L/D rises monotonically with camber: 23.00 < 26.25 < 27.93.
- Cm,c/4 at fixed CL becomes more nose-down with camber (CL=0.6:
  +0.012 / -0.057 / -0.129); 0012 ~0 as expected for a symmetric section.
- Separation moves forward monotonically with alpha on all three airfoils, and at
  any fixed pre-stall alpha it moves forward with camber (x/c_sep orders
  0012 > 2412 > 4412). This is the same physics as the cambered dip / earlier
  stall-onset seen earlier: heavier upper-surface loading -> stronger adverse
  gradient -> earlier separation. The crelax 4412 alpha=0 gives an attached,
  physical Cf (-0.0152, matching 0012/2412 at alpha=0) - an independent
  confirmation that the alpha=0 correction is sound.

Flagged nuances (call out in the report so they are not misread):
1. alpha_stall (2%-drop def) is NOT monotonic with camber: 12.81 / 12.86 / 12.28.
   NACA4412 has the EARLIEST alpha_stall despite the highest CL,max, because its
   CL,max peaks earliest (alpha=11 vs 12 for the others) and it then declines
   gradually, so it crosses the 0.98*CL,max threshold at a slightly lower alpha.
   This is an artifact of the metric's sensitivity to peak location + post-peak
   slope, not a real "stalls first" ordering - the breakdown angle (16) is the
   same as 2412 and later than 0012.
2. NACA4412 max L/D occurs at alpha=4.0, far below 0012/2412 (~9/8.5). This is
   because alpha=4 sits right at the top of the alpha=4->5 dip (the real,
   12000-iter-confirmed feature from section 14). 4412's L/D has TWO nearly-tied
   local maxima - alpha=4 (27.93) and alpha~8 (~27.6) - separated by the dip
   valley; the global max just happens to be the pre-dip one. Report the number
   but note it is dip-influenced and essentially tied with the alpha~8 peak.
3. At alpha=13 the separation-x/c camber ordering scrambles (0012=0.404,
   4412=0.451, 2412=0.484) because 13 deg is post-CL,max for all three but each is
   a different amount past its own peak (0012 stalls more abruptly once it goes).
   The clean camber ordering of separation holds pre-stall (alpha<=12); near/past
   stall it is not expected to.
