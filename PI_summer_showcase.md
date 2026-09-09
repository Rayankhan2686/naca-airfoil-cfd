# Summer 2026 Research Summary — Effect of Airfoil Camber on Aerodynamic Performance

**Rayan Khan — Low-Reynolds-Number Aerodynamics Lab, Rutgers University**

---

## Scope of Work

Completed a full computational aerodynamics study of camber effects across three NACA airfoils — NACA 0012 (0% camber), NACA 2412 (2% camber), and NACA 4412 (4% camber) — all at fixed 12% thickness and Re = 2×10⁵, using steady RANS CFD (OpenFOAM, k-ω SST). Every airfoil was swept across its full angle-of-attack range, with near-stall regions independently re-verified at higher iteration counts, and every result was validated directly against real XFOIL reference polars.

---

## Results

### Lift, Stall, and Breakdown

| Airfoil | Camber | CL,max | α(CL,max) | Breakdown α | Max L/D |
|---|---|---|---|---|---|
| NACA 0012 | 0% | 0.907 | 12° | 14° | 23.00 |
| NACA 2412 | 2% | 1.071 | 12° | 16° | 26.25 |
| NACA 4412 | 4% | 1.156 | 11° | 16° | 27.93 |

- Maximum lift increases 27% from 0012 to 4412.
- Camber delays breakdown onset (14°→16°), though the delay does not increase further between 2% and 4% camber.
- Both cambered airfoils show a real, reproducible pre-stall lift-curve dip (2412 at α=6–7°, 4412 at α=4–5°, larger and earlier with more camber) — independently confirmed at 2× the standard iteration count, not a convergence artifact.

### Drag and Moment at Representative Operating Lift

| Airfoil | CD @ CL=0.6 | Cm(c/4) @ 0.6 | CD @ CL=1.0 | Cm(c/4) @ 1.0 |
|---|---|---|---|---|
| NACA 0012 | 0.02944 | +0.0117 | not reached | — |
| NACA 2412 | 0.02841 | −0.0570 | 0.03981 | +0.0006 |
| NACA 4412 | 0.02947 | −0.1288 | 0.03620 | −0.0488 |

Pitching moment becomes more nose-down with camber at fixed operating lift, as expected.

### Separation Behavior

Tracked separation onset (upper-surface skin-friction sign change) as a function of angle of attack for all three airfoils. At a fixed pre-stall angle, separation moves further forward with increasing camber (e.g., at α=12°: 0012 separates at x/c=0.655, 2412 at 0.612, 4412 at 0.546) — direct confirmation of the predicted camber-separation relationship.

### Validation

Every airfoil's polar was cross-checked directly against real XFOIL at the same Reynolds number — including running a local XFOIL build for NACA 4412 (the one airfoil without a precomputed reference available), reproducing reference polars to within <0.01 CL / <0.0004 CD. A camber-scaling check on the CFD-vs-XFOIL offset confirmed the qualitative camber trends above are robust and reportable with confidence.

---

## Key Figures

(All included in `results/report_figures/` — recommend pulling these directly into the walkthrough)

- Lift curves, all three airfoils overlaid (`lift_curve_camber_CL_vs_alpha.png`)
- Drag polars, ascending branch (`drag_polar_camber_CD_vs_CL.png`)
- Per-airfoil validation dashboards vs. XFOIL (`NACA0012_vs_reference.png`, `NACA2412_vs_reference.png`, `NACA4412_vs_reference.png`)
- Surface pressure (Cp) comparisons vs. XFOIL (`NACA2412_Cp_alpha4_corrected.png`, `NACA4412_Cp_alpha4.png`)
- Three-way turbulence-offset certification overlay (`deltaCl_overlay_threeway.png`)

---

## Status

All three airfoils complete and fully validated. Draft technical report in progress; flow visualizations of separation behavior in progress. Manuscript in preparation for AIAA SciTech 2027.
