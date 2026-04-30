#!/usr/bin/env python3
"""
OpenFOAM Publication-Quality Overnight Batch Sweep  (FIXED)
Re = 2e5, NACA 0012/2412/4412, AoA -4 to 20 degrees
"""
import os, sys, subprocess, time, shutil, csv, math, glob
from pathlib import Path
from datetime import datetime

R="\033[0;31m"; G="\033[0;32m"; Y="\033[0;33m"
B="\033[0;34m"; C="\033[0;36m"; W="\033[1;37m"; RST="\033[0m"
def ok(m):   print(f"  {G}✔  {m}{RST}")
def warn(m): print(f"  {Y}⚠  {m}{RST}")
def err(m):  print(f"  {R}✘  {m}{RST}")
def info(m): print(f"  {C}→  {m}{RST}")
def hdr(t):  print(f"\n{B}{'─'*60}\n  {W}{t}{RST}{B}\n{'─'*60}{RST}")

HOME      = Path.home()
STL_DIR   = HOME/"OpenFOAM"/"airfoils"
CASES_DIR = HOME/"OpenFOAM"/"cases"
RESULTS   = HOME/"OpenFOAM"/"results"
SCRIPTS   = HOME/"OpenFOAM"/"scripts"
CSV_FILE  = RESULTS/"sweep_results.csv"
LOG_FILE  = RESULTS/"batch_log.txt"

AIRFOILS  = ["NACA0012","NACA2412","NACA4412"]
RE=2.0e5; RHO=1.225; MU=1.516e-5; CHORD=1.0; SPAN=0.1
VELOCITY  = RE*MU/(RHO*CHORD)
AREF      = CHORD*SPAN
TI=0.005; L_TURB=0.007*CHORD
K_INF     = 1.5*(VELOCITY*TI)**2
OMEGA_INF = K_INF**0.5/(0.09**0.25*L_TURB)

ANGLES = ([-4,-3,-2,-1]+list(range(0,12))+
          [12,12.5,13,13.5,14,14.5,15,15.5,16,16.5,17,17.5,18,19,20])

def log(msg):
    RESULTS.mkdir(parents=True,exist_ok=True)
    with open(LOG_FILE,"a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def naca4_points(naca="0012",n_points=150,chord=1.0):
    m=int(naca[0])/100.0; p=int(naca[1])/10.0; t=int(naca[2:])/100.0
    beta=[math.pi*i/(n_points-1) for i in range(n_points)]
    xc=[(1-math.cos(b))/2 for b in beta]
    def thickness(x):
        if x<=0: return 0.0
        return 5*t*chord*(0.2969*math.sqrt(x/chord)-0.1260*(x/chord)
               -0.3516*(x/chord)**2+0.2843*(x/chord)**3-0.1015*(x/chord)**4)
    def camber(x):
        xn=x/chord
        if m<1e-9 or p<1e-9: return 0.0,0.0
        if xn<p:
            return m/p**2*(2*p*xn-xn**2)*chord, 2*m/p**2*(p-xn)
        return m/(1-p)**2*(1-2*p+2*p*xn-xn**2)*chord, 2*m/(1-p)**2*(p-xn)
    upper,lower=[],[]
    for xi in xc:
        x=xi*chord; yt=thickness(x); yc,dyc=camber(x); th=math.atan(dyc)
        upper.append((x-yt*math.sin(th), yc+yt*math.cos(th)))
        lower.append((x+yt*math.sin(th), yc-yt*math.cos(th)))
    return upper+lower[-2:0:-1]

def write_stl(profile,extrude,path):
    import struct
    n=len(profile); z0,z1=0.0,extrude; tris=[]
    def norm(v1,v2,v3):
        ax,ay,az=v2[0]-v1[0],v2[1]-v1[1],v2[2]-v1[2]
        bx,by,bz=v3[0]-v1[0],v3[1]-v1[1],v3[2]-v1[2]
        nx=ay*bz-az*by; ny=az*bx-ax*bz; nz=ax*by-ay*bx
        mg=math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
        return nx/mg,ny/mg,nz/mg
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

def get_patch_name(case_dir):
    boundary=case_dir/"constant"/"polyMesh"/"boundary"
    if not boundary.exists(): return None
    skip={"inlet","outlet","top","bottom","frontandback","symmetryplane","defaultfaces"}
    for line in boundary.read_text().splitlines():
        s=line.strip().lower()
        if (s and not s.startswith(("//","foamfile","{"))
                and not any(x in s for x in skip) and not s.isdigit()):
            if any(k in s for k in ("naca","airfoil","wall","aerofoil")):
                return line.strip()
    return None

def fix_boundaries(case_dir,patch,ux,uy):
    zero=case_dir/"0"; zero.mkdir(parents=True,exist_ok=True)
    (zero/"U").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0];
