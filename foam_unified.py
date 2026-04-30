#!/usr/bin/env python3
"""
OpenFOAM Unified Research Tool
================================
Combined menu for:
  - foam-airfoil (Research) : NACA camber study, batch sweeps, data extraction
  - foam-helper  (SolidWorks): STL import, file browser, SolidWorks pipeline
"""

import os
import sys
import shutil
import subprocess
import struct
import math
import time
import csv
import threading
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
#  ANSI colours
# ─────────────────────────────────────────────
R   = "\033[0;31m";  G  = "\033[0;32m";  Y  = "\033[0;33m"
B   = "\033[0;34m";  C  = "\033[0;36m";  W  = "\033[1;37m"
DIM = "\033[2m";     RST = "\033[0m";    MAG = "\033[0;35m"

def ok(msg):   print(f"  {G}✔  {msg}{RST}")
def warn(msg): print(f"  {Y}⚠  {msg}{RST}")
def err(msg):  print(f"  {R}✘  {msg}{RST}")
def info(msg): print(f"  {C}→  {msg}{RST}")
def hdr(text): print(f"\n{B}{'─'*56}\n  {W}{text}{RST}{B}\n{'─'*56}{RST}")

# ─────────────────────────────────────────────
#  Paths
# ─────────────────────────────────────────────
HOME      = Path.home()
STL_DIR   = HOME / "OpenFOAM" / "airfoils"
CASES_DIR = HOME / "OpenFOAM" / "cases"
RESULTS   = HOME / "OpenFOAM" / "results"
SCRIPTS   = HOME / "OpenFOAM" / "scripts"

# ═══════════════════════════════════════════════════════════════
#  MAIN BANNER & MENU
# ═══════════════════════════════════════════════════════════════
def banner():
    print(f"""
{C}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║        OpenFOAM Unified Research Tool                        ║
║        openfoam2412  ·  Ubuntu 24  ·  Python 3              ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   {G}A.{C}  foam-airfoil {DIM}(Research){C}                              ║
║       NACA camber study · batch sweeps · data extraction     ║
║                                                              ║
║   {Y}B.{C}  foam-helper {DIM}(SolidWorks){C}                             ║
║       Import STL · file browser · custom geometry           ║
║                                                              ║
║   {DIM}0.  Exit{C}                                                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RST}""")


def main_menu():
    banner()
    while True:
        ch = input(f"\n  {C}Select [A / B / 0]: {RST}").strip().upper()
        if   ch == "A": research_menu()
        elif ch == "B": solidworks_menu()
        elif ch == "0": print(f"\n  {G}Goodbye! Happy simulating.{RST}\n"); break
        else: warn("Please enter A, B, or 0.")


# ═══════════════════════════════════════════════════════════════
#  SECTION A — foam-airfoil (Research)
# ═══════════════════════════════════════════════════════════════
def research_menu():
    while True:
        print(f"""
{G}╔══════════════════════════════════════════════════════════════╗
║   foam-airfoil  {DIM}(Research){G}                                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   {W}1.{G}  Generate NACA STL                                      ║
║       Create watertight NACA 0012 / 2412 / 4412 STL files   ║
║                                                              ║
║   {W}2.{G}  Run Single Simulation                                   ║
║       One airfoil · one angle of attack · get CL CD Cm      ║
║                                                              ║
║   {W}3.{G}  Overnight Batch Sweep                                   ║
║       All airfoils · all angles · auto data + screenshots    ║
║                                                              ║
║   {W}4.{G}  View Results                                            ║
║       Show saved CL CD data table from previous sweeps       ║
║                                                              ║
║   {W}0.{G}  Back to main menu                                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RST}""")
        ch = input(f"  {G}Select [0-4]: {RST}").strip()
        if   ch == "1": generate_naca()
        elif ch == "2": run_single()
        elif ch == "3": batch_sweep()
        elif ch == "4": view_results()
        elif ch == "0": break
        else: warn("Please enter 0-4.")


