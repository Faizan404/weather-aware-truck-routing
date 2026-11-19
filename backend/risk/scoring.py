"""Route-level risk metrics and the recommendation.

Each checkpoint covers half the distance to its neighbours (see
core.geo.coverage_miles), so miles-by-level always add up to the route length.

Recommendation order (from the spec), best first:
    0. Enough forecast data: a route with more than 10% of its miles Unknown
       (no forecast) ranks after every route with at least 90% coverage, since
       its risk can't be judged.
    1. Fewest Severe miles  (No Travel miles are compared first: No Travel is
                             worse than Severe, so a route with any No Travel
                             miles never beats one with only Severe miles)
    2. Fewest High miles
    3. Lowest average risk  (distance-weighted mean of level scores 0-4).
                             Differences under 0.1 count as a tie, so a long
                             detour can't win on a negligible difference and
                             travel time decides instead.
    4. Shortest travel time
Miles are rounded to 0.1 and average risk to 0.01 so float noise can't decide.
Unknown miles are not counted in any risk bucket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key

from risk.rules import RiskLevel

UNKNOWN_SHARE_LIMIT = 0.10
AVG_RISK_TIE = 0.1


@dataclass
class RouteMetrics:
    route_id: str
    distance_miles: float
    duration_seconds: float
    miles_by_level: dict[str, float]
    avg_risk: float | None
    unknown_miles: float
    max_level: RiskLevel
    incomplete: bool = False
    unknown_share: float = 0.0  # fraction of the route without forecast data

    @property
    def mostly_unknown(self) -> bool:
        return self.unknown_share > UNKNOWN_SHARE_LIMIT

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[RiskLevel.NO_TRAVEL.key]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[RiskLevel.SEVERE.key]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[RiskLevel.HIGH.key]


def route_metrics(
    route_id: str,
    distance_miles: float,
    duration_seconds: float,
    levels: list[RiskLevel],
    coverage: list[float],
) -> RouteMetrics:
    miles = {lvl.key: 0.0 for lvl in [*RiskLevel.ranked(), RiskLevel.UNKNOWN]}
    for lvl, cov in zip(levels, coverage):
        miles[lvl.key] += cov

    known = [(lvl, cov) for lvl, cov in zip(levels, coverage) if lvl is not RiskLevel.UNKNOWN]
    known_miles = sum(cov for _, cov in known)
    if known_miles > 0:
        avg = sum(lvl.rank * cov for lvl, cov in known) / known_miles
    elif known:  # zero-length coverage (single point): plain mean
        avg = sum(lvl.rank for lvl, _ in known) / len(known)
    else:
        avg = None

    max_level = max(
        (lvl for lvl, _ in known), key=lambda lvl: lvl.rank, default=RiskLevel.UNKNOWN
    )
    unknown = miles.pop(RiskLevel.UNKNOWN.key)
    total = sum(coverage)
    if total > 0:
        unknown_share = unknown / total
    else:  # zero-length coverage: share of Unknown checkpoints
        unknown_share = sum(lvl is RiskLevel.UNKNOWN for lvl in levels) / max(1, len(levels))
    return RouteMetrics(
        route_id=route_id,
        distance_miles=distance_miles,
        duration_seconds=duration_seconds,
        miles_by_level=miles,
        avg_risk=avg,
        unknown_miles=unknown,
        max_level=max_level,
        incomplete=RiskLevel.UNKNOWN in levels,
        unknown_share=unknown_share,
    )


CRITERIA: list[tuple[str, str]] = [
    ("forecast_coverage", "Most complete forecast"),
    ("no_travel_miles", "Fewest No Travel miles"),
    ("severe_miles", "Fewest Severe miles"),
    ("high_miles", "Fewest High miles"),
    ("avg_risk", "Lowest average risk"),
    ("duration_seconds", "Shortest travel time"),
]


def _value(m: RouteMetrics, attr: str) -> float:
    if attr == "forecast_coverage":
        return 1.0 if m.mostly_unknown else 0.0
    if attr == "avg_risk":
        return round(m.avg_risk, 2) if m.avg_risk is not None else float("inf")
    if attr == "duration_seconds":
        return round(m.duration_seconds)
    return round(getattr(m, attr), 1)


def decider(a: RouteMetrics, b: RouteMetrics) -> tuple[str, int] | None:
    """The first criterion on which a and b differ, and -1 if a is better
    (1 if b is). None if they tie on everything."""
    for attr, _ in CRITERIA:
        va, vb = _value(a, attr), _value(b, attr)
        if attr == "avg_risk" and va != float("inf") and vb != float("inf"):
            if round(abs(va - vb), 2) < AVG_RISK_TIE:
                continue
        if va != vb:
            return attr, -1 if va < vb else 1
    return None


def compare(a: RouteMetrics, b: RouteMetrics) -> int:
    result = decider(a, b)
    return 0 if result is None else result[1]


def _fmt_duration(seconds: float, with_seconds: bool = False) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    if with_seconds:
        return f"{h}h {m:02d}m {sec:02d}s" if h else f"{m}m {sec:02d}s"
    m = int(round(rem / 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h}h {m:02d}m" if h else f"{m} min"


def _fmt_gap(seconds: float) -> str:
    return f"{int(round(seconds))}s" if seconds < 60 else _fmt_duration(seconds)


def _miles(value: float) -> str:
    return f"{value:.0f} mi" if value >= 10 else f"{value:.1f} mi"


def _pct(share: float) -> str:
    return f"{round(share * 100)}%"


def _fmt(attr: str, m: RouteMetrics) -> str:
    if attr == "forecast_coverage":
        return f"{_pct(m.unknown_share)} of miles without forecast data"
    if attr == "duration_seconds":
        return _fmt_duration(m.duration_seconds)
    if attr == "avg_risk":
        return "n/a" if m.avg_risk is None else f"{m.avg_risk:.2f}"
    return f"{getattr(m, attr):.1f} mi"


LEVEL_NAMES = {"no_travel_miles": "No Travel conditions", "severe_miles": "Severe risk", "high_miles": "High risk"}


def _downside(attr: str, worse: RouteMetrics, better: RouteMetrics) -> str:
    """Why `worse` lost to `better` on `attr`, as a clause after "but"."""
    if attr == "forecast_coverage":
        return f"{_pct(worse.unknown_share)} of it has no forecast data"
    if attr == "avg_risk":
        return f"has a higher average risk ({_fmt(attr, worse)} vs {_fmt(attr, better)})"
    if attr in LEVEL_NAMES:
        text = f"has {_miles(getattr(worse, attr))} of {LEVEL_NAMES[attr]}"
        theirs = getattr(better, attr)
        return text + (f" (vs {_miles(theirs)})" if round(theirs, 1) > 0 else "")
    return "ranks lower"


@dataclass
class Recommendation:
    route_id: str
    ranking: list[str]
    criterion: str | None
    reason: str
    no_safe_route: bool
    notes: list[str] = field(default_factory=list)


def _runner_up_reason(best: RouteMetrics, runner: RouteMetrics) -> tuple[str | None, str]:
    result = decider(best, runner)
    if result is None:
        return None, "All routes tie on every criterion; the first option is shown."
    attr = result[0]
    label = dict(CRITERIA)[attr]
    best_txt, runner_txt = _fmt(attr, best), _fmt(attr, runner)
    if best_txt == runner_txt and attr == "duration_seconds":
        # Differ by seconds only: show them so it doesn't read as a tie.
        best_txt = _fmt_duration(best.duration_seconds, with_seconds=True)
        runner_txt = _fmt_duration(runner.duration_seconds, with_seconds=True)
    return attr, f"{label}: {best_txt} vs {runner_txt} on the next best route."


def recommend(metrics: list[RouteMetrics]) -> Recommendation:
    ranked = sorted(metrics, key=cmp_to_key(compare))  # stable: ties keep input order
    best = ranked[0]
    no_safe = all(m.no_travel_miles > 0 for m in metrics)

    criterion = None
    if len(ranked) == 1:
        reason = "Only one route option is available."
    else:
        criterion, reason = _runner_up_reason(best, ranked[1])
        # If a faster route lost, say why it lost: "shortest travel time"
        # against the runner-up would hide that a quicker option exists.
        faster = [m for m in ranked[1:] if round(m.duration_seconds) < round(best.duration_seconds)]
        if faster:
            quickest = min(faster, key=lambda m: m.duration_seconds)
            result = decider(best, quickest)
            if result is not None and result[1] < 0:
                criterion = result[0]
                gap = _fmt_gap(best.duration_seconds - quickest.duration_seconds)
                reason = (
                    f"Route {quickest.route_id} is {gap} faster but "
                    f"{_downside(criterion, quickest, best)}."
                )

    notes = []
    if no_safe:
        notes.append(
            "Every route passes through No Travel conditions at this departure time."
        )
    if best.mostly_unknown:
        notes.append(
            f"Every route has more than {_pct(UNKNOWN_SHARE_LIMIT)} of its miles without "
            f"forecast data ({_pct(best.unknown_share)} on this one), so its risk is uncertain."
        )
    else:
        for m in metrics:
            if m.mostly_unknown:
                notes.append(
                    f"Route {m.route_id} has {_pct(m.unknown_share)} of its miles without "
                    "forecast data, so it is ranked after routes with complete forecasts."
                )
        if best.incomplete:
            notes.append("Some checkpoints on this route have no forecast data (Unknown).")
    return Recommendation(
        route_id=best.route_id,
        ranking=[m.route_id for m in ranked],
        criterion=criterion,
        reason=reason,
        no_safe_route=no_safe,
        notes=notes,
    )
