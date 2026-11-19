import pytest

from risk.rules import (
    RiskLevel as R,
)
from risk.rules import (
    WeatherSample,
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    worst,
)


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, R.LOW), (24.9, R.LOW),
        (25, R.MODERATE), (34, R.MODERATE), (34.9, R.MODERATE),
        (35, R.HIGH), (44, R.HIGH), (44.9, R.HIGH),
        (45, R.SEVERE), (54, R.SEVERE), (54.9, R.SEVERE),
        (55, R.NO_TRAVEL), (80, R.NO_TRAVEL),
        (None, R.UNKNOWN),
    ],
)
def test_wind_bands(mph, expected):
    assert classify_wind(mph) is expected


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, R.LOW), (0.099, R.LOW),
        (0.10, R.MODERATE), (0.249, R.MODERATE),
        (0.25, R.HIGH), (0.499, R.HIGH),
        (0.50, R.SEVERE), (1.00, R.SEVERE),
        (1.001, R.NO_TRAVEL), (2.5, R.NO_TRAVEL),
        (None, R.UNKNOWN),
    ],
)
def test_rain_bands(inches, expected):
    assert classify_rain(inches) is expected


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, R.LOW), (0.49, R.LOW),
        (0.5, R.MODERATE), (0.99, R.MODERATE),
        (1.0, R.HIGH), (1.99, R.HIGH),
        (2.0, R.SEVERE), (3.0, R.SEVERE),
        (3.01, R.NO_TRAVEL),
        (None, R.UNKNOWN),
    ],
)
def test_snow_bands(inches, expected):
    assert classify_snow(inches) is expected


@pytest.mark.parametrize(
    "mph, load, expected",
    [
        # >=55 mph: No Travel for any load
        (55, 0, R.NO_TRAVEL),
        (55, 10_000, R.NO_TRAVEL),
        # 45-54 mph: No Travel only above 30,000 lb
        (45, 30_000, R.SEVERE),
        (45, 30_001, R.NO_TRAVEL),
        (54.9, 80_000, R.NO_TRAVEL),
        # 35-44 mph: Severe only above 40,000 lb
        (35, 40_000, R.HIGH),
        (35, 40_001, R.SEVERE),
        (44.9, 80_000, R.SEVERE),
        # below 35 mph load never matters
        (34.9, 80_000, R.MODERATE),
        (10, 80_000, R.LOW),
    ],
)
def test_load_rules(mph, load, expected):
    assert apply_load_rules(classify_wind(mph), load) is expected


def test_worst_picks_highest_known():
    assert worst([R.LOW, R.HIGH, R.MODERATE]) is R.HIGH
    assert worst([R.UNKNOWN, R.SEVERE, R.LOW]) is R.SEVERE
    assert worst([R.UNKNOWN, R.UNKNOWN, R.UNKNOWN]) is R.UNKNOWN


def test_assess_takes_max_of_conditions():
    result = assess(WeatherSample(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6), 20_000)
    assert result.level is R.HIGH
    assert result.wind is R.LOW and result.rain is R.HIGH and result.snow is R.MODERATE
    assert result.reasons == ["Rain 0.30 in/hr"]
    assert not result.incomplete


def test_assess_load_rule_reason():
    result = assess(WeatherSample(wind_mph=47, rain_in_hr=0, snow_in_hr=0), 35_000)
    assert result.level is R.NO_TRAVEL
    assert result.reasons == ["Wind 47.0 mph with 35,000 lb load"]


def test_assess_all_low_has_no_reasons():
    result = assess(WeatherSample(wind_mph=5, rain_in_hr=0, snow_in_hr=0), 80_000)
    assert result.level is R.LOW and result.reasons == []


def test_assess_missing_data_is_unknown_never_low():
    result = assess(WeatherSample(None, None, None), 10_000)
    assert result.level is R.UNKNOWN
    assert result.reasons == ["Weather data unavailable"]


def test_assess_partial_data_flags_incomplete():
    result = assess(WeatherSample(wind_mph=5, rain_in_hr=None, snow_in_hr=0), 10_000)
    assert result.level is R.LOW
    assert result.incomplete
    assert result.reasons == ["Some weather values missing"]
