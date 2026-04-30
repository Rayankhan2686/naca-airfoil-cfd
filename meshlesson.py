#!/usr/bin/env python3
"""
meshlesson.py — Standalone interactive blockMesh learning tool for OpenFOAM.

Five guided lessons teaching mesh generation from scratch.
Completely independent from foam_research.py and custommesh.py.
Shares no files, configs, or imports with either program.

Launch:  meshlesson  (alias in ~/.bashrc)
      or  python3 ~/OpenFOAM/scripts/meshlesson.py
"""

import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths  (entirely separate from research and custom pipelines)
# ---------------------------------------------------------------------------
LESSONS_DIR = Path.home() / "OpenFOAM" / "results" / "lessons"
TEST_CASE   = Path.home() / "OpenFOAM" / "run" / "meshlesson_test"
FOAM_BASHRC = "/usr/lib/openfoam/openfoam2412/etc/bashrc"

# ---------------------------------------------------------------------------
# Inline ANSI colours  (no imports from core/ui.py)
# ---------------------------------------------------------------------------
_G   = "\033[92m"   # green
_C   = "\033[96m"   # cyan
_Y   = "\033[93m"   # yellow
_R   = "\033[91m"   # red
_B   = "\033[1m"    # bold
_M   = "\033[95m"   # magenta  — used for blockMeshDict code lines
_DIM = "\033[2m"    # dim
_RS  = "\033[0m"    # reset

_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RS}" if _USE_COLOR else text


def _header(title: str):
    bar = "=" * 68
    print(f"\n{_c(_B + _C, bar)}")
    print(_c(_B + _C, f"  {title}"))
    print(_c(_B + _C, bar))


def _lesson_banner(n: int, title: str):
    bar = "-" * 68
    print(f"\n{_c(_B + _G, bar)}")
    print(_c(_B + _G, f"  Lesson {n}: {title}"))
    print(_c(_B + _G, bar))


def _section(title: str):
    print(f"\n  {_c(_B + _Y, '>>  ' + title)}")
    print(f"  {_c(_DIM, '-' * 60)}")


def _explain(text: str):
    lines = text.strip().splitlines()
    print()
    for line in lines:
        print(f"  {_c(_C, '|')}  {line}")
    print()


def _code_line(line: str, comment: str = ""):
    if comment:
        pad = max(0, 54 - len(line))
        print(f"    {_c(_M, line)}{' ' * pad}  {_c(_Y, '// ' + comment)}")
    else:
        print(f"    {_c(_M, line)}")


def _warn(msg: str):
    print(f"\n  {_c(_Y, '[!]')} {_c(_Y, msg)}")


def _ok(msg: str):
    print(f"\n  {_c(_G, '[OK]')} {msg}")


def _err(msg: str):
    print(f"\n  {_c(_R, '[ERROR]')} {msg}")


def _pause():
    input(f"\n  {_c(_C, 'Press Enter to continue...')}")


