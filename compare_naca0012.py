"""
NACA 0012 CFD vs Reference Comparison
Compares OpenFOAM simpleFoam (k-omega SST, Re=2e5) results against the
XFOIL Re=200,000 (Ncrit=9) reference polar (airfoiltools.com xf-n0012-il-200000),
the standard exact-Re-matched benchmark used for low-Re NACA0012 validation.
"""
import csv
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

HOME = os.path.expanduser("~")
RESULTS_DIR = os.path.join(HOME, "OpenFOAM", "results")
OUT_PATH = os.path.join(RESULTS_DIR, "NACA0012_vs_reference.png")
CSV_OUT = os.path.join(RESULTS_DIR, "NACA0012_vs_reference.csv")

cfd_csv = os.path.join(HOME, "OpenFOAM", "scripts", "results", "airfoil_results.csv")
xfoil_csv = "/tmp/xfoil_range.csv"

# ── Load OpenFOAM (CFD) data ──────────────────────────────────────────────
cfd = {}
with open(cfd_csv) as f:
    for row in csv.DictReader(f):
        if row["airfoil"] != "naca0012":
            continue
        if row.get("Cl", "") == "":
            continue
        a = float(row["alpha"])
        cfd[a] = {
            "Cl": float(row["Cl"]),
            "Cd": float(row["Cd"]),
            "note": row.get("note", "").strip(),
        }

# ── Load XFOIL reference data (Alpha,Cl,Cd,Cdp,Cm,Top_Xtr,Bot_Xtr) ────────
xfoil = {}
with open(xfoil_csv) as f:
    for line in f:
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        a = round(float(parts[0]), 2)
        xfoil[a] = {"Cl": float(parts[1]), "Cd": float(parts[2])}

# ── Match alphas present in both (nearest 0.25 deg snap for XFOIL grid) ──
def nearest_xfoil(a):
    key = min(xfoil.keys(), key=lambda k: abs(k - a))
    return key if abs(key - a) < 0.13 else None

rows = []
for a in sorted(cfd.keys()):
    xk = nearest_xfoil(a)
    if xk is None:
        continue
    cl_cfd, cd_cfd = cfd[a]["Cl"], cfd[a]["Cd"]
    cl_xf, cd_xf = xfoil[xk]["Cl"], xfoil[xk]["Cd"]
    rows.append({
        "alpha": a,
        "Cl_CFD": cl_cfd, "Cl_XFOIL": cl_xf, "Cl_diff": cl_cfd - cl_xf,
        "Cd_CFD": cd_cfd, "Cd_XFOIL": cd_xf, "Cd_diff": cd_cfd - cd_xf,
        "note": cfd[a]["note"],
    })

with open(CSV_OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

reliable = [r for r in rows if r["note"] != "post-stall-unreliable"]
cl_errs = [abs(r["Cl_diff"]) for r in reliable]
cd_errs = [abs(r["Cd_diff"]) for r in reliable]
print(f"Matched {len(rows)} alphas ({len(reliable)} reliable, pre/at-stall).")
print(f"Mean |Cl error| (reliable range): {np.mean(cl_errs):.4f}")
print(f"Max  |Cl error| (reliable range): {np.max(cl_errs):.4f} at alpha={reliable[int(np.argmax(cl_errs))]['alpha']}")
print(f"Mean |Cd error| (reliable range): {np.mean(cd_errs):.4f}")
print(f"Max  |Cd error| (reliable range): {np.max(cd_errs):.4f} at alpha={reliable[int(np.argmax(cd_errs))]['alpha']}")

# ── Plot ───────────────────────────────────────────────────────────────────
BLUE, RED, AMBER, GREEN = "#4fc3f7", "#ff5252", "#ffca28", "#69f0ae"
GRID, TEXT, AXES_BG = "#2a2d3a", "#e0e0e0", "#1a1d2e"

plt.rcParams.update({
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
    "axes.edgecolor": GRID,
})

fig = plt.figure(figsize=(15, 10))
fig.patch.set_facecolor("#0f1117")
gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.3)