internalField uniform ({ux} {uy} 0);
boundaryField
{{
    inlet        {{ type freestream; freestreamValue uniform ({ux} {uy} 0); }}
    outlet       {{ type freestream; freestreamValue uniform ({ux} {uy} 0); }}
    top          {{ type symmetryPlane; }}
    bottom       {{ type symmetryPlane; }}
    {patch}      {{ type noSlip; }}
    frontAndBack {{ type empty; }}
}}
""")
    (zero/"p").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object p; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet        {{ type freestreamPressure; freestreamValue uniform 0; }}
    outlet       {{ type freestreamPressure; freestreamValue uniform 0; }}
    top          {{ type symmetryPlane; }}
    bottom       {{ type symmetryPlane; }}
    {patch}      {{ type zeroGradient; }}
    frontAndBack {{ type empty; }}
}}
""")
    (zero/"k").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {K_INF:.8g};
boundaryField
{{
    inlet        {{ type freestream; freestreamValue uniform {K_INF:.8g}; }}
    outlet       {{ type freestream; freestreamValue uniform {K_INF:.8g}; }}
    top          {{ type symmetryPlane; }}
    bottom       {{ type symmetryPlane; }}
    {patch}      {{ type kqRWallFunction; value uniform {K_INF:.8g}; }}
    frontAndBack {{ type empty; }}
}}
""")
    (zero/"omega").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0];
internalField uniform {OMEGA_INF:.8g};
boundaryField
{{
    inlet        {{ type freestream; freestreamValue uniform {OMEGA_INF:.8g}; }}
    outlet       {{ type freestream; freestreamValue uniform {OMEGA_INF:.8g}; }}
    top          {{ type symmetryPlane; }}
    bottom       {{ type symmetryPlane; }}
    {patch}      {{ type omegaWallFunction; value uniform {OMEGA_INF:.8g}; }}
    frontAndBack {{ type empty; }}
}}
""")
    (zero/"nut").write_text(f"""FoamFile
{{ version 2.0; format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet        {{ type calculated; value uniform 0; }}
    outlet       {{ type calculated; value uniform 0; }}
    top          {{ type symmetryPlane; }}
    bottom       {{ type symmetryPlane; }}
    {patch}      {{ type nutkWallFunction; value uniform 0; }}
    frontAndBack {{ type empty; }}
}}
""")
    fvs=case_dir/"system"/"fvSchemes"
    if fvs.exists():
        c=fvs.read_text()
        if "wallDist" not in c:
            fvs.write_text(c.rstrip()+"\nwallDist\n{\n    method meshWave;\n}\n")
    fvsol=case_dir/"system"/"fvSolution"
    if fvsol.exists():
        c=fvsol.read_text()
        if "pRefCell" not in c:
            if "nNonOrthogonalCorrectors" in c:
                fvsol.write_text(c.replace("nNonOrthogonalCorrectors 0;",
                    "nNonOrthogonalCorrectors 0;\n    pRefCell 0;\n    pRefValue 0;"))
            else:
                fvsol.write_text(c.rstrip()+"\npRefCell 0;\npRefValue 0;\n")
    ctrl=case_dir/"system"/"controlDict"
    if ctrl.exists():
        c=ctrl.read_text()
        if "forceCoeffs" not in c:
            ctrl.write_text(c.rstrip()+f"""
functions
{{
    forceCoeffs
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   100;
        patches         ({patch});
        rho             rhoInf;
        rhoInf          {RHO};
        liftDir         (0 1 0);
        dragDir         (1 0 0);
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
        magUInf         {VELOCITY:.6f};
        lRef            {CHORD};
        Aref            {AREF};
    }}
}}
""")

def extract_coeffs(case_dir):
    for pat in ["postProcessing/forceCoeffs/*/forceCoeffs.dat",
                "postProcessing/forceCoeffs/*/coefficient.dat",
                "postProcessing/forces/*/forceCoeffs.dat"]:
        for filepath in sorted(glob.glob(str(case_dir/pat))):
            lines=[l for l in Path(filepath).read_text().splitlines()
                   if not l.startswith("#") and l.strip()]
            if not lines: continue
            data=lines[max(0,int(len(lines)*0.8)):]
            vals=[]
            for line in data:
                pts=line.split()
                if len(pts)>=6:
                    try: vals.append((float(pts[1]),float(pts[3]),float(pts[5])))
                    except: pass
            if vals:
                cd=sum(v[0] for v in vals)/len(vals)
                cl=sum(v[1] for v in vals)/len(vals)
                cm=sum(v[2] for v in vals)/len(vals)
                ld=cl/cd if abs(cd)>1e-9 else 0.0
                return cl,cd,cm,ld
    return None,None,None,None

