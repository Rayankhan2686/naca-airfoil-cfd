#!/usr/bin/env python3
"""
OpenFOAM Case Auto-Fixer
========================
Automatically fixes all common errors after airfoil_pipeline.py runs:
- Detects exact patch name from polyMesh/boundary
- Fixes all boundary condition files
- Creates missing 0/nut file
- Adds wallDist to fvSchemes
- Adds pRefCell to fvSolution
- Reruns simpleFoam
- Works for ANY case automatically
"""

import os
import sys
import subprocess
import time
import threading
from pathlib import Path

R  = "\033[0;31m";  G  = "\033[0;32m";  Y  = "\033[0;33m"
B  = "\033[0;34m";  C  = "\033[0;36m";  W  = "\033[1;37m"
DIM = "\033[2m";    RST = "\033[0m"

def ok(msg):   print(f"  {G}✔  {msg}{RST}")
def warn(msg): print(f"  {Y}⚠  {msg}{RST}")
def err(msg):  print(f"  {R}✘  {msg}{RST}")
def info(msg): print(f"  {C}→  {msg}{RST}")
def hdr(text): print(f"\n{B}{'─'*54}\n  {W}{text}{RST}{B}\n{'─'*54}{RST}")


def get_patch_name(case_dir):
    """Auto-detect the airfoil patch name from polyMesh/boundary."""
    boundary = case_dir / "constant" / "polyMesh" / "boundary"
    if not boundary.exists():
        return None
    
    text = boundary.read_text()
    lines = text.splitlines()
    
    # Skip standard patches, find the airfoil wall patch
    skip = {"inlet", "outlet", "top", "bottom", "frontAndBack", 
            "frontandback", "symmetryplane", "empty", "(", ")"}
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Look for patch names followed by { on next line
        if stripped and not stripped.startswith("//") and not stripped.startswith("FoamFile"):
            if i + 1 < len(lines) and "{" in lines[i + 1]:
                name = stripped.lower()
                if not any(s in name for s in skip) and not stripped.isdigit():
                    # Check if it's a wall type
                    for j in range(i, min(i + 10, len(lines))):
                        if "wall" in lines[j].lower() or "airfoil" in lines[j].lower():
                            return stripped
    
    # Fallback — look for anything with airfoil in the name
    for line in lines:
        stripped = line.strip()
        if "airfoil" in stripped.lower() and not stripped.startswith("type"):
            return stripped
    
    return None


def fix_boundary_file(filepath, old_patch, new_patch):
    """Replace patch name in a boundary condition file."""
    if not filepath.exists():
        warn(f"File not found: {filepath.name} — creating it")
        return False
    
    content = filepath.read_text()
    
    # Replace various forms of the old patch name
    replacements = [
        (f"{old_patch}\n", f"{new_patch}\n"),
        (f"{old_patch} ", f"{new_patch} "),
        (f"{old_patch}{{", f"{new_patch}{{"),
        (f"{old_patch}\t", f"{new_patch}\t"),
    ]
    
    for old, new in replacements:
        content = content.replace(old, new)
    
    filepath.write_text(content)
    return True


def create_nut(case_dir, patch_name):
    """Create 0/nut file with correct patch name."""
    nut_path = case_dir / "0" / "nut"
    content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nut;
}}

dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    outlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    top
    {{
        type            symmetryPlane;
    }}
    bottom
    {{
        type            symmetryPlane;
    }}
    {patch_name}
    {{
        type            nutkWallFunction;
        value           uniform 0;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    nut_path.write_text(content)
    ok(f"Created 0/nut with patch: {patch_name}")


def fix_fvschemes(case_dir):
    """Add wallDist method to fvSchemes if missing."""
    fvschemes = case_dir / "system" / "fvSchemes"
    if not fvschemes.exists():
        err("fvSchemes not found!"); return
    
    content = fvschemes.read_text()
    if "wallDist" not in content:
        content += "\nwallDist\n{\n    method meshWave;\n}\n"
        fvschemes.write_text(content)
        ok("Added wallDist to fvSchemes")
    else:
        ok("wallDist already in fvSchemes")


def fix_fvsolution(case_dir):
    """Add pRefCell and pRefValue to fvSolution if missing."""
    fvsolution = case_dir / "system" / "fvSolution"
    if not fvsolution.exists():
        err("fvSolution not found!"); return
    
    content = fvsolution.read_text()
    if "pRefCell" not in content:
        content = content.replace(
            "nNonOrthogonalCorrectors 0;",
            "nNonOrthogonalCorrectors 0;\n    pRefCell        0;\n    pRefValue       0;"
        )
        fvsolution.write_text(content)
        ok("Added pRefCell to fvSolution")
    else:
        ok("pRefCell already in fvSolution")


def rewrite_boundary_files(case_dir, patch_name):
    """Rewrite all 0/ boundary files with correct patch name."""
    
    # Get freestream velocity from existing U file
    u_file = case_dir / "0" / "U"
    u_val = "50"
    if u_file.exists():
        for line in u_file.read_text().splitlines():
            if "internalField" in line and "uniform" in line:
                parts = line.split("(")
                if len(parts) > 1:
                    ux = parts[1].split()[0]
                    try:
                        u_val = str(round(float(ux), 4))
                    except:
                        pass

    # Rewrite U
    u_content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}}

dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({u_val} 0 0);

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform ({u_val} 0 0);
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform ({u_val} 0 0);
    }}
    top
    {{
        type            symmetryPlane;
    }}
    bottom
    {{
        type            symmetryPlane;
    }}
    {patch_name}
    {{
        type            noSlip;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    (case_dir / "0" / "U").write_text(u_content)
    ok("Rewrote 0/U")

    # Rewrite p
    p_content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      p;
}}

dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            freestreamPressure;
        freestreamValue uniform 0;
    }}
    outlet
    {{
        type            freestreamPressure;
        freestreamValue uniform 0;
    }}
    top
    {{
        type            symmetryPlane;
    }}
    bottom
    {{
        type            symmetryPlane;
    }}
    {patch_name}
    {{
        type            zeroGradient;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    (case_dir / "0" / "p").write_text(p_content)
    ok("Rewrote 0/p")

    # Get k and omega values from existing files
    k_val = "0.00015"
    omega_val = "1.0"
    k_file = case_dir / "0" / "k"
    if k_file.exists():
        for line in k_file.read_text().splitlines():
            if "internalField" in line and "uniform" in line:
                try:
                    k_val = line.split("uniform")[1].strip().rstrip(";")
                except:
                    pass

    # Rewrite k
    k_content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      k;
}}

dimensions      [0 2 -2 0 0 0 0];
internalField   uniform {k_val};

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform {k_val};
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform {k_val};
    }}
    top
    {{
        type            symmetryPlane;
    }}
    bottom
    {{
        type            symmetryPlane;
    }}
    {patch_name}
    {{
        type            kqRWallFunction;
        value           uniform {k_val};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    (case_dir / "0" / "k").write_text(k_content)
    ok("Rewrote 0/k")

    # Rewrite omega
    omega_content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      omega;
}}

dimensions      [0 0 -1 0 0 0 0];
internalField   uniform {omega_val};

