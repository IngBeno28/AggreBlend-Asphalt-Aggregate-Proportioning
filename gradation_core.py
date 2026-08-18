"""
gradation_core.py
------------------
Core data and calculation engine for the Asphalt Coarse Aggregate
Proportioning Calculator.

Spec source: Ghana Highway Authority, Standard Specification for Road
and Bridge Works, Table 17.3 - Grading Requirements for Asphalt Concrete.

This module is UI-agnostic (no Streamlit imports) so the math can be
unit tested on its own and reused outside the web app if needed.
"""

import numpy as np
from scipy.optimize import minimize

# ---------------------------------------------------------------------
# Sieve sizes (mm), largest to smallest, as listed in Table 17.3
# ---------------------------------------------------------------------
SIEVES = [28, 20, 14, 10, 6.3, 4, 2, 1, 0.425, 0.300, 0.150, 0.075]

# Display labels matching Table 17.3's printed precision (Python's str()
# on the floats above would drop trailing zeros, e.g. 0.300 -> "0.3").
SIEVE_LABELS = ["28", "20", "14", "10", "6.3", "4", "2", "1",
                "0.425", "0.300", "0.150", "0.075"]

# ---------------------------------------------------------------------
# Nominal maximum aggregate size (mm) implied by each grading
# designation, shown to the user for reference only.
# ---------------------------------------------------------------------
NMAS_MM = {"0/20": 20, "0/14": 14, "0/10": 10, "0/6": 6.3}

# ---------------------------------------------------------------------
# Table 17.3 - Grading Requirements for Asphalt Concrete
# Each leaf value is (lower, upper) percent passing, or None where the
# spec shows "-" (no control point at that sieve).
# ---------------------------------------------------------------------
SPEC = {
    "Type I": {
        "Wearing Course": {
            "0/14": {
                28: None, 20: (100, 100), 14: (90, 100), 10: (70, 90),
                6.3: (55, 75), 4: (45, 63), 2: (33, 48), 1: (23, 38),
                0.425: (14, 25), 0.300: (12, 22), 0.150: (8, 16), 0.075: (5, 10),
            },
            "0/10": {
                28: None, 20: None, 14: (100, 100), 10: (90, 100),
                6.3: (60, 82), 4: (47, 67), 2: (33, 50), 1: (23, 38),
                0.425: (14, 25), 0.300: (12, 22), 0.150: (8, 16), 0.075: (5, 10),
            },
            "0/6": {
                28: None, 20: None, 14: None, 10: (100, 100),
                6.3: (90, 100), 4: (75, 95), 2: (50, 70), 1: (33, 50),
                0.425: (20, 33), 0.300: (16, 28), 0.150: (10, 20), 0.075: (6, 12),
            },
        },
        "Binder Course": {
            "0/20": {
                28: (100, 100), 20: (90, 100), 14: (75, 95), 10: (60, 82),
                6.3: (47, 68), 4: (37, 57), 2: (25, 43), 1: (18, 32),
                0.425: (11, 22), 0.300: (9, 17), 0.150: (5, 12), 0.075: (3, 7),
            },
            "0/14": {
                28: None, 20: (100, 100), 14: (90, 100), 10: (70, 90),
                6.3: (52, 75), 4: (40, 60), 2: (30, 45), 1: (20, 35),
                0.425: (12, 24), 0.300: (10, 20), 0.150: (6, 14), 0.075: (4, 8),
            },
            "0/10": {
                28: None, 20: None, 14: (100, 100), 10: (90, 100),
                6.3: (60, 82), 4: (45, 65), 2: (30, 47), 1: (20, 35),
                0.425: (12, 24), 0.300: (10, 20), 0.150: (6, 14), 0.075: (4, 8),
            },
        },
    },
    "Type II": {
        "Wearing Course": {
            "0/14": {
                28: None, 20: (100, 100), 14: (90, 100), 10: (70, 95),
                6.3: (55, 85), 4: (46, 75), 2: (35, 60), 1: (25, 45),
                0.425: (14, 32), 0.300: (11, 27), 0.150: (6, 17), 0.075: (3, 8),
            },
            "0/10": {
                28: None, 20: None, 14: (100, 100), 10: (90, 100),
                6.3: (62, 90), 4: (50, 80), 2: (35, 65), 1: (25, 50),
                0.425: (14, 33), 0.300: (11, 27), 0.150: (6, 17), 0.075: (3, 8),
            },
        },
    },
}


