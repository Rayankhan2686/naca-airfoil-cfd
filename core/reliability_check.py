"""
Lightweight two-mesh bistability check.

Cheap alternative to a full mesh-independence study (which needs 3-4 tiers to
tell "slow convergence" apart from "mesh-sensitive/bistable"): run the SAME
case at the fine and extra-fine tiers only, and flag it as unreliable if
either of two symptoms of bistability show up. This does NOT prove mesh
independence - it's a two-run smoke test meant to catch cases like NACA0012
alpha=9 (see debug_notes.md section 9) cheaply, before committing to a full
sweep at those angles.

Not wired into the main sweep pipeline (foam_research.py) yet - see
debug_notes.md section 10 for the proposed usage.
"""

import math
from pathlib import Path

from core.case_builder import build_case
from core.mesh_runner import run_pipeline_verbose
from core.results_extractor import extract_results

# Reuse the exact tiers from the mesh independence study - do not invent new ones.
FINE_TIER = {"nx": 283, "ny": 212}         # ~120k cells, current production default
EXTRA_FINE_TIER = {"nx": 400, "ny": 300}   # ~240k cells, 2x fine

# Threshold justification (see debug_notes.md section 9 data):
#   alpha=5 (known-good, attached flow):  |dCl| fine->extra-fine = 0.25%
#   alpha=9 (known-bad, bistable):        |dCl| fine->extra-fine = 8.35%
# 5% sits with wide margin above the good case (20x) and below the bad case
# (still comfortably inside it), so it separates the two known reference
# points cleanly without being tuned to exactly split the difference.
DEFAULT_CL_THRESHOLD_PCT = 5.0


def _pct_change(old: float, new: float) -> float:
    return (new - old) / abs(old) * 100.0 if old else float("nan")


def evaluate_reliability(
    fine_cl: float, fine_cd: float,
    extra_fine_cl: float, extra_fine_cd: float,
    prior_cd_delta_pct: float | None = None,
    cl_threshold_pct: float = DEFAULT_CL_THRESHOLD_PCT,
) -> dict:
    """
    Pure decision logic - no CFD execution, so this is trivially unit-testable.

    prior_cd_delta_pct: the % change in Cd from the refinement step BEFORE
    fine (i.e. medium->fine), if known (e.g. from an earlier
    mesh_independence.csv entry for this exact airfoil+alpha). Used only for
    the trend-reversal check. If None, that check is skipped (can't be
    evaluated with only two runs) and the verdict rests on the Cl threshold
    alone.

    Returns a dict with the computed deltas, which sub-check(s) fired, and
    an overall boolean verdict (unreliable=True/False).
    """
    d_cl_pct = _pct_change(fine_cl, extra_fine_cl)
    d_cd_pct = _pct_change(fine_cd, extra_fine_cd)

    trend_reversed = None
    if prior_cd_delta_pct is not None:
        # sign() treats 0 as its own sign; guard against a literal zero delta
        prior_sign = math.copysign(1.0, prior_cd_delta_pct) if prior_cd_delta_pct else 0.0
        new_sign = math.copysign(1.0, d_cd_pct) if d_cd_pct else 0.0
        trend_reversed = prior_sign != 0.0 and new_sign != 0.0 and prior_sign != new_sign

    large_cl_change = abs(d_cl_pct) > cl_threshold_pct

    unreliable = bool(trend_reversed) or large_cl_change

    return {
        "fine_cl": fine_cl, "fine_cd": fine_cd,
        "extra_fine_cl": extra_fine_cl, "extra_fine_cd": extra_fine_cd,
        "d_cl_pct": d_cl_pct, "d_cd_pct": d_cd_pct,
        "prior_cd_delta_pct": prior_cd_delta_pct,
        "trend_reversed": trend_reversed,
        "large_cl_change": large_cl_change,
        "cl_threshold_pct": cl_threshold_pct,
        "unreliable": unreliable,
    }


def run_two_tier_check(
    airfoil: str,
    alpha_deg: float,
    stl_src: str,
    cases_dir: str,
    prior_cd_delta_pct: float | None = None,
    cl_threshold_pct: float = DEFAULT_CL_THRESHOLD_PCT,
) -> dict:
    """
    Actually runs the two CFD cases (fine, extra-fine) for (airfoil, alpha),
    then hands the results to evaluate_reliability(). This is the expensive
    path - two full blockMesh+simpleFoam runs. Use evaluate_reliability()
    directly (with cached/known Cl,Cd) when you don't need fresh runs, e.g.
    for testing.
    """
    tag = f"{alpha_deg:+.1f}".replace("+", "p").replace("-", "m").replace(".", "_")
    results = {}
    for tier_name, dims in (("fine", FINE_TIER), ("extra-fine", EXTRA_FINE_TIER)):
        case_name = f"{airfoil}_relcheck_{tier_name}_a{tag}"
        case_dir = str(Path(cases_dir) / case_name)
        build_case(case_dir, airfoil, alpha_deg, stl_src=stl_src, **dims)
        ok = run_pipeline_verbose(case_dir, airfoil)
        if not ok:
            raise RuntimeError(f"{tier_name} run failed for {airfoil} alpha={alpha_deg}")
        result = extract_results(case_dir, airfoil, alpha_deg)
        if result is None:
            raise RuntimeError(f"could not extract results for {tier_name} {airfoil} alpha={alpha_deg}")
        results[tier_name] = result

    return evaluate_reliability(
        fine_cl=results["fine"]["Cl"], fine_cd=results["fine"]["Cd"],
        extra_fine_cl=results["extra-fine"]["Cl"], extra_fine_cd=results["extra-fine"]["Cd"],
        prior_cd_delta_pct=prior_cd_delta_pct, cl_threshold_pct=cl_threshold_pct,
    )
