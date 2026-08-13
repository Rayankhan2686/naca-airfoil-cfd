# Report figures — NACA camber study (Re = 2×10⁵)

One place collecting every analysis **plot** produced for the study. These are
**copies** — each original remains in its pipeline location (nothing was moved or
renamed). Flow visualizations (ParaView pressure/velocity renders, the
`naca0012_photos/` set) are handled separately and are **not** included here.

All coefficient plots use **validated data only** — points flagged
`post-stall-unreliable`, `diverged-unreliable`, or
`no-steady-solution-unsteady-separation` are excluded.

## Primary deliverables (new this pass)

| File | What it shows | Plotted data | Original |
|---|---|---|---|
| `lift_curve_camber_CL_vs_alpha.png` | CL vs α, all three airfoils overlaid; ★ = CLmax, ✖ = α_stall (first CL < 0.98·CLmax). Values boxed top-left. | `../lift_curve_data.csv` | (this file's location) |
| `drag_polar_camber_CD_vs_CL.png` | Drag polar CL vs CD, ascending branch to CLmax only (no post-stall points); ★ = CLmax. | `../drag_polar_data.csv` | (this file's location) |

## Validation vs real XFOIL (Re=2×10⁵, Ncrit=9)

The three `*_vs_reference.png` dashboards share one 4-panel dark-themed style
(CL–α, CD–α, ΔCl bars, drag polar); the two `*_Cp_alpha4*.png` plots are the
chordwise Cp comparison at α=4°. XFOIL reference = airfoiltools
`xf-naca<af>-il-200000` polars (real XFOIL), cross-checked for 4412 against a
locally run XFOIL 6.99 (agreement <0.01 Cl). 4412 Cp uses that local XFOIL run.

| File | What it shows | Original location |
|---|---|---|
| `NACA0012_vs_reference.png` | 4-panel validation vs XFOIL, NACA0012. | `OpenFOAM/results/` |
| `NACA2412_vs_reference.png` | 4-panel validation vs XFOIL, NACA2412. | `OpenFOAM/results/` |
| `NACA4412_vs_reference.png` | 4-panel validation vs XFOIL, NACA4412; breakdown α≥16° flagged red. **(new)** | `OpenFOAM/results/` |
| `NACA2412_Cp_alpha4_corrected.png` | Cp(x/c) NACA2412 α=4°: OpenFOAM vs NeuralFoil/XFOIL. | `scripts/results/` |
| `NACA4412_Cp_alpha4.png` | Cp(x/c) NACA4412 α=4°: OpenFOAM vs **real XFOIL 6.99**. **(new)** | `scripts/results/` |

## Turbulence-offset certification overlays

| File | What it shows | Original location |
|---|---|---|
| `deltaCl_overlay_threeway.png` | ΔCl (**XFOIL** − OpenFOAM) vs α, all three airfoils — three-way certification, **real XFOIL** (debug_notes §16, supersedes the NeuralFoil §14 version). Data: `deltaCl_overlay_threeway_data.csv`. | `scripts/results/` |
| `deltaCl_overlay_threeway_data.csv` | Underlying ΔCl values for the plot above. | `scripts/results/` |
| `deltaCl_overlay_0012_2412.png` | Two-way ΔCl overlay (0012 vs 2412), §13 precursor. Not regenerated this pass (0012/2412 out of scope). | `scripts/results/` |

## Deliberately excluded

- `OpenFOAM/results/NACA0012_analysis.png` — dated 2026-06-18, **before** the
  Aug-3 airfoil-geometry fix, so it is built on superseded data. Left out to
  avoid a stale figure in the report set.
- All flow-visualization renders/screenshots (handled separately).

Definitions/methods for every quantity: `../camber_study_summary.md`,
`debug_notes.md §15` (post-processing) and `§16` (real-XFOIL 4412 validation).