boundaryField
{{
    inlet
    {{
        type            freestream;
        freestreamValue uniform {omega_val};
    }}
    outlet
    {{
        type            freestream;
        freestreamValue uniform {omega_val};
    }}
    top
    {{
        type            symmetryPlane;
    }}
    bottom
    {{
        type            symmetryPlane;
    }}
    {patch_name}
    {{
        type            omegaWallFunction;
        value           uniform {omega_val};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    (case_dir / "0" / "omega").write_text(omega_content)
    ok("Rewrote 0/omega")


def run_solver(case_dir):
    """Run simpleFoam and tail the log."""
    logs = case_dir / "logs"
    logs.mkdir(exist_ok=True)
    solver_log = logs / "simpleFoam.log"

    info("Running simpleFoam ...")

    def tail():
        seen = 0
        while proc.poll() is None:
            time.sleep(0.5)
            if solver_log.exists():
                lines = solver_log.read_text().splitlines()
                for line in lines[seen:]:
                    stripped = line.strip()
                    if not stripped: continue
                    if any(k in stripped for k in ("ExecutionTime", "End", "ClockTime")):
                        print(f"  {G}{stripped}{RST}")
                    elif any(k in stripped for k in ("Time =", "SIMPLE")):
                        print(f"  {Y}{stripped}{RST}")
                    elif any(k in stripped for k in ("FOAM FATAL", "diverged")):
                        print(f"  {R}{stripped}{RST}")
                    elif any(k in stripped for k in ("Solving for", "residual")):
                        print(f"  {C}{stripped}{RST}")
                seen = len(solver_log.read_text().splitlines()) if solver_log.exists() else 0

    proc = subprocess.Popen(
        f"simpleFoam > '{solver_log}' 2>&1",
        shell=True, cwd=case_dir
    )
    t = threading.Thread(target=tail, daemon=True)
    t.start()
    proc.wait()
    t.join(timeout=2)

    if proc.returncode == 0:
        ok("simpleFoam finished successfully!")
        return True
    else:
        err(f"simpleFoam failed — check {solver_log}")
        return False


def extract_results(case_dir):
    """Extract CL, CD, Cm from forceCoeffs.dat."""
    forces_path = case_dir / "postProcessing" / "forces" / "0" / "forceCoeffs.dat"
    if not forces_path.exists():
        # Try alternative path
        for p in case_dir.rglob("forceCoeffs.dat"):
            forces_path = p
            break

    if not forces_path.exists():
        warn("forceCoeffs.dat not found — force output may not be configured")
        return

    lines = [l for l in forces_path.read_text().splitlines() if not l.startswith("#") and l.strip()]
    if not lines:
        warn("No data in forceCoeffs.dat yet")
        return

    last = lines[-1].split()
    if len(last) >= 5:
        print(f"\n  {W}━━━ RESULTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}")
        print(f"  {G}CL  (lift)    = {last[3]}{RST}")
        print(f"  {Y}CD  (drag)    = {last[1]}{RST}")
        print(f"  {C}Cm  (moment)  = {last[4]}{RST}")
        try:
            cl = float(last[3])
            cd = float(last[1])
            if cd > 0:
                print(f"  {W}L/D (efficiency) = {cl/cd:.2f}{RST}")
        except:
            pass
        print(f"  {W}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}\n")


def auto_fix_case(case_dir):
    """Run all fixes on a case directory."""
    hdr(f"Auto-Fixing: {case_dir.name}")

    if not case_dir.exists():
        err(f"Case directory not found: {case_dir}")
        return False

    # Detect patch name
    info("Detecting airfoil patch name ...")
    patch_name = get_patch_name(case_dir)
    if not patch_name:
        warn("Could not auto-detect patch name.")
        patch_name = input(f"  {C}Enter patch name manually: {RST}").strip()
    ok(f"Patch name: {patch_name}")

    # Fix all boundary files
    info("Rewriting boundary condition files ...")
    rewrite_boundary_files(case_dir, patch_name)

    # Create nut
    info("Creating 0/nut ...")
    create_nut(case_dir, patch_name)

    # Fix fvSchemes
    info("Checking fvSchemes ...")
    fix_fvschemes(case_dir)

    # Fix fvSolution
    info("Checking fvSolution ...")
    fix_fvsolution(case_dir)

    ok("All fixes applied!")
    return True


def main():
    print(f"""
{C}╔══════════════════════════════════════════════════════╗
║       OpenFOAM Case Auto-Fixer                       ║
║       Fixes all common errors automatically          ║
╚══════════════════════════════════════════════════════╝{RST}""")

    # Get case directory
    if len(sys.argv) > 1:
        case_dir = Path(sys.argv[1])
    else:
        default = Path.cwd()
        path_str = input(f"  {C}Case directory [{default}]: {RST}").strip()
        case_dir = Path(path_str).expanduser() if path_str else default

    if not auto_fix_case(case_dir):
        sys.exit(1)

    # Ask to run solver
    run = input(f"\n  {C}Run simpleFoam now? [Y/n]: {RST}").lower()
    if run != "n":
        success = run_solver(case_dir)
        if success:
            extract_results(case_dir)

            # Ask to open ParaView
            pv = input(f"\n  {C}Open ParaView? [Y/n]: {RST}").lower()
            if pv != "n":
                foam_file = list(case_dir.glob("*.foam"))
                if foam_file:
                    subprocess.Popen(f"paraview '{foam_file[0]}'", shell=True)
                    ok("ParaView launched!")
                else:
                    foam_file = case_dir / f"{case_dir.name}.foam"
                    foam_file.touch()
                    subprocess.Popen(f"paraview '{foam_file}'", shell=True)
                    ok("ParaView launched!")


if __name__ == "__main__":
    main()

