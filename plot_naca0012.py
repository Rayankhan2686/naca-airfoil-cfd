"""
NACA 0012 CFD Results — OpenFOAM simpleFoam (Re = 2e5, k-omega SST)
Data sources:
  - Aerodynamic coefficients: extracted from simpleFoam logs (ap12/ap13/ap14 cases)
  - Mesh quality metrics: NACA0012_mesh_stats.csv (60k-cell C-mesh, constant across alpha)
"""

import re
import csv
import math
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

CASES_DIR = os.path.join(os.path.dirname(__file__), "cases")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
OUT_PATH = os.path.join(RESULTS_DIR, "NACA0012_analysis.png")


def extract_alpha_from_U(case_path):
    u_file = os.path.join(case_path, "0", "U")
    with open(u_file) as f:
        text = f.read()
    m = re.search(r"internalField\s+uniform\s+\(([-\d.e+]+)\s+([-\d.e+]+)", text)
    if m:
        ux, uy = float(m.group(1)), float(m.group(2))
        return math.degrees(math.atan2(uy, ux))
    return None


def extract_final_coeffs(log_path):
    with open(log_path) as f:
        text = f.read()
    # Split on each forceCoeffs write block, take the last one
    blocks = re.split(r"forceCoeffs forceCoeffs write:", text)
    if len(blocks) < 2:
        return None, None
    last = blocks[-1]
    cd_m = re.search(r"\bCd:\s+([-\d.e+]+)", last)
    cl_m = re.search(r"\bCl:\s+([-\d.e+]+)", last)
    cd = float(cd_m.group(1)) if cd_m else None
    cl = float(cl_m.group(1)) if cl_m else None
    return cl, cd


def extract_coeff_history(log_path):
    """Return lists of (iteration, Cl, Cd) for convergence plots."""
    iters, cls, cds = [], [], []
    with open(log_path) as f:
        text = f.read()
    # Each SimpleFoam time-step has "Time = N" then later forceCoeffs
    time_blocks = re.split(r"\nTime = (\d+)\n", text)
    # time_blocks[0] = preamble, then alternating [timestep_str, block_text, ...]
    i = 1
    while i < len(time_blocks) - 1:
        t = int(time_blocks[i])
        block = time_blocks[i + 1]
        cd_m = re.search(r"\bCd:\s+([-\d.e+]+)", block)
        cl_m = re.search(r"\bCl:\s+([-\d.e+]+)", block)
        if cd_m and cl_m:
            iters.append(t)
            cls.append(float(cl_m.group(1)))
            cds.append(float(cd_m.group(1)))
        i += 2
    return iters, cls, cds


# ── Collect CFD data ──────────────────────────────────────────────────────────
case_names = ["naca0012_ap12_0", "naca0012_ap13_0", "naca0012_ap14_0"]
cfd_alpha, cfd_cl, cfd_cd = [], [], []
histories = {}

for name in case_names:
    case_path = os.path.join(CASES_DIR, name)
    log_path = os.path.join(case_path, "logs", "simpleFoam.log")
    alpha = extract_alpha_from_U(case_path)
    cl, cd = extract_final_coeffs(log_path)
    if alpha is not None and cl is not None:
        cfd_alpha.append(round(alpha, 1))
        cfd_cl.append(cl)
        cfd_cd.append(cd)
        iters, cls, cds = extract_coeff_history(log_path)
        histories[name] = {"iters": iters, "Cl": cls, "Cd": cds, "alpha": round(alpha, 1)}

# ── Load mesh quality data ────────────────────────────────────────────────────
mesh_alpha, mesh_nonortho, mesh_skew, mesh_aspect = [], [], [], []
csv_path = os.path.join(RESULTS_DIR, "NACA0012_mesh_stats.csv")
with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["quality"] == "PASS":
            mesh_alpha.append(float(row["alpha"]))
            mesh_nonortho.append(float(row["max_nonortho"]))
            mesh_skew.append(float(row["max_skewness"]))
            mesh_aspect.append(float(row["max_aspect"]))

# ── Sort CFD data by alpha ────────────────────────────────────────────────────
order = np.argsort(cfd_alpha)
cfd_alpha = [cfd_alpha[i] for i in order]
cfd_cl = [cfd_cl[i] for i in order]
cfd_cd = [cfd_cd[i] for i in order]
cfd_ld = [cl / cd if cd else None for cl, cd in zip(cfd_cl, cfd_cd)]

# ── Plot ──────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(16, 14))
fig.patch.set_facecolor("#0f1117")
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

BLUE  = "#4fc3f7"
GREEN = "#69f0ae"
AMBER = "#ffca28"
RED   = "#ff5252"
GRID  = "#2a2d3a"
TEXT  = "#e0e0e0"
AXES_BG = "#1a1d2e"

plt.rcParams.update({
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
    "axes.edgecolor": GRID,
})

def styled_ax(ax, title):
    ax.set_facecolor(AXES_BG)
    ax.set_title(title, color=TEXT, fontsize=11, fontweight="bold", pad=8)
    ax.grid(color=GRID, linestyle="--", linewidth=0.6, alpha=0.8)
    ax.tick_params(colors=TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)


