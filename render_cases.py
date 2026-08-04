"""
Headless ParaView renderer — generates PNG screenshots for each case.
Run with:  pvpython ~/OpenFOAM/scripts/render_cases.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "4.5")

from paraview.simple import (
    OpenFOAMReader, GetActiveViewOrCreate, ResetCamera,
    ColorBy, GetColorTransferFunction, GetScalarBar,
    Hide, Show, Render, SaveScreenshot,
)
import paraview.simple as pv

CASES_DIR  = Path(__file__).parent / "cases"
OUTPUT_DIR = Path(__file__).parent.parent / "results" / "renders"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDED = {"naca2412"}
VIEW_SIZE = [1920, 1080]

def decode(name):
    import re
    m = re.fullmatch(r"(naca\d+)_(ap|am)(\d+)_(\d+)", name)
    if not m:
        return None
    naca_raw, sign, intg, frac = m.groups()
    alpha = float(f"{intg}.{frac}")
    if sign == "am":
        alpha = -alpha
    label = naca_raw.upper()
    val   = int(alpha) if alpha == int(alpha) else alpha
    return label, alpha, f"{label} ({val}°)"


def render_case(case_path: Path, out_png: Path, title: str):
    foam_file = case_path / "case.foam"
    if not foam_file.exists():
        foam_file.touch()

    pv.ResetSession()
    reader = OpenFOAMReader(FileName=str(foam_file))
    reader.MeshRegions   = ["internalMesh"]
    reader.CellArrays    = ["p", "U"]
    reader.UpdatePipeline()

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize        = VIEW_SIZE
    view.Background         = [0.05, 0.07, 0.14]
    view.BackgroundColorMode = "Single Color"

    display = Show(reader, view)
    ColorBy(display, ("CELLS", "p"))
    display.RescaleTransferFunctionToDataRange(True)

    pLUT = GetColorTransferFunction("p")
    pLUT.ApplyPreset("Cool to Warm", True)

    # Colorbar
    bar = GetScalarBar(pLUT, view)
    bar.Title          = "Pressure (p)"
    bar.ComponentTitle = ""
    bar.Visibility     = 1
    bar.Orientation    = "Vertical"
    bar.Position       = [0.87, 0.1]
    bar.ScalarBarLength = 0.7

    # 2-D side view: camera along –Z, Y up, centred on the airfoil chord
    ResetCamera()
    view.CameraParallelProjection = 1
    view.CameraPosition    = [0.5, 0.0, 10.0]
    view.CameraFocalPoint  = [0.5, 0.0, 0.0]
    view.CameraViewUp      = [0.0, 1.0, 0.0]
    view.CameraParallelScale = 2.5   # zoom: smaller = tighter

    # Set (and verify) Surface representation as the LAST thing done to the
    # display before rendering - guards against ParaView ever picking up
    # "Surface LIC" or another representation from prior/persisted session
    # state, which renders as a dense streaky texture with no visible error
    # in a headless batch run. Fail loudly instead of silently.
    display.SetRepresentationType("Surface")
    assert display.Representation == "Surface", (
        f"Expected Surface representation, got {display.Representation!r}"
    )

    Render()
    SaveScreenshot(
        str(out_png),
        view,
        ImageResolution=VIEW_SIZE,
        TransparentBackground=0,
        CompressionLevel=6,
    )
    print(f"  ✓  {out_png.name}")


def main():
    cases = sorted(CASES_DIR.iterdir())
    rendered = 0
    for case_path in cases:
        if not case_path.is_dir():
            continue
        info = decode(case_path.name)
        if info is None:
            continue
        naca_label, alpha, display_name = info
        if naca_label.lower() in EXCLUDED:
            continue
        if not (case_path / "constant" / "polyMesh").exists():
            continue

        out_png = OUTPUT_DIR / f"{case_path.name}.png"
        print(f"Rendering {display_name} …")
        try:
            render_case(case_path, out_png, display_name)
            rendered += 1
        except Exception as e:
            print(f"  ✗  {display_name}: {e}", file=sys.stderr)

    print(f"\nDone — {rendered} render(s) saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
