# NACA Airfoil Aerodynamic Study

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![OpenFOAM](https://img.shields.io/badge/OpenFOAM-2412-informational?style=flat-square&logo=openfoam&logoColor=white)
![Solver](https://img.shields.io/badge/Solver-simpleFoam-blue?style=flat-square)
![Turbulence](https://img.shields.io/badge/Turbulence-kOmegaSST-blueviolet?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20WSL2-lightgrey?style=flat-square)

> Automated CFD pipeline for computing aerodynamic coefficients (C_L, C_D, C_M) for NACA 4-digit airfoils at low Reynolds number using OpenFOAM 2412.

---

## Overview

This project provides a fully automated, menu-driven CFD pipeline for studying the effect of camber on **NACA 0012**, **NACA 2412**, and **NACA 4412** airfoil performance at **Re = 2 × 10⁵** — a regime representative of small UAVs and micro wind-turbine blades.

The pipeline handles everything from geometry generation to post-processing:

```
NACA profile equations
        ↓
  Watertight STL (cosine spacing, fan-triangulated caps)
        ↓
  OpenFOAM case (blockMesh + snappyHexMesh + kOmegaSST)
        ↓
  simpleFoam steady-state RANS
        ↓
  Cl / Cd / Cm  →  results/airfoil_results.csv
        ↓
  ParaView visualisation
```

Results support an ongoing research paper investigating camber effects on low-Reynolds-number airfoil performance across the attached-flow regime (−5° ≤ α ≤ 10°).

---

## Screenshots

### Interactive Terminal Menu
```
============================================================
  OpenFOAM NACA Airfoil Research  |  Re = 2×10⁵
============================================================

  A) FOAM Airfoil Research
  B) Exit

--- FOAM Airfoil Research ---
    1) Generate STL
    2) Run single simulation
    3) Run angle sweep  (-5° to +10° default)
    4) View results
    5) Visualize in ParaView
    0) Back
```

### Sample Results Table
```
  Airfoil      Alpha         Cl            Cd            Cm
  -------------------------------------------------------
  naca0012      0.00         0.0012        0.0142       -0.0001
  naca0012      5.00         0.5731        0.0163       -0.0021
  naca0012     10.00         1.0842        0.0241       -0.0038
  naca2412      5.00         0.7204        0.0171       -0.0524
  naca4412      5.00         0.8916        0.0189       -0.1073
```

### Meshing Pipeline (snappyHexMesh)
The mesh is built on a background block (−20 ≤ x ≤ 30, −10 ≤ y ≤ 10, 100 × 80 × 1 cells) with snappyHexMesh surface refinement at levels 4–6 conforming to the airfoil wall.

---

## Requirements

| Dependency | Version | Purpose |
|---|---|---|
| OpenFOAM | 2412 (ESI) | Meshing and flow solver |
| Python | 3.10+ | Pipeline automation |
| ParaView | any recent | Flow-field visualisation (optional) |

No third-party Python packages are required — the pipeline uses only the standard library.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/sleepyheadron2686/naca-airfoil-cfd.git ~/OpenFOAM/scripts
cd ~/OpenFOAM/scripts

# 2. Verify OpenFOAM is accessible
source /usr/lib/openfoam/openfoam2412/etc/bashrc
simpleFoam --version

# 3. (Optional) Install ParaView for flow-field visualisation
sudo apt install paraview
```

---

## How to Run

```bash
cd ~/OpenFOAM/scripts
python3 foam_research.py
```

At the top-level prompt select **A** to enter the airfoil research menu.

---

## Menu Options

### 1 — Generate STL
Produces a watertight extruded ASCII STL (`stl/NACA<xxxx>.stl`) using cosine-spaced profile points, fan-triangulated end caps, and outward-facing normals. Span = 0.1 m. Supports NACA 0012, 2412, and 4412.

### 2 — Run Single Simulation
Prompts for airfoil selection and angle of attack α, then executes the full pipeline:

```
surfaceFeatureExtract  →  blockMesh  →  snappyHexMesh  →  simpleFoam
```

Case files are written to `cases/<airfoil>_a<alpha>/`. Per-step logs are saved to `cases/.../logs/`. On completion, C_L, C_D, and C_M are extracted from `postProcessing/forceCoeffs/` and appended to the results CSV.

### 3 — Run Angle Sweep
Iterates **Run Single Simulation** over a user-specified α range. Defaults: **−5° to +10°** at **1° steps** (all adjustable). Results accumulate in `results/airfoil_results.csv` after each angle so a partial sweep is never lost.

### 4 — View Results
Loads `results/airfoil_results.csv` and prints a formatted C_L / C_D / C_M table. Optionally displays an L/D ratio column. Results can be filtered by airfoil.

### 5 — Visualize in ParaView
Lists all meshed case directories, writes an empty `case.foam` trigger file (always overwritten), and launches ParaView.

> **WSL / Windows note:** Requires Windows 11 with WSLg, or an X server such as VcXsrv on Windows 10. With VcXsrv: `export DISPLAY=:0` before running.

---

## Fixed Physics Parameters

All simulations use the following locked values (Re = 2 × 10⁵, chord = 1 m, air at 20 °C):

| Parameter | Symbol | Value | Units |
|---|---|---|---|
| Reynolds number | Re | 2 × 10⁵ | — |
| Freestream velocity | V | 2.4751 | m/s |
| Density | ρ | 1.225 | kg/m³ |
| Dynamic viscosity | μ | 1.516 × 10⁻⁵ | Pa·s |
| Kinematic viscosity | ν | 1.2375 × 10⁻⁵ | m²/s |
| Chord length | c | 1.0 | m |
| Span | — | 0.1 | m |
| Reference area | A_ref | 0.1 | m² |
| Turbulent kinetic energy | k∞ | 2.297 × 10⁻⁴ | m²/s² |
| Specific dissipation rate | ω∞ | 3.95 | s⁻¹ |

---

## Numerical Setup

| Setting | Value |
|---|---|
| Solver | `simpleFoam` (steady RANS) |
| Turbulence model | `kOmegaSST` |
| End time | 3000 iterations |
| Write interval | 500 |
| Background mesh | 100 × 80 × 1 cells, x ∈ [−20, 30], y ∈ [−10, 10] |
| Surface refinement levels | 4–6 |
| Pressure–velocity coupling | SIMPLE with consistent formulation |
| Gradient scheme | `cellLimited Gauss linear 1` |
| Divergence (U) | `bounded Gauss linearUpwindV` |
| Top / bottom boundaries | `symmetry` |
| Front / back boundaries | `empty` (2-D) |
| Inlet / outlet | `freestream` |

---

## Project Structure

```
~/OpenFOAM/scripts/
├── foam_research.py          # Entry point — interactive menu
├── core/
│   ├── __init__.py
│   ├── ui.py                 # Coloured ANSI terminal UI
│   ├── stl_generator.py      # NACA 4-digit watertight STL generator
│   ├── case_builder.py       # Writes all OpenFOAM dictionaries
│   ├── mesh_runner.py        # Orchestrates the mesh + solve pipeline
│   └── results_extractor.py  # Parses coefficient.dat, manages CSV database
├── stl/                      # Generated STL geometry files
├── results/
│   └── airfoil_results.csv   # Accumulated Cl/Cd/Cm database
├── cases/                    # Case run directories (git-ignored, large files)
├── .gitignore
└── README.md
```

---

## Results Format

Coefficients are accumulated in `results/airfoil_results.csv`. Each row represents one converged steady-state solution:

```csv
airfoil,alpha,Cl,Cd,Cm
naca0012,0.0,0.0012,0.0142,-0.0001
naca0012,5.0,0.5731,0.0163,-0.0021
naca2412,5.0,0.7204,0.0171,-0.0524
naca4412,5.0,0.8916,0.0189,-0.1073
```

| Column | Type | Description |
|---|---|---|
| `airfoil` | string | `naca0012`, `naca2412`, or `naca4412` |
| `alpha` | float | Angle of attack (degrees) |
| `Cl` | float | Lift coefficient |
| `Cd` | float | Drag coefficient |
| `Cm` | float | Pitching-moment coefficient about the quarter-chord (c/4) |

---

## Research Context

This pipeline supports a research paper investigating **camber effects on NACA 4-digit airfoil aerodynamics at Re = 2 × 10⁵**. The three profiles form a controlled study:

| Profile | Max camber | Max camber location |
|---|---|---|
| NACA 0012 | 0 % | — (symmetric) |
| NACA 2412 | 2 % chord | 40 % chord |
| NACA 4412 | 4 % chord | 40 % chord |

The attached-flow sweep (−5° ≤ α ≤ 10°) targets the pre-stall regime where RANS with kOmegaSST is known to give reliable integral force predictions. The resulting lift polars, drag polars, and moment curves provide a quantitative basis for camber selection in low-speed UAV and wind-energy applications.

---

## License

MIT © 2026 — see `LICENSE` for details.
