"""Weather risk rules from the assessment spec.

Thresholds (per checkpoint):

    Condition  Low          Moderate    High        Severe      No Travel
    Wind       <25 mph      25-34       35-44       45-54       >=55 mph
    Rain       <0.10 in/hr  0.10-0.25   0.25-0.50   0.50-1.00   >1.00
    Snow       <0.5 in/hr   0.5-1.0     1.0-2.0     2.0-3.0     >3.0

The table shares values at band edges (e.g. 0.25 is in both Moderate and High),
so bands are made unambiguous: each band includes its lower bound, and the
upper bound of Severe is inclusive because No Travel is strictly ">".
Wind is read as continuous mph, so "25-34" means [25, 35).

Load rules (wind only, weight compared strictly with ">"):
    >=55 mph                 -> No Travel for any load
    45-54 mph and >30,000 lb -> No Travel
    35-44 mph and >40,000 lb -> Severe

A checkpoint's level is the worst of its wind (after load rules), rain and snow
levels. Missing data gives UNKNOWN; it is never treated as Low.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(Enum):
    LOW = ("low", "Low", 0)
    MODERATE = ("moderate", "Moderate", 1)
    HIGH = ("high", "High", 2)
    SEVERE = ("severe", "Severe", 3)
    NO_TRAVEL = ("no_travel", "No Travel", 4)
    UNKNOWN = ("unknown", "Unknown", None)

    def __init__(self, key: str, label: str, score: int | None):
        self.key = key
        self.label = label
        self.score = score

    @property
    def rank(self) -> int:
        """Score for ordering; UNKNOWN sorts below every known level."""
        return -1 if self.score is None else self.score

    @classmethod
    def ranked(cls) -> list[RiskLevel]:
        return [cls.LOW, cls.MODERATE, cls.HIGH, cls.SEVERE, cls.NO_TRAVEL]


# (lower bound, level, lower bound inclusive?) in ascending order.
# A value falls in the highest band whose lower bound it meets.
Band = tuple[float, RiskLevel, bool]

WIND_BANDS: list[Band] = [
    (25.0, RiskLevel.MODERATE, True),
    (35.0, RiskLevel.HIGH, True),
    (45.0, RiskLevel.SEVERE, True),
    (55.0, RiskLevel.NO_TRAVEL, True),
]
RAIN_BANDS: list[Band] = [
    (0.10, RiskLevel.MODERATE, True),
    (0.25, RiskLevel.HIGH, True),
    (0.50, RiskLevel.SEVERE, True),
    (1.00, RiskLevel.NO_TRAVEL, False),
]
SNOW_BANDS: list[Band] = [
    (0.5, RiskLevel.MODERATE, True),
    (1.0, RiskLevel.HIGH, True),
    (2.0, RiskLevel.SEVERE, True),
    (3.0, RiskLevel.NO_TRAVEL, False),
]

HEAVY_LOAD_NO_TRAVEL_LBS = 30_000  # with 45-54 mph wind
HEAVY_LOAD_SEVERE_LBS = 40_000  # with 35-44 mph wind


def classify(value: float | None, bands: list[Band]) -> RiskLevel:
    if value is None:
        return RiskLevel.UNKNOWN
    level = RiskLevel.LOW
    for bound, band_level, inclusive in bands:
        if value > bound or (inclusive and value == bound):
            level = band_level
    return level


def classify_wind(wind_mph: float | None) -> RiskLevel:
    return classify(wind_mph, WIND_BANDS)


def classify_rain(rain_in_hr: float | None) -> RiskLevel:
    return classify(rain_in_hr, RAIN_BANDS)


def classify_snow(snow_in_hr: float | None) -> RiskLevel:
    return classify(snow_in_hr, SNOW_BANDS)


def apply_load_rules(wind_level: RiskLevel, load_lbs: float) -> RiskLevel:
    """Raise the wind level for heavy loads, as the spec's load rules say."""
    if wind_level is RiskLevel.SEVERE and load_lbs > HEAVY_LOAD_NO_TRAVEL_LBS:
        return RiskLevel.NO_TRAVEL
    if wind_level is RiskLevel.HIGH and load_lbs > HEAVY_LOAD_SEVERE_LBS:
        return RiskLevel.SEVERE
    return wind_level


def worst(levels: list[RiskLevel]) -> RiskLevel:
    """Worst known level, or UNKNOWN if nothing is known. With partial data
    the true level is at least the worst known one, so that is what we use;
    callers flag the result as incomplete."""
    known = [lvl for lvl in levels if lvl is not RiskLevel.UNKNOWN]
    return max(known, key=lambda lvl: lvl.rank) if known else RiskLevel.UNKNOWN


@dataclass(frozen=True)
class WeatherSample:
    wind_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    reasons: list[str] = field(default_factory=list)
    incomplete: bool = False


def assess(sample: WeatherSample, load_lbs: float) -> RiskAssessment:
    base_wind = classify_wind(sample.wind_mph)
    wind = apply_load_rules(base_wind, load_lbs)
    rain = classify_rain(sample.rain_in_hr)
    snow = classify_snow(sample.snow_in_hr)
    level = worst([wind, rain, snow])
    incomplete = RiskLevel.UNKNOWN in (wind, rain, snow)

    reasons: list[str] = []
    if level is RiskLevel.UNKNOWN:
        reasons.append("Weather data unavailable")
    elif level is not RiskLevel.LOW:
        if wind is level:
            text = f"Wind {sample.wind_mph:.1f} mph"
            if wind is not base_wind:
                text += f" with {load_lbs:,.0f} lb load"
            reasons.append(text)
        if rain is level:
            reasons.append(f"Rain {sample.rain_in_hr:.2f} in/hr")
        if snow is level:
            reasons.append(f"Snow {sample.snow_in_hr:.2f} in/hr")
    if incomplete and level is not RiskLevel.UNKNOWN:
        reasons.append("Some weather values missing")
    return RiskAssessment(
        level=level, wind=wind, rain=rain, snow=snow, reasons=reasons, incomplete=incomplete
    )


def rules_payload() -> dict:
    """Thresholds as JSON for the frontend legend (single source of truth)."""

    def bands(spec: list[Band], unit: str) -> list[dict]:
        out: list[dict[str, object]] = [{"level": RiskLevel.LOW.key, "min": None, "min_inclusive": True}]
        out += [{"level": lvl.key, "min": b, "min_inclusive": inc} for b, lvl, inc in spec]
        return [dict(item, unit=unit) for item in out]

    return {
        "levels": [
            {"key": lvl.key, "label": lvl.label, "score": lvl.score}
            for lvl in [*RiskLevel.ranked(), RiskLevel.UNKNOWN]
        ],
        "conditions": {
            "wind": bands(WIND_BANDS, "mph"),
            "rain": bands(RAIN_BANDS, "in/hr"),
            "snow": bands(SNOW_BANDS, "in/hr"),
        },
        "load_rules": [
            # load_over_lbs None = any load, including an empty trailer.
            {"wind_min_mph": 55, "load_over_lbs": None, "result": RiskLevel.NO_TRAVEL.key},
            {"wind_min_mph": 45, "wind_max_mph": 54, "load_over_lbs": HEAVY_LOAD_NO_TRAVEL_LBS,
             "result": RiskLevel.NO_TRAVEL.key},
            {"wind_min_mph": 35, "wind_max_mph": 44, "load_over_lbs": HEAVY_LOAD_SEVERE_LBS,
             "result": RiskLevel.SEVERE.key},
        ],
    }
