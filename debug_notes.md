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
