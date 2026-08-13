# NACA camber study — post-processing summary

Re = 2×10⁵, simpleFoam (steady RANS) + k-ω SST. All quantities computed from the **validated** polar only (points flagged `post-stall-unreliable`, `diverged-unreliable`, or `no-steady-solution-unsteady-separation` are excluded). Definitions in `debug_notes.md` §15.

## 1. Lift, stall, breakdown, max L/D

| Airfoil | Camber | CLmax | α(CLmax)° | α_stall (0.98·CLmax)° | bracket | Breakdown α° | max L/D | α(max L/D)° |
|---|---|---|---|---|---|---|---|---|
| NACA0012 | 0% | 0.9066 | 12 | 12.81 | [12,13] | 14 | 23.00 | 9.0 |
| NACA2412 | 2% | 1.0707 | 12 | 12.86 | [12,13] | 16 | 26.25 | 8.5 |
| NACA4412 | 4% | 1.1563 | 11 | 12.28 | [12,13] | 16 | 27.93 | 4.0 |

α_stall is interpolated inside the listed sampled bracket (CL crosses 0.98·CLmax between those two sampled angles).

## 2. Drag / moment at target lift (interpolated on the ascending branch)

| Airfoil | CD@CL=0.6 | α@0.6° | Cm(c/4)@0.6 | L/D@0.6 | CD@CL=1.0 | α@1.0° | Cm(c/4)@1.0 | L/D@1.0 |
|---|---|---|---|---|---|---|---|---|
| NACA0012 | 0.02944 | 6.23 | 0.0117 | 20.38 | not reached | — | — | — |
| NACA2412 | 0.02841 | 3.36 | -0.0570 | 21.12 | 0.03981 | 10.30 | 0.0006 | 25.12 |
| NACA4412 | 0.02947 | 0.40 | -0.1288 | 20.36 | 0.03620 | 7.98 | -0.0488 | 27.63 |

NACA0012's CLmax (0.907) never reaches CL=1.0, so its CL=1.0 entries are reported as not reached rather than extrapolated.

## 3. Pitching moment Cm,c/4 at α_stall

| Airfoil | α_stall° | Cm(c/4) @ α_stall |
|---|---|---|
| NACA0012 | 12.81 | 0.0467 |
| NACA2412 | 12.86 | 0.0110 |
| NACA4412 | 12.28 | -0.0274 |

(Cm at CL=0.6 and CL=1.0 are in table 2.)

## 4. Separation onset x/c vs α (upper surface, Cf_x zero-crossing)

Skin friction Cf_x = τ_x /(½V²) from `wallShearStress`; separation = first sustained sign change (attached Cf_x<0 → reversed Cf_x>0) aft of x/c=0.05. "attached" = no crossing before x/c=0.99.

| α° | NACA0012 | NACA2412 | NACA4412 |
|---|---|---|---|
| 0 | attached | attached | attached |
| 4 | attached | attached | attached |
| 8 | attached | 0.909 | 0.809 |
| 10 | 0.969 | 0.795 | 0.705 |
| 11 | 0.818 | 0.718 | 0.633 |
| 12 | 0.655 | 0.612 | 0.546 |
| 13 | 0.404 | 0.484 | 0.451 |

Values are x/c of separation onset (smaller = further forward = more separated). Separation moves forward with α on every airfoil, and — at any fixed α — moves forward with camber (0012 > 2412 > 4412).

