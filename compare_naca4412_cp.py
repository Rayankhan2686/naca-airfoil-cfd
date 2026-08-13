"""
NACA 4412 surface pressure (Cp) distribution: OpenFOAM vs REAL XFOIL at
alpha=4, Re=2e5. Companion to compare_naca4412.py (Cl/Cd polar) and the direct
4412 analogue of compare_naca2412_cp.py -- but the reference here is a real
XFOIL 6.99 Cp distribution (locally run, Re=2e5, Ncrit=9), NOT the NeuralFoil
surrogate used in the 2412 version.

OpenFOAM wall Cp: map the zeroGradient airfoil-patch faces to their owner cells
(Cp = p_kinematic / (0.5 U^2)). XFOIL Cp: read from CPWR output (x, Cp), split
upper/lower at the leading edge (XFOIL node order: TE -> upper -> LE -> lower -> TE).
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import core.case_builder as cb

CASE = os.path.expanduser("~/OpenFOAM/scripts/cases/naca4412_ap4_0")
TIME = "6000"
V = 2.4751
QDYN = 0.5 * V * V
XFOIL_CP = os.path.expanduser("~/OpenFOAM/scripts/results/xfoil_reference/naca4412_cp_alpha4_re2e5.dat")
OUT = os.path.expanduser("~/OpenFOAM/scripts/results/NACA4412_Cp_alpha4.png")

# ---- OpenFOAM readers ----
def read_scalar_list(path, keyword=None):
    with open(path) as f:
        txt = f.read()
    if keyword:
        txt = txt[txt.find(keyword):]
    m = re.search(r'nonuniform List<scalar>\s*\n(\d+)\n\(', txt)
    n = int(m.group(1)); start = m.end(); vals = []
    for line in txt[start:].splitlines():
        line = line.strip()
        if line == '' or line.startswith('('):
            continue
        if line.startswith(')'):
            break
        try:
            vals.append(float(line))
        except ValueError:
            break
        if len(vals) >= n:
            break
    return vals

def read_label_list(path):
    with open(path) as f:
        txt = f.read()
    m = re.search(r'\n(\d+)\n\(\s*\n', txt)
    n = int(m.group(1)); start = m.end(); vals = []
    for line in txt[start:].splitlines():
        line = line.strip()
        if line == '' or line == '(':
            continue
        if line.startswith(')'):
            break
        try:
            vals.append(int(line))
        except ValueError:
            break
        if len(vals) >= n:
            break
    return vals

def read_points(path):
    with open(path) as f:
        txt = f.read()
    m = re.search(r'\n(\d+)\n\(\s*\n', txt)
    n = int(m.group(1)); start = m.end(); pts = []
    for line in txt[start:].splitlines():
        line = line.strip()
        if line.startswith('('):
            v = line.strip('()').split()
            pts.append((float(v[0]), float(v[1]), float(v[2])))
        if len(pts) >= n:
            break
    return pts

def read_boundary(path, patch):
    with open(path) as f:
        txt = f.read()
    m = re.search(patch + r'\s*\{([^}]*)\}', txt, re.S)
    b = m.group(1)
    return int(re.search(r'nFaces\s+(\d+)', b).group(1)), int(re.search(r'startFace\s+(\d+)', b).group(1))

def read_faces(path):
    with open(path) as f:
        txt = f.read()
    m = re.search(r'\n(\d+)\n\(\s*\n', txt)
    n = int(m.group(1)); start = m.end(); faces = []
    for line in txt[start:].splitlines():
        line = line.strip()
        mm = re.match(r'(\d+)\(([^)]*)\)', line)
        if mm:
            faces.append([int(x) for x in mm.group(2).split()])
        if len(faces) >= n:
            break
    return faces

pmesh = f"{CASE}/constant/polyMesh"
p_int = read_scalar_list(f"{CASE}/{TIME}/p", keyword="internalField")
owner = read_label_list(f"{pmesh}/owner")
points = read_points(f"{pmesh}/points")
faces = read_faces(f"{pmesh}/faces")
nF, startF = read_boundary(f"{pmesh}/boundary", "naca4412")
print(f"cells={len(p_int)} faces={len(faces)} owner={len(owner)} patch startFace={startF} nFaces={nF}")

of_pts = []
for fi in range(startF, startF + nF):
    verts = faces[fi]
    cx = sum(points[v][0] for v in verts) / len(verts)
    cy = sum(points[v][1] for v in verts) / len(verts)
    pw = p_int[owner[fi]]
    of_pts.append((cx, cy, pw / QDYN))

m4, p4, t4 = cb._naca4_params("naca4412")
def yc(x):
    x = min(max(x, 0.0), 1.0)
    if x < p4:
        return m4 / p4**2 * (2*p4*x - x**2)
    return m4 / (1-p4)**2 * (1 - 2*p4 + 2*p4*x - x**2)

of_up = sorted([(x, cp) for (x, y, cp) in of_pts if y > yc(x)])
of_lo = sorted([(x, cp) for (x, y, cp) in of_pts if y <= yc(x)])
print(f"OF upper faces={len(of_up)} lower faces={len(of_lo)}")
print(f"OF stagnation check: max Cp = {max(cp for _,_,cp in of_pts):.3f} (should be ~+1)")

# ---- real XFOIL Cp (CPWR output: x, Cp; node order TE->upper->LE->lower->TE) ----
xf = np.loadtxt(XFOIL_CP, comments="#")
xf_x, xf_cp = xf[:, 0], xf[:, 1]
imin = int(np.argmin(xf_x))
xf_up_x, xf_up_cp = xf_x[:imin + 1], xf_cp[:imin + 1]   # upper (TE -> LE)
xf_lo_x, xf_lo_cp = xf_x[imin:], xf_cp[imin:]           # lower (LE -> TE)
print(f"XFOIL Cp points={len(xf_x)}  suction peak Cp(upper)={xf_up_cp.min():.3f} "
      f"at x/c={xf_up_x[xf_up_cp.argmin()]:.3f}")

# ---- brief error metric on upper surface (interp OF onto XFOIL upper x) ----
of_up_x = np.array([x for x, _ in of_up]); of_up_cp = np.array([cp for _, cp in of_up])
xf_up_sorted = np.argsort(xf_up_x)
xu = xf_up_x[xf_up_sorted]; cu = xf_up_cp[xf_up_sorted]
of_on_xf = np.interp(xu, of_up_x, of_up_cp)
print(f"Upper-surface mean |Cp(OF) - Cp(XFOIL)| = {np.abs(of_on_xf - cu).mean():.3f}")

# ---- Plot (style matches compare_naca2412_cp.py) ----
fig, ax = plt.subplots(figsize=(11, 7))
ax.plot(of_up_x, of_up_cp, '-', color='#4fc3f7', lw=1.5, label='OpenFOAM upper (corrected mesh)')
ax.plot([x for x, _ in of_lo], [cp for _, cp in of_lo], '-', color='#7e57c2', lw=1.5,
        label='OpenFOAM lower')
ax.plot(xf_up_x, xf_up_cp, 'o', color='#69f0ae', ms=3.5, label='XFOIL upper (real, Re=2×10⁵)')
ax.plot(xf_lo_x, xf_lo_cp, 's', color='#ffca28', ms=3, label='XFOIL lower (real, Re=2×10⁵)')
ax.invert_yaxis()
ax.set_xlabel('x/c'); ax.set_ylabel('Cp')
ax.set_title('NACA4412  α=4°  Re=2×10⁵  —  OpenFOAM (corrected mesh, 6000 iter) vs real XFOIL 6.99')
ax.grid(alpha=0.3); ax.legend()
plt.savefig(OUT, dpi=140, bbox_inches='tight')
print(f"\nSaved plot -> {OUT}")
