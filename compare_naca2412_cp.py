"""
NACA 2412 surface pressure (Cp) distribution: OpenFOAM vs NeuralFoil/XFOIL
at alpha=4, Re=2e5. Companion to compare_naca2412.py (which does the Cl/Cd
polar) - this one does the chordwise Cp distribution, the decisive diagnostic
for the suction-peak / turbulence-model question (see debug_notes 10.4, 12.7).

OpenFOAM wall Cp is read by mapping the zeroGradient airfoil-patch faces to
their owner cells (Cp = p_kinematic / (0.5 U^2)); NeuralFoil Cp is
reconstructed from its ue/vinf edge-velocity output as 1 - (ue/vinf)^2.

Run: python3 compare_naca2412_cp.py   (needs the naca2412_ap4_0 case solved)
"""
import sys, os, re, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import neuralfoil as nf
import core.case_builder as cb

CASE = os.path.expanduser("~/OpenFOAM/scripts/cases/naca2412_ap4_0")
TIME = "6000"
V = 2.4751
QDYN = 0.5 * V * V   # kinematic dynamic pressure (p in OpenFOAM is p/rho)
OUT = os.path.expanduser("~/OpenFOAM/scripts/results/NACA2412_Cp_alpha4_corrected.png")

# ---- OpenFOAM readers ----
def read_scalar_list(path, keyword=None):
    """Read a nonuniform List<scalar> internalField from an OpenFOAM field file."""
    with open(path) as f:
        txt = f.read()
    if keyword:
        txt = txt[txt.find(keyword):]
    m = re.search(r'nonuniform List<scalar>\s*\n(\d+)\n\(', txt)
    n = int(m.group(1))
    start = m.end()
    vals = []
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
    n = int(m.group(1))
    start = m.end()
    vals = []
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
    n = int(m.group(1)); start = m.end()
    pts = []
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
    n = int(m.group(1)); start = m.end()
    faces = []
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
nF, startF = read_boundary(f"{pmesh}/boundary", "naca2412")
print(f"cells={len(p_int)} faces={len(faces)} owner={len(owner)} patch startFace={startF} nFaces={nF}")

# For each airfoil wall face: p_wall = p[owner] (zeroGradient), center from verts
of_pts = []  # (x, y, Cp)
for fi in range(startF, startF + nF):
    verts = faces[fi]
    cx = sum(points[v][0] for v in verts) / len(verts)
    cy = sum(points[v][1] for v in verts) / len(verts)
    pw = p_int[owner[fi]]
    of_pts.append((cx, cy, pw / QDYN))

# split upper/lower by camber line: NACA2412 camber yc(x); a face is "upper"
# if its y is above the local camber line
m4, p4, t4 = cb._naca4_params("naca2412")
def yc(x):
    x = min(max(x, 0.0), 1.0)
    if x < p4:
        return m4 / p4**2 * (2*p4*x - x**2)
    return m4 / (1-p4)**2 * (1 - 2*p4 + 2*p4*x - x**2)

of_up = sorted([(x, cp) for (x, y, cp) in of_pts if y > yc(x)])
of_lo = sorted([(x, cp) for (x, y, cp) in of_pts if y <= yc(x)])
print(f"OF upper faces={len(of_up)} lower faces={len(of_lo)}")
print(f"OF stagnation check: max Cp = {max(cp for _,_,cp in of_pts):.3f} (should be ~+1)")

# ---- NeuralFoil Cp ----
n = 160
xs = [(1 - math.cos(math.pi*i/(n-1)))/2 for i in range(n)]
up, lo = [], []
for x in xs:
    (xu, yu), (xl, yl) = cb._naca4_surface_point(x, m4, p4, t4)
    up.append((xu, yu)); lo.append((xl, yl))
coords = np.array(list(reversed(up)) + lo[1:])
aero = nf.get_aero_from_coordinates(coords, alpha=4.0, Re=200000, model_size="large")
bx = np.asarray(nf.bl_x_points)
def sc(key):
    return float(np.asarray(aero[key]).ravel()[0])
nf_up = np.array([1 - sc(f"upper_bl_ue/vinf_{i}")**2 for i in range(len(bx))])
nf_lo = np.array([1 - sc(f"lower_bl_ue/vinf_{i}")**2 for i in range(len(bx))])
print(f"NeuralFoil CL={sc('CL'):.4f}  suction peak Cp(upper) = {nf_up.min():.3f} at x/c={bx[nf_up.argmin()]:.3f}")

# ---- Compare: interpolate OF Cp onto NeuralFoil's bl_x_points (upper surface) ----
of_up_x = np.array([x for x,_ in of_up]); of_up_cp = np.array([cp for _,cp in of_up])
of_lo_x = np.array([x for x,_ in of_lo]); of_lo_cp = np.array([cp for _,cp in of_lo])
of_up_interp = np.interp(bx, of_up_x, of_up_cp)
of_lo_interp = np.interp(bx, of_lo_x, of_lo_cp)
up_err = of_up_interp - nf_up
lo_err = of_lo_interp - nf_lo

print("\n=== Upper (suction) surface Cp: OpenFOAM vs NeuralFoil ===")
print(f"{'x/c':>7} {'Cp_OF':>9} {'Cp_NF':>9} {'diff':>9}")
for i in range(len(bx)):
    if bx[i] <= 0.5:
        print(f"{bx[i]:>7.3f} {of_up_interp[i]:>9.3f} {nf_up[i]:>9.3f} {up_err[i]:>9.3f}")
le_region = (bx >= 0.10) & (bx <= 0.25)
print(f"\nUpper-surface |Cp error| peak (x/c 0.10-0.25, the old hotspot): "
      f"{np.abs(up_err[le_region]).max():.3f} at x/c={bx[le_region][np.abs(up_err[le_region]).argmax()]:.3f}")
print(f"Upper-surface mean |Cp error| (all x): {np.abs(up_err).mean():.3f}")
print(f"Lower-surface mean |Cp error| (all x): {np.abs(lo_err).mean():.3f}")

# ---- Plot ----
fig, ax = plt.subplots(figsize=(11, 7))
ax.plot(of_up_x, of_up_cp, '-', color='#4fc3f7', lw=1.5, label='OpenFOAM upper (corrected mesh)')
ax.plot(of_lo_x, of_lo_cp, '-', color='#7e57c2', lw=1.5, label='OpenFOAM lower')
ax.plot(bx, nf_up, 'o', color='#69f0ae', ms=5, label='NeuralFoil/XFOIL upper')
ax.plot(bx, nf_lo, 's', color='#ffca28', ms=4, label='NeuralFoil/XFOIL lower')
ax.invert_yaxis()
ax.set_xlabel('x/c'); ax.set_ylabel('Cp')
ax.set_title('NACA2412  α=4°  Re=2×10⁵  —  OpenFOAM (corrected mesh, 6000 iter) vs NeuralFoil/XFOIL')
ax.grid(alpha=0.3); ax.legend()
plt.savefig(OUT, dpi=140, bbox_inches='tight')
print(f"\nSaved plot -> {OUT}")