# ── 1. Generate NACA STL ──────────────────────────────────────
def naca4_points(naca="0012", n_points=150, chord=1.0):
    t = int(naca[2:]) / 100.0
    beta = [math.pi * i / (n_points - 1) for i in range(n_points)]
    x = [(1 - math.cos(b)) / 2 for b in beta]
    def yt(xc):
        if xc <= 0: return 0.0
        return 5*t*chord*(0.2969*math.sqrt(xc/chord) - 0.1260*(xc/chord)
               - 0.3516*(xc/chord)**2 + 0.2843*(xc/chord)**3 - 0.1015*(xc/chord)**4)
    upper = [(xc*chord, yt(xc*chord)) for xc in x]
    lower = [(xc*chord, -yt(xc*chord)) for xc in x]
    return upper + lower[-2:0:-1]

def write_closed_stl(profile, extrude, path):
    n = len(profile)
    z0, z1 = 0.0, extrude
    tris = []
    def norm(v1,v2,v3):
        ax,ay,az=v2[0]-v1[0],v2[1]-v1[1],v2[2]-v1[2]
        bx,by,bz=v3[0]-v1[0],v3[1]-v1[1],v3[2]-v1[2]
        nx=ay*bz-az*by; ny=az*bx-ax*bz; nz=ax*by-ay*bx
        mg=math.sqrt(nx*nx+ny*ny+nz*nz) or 1
        return (nx/mg,ny/mg,nz/mg)
    def add(v1,v2,v3): tris.append((norm(v1,v2,v3),v1,v2,v3))
    cx=sum(p[0] for p in profile)/n; cy=sum(p[1] for p in profile)/n
    for i in range(n):
        p1=profile[i]; p2=profile[(i+1)%n]
        add((cx,cy,z0),(p2[0],p2[1],z0),(p1[0],p1[1],z0))
        add((cx,cy,z1),(p1[0],p1[1],z1),(p2[0],p2[1],z1))
        add((p1[0],p1[1],z0),(p2[0],p2[1],z0),(p2[0],p2[1],z1))
        add((p1[0],p1[1],z0),(p2[0],p2[1],z1),(p1[0],p1[1],z1))
    with open(path,"wb") as f:
        f.write(b"NACA watertight STL"+b" "*61)
        f.write(struct.pack("<I",len(tris)))
        for tri in tris:
            f.write(struct.pack("<fff",*tri[0]))
            for v in tri[1:]: f.write(struct.pack("<fff",*v))
            f.write(struct.pack("<H",0))
    return len(tris)

def generate_naca():
    hdr("Generate NACA Airfoil STL")
    print(f"\n  {W}Common profiles:{RST}")
    print(f"  {DIM}0012{RST} — symmetric, 0% camber  (baseline)")
    print(f"  {DIM}2412{RST} — 2% camber at 40% chord")
    print(f"  {DIM}4412{RST} — 4% camber at 40% chord")
    print(f"  {DIM}6412{RST} — 6% camber, high lift\n")

    naca = input(f"  {C}NACA profile [0012]: {RST}").strip() or "0012"
    chord_str = input(f"  {C}Chord length metres [1.0]: {RST}").strip()
    chord = float(chord_str) if chord_str else 1.0

    STL_DIR.mkdir(parents=True, exist_ok=True)
    out = STL_DIR / f"NACA{naca}.stl"
    info(f"Generating NACA {naca} watertight mesh ...")
    profile = naca4_points(naca=naca, chord=chord)
    n = write_closed_stl(profile, 0.1, out)
    ok(f"STL saved → {out}")
    ok(f"Triangles: {n} (fully closed, watertight)")

    ch = input(f"\n  {C}Run simulation with this STL now? [Y/n]: {RST}").lower()
    if ch != "n":
        run_single(stl_override=out)


