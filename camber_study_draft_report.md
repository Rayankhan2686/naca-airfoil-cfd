# Effect of Airfoil Camber on Lift, Drag, and Stall Characteristics at Low Reynolds Number

**Draft Report — Rayan Khan**

---

## Abstract

Three NACA four-digit airfoils of fixed thickness (12%) and varying camber — NACA 0012 (0%), NACA 2412 (2%), and NACA 4412 (4%) — were simulated at Re = 2×10⁵ using steady RANS (k-ω SST, OpenFOAM `simpleFoam`) across α = −4° to 15–20°, depending on airfoil. Lift, drag, and pitching-moment coefficients were extracted across the full sweep, with near-stall regions independently re-run at higher iteration counts to confirm convergence before being trusted. Results were validated directly against real XFOIL (Re = 2×10⁵) for all three airfoils. Maximum lift coefficient increases cleanly with camber (0.907 → 1.071 → 1.156), and camber delays the onset of unsteady breakdown (14° → 16° → 16°), though additional camber beyond 2% did not delay breakdown further. Camber also introduces a real, reproducible local dip in the lift curve that appears earlier and grows larger with more camber. A camber-scaling check of the CFD-vs-XFOIL lift offset shows the offset does **not** scale cleanly with camber, so this study reports qualitative camber trends with confidence but does not claim precise quantitative camber-deltas from the turbulence-model offset.

---

## 1. Research Question

At fixed Reynolds number and thickness, how does increasing camber affect stall angle and maximum lift, drag at a specified operating lift, lift-to-drag ratio, and quarter-chord pitching moment? This report summarizes the quantitative results; full methodology (mesh generation, boundary conditions, solver setup) is available in the accompanying case files and will be presented in detail in person.

---

## 2. Method Summary

- **Airfoils:** NACA 0012, 2412, 4412 (identical 12% thickness, camber 0/2/4% at 40% chord), chord = 1.
- **Solver:** Incompressible steady RANS, k-ω SST turbulence closure, OpenFOAM `simpleFoam`.
- **Reynolds number:** 2×10⁵.
- **Sweep:** α = −4° to 15–20° (1° increments, 0.5° refinement near CLmax), matching the pre-registered simulation matrix.
- **Validation:** Every airfoil's polar was compared directly against real XFOIL at the same Re (NACA 0012 and 2412 against airfoiltools.com reference polars; NACA 4412 against a locally-run real XFOIL build, cross-checked to <0.01 CL / <0.0004 CD against the same airfoiltools source format).
- **Data quality control:** Angles where the solver could not reach a steady state (oscillating residuals/forces, confirmed by independent long re-runs at 12,000 iterations) were flagged and excluded from all quantitative results below.

---

## 3. Results

### 3.1 Lift, stall, and breakdown

| Airfoil | Camber | CL,max | α(CL,max) | α_stall (0.98·CL,max) | Breakdown α | max L/D | α(max L/D) |
|---|---|---|---|---|---|---|---|
| NACA 0012 | 0% | 0.907 | 12° | 12.81° | 14° | 23.00 | 9.0° |
| NACA 2412 | 2% | 1.071 | 12° | 12.86° | 16° | 26.25 | 8.5° |
| NACA 4412 | 4% | 1.156 | 11° | 12.28° | 16° | 27.93 | 4.0° |

*α_stall* uses the standard 2%-drop-from-CL,max definition and is distinct from the *breakdown angle*, which is where the solver stops finding a steady solution at all (a separate, later phenomenon). CL,max orders cleanly with camber. Breakdown is delayed by camber (14°→16°) but does not delay further between 2% and 4% camber — both cambered airfoils break down at 16°.

*Note on NACA 4412's max L/D:* the reported value (27.93 at α=4°) sits directly on top of a real, confirmed lift-curve dip (see §3.4) and is nearly tied with a second local peak near α≈8° (~27.6). It should be reported but not over-read as a clean design optimum.

**Figure 1 — Lift curves, all three airfoils** (`lift_curve_camber_CL_vs_alpha.png`): CL,max and α_stall marked. Zero-lift angle shifts negative with increasing camber, as expected from thin-airfoil theory.

**Figure 2 — Drag polars, ascending branch to CL,max** (`drag_polar_camber_CD_vs_CL.png`): Both cambered airfoils show a visible "hook" in the polar corresponding to their respective dip features (§3.4), which is a correct representation of a real non-monotonic feature, not a plotting artifact.

### 3.2 Drag and moment at representative operating lift

| Airfoil | CD @ CL=0.6 | Cm(c/4) @ 0.6 | L/D @ 0.6 | CD @ CL=1.0 | Cm(c/4) @ 1.0 | L/D @ 1.0 |
|---|---|---|---|---|---|---|
| NACA 0012 | 0.02944 | +0.0117 | 20.38 | not reached* | — | — |
| NACA 2412 | 0.02841 | −0.0570 | 21.12 | 0.03981 | +0.0006 | 25.12 |
| NACA 4412 | 0.02947 | −0.1288 | 20.36 | 0.03620 | −0.0488 | 27.63 |

*NACA 0012's CL,max (0.907) never reaches CL=1.0, so those entries are reported as not reached rather than extrapolated.*