def available_courses(mix_type):
    """Return the courses (e.g. Wearing/Binder) defined for a mix type."""
    return list(SPEC[mix_type].keys())


def available_designations(mix_type, course):
    """Return the grading designations (0/14, 0/10, ...) for a type+course."""
    return list(SPEC[mix_type][course].keys())


def get_target(mix_type, course, designation):
    """Return {sieve_mm: (lower, upper) or None} for the chosen spec cell."""
    return SPEC[mix_type][course][designation]


def target_bounds_arrays(target):
    """
    Convert a target dict into aligned numpy arrays over SIEVES.
    Sieves with no control point get NaN in both bounds and are excluded
    from the objective/scoring via a boolean mask.
    """
    lower = np.full(len(SIEVES), np.nan)
    upper = np.full(len(SIEVES), np.nan)
    mask = np.zeros(len(SIEVES), dtype=bool)
    for i, s in enumerate(SIEVES):
        band = target.get(s)
        if band is not None:
            lower[i], upper[i] = band
            mask[i] = True
    return lower, upper, mask


def optimize_blend(stockpile_matrix, target, min_pct=None, max_pct=None,
                    violation_weight=1000.0, target_frac=0.5):
    """
    Solve for the stockpile proportions (summing to 100%) that best fit the
    target gradation band.

    stockpile_matrix : ndarray, shape (n_sieves, n_stockpiles)
                        % passing of each stockpile at each sieve in SIEVES.
    target            : dict as returned by get_target()
    min_pct, max_pct  : optional per-stockpile proportion bounds (0-100).
                         Default is 0-100 for every stockpile.
    violation_weight  : how heavily out-of-band deviation is penalized
                         relative to distance from the target line. Kept
                         high so the optimizer prioritizes landing inside
                         the spec band over hugging the target line.
    target_frac       : where within the band (0 = lower control point,
                         1 = upper control point, 0.5 = mid-band) the
                         secondary objective aims once a sieve is inside
                         the band. Lets you generate a family of distinct,
                         all-in-spec trial blends (coarse-leaning,
                         balanced, fine-leaning) instead of a single
                         midpoint-only answer.

    Returns dict with weights (fractions, sum to 1), blend (% passing per
    sieve), lower/upper/mask arrays, and per-sieve pass/fail booleans.
    """
    n_sieves, n_piles = stockpile_matrix.shape
    lower, upper, mask = target_bounds_arrays(target)
    mid = lower + target_frac * (upper - lower)

    if min_pct is None:
        min_pct = np.zeros(n_piles)
    if max_pct is None:
        max_pct = np.full(n_piles, 100.0)
    min_pct = np.asarray(min_pct, dtype=float)
    max_pct = np.asarray(max_pct, dtype=float)

    if np.any(min_pct > max_pct):
        raise ValueError("A stockpile's minimum % exceeds its maximum %.")
    if min_pct.sum() > 100.0 + 1e-9:
        raise ValueError("The sum of minimum % constraints exceeds 100%.")

    def blend_of(w):
        return stockpile_matrix @ w  # w is fraction (0-1), matrix is in %

    def objective_and_grad(w):
        blend = blend_of(w)
        below = mask & (blend < lower)
        above = mask & (blend > upper)
        # signed distance outside the band (0 if inside or unconstrained)
        band_viol = np.where(below, lower - blend, np.where(above, blend - upper, 0.0))
        sign = np.where(below, -1.0, np.where(above, 1.0, 0.0))
        mid_dev = np.where(mask, blend - mid, 0.0)

        obj = violation_weight * np.sum(band_viol ** 2) + np.sum(mid_dev ** 2)

        # d(band_viol_j^2)/dw = 2 * band_viol_j * sign_j * M[j, :]
        grad = (
            violation_weight * (2 * band_viol * sign) @ stockpile_matrix
            + (2 * mid_dev) @ stockpile_matrix
        )
        return obj, grad

    def objective(w):
        return objective_and_grad(w)[0]

    def objective_grad(w):
        return objective_and_grad(w)[1]

    w0 = np.full(n_piles, 1.0 / n_piles)
    bounds = [(min_pct[i] / 100.0, max_pct[i] / 100.0) for i in range(n_piles)]
    constraints = [{
        "type": "eq", "fun": lambda w: np.sum(w) - 1.0,
        "jac": lambda w: np.ones(n_piles),
    }]

    best = None
    # Multi-start: the objective is piecewise-quadratic (non-smooth at band
    # edges), so SLSQP can occasionally stall at the initial point. A few
    # varied starts make the solve robust without changing the result when
    # a single start already succeeds.
    rng_starts = [w0] + [
        np.clip(w0 + d, min_pct / 100.0, max_pct / 100.0)
        for d in (
            np.linspace(0.05, -0.05, n_piles),
            np.linspace(-0.05, 0.05, n_piles),
        )
    ]
    for start in rng_starts:
        start = start / start.sum()
        result = minimize(
            objective, start, jac=objective_grad, method="SLSQP", bounds=bounds,
            constraints=constraints, options={"maxiter": 500, "ftol": 1e-12},
        )
        if best is None or (result.fun < best.fun):
            best = result
    result = best

    # Clip to each stockpile's actual bounds (not just [0, 1]) so a min/max
    # constraint (e.g. a filler locked to a narrow range) is respected, then
    # only renormalize if the sum has drifted from 1 by more than floating
    # point noise — and re-clip afterward, since scaling can otherwise nudge
    # a tightly-bounded stockpile a hair outside its limit.
    lb = min_pct / 100.0
    ub = max_pct / 100.0
    w = np.clip(result.x, lb, ub)
    if abs(w.sum() - 1.0) > 1e-8:
        w = np.clip(w / w.sum(), lb, ub)
    blend = blend_of(w)

    passes = np.where(
        mask,
        (blend >= lower - 1e-6) & (blend <= upper + 1e-6),
        True,
    )

    return {
        "success": bool(result.success),
        "message": result.message,
        "weights": w,                # fractions, sum to 1
        "blend": blend,               # % passing per sieve
        "lower": lower, "upper": upper, "mid": mid, "mask": mask,
        "passes": passes,
    }