# ── 2. Run single simulation ──────────────────────────────────
def run_single(stl_override=None):
    hdr("Run Single Simulation")

    if stl_override:
        stl_path = stl_override
        print(f"  {C}STL: {W}{stl_path.name}{RST}")
    else:
        # Show available STLs
        stls = list(STL_DIR.glob("*.stl")) if STL_DIR.exists() else []
        if stls:
            print(f"\n  {W}Available STLs in ~/OpenFOAM/airfoils/:{RST}")
            for i, s in enumerate(stls, 1):
                print(f"  {DIM}{i:>3}.{RST}  {G}{s.name}{RST}")
            print(f"  {DIM}  0.  Enter path manually{RST}")
            ch = input(f"\n  {C}Select [0-{len(stls)}]: {RST}").strip()
            if ch == "0" or not ch.isdigit():
                path_str = input(f"  {C}STL path: {RST}").strip()
                stl_path = Path(path_str)
            else:
                stl_path = stls[int(ch)-1]
        else:
            path_str = input(f"  {C}STL path: {RST}").strip()
            stl_path = Path(path_str)

    if not stl_path.exists():
        err(f"File not found: {stl_path}"); return

    u_str = input(f"  {C}Freestream velocity m/s [3.0]: {RST}").strip()
    u_inf = float(u_str) if u_str else 3.0

    aoa_str = input(f"  {C}Angle of attack degrees [0]: {RST}").strip()
    aoa = float(aoa_str) if aoa_str else 0.0

    stl_stem = stl_path.stem.lower()
    default_case = CASES_DIR / f"{stl_stem}_aoa{int(aoa)}"
    dest_str = input(f"  {C}Case directory [{default_case}]: {RST}").strip()
    case_dir = Path(dest_str).expanduser() if dest_str else default_case

    _run_pipeline(stl_path, u_inf, aoa, case_dir)


def _run_pipeline(stl_path, u_inf, aoa, case_dir):
    """Core pipeline runner used by single and batch modes."""
    pipeline = SCRIPTS / "airfoil_pipeline.py"
    if not pipeline.exists():
        err(f"airfoil_pipeline.py not found at {pipeline}")
        err("Make sure your scripts are saved at ~/OpenFOAM/scripts/")
        return None

    inputs = "\n".join([
        "Y", str(stl_path), "1", "1",
        str(u_inf), str(aoa), str(case_dir), "y", "n"
    ])
    proc = subprocess.run(
        ["python3", str(pipeline)],
        input=inputs, text=True, capture_output=True
    )
    cl, cd, cm, ld = _extract_coeffs(case_dir)
    if cl is not None:
        print(f"\n  {W}━━━ RESULTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}")
        print(f"  {G}CL  = {cl:.6f}{RST}")
        print(f"  {Y}CD  = {cd:.6f}{RST}")
        print(f"  {C}Cm  = {cm:.6f}{RST}")
        print(f"  {W}L/D = {ld:.2f}{RST}")
        print(f"  {W}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}\n")

        pv = input(f"  {C}Open ParaView? [Y/n]: {RST}").lower()
        if pv != "n":
            foam = case_dir / f"{case_dir.name}.foam"
            foam.touch()
            subprocess.Popen(f"paraview '{foam}'", shell=True)
            ok("ParaView launched!")
    else:
        warn("Simulation may need manual fixing — run foam-fix")
    return cl, cd, cm, ld


def _extract_coeffs(case_dir):
    for pat in ["postProcessing/forceCoeffs/0/coefficient.dat",
                "postProcessing/forces/0/coefficient.dat",
                "postProcessing/forceCoeffs/0/forceCoeffs.dat"]:
        p = case_dir / pat
        if p.exists():
            lines = [l for l in p.read_text().splitlines()
                     if not l.startswith("#") and l.strip()]
            if lines:
                last = lines[-1].split()
                if len(last) >= 4:
                    try:
                        cd=float(last[1]); cl=float(last[3])
                        cm=float(last[4]) if len(last)>4 else 0.0
                        ld=cl/cd if cd!=0 else 0.0
                        return cl,cd,cm,ld
                    except: pass
    return None,None,None,None