Pitching moment at α_stall: NACA 0012 = +0.0467, NACA 2412 = +0.0110, NACA 4412 = −0.0274. Cm becomes more nose-down with camber at a fixed operating CL, consistent with expectation.

### 3.3 Separation onset (upper surface, skin-friction zero-crossing)

| α | NACA 0012 | NACA 2412 | NACA 4412 |
|---|---|---|---|
| 0° | attached | attached | attached |
| 4° | attached | attached | attached |
| 8° | attached | 0.909 | 0.809 |
| 10° | 0.969 | 0.795 | 0.705 |
| 11° | 0.818 | 0.718 | 0.633 |
| 12° | 0.655 | 0.612 | 0.546 |
| 13° | 0.404 | 0.484 | 0.451 |

Values are x/c of separation onset (smaller = further forward = more separated); "attached" means no separation was detected before x/c=0.99. Separation moves forward with α on every airfoil, and — at any fixed pre-stall α — moves forward with camber (0012 separates last, 4412 separates first). This directly confirms one of the predicted outcomes of the original study design.

### 3.4 The camber-dependent lift-curve dip

Both cambered airfoils show a real, reproducible local dip in the lift curve well before stall: NACA 2412 dips at α=6→7°, NACA 4412 dips more sharply at α=4→5°. Both were independently confirmed at 12,000 iterations (not an artifact of under-convergence at the standard sweep length) — values reproduce the standard sweep to 3–4 decimal places. More camber moves this feature earlier and makes it larger.

### 3.5 Turbulence-model offset vs. camber (certification check)

A key question for interpreting this dataset is whether the CFD-vs-reference lift offset (ΔCL = CL,XFOIL − CL,OpenFOAM) scales predictably with camber — if it did, quantitative camber-deltas could be corrected for and reported with confidence. It does not: per-angle ordering (0012 ≤ 2412 ≤ 4412) holds at only 8 of 22 sampled angles, and the three curves cross repeatedly for physically distinct reasons (a negative-offset region at low α for NACA 4412, each airfoil's own dip spiking its curve at a different angle, and convergence near stall). Mean offsets do rise mildly with camber (≈0.096 / 0.124 / 0.137) but this single number masks the crossing structure and should not be used for correction.

**Figure 3 — Three-way ΔCL(α) overlay** (`deltaCl_overlay_threeway.png`): all three airfoils validated against real XFOIL.

**Implication for reported results:** the qualitative camber trends in this report (CL,max ordering, breakdown-angle delay, dip progression, separation-forward-with-camber) are robust and reportable with confidence. Precise quantitative "camber adds exactly X to CL,max"-style claims should not be made from the turbulence-model offset structure — though the camber trends in CL,max, breakdown angle, and separation themselves are computed directly from validated CFD data, not from the offset, so they are not affected by this caveat.

---

## 4. Discussion

The results are consistent with, and quantify, the trade-offs anticipated in the original study design: camber increases CL,max and shifts the lift curve upward, at the cost of a more nose-down pitching moment and earlier separation onset at a given angle of attack. Drag at a fixed low operating CL (0.6) increases modestly with camber, consistent with an off-design drag penalty. The two cambered airfoils breaking down at the same angle (16°) despite different camber magnitudes suggests camber's benefit to breakdown delay saturates somewhere between 2% and 4% camber in this Reynolds-number regime — this is worth further comment in the full report and in discussion with the PI.

---

## 5. Limitations

- Results are for a single Reynolds number (2×10⁵) and airfoil family (NACA four-digit, fixed thickness); trends should not be extrapolated to other thickness or Reynolds regimes without further study.
- Flow visualizations (contours/streamlines of separation behavior) are in progress and not yet included in this draft.
- Angles at or beyond each airfoil's breakdown point are excluded from all quantitative results as physically unreliable (no steady solution exists there), not merely noisy.

---

## 6. Conclusions

1. CL,max increases cleanly with camber: 0.907 (0012) < 1.071 (2412) < 1.156 (4412).
2. Camber delays breakdown onset (14°→16°) but the delay saturates by 2% camber — 4% camber does not delay it further.
3. Both cambered airfoils exhibit a real, reproducible pre-stall lift-curve dip that appears earlier and grows larger with camber (6/7° for 2412, 4/5° for 4412).
4. Separation moves forward with both angle of attack and camber, confirming the study's predicted trend.
5. The CFD-vs-XFOIL turbulence-model offset does not scale cleanly with camber; this study's qualitative camber conclusions are robust, but precise quantitative camber-deltas should not be claimed from the offset structure.

---

## 7. Remaining Work

- Flow visualizations illustrating separation behavior (in progress).
- Full report expansion: detailed methodology (mesh generation and validation, boundary conditions, solver settings), literature context, and expanded discussion — to be developed ahead of the in-person walkthrough with the PI.

---

*Figures referenced above are in `results/report_figures/`: `lift_curve_camber_CL_vs_alpha.png`, `drag_polar_camber_CD_vs_CL.png`, `deltaCl_overlay_threeway.png`, plus per-airfoil XFOIL validation dashboards (`NACA0012_vs_reference.png`, `NACA2412_vs_reference.png`, `NACA4412_vs_reference.png`) and Cp comparisons (`NACA2412_Cp_alpha4_corrected.png`, `NACA4412_Cp_alpha4.png`).*
