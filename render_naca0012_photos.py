"""
Renders pressure-field PNGs for a representative subset of the NACA0012
sweep, into results/naca0012_photos/. Adapted from render_cases.py (same
OpenFOAMReader/camera/colormap setup), just retargeted at specific alphas,
output folder, and filename convention.

Run with: pvpython render_naca0012_photos.py
"""

import os
from pathlib import Path

os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_GL_VERSION_OVERRIDE", "4.5")

from paraview.simple import (
    OpenFOAMReader, GetActiveViewOrCreate, ResetCamera,
    ColorBy, GetColorTransferFunction, GetScalarBar,
    Show, Render, SaveScreenshot,
)
import paraview.simple as pv
# Without this, ParaView auto-resets the camera to fit the WHOLE dataset on the
# first Render() call after Show(), silently overriding any explicit camera
# settings made beforehand - this was the actual cause of the "flat diamond"
# renders (camera was ending up fit to the full ~60x40 domain, not the airfoil).
pv._DisableFirstRenderCameraReset()

SCRIPTS_DIR = Path(os.path.expanduser("~/OpenFOAM/scripts"))
CASES_DIR = SCRIPTS_DIR / "cases"
OUTPUT_DIR = SCRIPTS_DIR / "results" / "naca0012_photos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VIEW_SIZE = [1920, 1080]
ALPHAS = [-4.0, 0.0, 4.0, 8.0, 9.0, 11.5, 15.0, 20.0]


def alpha_to_case_name(alpha: float) -> str:
    tag = f"{alpha:+.1f}".replace("+", "p").replace("-", "m").replace(".", "_")
    return f"naca0012_a{tag}"


def render_case(case_path: Path, out_png: Path, alpha: float):
    foam_file = case_path / "case.foam"
    if not foam_file.exists():
        foam_file.touch()

    pv.ResetSession()
    reader = OpenFOAMReader(FileName=str(foam_file))
    reader.MeshRegions = ["internalMesh"]
    reader.CellArrays = ["p", "U"]
    reader.UpdatePipeline()

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = VIEW_SIZE
    view.Background = [0.05, 0.07, 0.14]
    view.BackgroundColorMode = "Single Color"

    display = Show(reader, view)
    ColorBy(display, ("CELLS", "p"))

    pLUT = GetColorTransferFunction("p")
    pLUT.ApplyPreset("Cool to Warm", True)

    bar = GetScalarBar(pLUT, view)
    bar.Title = f"NACA0012 alpha={alpha:g} deg -- Pressure (p)"
    bar.ComponentTitle = ""
    bar.Visibility = 1
    bar.Orientation = "Vertical"
    bar.Position = [0.87, 0.1]
    bar.ScalarBarLength = 0.7

    # Camera: looking down -z (span axis) at the x-y chord/thickness cross-section -
    # this part was already correct. The bug was zoom: parallel scale of 2.5 shows
    # ~5 chord-lengths vertically, so the 0.12c-thick airfoil occupied only ~2% of
    # the frame (the "flat diamond" look). Tightened to frame ~1.8 chords vertically
    # so the airfoil is actually recognizable.
    view.CameraParallelProjection = 1
    view.CameraPosition = [0.5, 0.0, 10.0]
    view.CameraFocalPoint = [0.5, 0.0, 0.0]
    view.CameraViewUp = [0.0, 1.0, 0.0]
    view.CameraParallelScale = 0.9

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
    # Rescale color range to what's actually visible post-zoom, not the raw
    # full-domain data range (measured to be numerically the same here since the
    # pressure extremes happen to sit near the airfoil anyway, but this is the
    # more correct/robust call in general and costs nothing).
    display.RescaleTransferFunctionToVisibleRange(view)
    Render()
    SaveScreenshot(str(out_png), view, ImageResolution=VIEW_SIZE,
                   TransparentBackground=0, CompressionLevel=6)
    print(f"  OK  {out_png.name}", flush=True)


def main():
    rendered, missing = [], []
    for alpha in ALPHAS:
        case_name = alpha_to_case_name(alpha)
        case_path = CASES_DIR / case_name
        if not (case_path / "constant" / "polyMesh").exists():
            print(f"MISSING mesh for alpha={alpha} ({case_name})", flush=True)
            missing.append(alpha)
            continue
        out_png = OUTPUT_DIR / f"naca0012_a{alpha:.1f}_pressure.png"
        print(f"Rendering alpha={alpha} -> {out_png.name}", flush=True)
        try:
            render_case(case_path, out_png, alpha)
            rendered.append(alpha)
        except Exception as e:
            print(f"  FAIL alpha={alpha}: {e}", flush=True)
            missing.append(alpha)

    print(f"\n=== DONE: rendered {len(rendered)}/{len(ALPHAS)}, missing/failed: {missing} ===", flush=True)


if __name__ == "__main__":
    main()
