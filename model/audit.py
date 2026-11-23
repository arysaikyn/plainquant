"""The grid check: is a run's return coming from the cross-section or from the path?

Port of web/src/lib/gridcheck.ts, which stays the reference until the web app reads
this module's output. Same findings, same points, same thresholds. Nothing here
embeds a number that is not computed from the curve, the families or the facts the
caller passes in.
"""

from __future__ import annotations

from collections.abc import Sequence

from .stats import mean, sd

# Where a rule reads its input. The price block is Alpha101 / GTJA-191 / Alpha158
# territory; splitting it from the fundamental block is the point.
PRICE_BLOCK = {
    "price": True,
    "volume": True,
    "momentum": True,
    "reversal": True,
    "volatility": True,
    "fundamental": False,
    "sharia": False,
    "event": False,
}

# Bars a signal stays useful: an annual report decays over a year, a print over a day.
FAMILY_DECAY = {
    "price": 1,
    "volume": 1,
    "momentum": 5,
    "reversal": 5,
    "volatility": 5,
    "fundamental": 252,
    "sharia": 252,
    "event": 3,
}

TURNOVER_CAP = 1.0  # a book that replaces itself more than once a year cannot out-earn costs
WEIGHT_CAP = 0.1
SHORT_DECAY_BARS = 20


def returns_of(curve: Sequence[float]) -> list[float]:
    """Per-period simple returns. A flat or broken curve contributes nothing."""
    out = []
    for prev, now in zip(curve, curve[1:]):
        if prev > 0 and now > 0:
            out.append(now / prev - 1)
    return out


def _solve3(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting on a 3x3 system."""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for row in range(3):
            if row == col:
                continue
            factor = m[row][col] / m[col][col]
            for k in range(col, 4):
                m[row][k] -= factor * m[col][k]
    return [m[i][3] / m[i][i] for i in range(3)]


def exposure_of(curve: Sequence[float], bench: Sequence[float]) -> dict | None:
    """Split the run's return into a directional and a magnitude part.

    A grid earns |move|; a rule that knows the cross-section earns the signed move.
    OLS of the run's returns on the benchmark's return and its absolute value.
    """
    y, raw = returns_of(curve), returns_of(bench)
    n = min(len(y), len(raw))
    if n < 8:
        return None
    x1 = raw[:n]
    x2 = [abs(x) for x in x1]
    ys = y[:n]
    s1, s2 = sum(x1), sum(x2)
    s11 = sum(x * x for x in x1)
    s22 = sum(x * x for x in x2)
    s12 = sum(a * b for a, b in zip(x1, x2))
    sy = sum(ys)
    s1y = sum(a * b for a, b in zip(x1, ys))
    s2y = sum(a * b for a, b in zip(x2, ys))
    coef = _solve3([[n, s1, s2], [s1, s11, s12], [s2, s12, s22]], [sy, s1y, s2y])
    if coef is None:
        return None
    alpha, beta_drift, beta_vol = coef
    m = sy / n
    ss_res = sum((y_ - (alpha + beta_drift * a + beta_vol * b)) ** 2 for y_, a, b in zip(ys, x1, x2))
    ss_tot = sum((y_ - m) ** 2 for y_ in ys)
    drift = abs(beta_drift) * sd(x1)
    vol = abs(beta_vol) * sd(x2)
    total = drift + vol
    return {
        "beta_drift": beta_drift,
        "beta_vol": beta_vol,
        "vol_share": vol / total if total > 1e-12 else 0.0,
        "r2": max(0.0, 1 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0,
        "n": n,
    }


def persistence_of(curve: Sequence[float]) -> dict | None:
    """Lag-one autocorrelation and per-observation Sharpe of the run's own returns.

    Kaminski & Lo: a stop adds expected return only when persistence clears Sharpe.
    """
    rets = returns_of(curve)
    n = len(rets)
    if n < 8:
        return None
    m = mean(rets)
    denom = sum((r - m) ** 2 for r in rets)
    if denom <= 0:
        return None
    num = sum((rets[i] - m) * (rets[i - 1] - m) for i in range(1, n))
    gamma1 = num / denom
    spread = sd(rets)
    sr = m / spread if spread > 0 else 0.0
    stop = "adds" if gamma1 >= sr else "insurance" if gamma1 >= 0 else "hurts"
    return {"gamma1": gamma1, "sr": sr, "stop": stop}


def grid_check(
    families: Sequence[str],
    rank_exit: bool,
    curve: Sequence[float] | None = None,
    bench: Sequence[float] | None = None,
    turnover: float | None = None,
    max_weight: float | None = None,
) -> dict:
    """Points add up rather than multiply, so one hard structural failure cannot be
    outvoted by four mild ones, and the report names every finding it charged for."""
    fams: list[str] = []
    for family in families:
        if family not in fams:
            fams.append(family)
    findings: list[dict] = []

    if not rank_exit:
        findings.append({"id": "noExitPolicy", "points": 30})
    if fams and all(PRICE_BLOCK[f] for f in fams):
        findings.append({"id": "priceOnly", "points": 25})
    if fams and max(FAMILY_DECAY[f] for f in fams) < SHORT_DECAY_BARS:
        findings.append({"id": "shortDecay", "points": 10})

    exposure = exposure_of(curve, bench) if curve is not None and bench is not None else None
    if exposure:
        if exposure["vol_share"] >= 0.6:
            findings.append({"id": "volHarvest", "points": 20})
        elif exposure["vol_share"] >= 0.35:
            findings.append({"id": "volHarvest", "points": 10})

    persistence = persistence_of(curve) if curve is not None else None
    if persistence and persistence["stop"] == "hurts":
        findings.append({"id": "stopHurts", "points": 10})

    if turnover is not None and turnover > TURNOVER_CAP:
        findings.append({"id": "highTurnover", "points": 10})
    if max_weight is not None and max_weight > WEIGHT_CAP:
        findings.append({"id": "concentrated", "points": 5})

    score = min(100, sum(f["points"] for f in findings))
    verdict = "gridlike" if score >= 55 else "thin" if score >= 25 else "crossSection"
    return {
        "score": score,
        "verdict": verdict,
        "families": fams,
        "findings": findings,
        "exposure": exposure,
        "persistence": persistence,
    }


def grid_block(report: dict) -> dict:
    """The `audit.grid` object of the Result contract."""
    exposure, persistence = report["exposure"], report["persistence"]
    return {
        "score": report["score"],
        "verdict": report["verdict"],
        "families": report["families"],
        "path_exposure": None if exposure is None else min(1.0, max(0.0, exposure["vol_share"])),
        "persistence": None
        if persistence is None
        else {
            "gamma1": min(1.0, max(-1.0, persistence["gamma1"])),
            "stop": persistence["stop"],
        },
        "findings": [{"id": f["id"], "points": f["points"]} for f in report["findings"]],
    }