def run_case(airfoil,aoa):
    stl=STL_DIR/f"{airfoil}.stl"
    aoa_label=str(aoa).replace(".","p").replace("-","m")
    case_dir=CASES_DIR/f"{airfoil}_aoa{aoa_label}"
    aoa_rad=math.radians(aoa)
    ux=round(VELOCITY*math.cos(aoa_rad),8)
    uy=round(VELOCITY*math.sin(aoa_rad),8)
    pipeline=SCRIPTS/"airfoil_pipeline.py"
    if not pipeline.exists(): err("airfoil_pipeline.py not found"); return None
    inputs="\n".join(["Y",str(stl),"1","1",str(VELOCITY),str(aoa),str(case_dir),"y","n"])
    r=subprocess.run(["python3",str(pipeline)],input=inputs,text=True,capture_output=True)
    # Fix missing eMesh file that pipeline generates with wrong name
    import glob as _g
    for _f in _g.glob(str(case_dir / "constant" / "triSurface" / "*.eMesh")):
        from pathlib import Path as _P
        _p = _P(_f)
        _t = _p.parent / (_p.stem + ".stl.eMesh")
        if _p.name != _t.name and not _t.exists():
            import shutil as _sh; _sh.copy(str(_p), str(_t))
    if not case_dir.exists():
        log(f"FAILED no case dir: {airfoil} AoA={aoa}")
        err(f"Pipeline failed: {r.stderr[:200] if r.stderr else 'no stderr'}")
        return None
    patch=get_patch_name(case_dir) or airfoil.lower()
    fix_boundaries(case_dir,patch,ux,uy)
    logs=case_dir/"logs"; logs.mkdir(exist_ok=True)
    solver_log=logs/"simpleFoam.log"
    subprocess.run(f"simpleFoam > '{solver_log}' 2>&1",shell=True,cwd=case_dir)
    cl,cd,cm,ld=extract_coeffs(case_dir)
    if cl is not None:
        ok(f"CL={cl:>9.5f}  CD={cd:>9.5f}  Cm={cm:>9.5f}  L/D={ld:>7.2f}")
        log(f"OK {airfoil} AoA={aoa} CL={cl:.6f} CD={cd:.6f}")
        return {"airfoil":airfoil,"aoa":aoa,"CL":cl,"CD":cd,"Cm":cm,"LD":ld}
    warn(f"No coefficients for {airfoil} AoA={aoa}")
    log(f"WARN {airfoil} AoA={aoa} no coefficients")
    return {"airfoil":airfoil,"aoa":aoa,"CL":None,"CD":None,"Cm":None,"LD":None}

def save_csv(results):
    RESULTS.mkdir(parents=True,exist_ok=True)
    with open(CSV_FILE,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["airfoil","aoa","CL","CD","Cm","LD"])
        w.writeheader(); w.writerows(results)

def main():
    print(f"\n  OpenFOAM Overnight Sweep — NACA 0012, 2412, 4412")
    print(f"  Re={RE:.2e}  V={VELOCITY:.4f} m/s  k∞={K_INF:.3e}  ω∞={OMEGA_INF:.2f}")
    print(f"  Angles: {min(ANGLES)}° to {max(ANGLES)}°  |  {len(ANGLES)} angles per airfoil")
    print(f"  Total: {len(AIRFOILS)*len(ANGLES)} cases\n")
    if not shutil.which("simpleFoam"):
        err("OpenFOAM not in PATH — run: source /usr/lib/openfoam/openfoam2412/etc/bashrc")
        sys.exit(1)
    STL_DIR.mkdir(parents=True,exist_ok=True)
    for airfoil in AIRFOILS:
        stl=STL_DIR/f"{airfoil}.stl"
        if not stl.exists():
            info(f"Generating {airfoil} STL with correct camber...")
            profile=naca4_points(naca=airfoil.replace("NACA",""),chord=CHORD)
            write_stl(profile,SPAN,stl)
            ok(f"Generated {stl.name}")
        else:
            info(f"{airfoil}.stl already exists")
    if input("\n  Start sweep? [Y/n]: ").strip().lower()=="n": sys.exit(0)
    RESULTS.mkdir(parents=True,exist_ok=True)
    log(f"Sweep started V={VELOCITY:.4f} Re={RE:.2e}")
    start=time.time(); all_results=[]; done=0; failed=[]
    total=len(AIRFOILS)*len(ANGLES)
    for airfoil in AIRFOILS:
        hdr(f"Running {airfoil}")
        for aoa in ANGLES:
            done+=1
            elapsed=time.time()-start
            rem=(elapsed/done)*(total-done) if done>1 else 0
            print(f"\n  [{done:>3}/{total}]  {airfoil}  AoA={aoa:>6.1f}°  "
                  f"Elapsed:{elapsed/60:.0f}m  ETA:{rem/60:.0f}m")
            result=run_case(airfoil,aoa)
            if result: all_results.append(result); save_csv(all_results)
            else: failed.append((airfoil,aoa))
    ok(f"Done! {len(all_results)}/{total} in {(time.time()-start)/60:.1f} min")
    if failed: warn(f"Failed: {failed}")
    print(f"  Results → {CSV_FILE}\n")

if __name__=="__main__":
    main()