def styled_ax(ax, title):
    ax.set_facecolor(AXES_BG)
    ax.set_title(title, color=TEXT, fontsize=11, fontweight="bold", pad=8)
    ax.grid(color=GRID, linestyle="--", linewidth=0.6, alpha=0.8)
    ax.tick_params(colors=TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)

all_a = [r["alpha"] for r in rows]
rel_a = [r["alpha"] for r in reliable]
unrel = [r for r in rows if r["note"] == "post-stall-unreliable"]
unrel_a = [r["alpha"] for r in unrel]

xf_a_sorted = sorted(xfoil.keys())
xf_cl_sorted = [xfoil[a]["Cl"] for a in xf_a_sorted]
xf_cd_sorted = [xfoil[a]["Cd"] for a in xf_a_sorted]

# 1) Cl vs alpha
ax1 = fig.add_subplot(gs[0, 0])
styled_ax(ax1, "Lift Coefficient  Cl vs α")
ax1.plot(xf_a_sorted, xf_cl_sorted, "-", color=GREEN, lw=2, label="XFOIL Re=2×10⁵ (reference)")
ax1.plot(rel_a, [cfd[a]["Cl"] for a in rel_a], "o", color=BLUE, ms=7,
         markeredgecolor="white", markeredgewidth=0.8, label="OpenFOAM k-ω SST (reliable)")
if unrel_a:
    ax1.plot(unrel_a, [cfd[a]["Cl"] for a in unrel_a], "x", color=RED, ms=8, mew=2,
             label="OpenFOAM post-stall (unreliable)")
ax1.axhline(0, color=GRID, lw=0.8)
ax1.set_xlabel("Angle of Attack α (°)")
ax1.set_ylabel("Cl")
ax1.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)

# 2) Cd vs alpha
ax2 = fig.add_subplot(gs[0, 1])
styled_ax(ax2, "Drag Coefficient  Cd vs α")
ax2.plot(xf_a_sorted, xf_cd_sorted, "-", color=GREEN, lw=2, label="XFOIL Re=2×10⁵ (reference)")
ax2.plot(rel_a, [cfd[a]["Cd"] for a in rel_a], "o", color=BLUE, ms=7,
         markeredgecolor="white", markeredgewidth=0.8, label="OpenFOAM k-ω SST (reliable)")
if unrel_a:
    ax2.plot(unrel_a, [cfd[a]["Cd"] for a in unrel_a], "x", color=RED, ms=8, mew=2,
             label="OpenFOAM post-stall (unreliable)")
ax2.set_xlabel("Angle of Attack α (°)")
ax2.set_ylabel("Cd")
ax2.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)

# 3) Cl error vs alpha
ax3 = fig.add_subplot(gs[1, 0])
styled_ax(ax3, "Cl Difference (CFD − XFOIL)")
colors3 = [RED if r["note"] == "post-stall-unreliable" else AMBER for r in rows]
ax3.bar(all_a, [r["Cl_diff"] for r in rows], color=colors3, width=0.35)
ax3.axhline(0, color=TEXT, lw=0.8)
ax3.set_xlabel("Angle of Attack α (°)")
ax3.set_ylabel("ΔCl")

# 4) Drag polar
ax4 = fig.add_subplot(gs[1, 1])
styled_ax(ax4, "Drag Polar  Cl vs Cd")
ax4.plot(xf_cd_sorted, xf_cl_sorted, "-", color=GREEN, lw=2, label="XFOIL Re=2×10⁵")
ax4.plot([cfd[a]["Cd"] for a in rel_a], [cfd[a]["Cl"] for a in rel_a], "o", color=BLUE, ms=7,
         markeredgecolor="white", markeredgewidth=0.8, label="OpenFOAM (reliable)")
ax4.set_xlabel("Cd")
ax4.set_ylabel("Cl")
ax4.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)

fig.suptitle(
    "NACA 0012 — OpenFOAM RANS vs XFOIL Reference  |  Re = 2×10⁵",
    color=TEXT, fontsize=14, fontweight="bold", y=0.98
)
plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved plot -> {OUT_PATH}")
print(f"Saved comparison table -> {CSV_OUT}")
