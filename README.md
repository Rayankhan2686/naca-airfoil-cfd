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