# Three trial blends spread across the spec band, mirroring how mix
# designers typically look at a coarse-side, mid-band, and fine-side
# trial blend before picking a job-mix formula.
BLEND_PRESETS = [
    {"key": "coarse", "label": "Coarse-leaning", "frac": 0.3,
     "note": "Trial blend biased toward the lower (coarser) control points."},
    {"key": "balanced", "label": "Balanced (mid-band)", "frac": 0.5,
     "note": "Trial blend targeting the middle of the spec band at every sieve."},
    {"key": "fine", "label": "Fine-leaning", "frac": 0.7,
     "note": "Trial blend biased toward the upper (finer) control points."},
]


def optimize_blend_options(stockpile_matrix, target, min_pct=None, max_pct=None,
                            presets=BLEND_PRESETS):
    """
    Run optimize_blend() once per preset in `presets`, returning a list of
    {key, label, note, frac, result} dicts — one independent trial blend
    per preset. Each blend individually satisfies the spec as well as the
    available stockpiles allow; they are not required to differ from each
    other (if the stockpiles only support one feasible blend, some presets
    may converge to essentially the same answer).
    """
    options = []
    for preset in presets:
        res = optimize_blend(
            stockpile_matrix, target, min_pct=min_pct, max_pct=max_pct,
            target_frac=preset["frac"],
        )
        options.append({**preset, "result": res})
    return options


def evaluate_blend(weights, stockpile_matrix, target):
    """Compute the blended gradation and pass/fail for a given weight vector."""
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    blend = stockpile_matrix @ w
    lower, upper, mask = target_bounds_arrays(target)
    passes = np.where(mask, (blend >= lower - 1e-6) & (blend <= upper + 1e-6), True)
    return {"blend": blend, "lower": lower, "upper": upper, "mask": mask, "passes": passes}
