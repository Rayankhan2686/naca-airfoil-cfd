# NACA Airfoil Aerodynamic Study

Automated CFD pipeline for computing lift (Cl), drag (Cd), and pitching-moment (Cm) coefficients for **NACA 0012**, **NACA 2412**, and **NACA 4412** airfoils at **Re = 2 × 10⁵** using OpenFOAM 2412 with the `simpleFoam` solver and `kOmegaSST` turbulence model.

Results support an ongoing research paper investigating the effect of camber on low-Reynolds-number airfoil performance.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| OpenFOAM | 2412 (ESI) | Installed at `/usr/lib/openfoam/openfoam2412/` |
| Python | 3.10+ | For type-hint syntax used throughout |
| ParaView | any recent | Optional — for flow-field visualisation |

No third-party Python packages are required. The pipeline uses only the standard library.

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url> ~/OpenFOAM/scripts
cd ~/OpenFOAM/scripts

# 2. Verify OpenFOAM is accessible
source /usr/lib/openfoam/openfoam2412/etc/bashrc
simpleFoam --version

# 3. (Optional) Install ParaView for visualisation
sudo apt install paraview
```

---

## How to Run

```bash
cd ~/OpenFOAM/scripts
python3 foam_research.py
```

At the top-level prompt choose **A** for the airfoil research menu.

---

## Menu Options

```
A) FOAM Airfoil Research
   1) Generate STL          — build a watertight ASCII STL for the chosen airfoil
   2) Run single simulation — mesh + solve one airfoil / angle-of-attack combination
   3) Run angle sweep       — sweep α from −5° to +10° (1° step, adjustable)
   4) View results          — print Cl/Cd/Cm table from the results CSV
   5) Visualize in ParaView — open a completed case in ParaView
   0) Back
B) Exit
```

### Generate STL
Produces a watertight extruded ASCII STL (`stl/NACA<xxxx>.stl`) using cosine-spaced profile points, fan-triangulated end caps, and outward-facing normals.  Span = 0.1 m.

### Run Single Simulation
Prompts for airfoil and α, then runs the full pipeline:

```
surfaceFeatureExtract → blockMesh → snappyHexMesh → simpleFoam
```

Case files are written to `cases/<airfoil>_a<alpha>/`.  Logs land in `cases/.../logs/`.

### Run Angle Sweep
Loops `Run Single Simulation` over a user-specified α range.  Defaults: −5° to +10°, step 1°.  Results are appended to `results/airfoil_results.csv` after each angle.

### View Results
Loads `results/airfoil_results.csv` and prints a formatted table.  Optionally prints an L/D ratio column.

### Visualize in ParaView
Lists all meshed case directories, writes an empty `case.foam` trigger file, and launches ParaView.  Requires WSLg (Windows 11) or an X server (VcXsrv) on Windows 10.

---

## Fixed Physics Parameters

All simulations use the following locked values (Re = 2 × 10⁵, chord = 1 m):

| Parameter | Symbol | Value | Units |
|---|---|---|---|
| Reynolds number | Re | 2 × 10⁵ | — |
| Freestream velocity | V | 2.4751 | m/s |
| Density | ρ | 1.225 | kg/m³ |
| Dynamic viscosity | μ | 1.516 × 10⁻⁵ | Pa·s |
| Kinematic viscosity | ν | 1.2375 × 10⁻⁵ | m²/s |
| Chord length | c | 1.0 | m |
| Span | — | 0.1 | m |
| Reference area | Aref | 0.1 | m² |
| Turbulent kinetic energy | k∞ | 2.297 × 10⁻⁴ | m²/s² |
| Specific dissipation rate | ω∞ | 3.95 | 1/s |

---

## Project Structure

```
~/OpenFOAM/scripts/
├── foam_research.py          # Entry point — interactive menu
├── core/
│   ├── __init__.py
│   ├── ui.py                 # Coloured terminal UI helpers
│   ├── stl_generator.py      # NACA 4-digit STL generator
│   ├── case_builder.py       # Writes all OpenFOAM dictionaries
│   ├── mesh_runner.py        # Runs the surfaceFeatureExtract→simpleFoam pipeline
│   └── results_extractor.py  # Reads coefficient.dat, manages results CSV
├── stl/                      # Generated STL files (committed)
├── results/
│   └── airfoil_results.csv   # Accumulated Cl/Cd/Cm database (committed)
├── cases/                    # Case directories — excluded from git (large files)
├── .gitignore
└── README.md
```

---

## Results Format

Coefficients are accumulated in `results/airfoil_results.csv`:

```
airfoil,alpha,Cl,Cd,Cm
naca0012,0.0,0.0012,0.0142,-0.0001
naca0012,5.0,0.5731,0.0163,-0.0021
naca2412,5.0,0.7204,0.0171,-0.0524
...
```

| Column | Description |
|---|---|
| `airfoil` | `naca0012`, `naca2412`, or `naca4412` |
| `alpha` | Angle of attack in degrees |
| `Cl` | Lift coefficient |
| `Cd` | Drag coefficient |
| `Cm` | Pitching-moment coefficient (about c/4) |

---

## Research Context

This tool supports a research paper studying the influence of camber on NACA 4-digit airfoil performance at low Reynolds numbers (Re = 2 × 10⁵), representative of small UAV and wind-turbine blade operating conditions.  The three profiles span zero camber (0012), moderate camber (2412), and high camber (4412), enabling a controlled comparison of lift slope, stall angle, and drag polar across the attached-flow regime (−5° ≤ α ≤ 10°).