# 1) Cl vs alpha
ax1 = fig.add_subplot(gs[0, 0])
styled_ax(ax1, "Lift Coefficient  Cl vs α")
ax1.plot(cfd_alpha, cfd_cl, "o-", color=BLUE, lw=2, ms=8, markerfacecolor="white",
         markeredgecolor=BLUE, markeredgewidth=1.5, label="OpenFOAM (k-ω SST)")
ax1.axhline(0, color=GRID, lw=0.8)
for a, c in zip(cfd_alpha, cfd_cl):
    ax1.annotate(f"{c:.3f}", (a, c), textcoords="offset points",
                 xytext=(6, 4), color=TEXT, fontsize=8)
ax1.set_xlabel("Angle of Attack α (°)", labelpad=6)
ax1.set_ylabel("Cl", labelpad=6)
ax1.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)


# 2) Cd vs alpha
ax2 = fig.add_subplot(gs[0, 1])
styled_ax(ax2, "Drag Coefficient  Cd vs α")
ax2.plot(cfd_alpha, cfd_cd, "s-", color=RED, lw=2, ms=8, markerfacecolor="white",
         markeredgecolor=RED, markeredgewidth=1.5, label="OpenFOAM (k-ω SST)")
for a, c in zip(cfd_alpha, cfd_cd):
    ax2.annotate(f"{c:.4f}", (a, c), textcoords="offset points",
                 xytext=(6, 4), color=TEXT, fontsize=8)
ax2.set_xlabel("Angle of Attack α (°)", labelpad=6)
ax2.set_ylabel("Cd", labelpad=6)
ax2.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)


# 3) Cl/Cd vs alpha
ax3 = fig.add_subplot(gs[1, 0])
styled_ax(ax3, "Aerodynamic Efficiency  Cl/Cd vs α")
ax3.plot(cfd_alpha, cfd_ld, "^-", color=GREEN, lw=2, ms=8, markerfacecolor="white",
         markeredgecolor=GREEN, markeredgewidth=1.5)
for a, v in zip(cfd_alpha, cfd_ld):
    ax3.annotate(f"{v:.2f}", (a, v), textcoords="offset points",
                 xytext=(6, 4), color=TEXT, fontsize=8)
ax3.set_xlabel("Angle of Attack α (°)", labelpad=6)
ax3.set_ylabel("Cl / Cd", labelpad=6)


# 4) Polar (Cl vs Cd)
ax4 = fig.add_subplot(gs[1, 1])
styled_ax(ax4, "Drag Polar  Cl vs Cd")
ax4.plot(cfd_cd, cfd_cl, "D-", color=AMBER, lw=2, ms=8, markerfacecolor="white",
         markeredgecolor=AMBER, markeredgewidth=1.5)
for a, cl, cd in zip(cfd_alpha, cfd_cl, cfd_cd):
    ax4.annotate(f"α={a}°", (cd, cl), textcoords="offset points",
                 xytext=(6, -4), color=TEXT, fontsize=8)
ax4.set_xlabel("Cd", labelpad=6)
ax4.set_ylabel("Cl", labelpad=6)


# 5) Convergence history for each case
ax5 = fig.add_subplot(gs[2, 0])
styled_ax(ax5, "Cl Convergence History")
colors_hist = [BLUE, GREEN, AMBER]
for (name, h), col in zip(histories.items(), colors_hist):
    if h["iters"]:
        ax5.plot(h["iters"], h["Cl"], lw=1.2, color=col, label=f"α={h['alpha']}°")
ax5.set_xlabel("Iteration", labelpad=6)
ax5.set_ylabel("Cl", labelpad=6)
ax5.legend(facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=8)


# 6) Mesh quality metrics vs alpha
ax6 = fig.add_subplot(gs[2, 1])
styled_ax(ax6, "Mesh Quality Metrics vs α  (60k-cell C-mesh)")
ax6_r = ax6.twinx()
ax6.plot(mesh_alpha, mesh_nonortho, "-", color=BLUE, lw=1.5, label="Max Non-ortho (°)")
ax6.plot(mesh_alpha, mesh_skew, "--", color=GREEN, lw=1.5, label="Max Skewness")
ax6_r.plot(mesh_alpha, mesh_aspect, ":", color=AMBER, lw=1.5, label="Max Aspect Ratio")
ax6.set_xlabel("α (°)", labelpad=6)
ax6.set_ylabel("Non-ortho / Skewness", color=TEXT, labelpad=6)
ax6_r.set_ylabel("Aspect Ratio", color=AMBER, labelpad=6)
ax6_r.tick_params(colors=AMBER, labelsize=9)
ax6_r.spines["right"].set_edgecolor(AMBER)
lines1, labels1 = ax6.get_legend_handles_labels()
lines2, labels2 = ax6_r.get_legend_handles_labels()
ax6.legend(lines1 + lines2, labels1 + labels2,
           facecolor=AXES_BG, edgecolor=GRID, labelcolor=TEXT, fontsize=7)
ax6_r.set_facecolor(AXES_BG)


# ── Title ─────────────────────────────────────────────────────────────────────
fig.suptitle(
    "NACA 0012 — OpenFOAM CFD Analysis  |  Re = 2×10⁵  |  k-ω SST",
    color=TEXT, fontsize=14, fontweight="bold", y=0.98
)

plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved → {OUT_PATH}")