def _ask_float(prompt: str, default: float) -> float:
    while True:
        raw = input(f"  {_c(_C, prompt + f'  [{default:g}]')}: ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            _warn("Enter a valid number.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"  {_c(_C, prompt + f'  [{default}]')}: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            _warn("Enter a valid integer.")


# ---------------------------------------------------------------------------
# blockMeshDict / controlDict generation
# ---------------------------------------------------------------------------

def _foam_header(obj: str) -> str:
    return (
        f"FoamFile\n"
        f"{{\n"
        f"    version     2.0;\n"
        f"    format      ascii;\n"
        f"    class       dictionary;\n"
        f"    object      {obj};\n"
        f"}}\n"
        f"// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n"
    )


def _make_blockmesh(
    x0: float, x1: float,
    y0: float, y1: float,
    z0: float, z1: float,
    nx: int, ny: int, nz: int,
    gx: float = 1.0, gy: float = 1.0, gz: float = 1.0,
) -> str:
    return (
        _foam_header("blockMeshDict") + "\n"
        f"scale   1;\n\n"
        f"vertices\n(\n"
        f"    ( {x0:9.4f}  {y0:9.4f}  {z0:.4f} )   // vertex 0  bottom-left-front\n"
        f"    ( {x1:9.4f}  {y0:9.4f}  {z0:.4f} )   // vertex 1  bottom-right-front\n"
        f"    ( {x1:9.4f}  {y1:9.4f}  {z0:.4f} )   // vertex 2  top-right-front\n"
        f"    ( {x0:9.4f}  {y1:9.4f}  {z0:.4f} )   // vertex 3  top-left-front\n"
        f"    ( {x0:9.4f}  {y0:9.4f}  {z1:.4f} )   // vertex 4  bottom-left-back\n"
        f"    ( {x1:9.4f}  {y0:9.4f}  {z1:.4f} )   // vertex 5  bottom-right-back\n"
        f"    ( {x1:9.4f}  {y1:9.4f}  {z1:.4f} )   // vertex 6  top-right-back\n"
        f"    ( {x0:9.4f}  {y1:9.4f}  {z1:.4f} )   // vertex 7  top-left-back\n"
        f");\n\n"
        f"blocks\n(\n"
        f"    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading ({gx:g} {gy:g} {gz:g})\n"
        f");\n\n"
        f"boundary\n(\n"
        f"    inlet\n"
        f"    {{\n"
        f"        type patch;\n"
        f"        faces ( (0 4 7 3) );\n"
        f"    }}\n"
        f"    outlet\n"
        f"    {{\n"
        f"        type patch;\n"
        f"        faces ( (1 2 6 5) );\n"
        f"    }}\n"
        f"    top\n"
        f"    {{\n"
        f"        type symmetry;\n"
        f"        faces ( (3 7 6 2) );\n"
        f"    }}\n"
        f"    bottom\n"
        f"    {{\n"
        f"        type symmetry;\n"
        f"        faces ( (0 1 5 4) );\n"
        f"    }}\n"
        f"    front\n"
        f"    {{\n"
        f"        type empty;\n"
        f"        faces ( (0 3 2 1) );\n"
        f"    }}\n"
        f"    back\n"
        f"    {{\n"
        f"        type empty;\n"
        f"        faces ( (4 5 6 7) );\n"
        f"    }}\n"
        f");\n"
    )


_CONTROL_DICT_CONTENT = (
    _foam_header("controlDict") + "\n"
    "application     checkMesh;\n"
    "startFrom       startTime;\n"
    "startTime       0;\n"
    "stopAt          endTime;\n"
    "endTime         1;\n"
    "deltaT          1;\n"
    "writeControl    timeStep;\n"
    "writeInterval   1;\n"
)


# ---------------------------------------------------------------------------
# Lesson 1 — Build a simple rectangle domain from scratch
# ---------------------------------------------------------------------------

def lesson_1():
    _lesson_banner(1, "Build a Simple Rectangle Domain From Scratch")

    _explain(
        "In OpenFOAM, every CFD simulation starts with a mesh — a grid that\n"
        "divides the fluid domain into small cells. The simplest mesh tool\n"
        "is blockMesh. It builds rectangular blocks made of hexahedral cells\n"
        "(hex cells — 6 faces, 8 vertices, just like a shoebox).\n"
        "\n"
        "In this lesson you will define a rectangular domain step by step,\n"
        "and we will build the blockMeshDict together, explaining every line."
    )
    _pause()

    # --- Domain extents ---
    _section("Step 1: Domain Extents (Vertices)")
    _explain(
        "A blockMesh domain needs 8 corner points called VERTICES.\n"
        "Think of them as the 8 corners of a 3D box.\n"
        "\n"
        "We label them 0 through 7:\n"
        "  Vertices 0-3 sit on the FRONT face (z = 0)\n"
        "  Vertices 4-7 sit on the BACK  face (z = span)\n"
        "\n"
        "You will now define the x and y extents of your domain.\n"
        "For a typical airfoil study: x from -20 to 30, y from -10 to 10."
    )

    x0 = _ask_float("Left edge x0  (inlet, e.g. -20.0)", -20.0)
    _explain(
        f"x0 = {x0:g}. This is the INLET — where freestream flow enters the domain.\n"
        f"We put it {abs(x0):g} chord lengths upstream so the velocity profile\n"
        f"is uniform before it reaches the airfoil. Too close means the inlet\n"
        f"boundary condition will distort the flow around the airfoil."
    )

    x1 = _ask_float("Right edge x1 (outlet, e.g. 30.0)", 30.0)
    _explain(
        f"x1 = {x1:g}. This is the OUTLET — where the flow exits the domain.\n"
        f"Airfoil wakes extend many chord lengths downstream. With only {x1:g}\n"
        f"chord lengths, if the outlet is too close, pressure disturbances\n"
        f"from the wake reflect off the outlet boundary and corrupt drag values."
    )

    y0 = _ask_float("Bottom edge y0 (e.g. -10.0)", -10.0)
    _explain(
        f"y0 = {y0:g}. The bottom farfield boundary.\n"
        f"Placing it {abs(y0):g} chord lengths from the airfoil prevents BLOCKAGE:\n"
        f"if the walls are too close, the flow has to accelerate around the airfoil\n"
        f"more than it would in free air, making lift and drag look higher than real."
    )

    y1 = _ask_float("Top edge y1    (e.g. 10.0)", 10.0)
    _explain(
        f"y1 = {y1:g}. The top farfield boundary — same blockage reasoning.\n"
        f"Total domain height: {y1 - y0:g} chord lengths."
    )

    span = _ask_float("Span (Z thickness, e.g. 0.1 for 2D)", 0.1)
    z0, z1 = 0.0, span
    _explain(
        f"span = {span:g} m. OpenFOAM is always 3D, even for '2D' problems.\n"
        f"We use just ONE cell thick in Z (span = {span:g} m), and set the front\n"
        f"and back faces to type 'empty'. This tells the solver: do not solve\n"
        f"any equations in the Z direction. Effectively it becomes 2D RANS."
    )

    # Validation
    if x1 <= x0:
        _warn("x1 must be greater than x0. Domain has no width.")
    if y1 <= y0:
        _warn("y1 must be greater than y0. Domain has no height.")
    if abs(x0) < 5:
        _warn(f"Inlet only {abs(x0):g} chord lengths upstream — boundary effects likely.")
    if x1 < 5:
        _warn(f"Outlet only {x1:g} chord lengths downstream — wake not captured.")
    if min(abs(y0), y1) < 5:
        _warn("Top/bottom closer than 5 chords — blockage effect will inflate lift/drag.")

    _pause()

    # --- Vertex layout ---
    _section("Step 2: The Vertex Numbering Rule")
    _explain(
        "OpenFOAM REQUIRES a specific vertex ordering for hex blocks.\n"
        "This is the correct layout — you must follow it exactly:\n"
        "\n"
        "  Front face (z=0):              Back face (z=span):\n"
        "\n"
        "  3 ----------- 2               7 ----------- 6\n"
        "  |             |               |             |\n"
        "  |  (y+ = top) |               |             |\n"
        "  |             |               |             |\n"
        "  0 ----------- 1               4 ----------- 5\n"
        "\n"
        "  Vertex 0 = (x0, y0, z0)   bottom-left-front\n"
        "  Vertex 1 = (x1, y0, z0)   bottom-right-front\n"
        "  Vertex 2 = (x1, y1, z0)   top-right-front\n"
        "  Vertex 3 = (x0, y1, z0)   top-left-front\n"
        "  Vertex 4 = (x0, y0, z1)   bottom-left-back\n"
        "  Vertex 5 = (x1, y0, z1)   bottom-right-back\n"
        "  Vertex 6 = (x1, y1, z1)   top-right-back\n"
        "  Vertex 7 = (x0, y1, z1)   top-left-back\n"
        "\n"
        "Rule: vertices 0-1-2-3 go COUNTER-CLOCKWISE on the front face.\n"
        "      Vertices 4-7 mirror them on the back face."
    )

    print()
    _code_line("vertices")
    _code_line("(")
    _code_line(f"    ( {x0:8.2f}  {y0:8.2f}  {z0:.2f} )", "vertex 0 — bottom-left-front (inlet-bottom)")
    _code_line(f"    ( {x1:8.2f}  {y0:8.2f}  {z0:.2f} )", "vertex 1 — bottom-right-front (outlet-bottom)")
    _code_line(f"    ( {x1:8.2f}  {y1:8.2f}  {z0:.2f} )", "vertex 2 — top-right-front (outlet-top)")
    _code_line(f"    ( {x0:8.2f}  {y1:8.2f}  {z0:.2f} )", "vertex 3 — top-left-front (inlet-top)")
    _code_line(f"    ( {x0:8.2f}  {y0:8.2f}  {z1:.2f} )", "vertex 4 — bottom-left-back")
    _code_line(f"    ( {x1:8.2f}  {y0:8.2f}  {z1:.2f} )", "vertex 5 — bottom-right-back")
    _code_line(f"    ( {x1:8.2f}  {y1:8.2f}  {z1:.2f} )", "vertex 6 — top-right-back")
    _code_line(f"    ( {x0:8.2f}  {y1:8.2f}  {z1:.2f} )", "vertex 7 — top-left-back")
    _code_line(");")
    _pause()

    # --- Cell counts ---
    _section("Step 3: Cell Count (blocks)")
    _explain(
        "The 'blocks' section tells blockMesh how many cells to create\n"
        "in each direction inside the domain.\n"
        "\n"
        "  hex (0 1 2 3 4 5 6 7) (nx ny nz) simpleGrading (gx gy gz)\n"
        "\n"
        "More cells = more accuracy, but slower simulation and more memory.\n"
        "For a 2D airfoil study, 100 x 80 x 1 is a good starting point."
    )

    width  = x1 - x0
    height = y1 - y0

    nx = _ask_int("Cells in X (streamwise direction, e.g. 100)", 100)
    _explain(
        f"nx = {nx} cells across {width:g} m width.\n"
        f"Average cell size in X: {width / nx:.3f} m.\n"
        f"{'Good resolution in the streamwise direction.' if nx >= 60 else 'Consider at least 60 cells in X for reasonable accuracy.'}"
    )
    if nx < 20:
        _warn(f"nx={nx} is very coarse. blockMesh will run but resolution is too poor for real CFD.")
    if nx > 500:
        _warn(f"nx={nx} is very fine — mesh generation will take a long time.")

    ny = _ask_int("Cells in Y (normal to flow, e.g. 80)", 80)
    _explain(
        f"ny = {ny} cells across {height:g} m height.\n"
        f"Average cell size in Y: {height / ny:.3f} m.\n"
        f"Without grading, cells near the airfoil are as large as farfield cells.\n"
        f"Lesson 3 shows how to use grading to put fine cells near the surface."
    )
    if ny < 20:
        _warn(f"ny={ny} is too coarse for boundary layer resolution.")

    nz = _ask_int("Cells in Z (span direction, use 1 for 2D)", 1)
    if nz == 1:
        _explain(
            "nz=1: correct for pseudo-2D RANS. One cell layer, front and back\n"
            "patches set to type 'empty' — no equations solved in Z direction."
        )
    else:
        _explain(
            f"nz={nz}: for a true 3D simulation you would change front/back from\n"
            f"'empty' to a real patch type (e.g. wall or periodic)."
        )

    _pause()

    # --- Grading ---
    _section("Step 4: simpleGrading — Cell Stretching")
    _explain(
        "simpleGrading (gx gy gz) controls how cell sizes vary across the block.\n"
        "\n"
        "The value is the RATIO of the LAST cell size to the FIRST cell size:\n"
        "\n"
        "  gx = 1.0  →  all cells equal size in X\n"
        "  gx = 4.0  →  cells near outlet are 4x larger than cells near inlet\n"
        "  gx = 0.25 →  cells near outlet are 0.25x (smaller) than near inlet\n"
        "\n"
        "For a simple rectangle with no airfoil, use 1 1 1 (uniform).\n"
        "For an airfoil domain you grade Y to put small cells near y=0 (the wall)."
    )

    gx = _ask_float("Grading in X (1 = uniform, 4 = cells grow toward outlet)", 1.0)
    gy = _ask_float("Grading in Y (1 = uniform, 4 = cells grow toward top)", 1.0)
    gz = _ask_float("Grading in Z (use 1 for 2D)", 1.0)

    if any(v <= 0 for v in (gx, gy, gz)):
        _warn("Grading values must be positive. Negative or zero grading is invalid.")
    if max(gx, gy) > 10:
        _warn("Grading > 10 creates very stretched cells — mesh quality will be poor.")

    _explain(
        f"Your grading: ({gx:g} {gy:g} {gz:g})\n"
        f"  In X: last cell is {gx:g}x the size of the first cell\n"
        f"  In Y: last cell is {gy:g}x the size of the first cell\n"
        f"  In Z: last cell is {gz:g}x the size of the first cell"
    )
    _pause()

    # --- Show the full blockMeshDict ---
    _section("Step 5: Complete blockMeshDict — Every Line Explained")

    print()
    _code_line("FoamFile", "Required header — every OpenFOAM input file starts with this")
    _code_line("{")
    _code_line("    version     2.0;",  "OpenFOAM file format version (always 2.0)")
    _code_line("    format      ascii;", "Human-readable text (not binary)")
    _code_line("    class       dictionary;", "This file is a key-value dictionary")
    _code_line("    object      blockMeshDict;", "The filename OpenFOAM looks for")
    _code_line("}")
    print()
    _code_line("scale   1;",  "Multiply ALL coordinates by this. 1 means values are in metres.")
    print()
    _code_line("vertices", "The 8 corners of your domain box")
    _code_line("(")
    _code_line(f"    ( {x0:8.2f}  {y0:8.2f}  {z0:.2f} )", "vertex 0: inlet-bottom-front")
    _code_line(f"    ( {x1:8.2f}  {y0:8.2f}  {z0:.2f} )", "vertex 1: outlet-bottom-front")
    _code_line(f"    ( {x1:8.2f}  {y1:8.2f}  {z0:.2f} )", "vertex 2: outlet-top-front")
    _code_line(f"    ( {x0:8.2f}  {y1:8.2f}  {z0:.2f} )", "vertex 3: inlet-top-front")
    _code_line(f"    ( {x0:8.2f}  {y0:8.2f}  {z1:.2f} )", "vertex 4: inlet-bottom-back")
    _code_line(f"    ( {x1:8.2f}  {y0:8.2f}  {z1:.2f} )", "vertex 5: outlet-bottom-back")
    _code_line(f"    ( {x1:8.2f}  {y1:8.2f}  {z1:.2f} )", "vertex 6: outlet-top-back")
    _code_line(f"    ( {x0:8.2f}  {y1:8.2f}  {z1:.2f} )", "vertex 7: inlet-top-back")
    _code_line(");")
    print()
    _code_line("blocks", "Define the block(s) — we only have one rectangular block here")
    _code_line("(")
    _code_line(
        f"    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading ({gx:g} {gy:g} {gz:g})",
        "hex = hexahedral; 8 vertices in order; cell count; grading"
    )
    _code_line(");")
    print()
    _code_line("boundary",  "Name and type the 6 faces of the box")
    _code_line("(")
    _code_line("    inlet",                    "Left face — flow enters here")
    _code_line("    {")
    _code_line("        type patch;",          "'patch': generic BC; set U and p in the 0/ folder")
    _code_line("        faces ( (0 4 7 3) );", "4 vertices of the left face, outward-normal order")
    _code_line("    }")
    _code_line("    outlet",                   "Right face — flow exits here")
    _code_line("    {")
    _code_line("        type patch;")
    _code_line("        faces ( (1 2 6 5) );", "Right face vertices")
    _code_line("    }")
    _code_line("    top")
    _code_line("    {")
    _code_line("        type symmetry;",       "'symmetry': zero normal gradient; not a solid wall")
    _code_line("        faces ( (3 7 6 2) );", "Top face vertices")
    _code_line("    }")
    _code_line("    bottom")
    _code_line("    {")
    _code_line("        type symmetry;",       "Same as top — farfield, not a wall")
    _code_line("        faces ( (0 1 5 4) );", "Bottom face vertices")
    _code_line("    }")
    _code_line("    front")
    _code_line("    {")
    _code_line("        type empty;",          "'empty': 2D face — solver skips all equations here")
    _code_line("        faces ( (0 3 2 1) );", "Front face at z=0")
    _code_line("    }")
    _code_line("    back")
    _code_line("    {")
    _code_line("        type empty;",          "Same 2D treatment for the back face")
    _code_line("        faces ( (4 5 6 7) );", "Back face at z=span")
    _code_line("    }")
    _code_line(");")

    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    out = LESSONS_DIR / "lesson1_blockMeshDict"
    out.write_text(_make_blockmesh(x0, x1, y0, y1, z0, z1, nx, ny, nz, gx, gy, gz))
    _ok(f"Saved to: {out}")
    _explain(
        f"Domain : x=[{x0:g}, {x1:g}]  y=[{y0:g}, {y1:g}]  z=[{z0:g}, {z1:g}]\n"
        f"Cells  : {nx} x {ny} x {nz} = {nx * ny * nz:,} total\n"
        f"Grading: ({gx:g} {gy:g} {gz:g})"
    )
    _pause()


# ---------------------------------------------------------------------------
# Lesson 2 — Build an airfoil domain from scratch
# ---------------------------------------------------------------------------

def lesson_2():
    _lesson_banner(2, "Build an Airfoil Domain From Scratch")

    _explain(
        "An airfoil CFD domain looks exactly like the rectangle from Lesson 1,\n"
        "but the dimensions are chosen carefully based on the physics:\n"
        "the airfoil CHORD LENGTH (the distance from leading to trailing edge).\n"
        "\n"
        "In the research program the chord = 1.0 m, so 'chord lengths' and\n"
        "'metres' are the same number. We will use Re = 2x10^5.\n"
        "\n"
        "Let's walk through EVERY parameter and understand WHY it has that value."
    )
    _pause()

    _section("Why 20 Chord Lengths Upstream?")
    _explain(
        "Inlet x0 = -20.0  (20 chord lengths upstream)\n"
        "\n"
        "At the inlet we apply a UNIFORM freestream velocity boundary condition:\n"
        "  U = (2.4751, 0, 0) m/s  (for angle of attack = 0 degrees)\n"
        "\n"
        "This is an approximation — in reality flow far from a body IS uniform.\n"
        "But if the inlet is too close to the airfoil, the airfoil's pressure\n"
        "field reaches the inlet and the BC becomes wrong.\n"
        "\n"
        "Rule of thumb: inlet at least 10-20 chord lengths upstream.\n"
        "The research program uses 20 to be safe."
    )
    _pause()

    _section("Why 30 Chord Lengths Downstream?")
    _explain(
        "Outlet x1 = +30.0  (30 chord lengths downstream)\n"
        "\n"
        "At the outlet we apply a ZERO GRADIENT (pressure outlet) condition.\n"
        "This assumes the flow has returned to near-freestream conditions.\n"
        "\n"
        "Airfoil wakes — regions of reduced velocity and turbulence — can\n"
        "persist 10-20+ chord lengths downstream, especially at high angles\n"
        "of attack near stall. If the outlet cuts through the wake, the\n"
        "zero-gradient assumption is violated and Cd is overestimated.\n"
        "\n"
        "The outlet is longer than the inlet (30 vs 20) because the wake\n"
        "travels downstream — there is no upstream wake."
    )
    _pause()

    _section("Why 10 Chord Lengths Top and Bottom?")
    _explain(
        "Top    y1 = +10.0\n"
        "Bottom y0 = -10.0   (10 chord lengths each side)\n"
        "\n"
        "This is the BLOCKAGE RATIO problem. Imagine squeezing a wing in a\n"
        "very narrow wind tunnel — the walls force the air to speed up more\n"
        "than it would in free air. This artificially increases measured lift.\n"
        "\n"
        "Blockage ratio = frontal area / tunnel cross-section\n"
        "  Chord = 1 m, span = 0.1 m\n"
        "  Domain height = 20 m, domain span = 0.1 m\n"
        "  Blockage < 0.5% — acceptable for open-field simulation.\n"
        "\n"
        "We use 'symmetry' patches (not walls) top and bottom so the solver\n"
        "applies zero-normal-gradient rather than a no-slip wall condition."
    )
    _pause()

    _section("The Complete Research-Program blockMeshDict")
    _explain(
        "Here is the actual blockMeshDict used for every NACA simulation.\n"
        "Chord = 1.0 m, span = 0.1 m.\n"
        "Domain: x = [-20, 30]  y = [-10, 10]  z = [0, 0.1]\n"
        "Cells:  100 x 80 x 1 = 8,000 background cells\n"
        "Grading: 1 1 1 (uniform — snappyHexMesh adds refinement near airfoil)"
    )

    print()
    _code_line("scale   1;")
    print()
    _code_line("vertices")
    _code_line("(")
    _code_line("    ( -20.0000   -10.0000   0.0000 )", "vertex 0: inlet-bottom-front")
    _code_line("    (  30.0000   -10.0000   0.0000 )", "vertex 1: outlet-bottom-front")
    _code_line("    (  30.0000    10.0000   0.0000 )", "vertex 2: outlet-top-front")
    _code_line("    ( -20.0000    10.0000   0.0000 )", "vertex 3: inlet-top-front")
    _code_line("    ( -20.0000   -10.0000   0.1000 )", "vertex 4: inlet-bottom-back")
    _code_line("    (  30.0000   -10.0000   0.1000 )", "vertex 5: outlet-bottom-back")
    _code_line("    (  30.0000    10.0000   0.1000 )", "vertex 6: outlet-top-back")
    _code_line("    ( -20.0000    10.0000   0.1000 )", "vertex 7: inlet-top-back")
    _code_line(");")
    print()
    _code_line("blocks")
    _code_line("(")
    _code_line(
        "    hex (0 1 2 3 4 5 6 7) (100 80 1) simpleGrading (1 1 1)",
        "100 streamwise, 80 normal, 1 spanwise — 8000 background cells"
    )
    _code_line(");")
    print()
    _code_line("boundary")
    _code_line("(")
    _code_line("    inlet { type patch;    faces ( (0 4 7 3) ); }",
               "Dirichlet: U=(Uinf*cos(alpha), Uinf*sin(alpha), 0), p=zeroGradient")
    _code_line("    outlet { type patch;   faces ( (1 2 6 5) ); }",
               "Neumann: p=0 (reference), U=zeroGradient")
    _code_line("    top    { type symmetry; faces ( (3 7 6 2) ); }",
               "Symmetry: normal velocity=0, tangential gradient=0")
    _code_line("    bottom { type symmetry; faces ( (0 1 5 4) ); }",
               "Symmetry: same as top")
    _code_line("    front  { type empty;   faces ( (0 3 2 1) ); }",
               "2D: no equations solved in Z direction")
    _code_line("    back   { type empty;   faces ( (4 5 6 7) ); }",
               "2D: same")
    _code_line(");")

    _pause()

    _section("Why blockMesh Then snappyHexMesh?")
    _explain(
        "The blockMesh step ONLY creates the BACKGROUND mesh — a plain rectangle.\n"
        "There is no airfoil shape yet.\n"
        "\n"
        "The airfoil shape is added in the NEXT step: snappyHexMesh.\n"
        "snappyHexMesh reads the background mesh from blockMesh, then:\n"
        "  1. Reads the airfoil surface from an STL file\n"
        "  2. Identifies cells that are inside the airfoil and removes them\n"
        "  3. Snaps the remaining cell faces to the curved airfoil surface\n"
        "  4. Refines cells near the surface to capture boundary layer gradients\n"
        "\n"
        "This is why the background mesh does not need to be fine — snappyHexMesh\n"
        "handles the near-wall refinement. 100x80 gives good far-field resolution\n"
        "without wasting cells where the flow is nearly uniform."
    )

    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    out = LESSONS_DIR / "lesson2_airfoil_blockMeshDict"
    out.write_text(_make_blockmesh(-20, 30, -10, 10, 0, 0.1, 100, 80, 1))
    _ok(f"Research-program blockMeshDict saved to: {out}")
    _pause()


# ---------------------------------------------------------------------------
# Lesson 3 — Understanding mesh grading and cell stretching
# ---------------------------------------------------------------------------

def lesson_3():
    _lesson_banner(3, "Understanding Mesh Grading and Cell Stretching")

    _explain(
        "simpleGrading stretches cells so they are small where you need\n"
        "precision (near the airfoil wall) and large where the flow is\n"
        "smooth (in the farfield). This saves cells without losing accuracy.\n"
        "\n"
        "The grading ratio g is defined as:\n"
        "  g = size of LAST cell / size of FIRST cell\n"
        "\n"
        "g > 1 : cells grow in the positive direction (stretch away from start)\n"
        "g < 1 : cells shrink in the positive direction (compress toward end)\n"
        "g = 1 : all cells equal size (uniform)"
    )
    _pause()

    _section("Example 1: Uniform Grading (1 1 1)")
    _explain(
        "simpleGrading (1 1 1)\n"
        "\n"
        "X direction: 10 cells, all equal width = 5/10 = 0.5 m each\n"
        "Y direction: 6 cells, all equal height = 3/6 = 0.5 m each\n"
        "\n"
        "  |  |  |  |  |  |  |  |  |  |   (X cells)\n"
        "\n"
        "  ----  ----  ----  ----  ----  ----  (Y cells)\n"
        "\n"
        "WHEN TO USE: Simple test cases, no airfoil, or when you just want\n"
        "to check the domain runs. NOT suitable near solid walls."
    )
    _pause()

    _section("Example 2: gx = 4.0 (Cells Grow Toward Outlet)")
    _explain(
        "simpleGrading (4 1 1)\n"
        "\n"
        "X direction: last cell is 4x larger than first cell.\n"
        "If you have 10 cells over 5 m:\n"
        "  First cell ≈ 0.28 m  →  Last cell ≈ 1.12 m\n"
        "\n"
        "  ||| ||  |   |    |     (X cells — small near inlet, large near outlet)\n"
        "\n"
        "WHEN TO USE: When the inlet region matters most — e.g. when you want\n"
        "fine cells near the airfoil leading edge. The wake downstream can\n"
        "tolerate coarser cells because gradients are smaller there."
    )
    _pause()

    _section("Example 3: gx = 0.25 (Cells Shrink Toward Outlet)")
    _explain(
        "simpleGrading (0.25 1 1)\n"
        "\n"
        "X direction: last cell is 0.25x (one-quarter) the size of first cell.\n"
        "Cells grow from outlet toward inlet — fine cells near OUTLET.\n"
        "\n"
        "  |     |    |   |  || ||| (X cells — large near inlet, small near outlet)\n"
        "\n"
        "NOTE: 0.25 = 1/4, so this is the inverse of gx=4.\n"
        "You can achieve the same result with gx=4 if you reverse the block\n"
        "vertex ordering. Both approaches are valid."
    )
    _pause()

    _section("The Real Use Case: Y-Grading for Boundary Layers")
    _explain(
        "In airfoil CFD the most important grading is in Y.\n"
        "\n"
        "The boundary layer — the thin region of retarded flow near the\n"
        "airfoil surface — is typically only 1-5 mm thick at Re=2e5.\n"
        "If your cells near the wall are 0.5 m wide, you will miss the\n"
        "boundary layer completely and predict wrong Cf, wrong Cd, wrong Cl.\n"
        "\n"
        "For the airfoil domain (y from -10 to 10, 80 cells in Y):\n"
        "\n"
        "  gy = 1     → avg cell height = 0.25 m  (misses boundary layer)\n"
        "  gy = 100   → first cell height ≈ 0.003 m, last ≈ 0.3 m\n"
        "               Resolves y+ < 1 near the wall without wasting cells\n"
        "\n"
        "However, the research program uses gy = 1 because snappyHexMesh\n"
        "handles the near-wall refinement directly on the airfoil surface.\n"
        "The background mesh grading only matters for simulations WITHOUT\n"
        "snappyHexMesh (i.e., when you use blockMesh alone with a body-fitted grid)."
    )

    _section("Interactive: Try Your Own Grading")
    _explain(
        "Enter a grading value and we will show what cell distribution\n"
        "you get for a 10-cell block spanning 5 m."
    )

    g = _ask_float("Enter a grading value (e.g. 1, 4, 0.25, 100)", 4.0)
    n = 10
    L = 5.0

    if g <= 0:
        _warn("Grading must be positive.")
        return

    if abs(g - 1.0) < 1e-9:
        sizes = [L / n] * n
    else:
        r = g ** (1.0 / (n - 1))
        s0 = L * (1 - r) / (1 - r ** n)
        sizes = [s0 * (r ** i) for i in range(n)]

    print()
    _explain(
        f"grading = {g:g}  ({n} cells over {L} m)\n"
        f"First cell size: {sizes[0]:.4f} m\n"
        f"Last  cell size: {sizes[-1]:.4f} m\n"
        f"Ratio (actual) : {sizes[-1] / sizes[0]:.3f}"
    )
    bar_max = 40
    scale = bar_max / max(sizes)
    for i, s in enumerate(sizes):
        bar = "#" * max(1, int(s * scale))
        print(f"  cell {i+1:2d}: {_c(_M, bar):<42}  {s:.4f} m")

    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    out = LESSONS_DIR / f"lesson3_grading_g{g:g}.txt"
    lines = [f"grading = {g:g}, {n} cells over {L} m\n"]
    for i, s in enumerate(sizes):
        lines.append(f"cell {i+1:2d}: {s:.6f} m\n")
    out.write_text("".join(lines))
    _ok(f"Cell distribution saved to: {out}")
    _pause()


# ---------------------------------------------------------------------------
# Lesson 4 — Understanding boundary patches
# ---------------------------------------------------------------------------

def lesson_4():
    _lesson_banner(4, "Understanding Boundary Patches")

    _explain(
        "Every face on the outside of your mesh must belong to a named 'patch'.\n"
        "A patch has a NAME and a TYPE.\n"
        "\n"
        "  The NAME is what you use in the 0/ folder files (U, p, k, omega) to\n"
        "  apply boundary conditions. The name must match EXACTLY — case sensitive.\n"
        "\n"
        "  The TYPE tells OpenFOAM what kind of boundary it is geometrically.\n"
        "  It does NOT set the physics — physics comes from the 0/ files.\n"
        "\n"
        "Let's go through each patch used in the airfoil domain."
    )
    _pause()

    _section("Patch: inlet  (type patch)")
    _explain(
        "type patch\n"
        "\n"
        "The most generic boundary type. It just marks a face as an external\n"
        "boundary. The physics are defined entirely by the 0/ files:\n"
        "\n"
        "  0/U:     inletOutlet with inletValue (Uinf * direction vector)\n"
        "  0/p:     zeroGradient (pressure not fixed at inlet)\n"
        "  0/k:     fixedValue (turbulent kinetic energy = 2.297e-4 m2/s2)\n"
        "  0/omega: fixedValue (specific dissipation rate = 3.95 1/s)\n"
        "\n"
        "WHY 'inletOutlet' and not 'fixedValue' for U?\n"
        "If the flow reverses at the inlet (e.g. near stall), fixedValue would\n"
        "inject momentum you didn't want. inletOutlet allows outflow gracefully."
    )
    _pause()

    _section("Patch: outlet  (type patch)")
    _explain(
        "type patch\n"
        "\n"
        "Same geometry type as inlet. Physics in 0/ files:\n"
        "\n"
        "  0/U:     zeroGradient (velocity gradients are zero at outlet)\n"
        "  0/p:     fixedValue = 0 (pressure reference)\n"
        "  0/k:     zeroGradient\n"
        "  0/omega: zeroGradient\n"
        "\n"
        "WHY p=0 at outlet?\n"
        "simpleFoam solves for gauge pressure (p - p_ref). Setting p=0 at\n"
        "outlet defines the reference level. The absolute pressure does not\n"
        "matter for incompressible RANS — only the GRADIENT of p drives flow."
    )
    _pause()

    _section("Patch: top / bottom  (type symmetry)")
    _explain(
        "type symmetry\n"
        "\n"
        "A symmetry patch enforces:\n"
        "  - Zero velocity component NORMAL to the face (flow can't pass through)\n"
        "  - Zero gradient of all variables PARALLEL to the face\n"
        "\n"
        "This is different from 'wall':\n"
        "  wall      → no-slip: ALL velocity components = 0 at face\n"
        "  symmetry  → only normal component = 0; tangential flow is free\n"
        "\n"
        "WHY symmetry at top and bottom, not wall?\n"
        "The top and bottom of the domain are not physical walls — they represent\n"
        "open air far from the airfoil. A wall would create spurious drag.\n"
        "Symmetry mimics a farfield: flow slides along the boundary freely.\n"
        "\n"
        "NOTE: Some setups use 'slip' walls instead of symmetry. Both give\n"
        "similar results, but symmetry is more common for external aerodynamics."
    )
    _pause()

    _section("Patch: front / back  (type empty)")
    _explain(
        "type empty\n"
        "\n"
        "This is OpenFOAM's 2D trick. A 3D mesh has 6 faces, but we want\n"
        "to solve a 2D problem. Setting the two Z-normal faces to 'empty'\n"
        "tells the solver: completely ignore these faces.\n"
        "\n"
        "OpenFOAM will NOT apply any boundary conditions to 'empty' patches.\n"
        "It will NOT solve any equations in the Z direction.\n"
        "The result is mathematically equivalent to a 2D simulation.\n"
        "\n"
        "WHY is the span 0.1 m and not 1 m?\n"
        "It does not matter — with type 'empty', the Z thickness is irrelevant\n"
        "to the solution. We use 0.1 m (matching the chord) so that face areas\n"
        "come out as round numbers when computing force coefficients.\n"
        "Reference area Aref = chord x span = 1.0 x 0.1 = 0.1 m2."
    )
    _pause()

    _section("Patch: airfoil surface  (type wall)")
    _explain(
        "type wall  (added by snappyHexMesh, not blockMesh)\n"
        "\n"
        "After snappyHexMesh snaps the mesh to the airfoil STL, it creates\n"
        "a new patch named 'airfoil' (or whatever you call it in snappyHexMeshDict).\n"
        "\n"
        "type wall applies the correct physics:\n"
        "  0/U:     noSlip  (all velocity components = 0 at the solid surface)\n"
        "  0/p:     zeroGradient (no pressure jump across a solid wall)\n"
        "  0/k:     kqRWallFunction (turbulent kinetic energy wall function)\n"
        "  0/omega: omegaWallFunction (omega wall function)\n"
        "\n"
        "Wall functions are approximations that model the sub-layer of the\n"
        "boundary layer you cannot resolve without extremely fine cells.\n"
        "They allow coarser meshes near walls while still capturing drag\n"
        "reasonably accurately."
    )
    _pause()

    _section("Why Patch Names Must Match EXACTLY")
    _explain(
        "OpenFOAM links patch names in blockMeshDict/snappyHexMeshDict\n"
        "to boundary conditions in the 0/ files by STRING MATCHING.\n"
        "\n"
        "If your blockMeshDict says 'Inlet' but your 0/U file says 'inlet',\n"
        "OpenFOAM will CRASH with:\n"
        "  'Cannot find patchField entry for patch inlet'\n"
        "\n"
        "The research program uses lowercase throughout:\n"
        "  inlet, outlet, top, bottom, front, back, airfoil\n"
        "\n"
        "IMPORTANT: The patch name 'airfoil' in snappyHexMeshDict must EXACTLY\n"
        "match the STL filename (without extension) placed in\n"
        "  constant/triSurface/airfoil.stl\n"
        "Change one and not the other → FOAM FATAL ERROR."
    )
    _pause()


# ---------------------------------------------------------------------------
# Lesson 5 — Run your custom blockMesh and see the result
# ---------------------------------------------------------------------------

def lesson_5():
    _lesson_banner(5, "Run Your Custom blockMesh and See the Result")

    _explain(
        "In this lesson you will build a complete blockMeshDict from scratch,\n"
        "run blockMesh on it, run checkMesh to validate it, and read the results.\n"
        "\n"
        "The test case will be created in:\n"
        f"  {TEST_CASE}\n"
        "\n"
        "This directory is completely isolated from the research and custom\n"
        "mesh cases. It will be overwritten each time you run Lesson 5."
    )
    _pause()

    _section("Build Your Domain")
    print(f"  {_c(_DIM, 'Enter domain parameters. Press Enter to accept defaults.')}\n")

    x0 = _ask_float("Left edge x0  (inlet, e.g. -20)", -20.0)
    x1 = _ask_float("Right edge x1 (outlet, e.g. 30)", 30.0)
    y0 = _ask_float("Bottom y0     (e.g. -10)", -10.0)
    y1 = _ask_float("Top y1        (e.g. 10)", 10.0)
    span = _ask_float("Span (Z, e.g. 0.1)", 0.1)
    z0, z1 = 0.0, span

    # Validate
    errors = []
    if x1 <= x0:
        errors.append("x1 must be > x0")
    if y1 <= y0:
        errors.append("y1 must be > y0")
    if span <= 0:
        errors.append("span must be > 0")
    if errors:
        for e in errors:
            _err(e)
        _warn("Fix the domain extents and try again.")
        return

    if abs(x0) < 3:
        _warn(f"Inlet only {abs(x0):g} chords upstream. blockMesh will run but CFD results would be bad.")
    if x1 < 3:
        _warn(f"Outlet only {x1:g} chords downstream. Wake not captured.")

    nx   = _ask_int("Cells in X", 100)
    ny   = _ask_int("Cells in Y", 80)
    nz   = _ask_int("Cells in Z (1 for 2D)", 1)
    gx   = _ask_float("Grading X", 1.0)
    gy   = _ask_float("Grading Y", 1.0)
    gz   = _ask_float("Grading Z", 1.0)

    if nx < 2 or ny < 2 or nz < 1:
        _err("Cell counts must be at least 2 in X and Y, 1 in Z.")
        return

    total_cells = nx * ny * nz
    _explain(
        f"Domain : x=[{x0:g},{x1:g}]  y=[{y0:g},{y1:g}]  z=[{z0:g},{z1:g}]\n"
        f"Cells  : {nx} x {ny} x {nz} = {total_cells:,} total\n"
        f"Grading: ({gx:g} {gy:g} {gz:g})"
    )

    ans = input(f"\n  {_c(_Y, 'Create case and run blockMesh? [Y/n]')}: ").strip().lower()
    if ans in ("n", "no"):
        _warn("Aborted. No files written.")
        return

    _section("Creating Test Case Directory")
    try:
        import shutil
        if TEST_CASE.exists():
            shutil.rmtree(TEST_CASE)
        (TEST_CASE / "system").mkdir(parents=True)
        (TEST_CASE / "constant").mkdir()
        _ok(f"Created: {TEST_CASE}")
    except Exception as exc:
        _err(f"Could not create case directory: {exc}")
        return

    # Write blockMeshDict
    bmd = _make_blockmesh(x0, x1, y0, y1, z0, z1, nx, ny, nz, gx, gy, gz)
    (TEST_CASE / "system" / "blockMeshDict").write_text(bmd)

    # Write controlDict
    (TEST_CASE / "system" / "controlDict").write_text(_CONTROL_DICT_CONTENT)

    _ok("Wrote system/blockMeshDict")
    _ok("Wrote system/controlDict")
    _pause()

    _section("Running blockMesh")
    log_dir = TEST_CASE / "logs"
    log_dir.mkdir()
    log_path = log_dir / "blockMesh.log"

    bm_cmd = (
        f'set -o pipefail && source "{FOAM_BASHRC}" && '
        f'blockMesh 2>&1 | tee "{log_path}"'
    )
    print(f"\n  Running: blockMesh  →  {log_path}\n")
    bm_result = subprocess.run(["bash", "-c", bm_cmd], cwd=str(TEST_CASE))

    if bm_result.returncode != 0:
        _err("blockMesh failed. Check the log:")
        _err(f"  {log_path}")
        _explain(
            "Common blockMesh failures:\n"
            "  - Vertex ordering wrong (0 1 2 3 4 5 6 7 out of sequence)\n"
            "  - Domain has zero or negative extent (x1 <= x0, etc.)\n"
            "  - Grading value is 0 or negative\n"
            "  - Cell count nz > 1 but span = 0"
        )
        return

    _ok("blockMesh completed successfully.")
    _pause()

    _section("Running checkMesh")
    cm_log = log_dir / "checkMesh.log"
    cm_cmd = (
        f'set -o pipefail && source "{FOAM_BASHRC}" && '
        f'checkMesh 2>&1 | tee "{cm_log}"'
    )
    print(f"\n  Running: checkMesh  →  {cm_log}\n")
    subprocess.run(["bash", "-c", cm_cmd], cwd=str(TEST_CASE))

    _section("Mesh Quality Report")
    _parse_and_print_checkmesh(cm_log)
    _pause()

    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    out = LESSONS_DIR / "lesson5_blockMeshDict"
    out.write_text(bmd)
    _ok(f"blockMeshDict saved to: {out}")
    _ok(f"Full logs in: {log_dir}")


def _parse_and_print_checkmesh(log_path: Path):
    if not log_path.exists():
        _err("checkMesh log not found.")
        return

    text = log_path.read_text()

    def _find(pattern: str) -> str:
        m = re.search(pattern, text, re.I | re.M)
        return m.group(1).strip() if m else "N/A"

    cells    = _find(r'^\s*cells:\s*(\d+)')
    faces    = _find(r'^\s*faces:\s*(\d+)')
    points   = _find(r'^\s*points:\s*(\d+)')
    nonortho = _find(r'[Mm]ax(?:imum)?\s+non-orthogonality\s*[=:]\s*([\d.eE+\-]+)')
    skewness = _find(r'[Mm]ax(?:imum)?\s+skewness\s*[=:]\s*([\d.eE+\-]+)')
    min_vol  = _find(r'[Mm]in(?:imum)?\s+(?:cell\s+)?volume\s*[=:]\s*([\d.eE+\-]+)')
    max_asp  = _find(r'[Mm]ax(?:imum)?\s+(?:cell\s+)?aspect\s+ratio\s*[=:]\s*([\d.eE+\-]+)')
    qual_m   = re.search(r'(PASS|FAIL\s*\(\d+\))', text, re.I)
    quality  = qual_m.group(1).strip() if qual_m else "N/A"

    w = 28
    hdr = f"Metric{'':{w-6}}  Value"
    print()
    print(f"  {_c(_B + _C, hdr)}")
    print(f"  {'-' * (w + 16)}")
    print(f"  {'Total cells':<{w}} {cells}")
    print(f"  {'Total faces':<{w}} {faces}")
    print(f"  {'Total points':<{w}} {points}")

    try:
        no_val = float(nonortho)
        no_str = f"{nonortho}  {'<-- FAIL (>70 degrees)' if no_val > 70 else '<-- OK'}"
        no_color = _R if no_val > 70 else _G
    except ValueError:
        no_str, no_color = nonortho, _RS
    print(f"  {'Max non-orthogonality':<{w}} {_c(no_color, no_str)}")

    try:
        sk_val = float(skewness)
        sk_str = f"{skewness}  {'<-- FAIL (>4)' if sk_val > 4 else '<-- OK'}"
        sk_color = _R if sk_val > 4 else _G
    except ValueError:
        sk_str, sk_color = skewness, _RS
    print(f"  {'Max skewness':<{w}} {_c(sk_color, sk_str)}")

    print(f"  {'Min cell volume':<{w}} {min_vol}")
    print(f"  {'Max aspect ratio':<{w}} {max_asp}")

    if quality.upper().startswith("PASS"):
        print(f"\n  {_c(_B + _G, 'Overall: ' + quality)}")
    elif quality.upper().startswith("FAIL"):
        print(f"\n  {_c(_B + _R, 'Overall: ' + quality)}")
    else:
        print(f"\n  Overall: {quality}")

    print()
    if quality.upper().startswith("PASS"):
        _explain(
            "PASS means all OpenFOAM mesh quality checks are within acceptable limits.\n"
            "This mesh is suitable for running a CFD simulation.\n"
            "\n"
            "In the research pipeline, blockMesh is followed by snappyHexMesh\n"
            "which adds the airfoil shape. You would run checkMesh again after\n"
            "snappyHexMesh to verify the near-wall mesh quality."
        )
    elif quality.upper().startswith("FAIL"):
        _explain(
            "FAIL means one or more mesh quality checks exceeded OpenFOAM's limits.\n"
            "The number in brackets is how many checks failed.\n"
            "\n"
            "A failed blockMesh mesh usually means:\n"
            "  - Non-orthogonality > 70 degrees: your domain is very non-rectangular,\n"
            "    or cell aspect ratios are extreme.\n"
            "  - Negative volume: the block vertex ordering is wrong.\n"
            "\n"
            "For a simple rectangular blockMesh you should always get PASS.\n"
            "If you got FAIL, check your vertex order and grading values."
        )


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

_LESSONS = {
    "A": ("Lesson 1: Build a simple rectangle domain from scratch", lesson_1),
    "B": ("Lesson 2: Build an airfoil domain from scratch",         lesson_2),
    "C": ("Lesson 3: Understanding mesh grading and cell stretching", lesson_3),
    "D": ("Lesson 4: Understanding boundary patches",               lesson_4),
    "E": ("Lesson 5: Run your custom blockMesh and see the result", lesson_5),
    "F": ("Exit",                                                    None),
}


def main():
    _header("meshlesson  |  Interactive OpenFOAM blockMesh Learning Tool")
    _explain(
        "This tool teaches you how OpenFOAM blockMesh works from first principles.\n"
        "Each lesson is interactive — you supply values and we explain everything.\n"
        "\n"
        f"Lesson outputs are saved to: {LESSONS_DIR}\n"
        f"Lesson 5 test case:          {TEST_CASE}"
    )

    while True:
        print()
        for key, (label, _) in _LESSONS.items():
            print(f"  {_c(_Y, key)}) {label}")
        choice = input(f"\n  {_c(_C, 'Select')}: ").strip().upper()
        if choice == "F":
            print(f"\n  {_c(_G, 'Goodbye. Keep learning and keep meshing.')}\n")
            break
        if choice in _LESSONS:
            _, fn = _LESSONS[choice]
            fn()
        else:
            _warn("Enter A through F.")


if __name__ == "__main__":
    main()