# ── 3. Overnight batch sweep ──────────────────────────────────
def batch_sweep():
    hdr("Overnight Batch Sweep")

    print(f"\n  {W}Select airfoils to sweep:{RST}")
    print(f"  {C}1.{RST}  NACA 2412 + 4412  (for camber study)")
    print(f"  {C}2.{RST}  NACA 0012 + 2412 + 4412  (all three)")
    print(f"  {C}3.{RST}  Custom selection")
    ch = input(f"\n  {C}Select [1-3]: {RST}").strip()

    if ch == "1":   airfoils = ["NACA2412","NACA4412"]
    elif ch == "2": airfoils = ["NACA0012","NACA2412","NACA4412"]
    elif ch == "3":
        inp = input(f"  {C}Enter profiles comma separated (e.g. 0012,2412): {RST}").strip()
        airfoils = [f"NACA{p.strip()}" for p in inp.split(",")]
    else: return

    angles_str = input(f"  {C}Angles [0,5,10,15,20]: {RST}").strip()
    angles = [int(a) for a in angles_str.split(",")] if angles_str else [0,5,10,15,20]

    u_str = input(f"  {C}Velocity m/s [3.0]: {RST}").strip()
    velocity = float(u_str) if u_str else 3.0

    total = len(airfoils) * len(angles)
    print(f"\n  {W}Summary:{RST}")
    print(f"  Airfoils : {airfoils}")
    print(f"  Angles   : {angles}")
    print(f"  Total    : {total} cases")
    print(f"  Results  → ~/OpenFOAM/results/sweep_results.csv")

    confirm = input(f"\n  {C}Start batch sweep? [Y/n]: {RST}").lower()
    if confirm == "n": return

    # Generate missing STLs
    for airfoil in airfoils:
        stl = STL_DIR / f"{airfoil}.stl"
        if not stl.exists():
            info(f"Generating {airfoil} STL ...")
            STL_DIR.mkdir(parents=True, exist_ok=True)
            naca = airfoil.replace("NACA","")
            profile = naca4_points(naca=naca, chord=1.0)
            write_closed_stl(profile, 0.1, stl)
            ok(f"Generated {stl.name}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_file = RESULTS / "sweep_results.csv"
    all_results = []
    done = 0
    start = time.time()

    for airfoil in airfoils:
        for aoa in angles:
            done += 1
            stl = STL_DIR / f"{airfoil}.stl"
            case_dir = CASES_DIR / f"{airfoil}_aoa{aoa}"
            print(f"\n  {Y}[{done}/{total}] {airfoil} AoA={aoa}°{RST}")

            result = _run_batch_case(airfoil, aoa, stl, case_dir, velocity)
            if result:
                all_results.append(result)
                # Save CSV after every case
                with open(csv_file,"w",newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["airfoil","aoa","CL","CD","Cm","LD"])
                    w.writeheader(); w.writerows(all_results)

            elapsed = time.time() - start
            rem = (elapsed/done)*(total-done) if done>0 else 0
            print(f"  {DIM}Elapsed: {elapsed/60:.1f}m  Remaining: {rem/60:.1f}m{RST}")

    # Print summary
    print(f"\n{W}{'═'*60}{RST}")
    print(f"{W}  SWEEP COMPLETE — RESULTS{RST}")
    print(f"{W}{'═'*60}{RST}")
    print(f"  {'Airfoil':<12} {'AoA':>5} {'CL':>10} {'CD':>10} {'L/D':>8}")
    print(f"  {'-'*50}")
    for r in all_results:
        print(f"  {r['airfoil']:<12} {r['aoa']:>4}°  "
              f"{r['CL']:>10.6f}  {r['CD']:>10.6f}  {r['LD']:>8.2f}")
    print(f"\n  {G}Results saved → {csv_file}{RST}")
    ok(f"All {total} cases done in {(time.time()-start)/60:.1f} minutes!")


def _run_batch_case(airfoil, aoa, stl, case_dir, velocity):
    """Run a single case in batch mode with auto-fix."""
    pipeline = SCRIPTS / "airfoil_pipeline.py"
    if not pipeline.exists():
        err("airfoil_pipeline.py not found"); return None

    inputs = "\n".join(["Y",str(stl),"1","1",str(velocity),str(aoa),str(case_dir),"y","n"])
    subprocess.run(["python3",str(pipeline)], input=inputs, text=True, capture_output=True)

    cl,cd,cm,ld = _extract_coeffs(case_dir)
    if cl is not None:
        ok(f"CL={cl:.4f}  CD={cd:.4f}  L/D={ld:.2f}")
        return {"airfoil":airfoil,"aoa":aoa,"CL":cl,"CD":cd,"Cm":cm,"LD":ld}
    warn("No coefficients extracted")
    return {"airfoil":airfoil,"aoa":aoa,"CL":0,"CD":0,"Cm":0,"LD":0}


# ── 4. View results ───────────────────────────────────────────
def view_results():
    hdr("Saved Results")
    csv_file = RESULTS / "sweep_results.csv"
    if not csv_file.exists():
        warn("No results found. Run a batch sweep first.")
        return

    with open(csv_file) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        warn("CSV is empty."); return

    print(f"\n  {W}{'Airfoil':<12} {'AoA':>5} {'CL':>10} {'CD':>10} {'Cm':>10} {'L/D':>8}{RST}")
    print(f"  {DIM}{'-'*55}{RST}")
    for r in rows:
        try:
            cl=float(r['CL']); cd=float(r['CD'])
            cm=float(r.get('Cm',0)); ld=float(r.get('LD',0))
            print(f"  {G}{r['airfoil']:<12}{RST} {r['aoa']:>4}°  "
                  f"{cl:>10.6f}  {cd:>10.6f}  {cm:>10.6f}  {ld:>8.2f}")
        except: print(f"  {r}")

    print(f"\n  {C}CSV at: {csv_file}{RST}")
    print(f"  {DIM}Open in Excel to plot lift curves{RST}")


# ═══════════════════════════════════════════════════════════════
#  SECTION B — foam-helper (SolidWorks)
# ═══════════════════════════════════════════════════════════════
def solidworks_menu():
    while True:
        print(f"""
{Y}╔══════════════════════════════════════════════════════════════╗
║   foam-helper  {DIM}(SolidWorks){Y}                                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   {W}1.{Y}  Recent Downloads & Desktop                             ║
║       Newest STL files sorted by time — find yours fast      ║
║                                                              ║
║   {W}2.{Y}  Home Folder                                            ║
║       Scan ~/home for all STL files grouped by folder        ║
║                                                              ║
║   {W}3.{Y}  Windows Files  {DIM}(WSL only){Y}                            ║
║       Browse /mnt/c/Users/khanr/ for SolidWorks exports     ║
║                                                              ║
║   {W}4.{Y}  Browse Anywhere                                        ║
║       Full file browser — navigate any folder                ║
║                                                              ║
║   {W}5.{Y}  STL Validator                                          ║
║       Check if your STL is watertight for OpenFOAM           ║
║                                                              ║
║   {W}0.{Y}  Back to main menu                                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RST}""")
        ch = input(f"  {Y}Select [0-5]: {RST}").strip()
        if   ch == "1": sw_recent()
        elif ch == "2": sw_home()
        elif ch == "3": sw_windows()
        elif ch == "4": sw_browse()
        elif ch == "5": sw_validate()
        elif ch == "0": break
        else: warn("Please enter 0-5.")


# ── STL file picker shared logic ──────────────────────────────
def _confirm_stl(stl_path):
    """Show STL info and ask what to do with it."""
    size_kb = stl_path.stat().st_size // 1024
    print(f"""
  {W}┌─────────────────────────────────────────────────────┐
  │  {G}STL Ready!{W}                                          │
  │  {stl_path.name:<51} │
  │  Size: {size_kb} KB                                        │
  └─────────────────────────────────────────────────────┘{RST}""")

    print(f"\n  {W}What would you like to do?{RST}")
    print(f"  {C}1.{RST}  Run simulation pipeline with this STL")
    print(f"  {C}2.{RST}  Validate STL (check watertight)")
    print(f"  {C}3.{RST}  Show path only")
    print(f"  {C}0.{RST}  Go back")

    ch = input(f"\n  {C}Select [0-3]: {RST}").strip()
    if ch == "1":
        run_single(stl_override=stl_path)
    elif ch == "2":
        _validate_stl(stl_path)
    elif ch == "3":
        print(f"\n  {G}{stl_path}{RST}\n")
        input(f"  {DIM}Press Enter to continue...{RST}")


# ── 1. Recent downloads ───────────────────────────────────────
def sw_recent():
    hdr("Recent STL Files — Downloads & Desktop")
    info("Scanning Downloads, Desktop, Documents ...")

    search = []
    wsl = Path("/mnt/c/Users")
    if wsl.exists():
        for u in wsl.iterdir():
            if u.is_dir():
                for sub in ["Downloads","Desktop","Documents","OneDrive/Downloads","OneDrive/Desktop"]:
                    search.append(u/sub)
    for sub in ["Downloads","Desktop","Documents","OpenFOAM/airfoils"]:
        search.append(HOME/sub)

    found = []
    for d in search:
        if d.exists():
            try:
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() == ".stl":
                        found.append(f)
            except PermissionError: pass

    found.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    found = found[:20]

    if not found:
        warn("No STL files found in Downloads, Desktop, or Documents.")
        input(f"\n  {DIM}Press Enter to return...{RST}"); return

    print(f"\n  {W}Found {len(found)} STL file(s) — newest first:{RST}\n")
    for i, f in enumerate(found, 1):
        age = time.time() - f.stat().st_mtime
        age_str = (f"{int(age//60)}m ago" if age<3600
                   else f"{int(age//3600)}h ago" if age<86400
                   else f"{int(age//86400)}d ago")
        size_kb = max(1, f.stat().st_size//1024)
        loc = str(f.parent); loc = ("..."+loc[-42:]) if len(loc)>45 else loc
        print(f"  {DIM}{i:>2}.{RST}  {G}{W}{f.name}{RST}")
        print(f"        {DIM}{loc}{RST}")
        print(f"        {C}{age_str}{RST}  {DIM}·  {size_kb} KB{RST}\n")

    try:
        ch = input(f"  {C}Select [1-{len(found)}] or 0 to go back: {RST}").strip()
        if ch == "0": return
        _confirm_stl(found[int(ch)-1])
    except (ValueError,IndexError): warn("Invalid selection.")


# ── 2. Home folder ────────────────────────────────────────────
def sw_home():
    hdr("Home Folder — All STL Files")
    info(f"Scanning {HOME} ...")
    stls = []
    def scan(p, d=0):
        if d>4: return
        try:
            for i in sorted(p.iterdir()):
                if i.is_file() and i.suffix.lower()==".stl": stls.append(i)
                elif i.is_dir() and not i.name.startswith("."): scan(i,d+1)
        except PermissionError: pass
    scan(HOME)

    if not stls:
        warn("No STL files found."); input(f"\n  {DIM}Press Enter...{RST}"); return

    by_folder = {}
    for f in stls:
        folder = str(f.parent).replace(str(HOME),"~")
        by_folder.setdefault(folder,[]).append(f)

    print(f"\n  {W}STL files in {HOME}:{RST}\n")
    entries = []
    for folder, files in sorted(by_folder.items()):
        print(f"  {B}{folder}/{RST}")
        for f in files:
            size_kb = max(1, f.stat().st_size//1024)
            mtime = time.strftime("%d %b %Y", time.localtime(f.stat().st_mtime))
            print(f"  {DIM}{len(entries)+1:>3}.{RST}  {G}{f.name:<35}{RST}  {DIM}{size_kb:>5} KB  {mtime}{RST}")
            entries.append(f)
        print()

    try:
        ch = input(f"  {C}Select [1-{len(entries)}] or 0 to go back: {RST}").strip()
        if ch == "0": return
        _confirm_stl(entries[int(ch)-1])
    except (ValueError,IndexError): warn("Invalid selection.")


# ── 3. Windows files ──────────────────────────────────────────
def sw_windows():
    hdr("Windows Files (WSL)")
    wsl = Path("/mnt/c/Users")
    if not wsl.exists():
        warn("Windows files not accessible. This only works on WSL.")
        input(f"\n  {DIM}Press Enter...{RST}"); return
    _file_browser(wsl)


# ── 4. Browse anywhere ────────────────────────────────────────
def sw_browse():
    hdr("Browse Anywhere")
    print(f"\n  {C}1.{RST}  Home folder")
    print(f"  {C}2.{RST}  Windows Downloads (WSL)")
    print(f"  {C}3.{RST}  Type a path")
    ch = input(f"\n  {C}Select [1-3]: {RST}").strip()
    if ch=="1": _file_browser(HOME)
    elif ch=="2":
        wsl = Path("/mnt/c/Users")
        _file_browser(wsl if wsl.exists() else HOME)
    elif ch=="3":
        p = Path(input(f"  {C}Path: {RST}").strip()).expanduser()
        if p.exists(): _file_browser(p)
        else: err(f"Not found: {p}")


def _file_browser(start):
    current = start
    while True:
        try: items = sorted(current.iterdir(), key=lambda p:(p.is_file(),p.name.lower()))
        except PermissionError: warn("Permission denied."); current=current.parent; continue

        dirs  = [i for i in items if i.is_dir() and not i.name.startswith(".")]
        stls  = [i for i in items if i.is_file() and i.suffix.lower()==".stl"]
        others= [i for i in items if i.is_file() and i.suffix.lower()!=".stl"]

        print(f"\n  {W}📁 {current}{RST}")
        print(f"  {DIM}  0.  .. (go up){RST}\n")
        entries=[]; idx=1

        if dirs:
            print(f"  {B}Folders:{RST}")
            for d in dirs:
                print(f"  {DIM}{idx:>3}.{RST}  {B}[DIR]{RST}  {d.name}")
                entries.append(d); idx+=1
            print()
        if stls:
            print(f"  {G}STL Files:{RST}")
            for s in stls:
                size_kb=max(1,s.stat().st_size//1024)
                mtime=time.strftime("%d %b",time.localtime(s.stat().st_mtime))
                print(f"  {DIM}{idx:>3}.{RST}  {G}[STL]{RST}  {W}{s.name:<35}{RST}  {DIM}{size_kb} KB  {mtime}{RST}")
                entries.append(s); idx+=1
            print()
        else: warn("No STL files here — navigate into a folder\n")
        if others: print(f"  {DIM}({len(others)} other files hidden){RST}\n")

        try:
            ch = input(f"  {C}Select [0-{len(entries)}]: {RST}").strip()
            if ch=="0":
                if current.parent!=current: current=current.parent
                continue
            sel=entries[int(ch)-1]
            if sel.is_dir(): current=sel
            elif sel.suffix.lower()==".stl": _confirm_stl(sel); return
            else: warn("Please select an STL file.")
        except (ValueError,IndexError): warn("Invalid selection.")
        except KeyboardInterrupt: print(f"\n  {Y}Cancelled.{RST}"); return


# ── 5. STL Validator ──────────────────────────────────────────
def sw_validate():
    hdr("STL Validator")
    path_str = input(f"  {C}STL file path: {RST}").strip()
    stl = Path(path_str).expanduser()
    if not stl.exists():
        err(f"File not found: {stl}"); return
    _validate_stl(stl)


def _validate_stl(stl):
    info(f"Validating {stl.name} ...")
    try:
        with open(stl,"rb") as f:
            f.read(80)
            n = struct.unpack("<I",f.read(4))[0]
            edges={}
            for _ in range(n):
                f.read(12)
                verts=[struct.unpack("<fff",f.read(12)) for _ in range(3)]
                f.read(2)
                for j in range(3):
                    e=tuple(sorted([verts[j],verts[(j+1)%3]]))
                    edges[e]=edges.get(e,0)+1
        open_edges=[e for e,c in edges.items() if c!=2]
        print(f"\n  {W}File     : {stl.name}{RST}")
        print(f"  {W}Size     : {stl.stat().st_size//1024} KB{RST}")
        print(f"  {W}Triangles: {n}{RST}")
        if open_edges:
            print(f"  {R}Watertight: NO — {len(open_edges)} open edges{RST}")
            print(f"  {R}snappyHexMesh will FAIL with this STL{RST}")
            print(f"  {Y}Fix: re-export from SolidWorks with Fine resolution{RST}")
        else:
            print(f"  {G}Watertight: YES — ready for OpenFOAM!{RST}")
    except Exception as e:
        err(f"Could not read STL: {e}")


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if not shutil.which("blockMesh"):
        print(f"\n  {Y}OpenFOAM not detected in this terminal.{RST}")
        print(f"  {C}Run: source /usr/lib/openfoam/openfoam2412/etc/bashrc{RST}\n")
    main_menu()

