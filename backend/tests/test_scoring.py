import pytest

from risk.rules import RiskLevel as R
from risk.scoring import recommend, route_metrics


def metrics(route_id, levels, coverage=None, duration=3600.0):
    coverage = coverage or [10.0] * len(levels)
    return route_metrics(route_id, sum(coverage), duration, levels, coverage)


def test_miles_by_level_and_weighted_average():
    m = metrics("A", [R.LOW, R.HIGH, R.SEVERE], [10, 20, 10])
    assert m.miles_by_level["high"] == 20
    assert m.severe_miles == 10
    assert m.avg_risk == pytest.approx((0 * 10 + 2 * 20 + 3 * 10) / 40)
    assert m.max_level is R.SEVERE
    assert sum(m.miles_by_level.values()) + m.unknown_miles == pytest.approx(40)


def test_unknown_excluded_from_average_and_flagged():
    m = metrics("A", [R.HIGH, R.UNKNOWN], [10, 30])
    assert m.avg_risk == pytest.approx(2.0)
    assert m.unknown_miles == 30
    assert m.incomplete


def test_all_unknown_average_is_none():
    m = metrics("A", [R.UNKNOWN, R.UNKNOWN])
    assert m.avg_risk is None and m.max_level is R.UNKNOWN


def test_single_point_route_uses_plain_mean():
    m = route_metrics("A", 0.0, 0.0, [R.HIGH], [0.0])
    assert m.avg_risk == 2.0


def test_criterion_1_fewest_severe_miles():
    a = metrics("A", [R.SEVERE, R.LOW, R.LOW], duration=9000)
    b = metrics("B", [R.HIGH, R.HIGH, R.HIGH], duration=9000)
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert rec.criterion == "severe_miles"
    assert "Fewest Severe miles" in rec.reason


def test_no_travel_ranks_worse_than_severe():
    a = metrics("A", [R.NO_TRAVEL, R.LOW, R.LOW])  # 10 mi No Travel
    b = metrics("B", [R.SEVERE, R.SEVERE, R.LOW])  # 20 mi Severe
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert rec.criterion == "no_travel_miles"
    assert not rec.no_safe_route


def test_criterion_2_fewest_high_miles():
    a = metrics("A", [R.HIGH, R.HIGH, R.LOW])
    b = metrics("B", [R.HIGH, R.MODERATE, R.MODERATE])
    rec = recommend([a, b])
    assert rec.route_id == "B" and rec.criterion == "high_miles"


def test_criterion_3_lowest_average_risk():
    a = metrics("A", [R.MODERATE, R.MODERATE, R.LOW], duration=100)
    b = metrics("B", [R.MODERATE, R.LOW, R.LOW], duration=200)
    rec = recommend([a, b])
    assert rec.route_id == "B" and rec.criterion == "avg_risk"


def test_criterion_4_shortest_travel_time():
    a = metrics("A", [R.LOW, R.LOW], duration=7200)
    b = metrics("B", [R.LOW, R.LOW], duration=3600)
    c = metrics("C", [R.LOW, R.LOW], duration=5400)
    rec = recommend([a, b, c])
    assert rec.route_id == "B"
    assert rec.ranking == ["B", "C", "A"]
    assert rec.criterion == "duration_seconds"
    assert "1h 00m vs 1h 30m" in rec.reason


def test_float_noise_does_not_decide():
    a = metrics("A", [R.SEVERE], [10.0000001], duration=100)
    b = metrics("B", [R.SEVERE], [10.0], duration=200)
    assert recommend([a, b]).route_id == "A"  # tie on miles -> faster wins


def test_full_tie_keeps_first_route():
    a = metrics("A", [R.LOW])
    b = metrics("B", [R.LOW])
    rec = recommend([a, b])
    assert rec.route_id == "A" and rec.criterion is None


def test_no_safe_route_flag():
    a = metrics("A", [R.NO_TRAVEL, R.LOW])
    b = metrics("B", [R.NO_TRAVEL, R.NO_TRAVEL])
    rec = recommend([a, b])
    assert rec.route_id == "A"
    assert rec.no_safe_route
    assert rec.notes


def test_single_route():
    rec = recommend([metrics("A", [R.LOW])])
    assert rec.route_id == "A" and "Only one route" in rec.reason


def test_reason_shows_seconds_when_minutes_match():
    a = metrics("A", [R.LOW], duration=13 * 60 + 5)
    b = metrics("B", [R.LOW], duration=13 * 60 + 20)
    assert "13m 05s vs 13m 20s" in recommend([a, b]).reason


def test_reason_short_durations_in_minutes():
    a = metrics("A", [R.LOW], duration=10 * 60)
    b = metrics("B", [R.LOW], duration=25 * 60)
    assert "10 min vs 25 min" in recommend([a, b]).reason


# --- Unknown data ---------------------------------------------------------------

def test_mostly_unknown_route_ranks_after_known_routes():
    # A looks perfect but 2 of 3 checkpoints have no forecast (67% Unknown).
    a = metrics("A", [R.LOW, R.UNKNOWN, R.UNKNOWN], duration=100)
    b = metrics("B", [R.HIGH, R.HIGH, R.LOW], duration=9000)
    rec = recommend([a, b])
    assert rec.route_id == "B" and rec.ranking == ["B", "A"]
    assert rec.criterion == "forecast_coverage"
    assert "67% of it has no forecast data" in rec.reason
    assert any("Route A has 67%" in n and "ranked after" in n for n in rec.notes)


def test_up_to_ten_percent_unknown_still_competes():
    a = metrics("A", [R.LOW, R.UNKNOWN], [90, 10], duration=100)  # exactly 10%
    b = metrics("B", [R.LOW, R.LOW], [50, 50], duration=200)
    rec = recommend([a, b])
    assert rec.route_id == "A"
    assert not any("ranked after" in n for n in rec.notes)
    assert any("no forecast data (Unknown)" in n for n in rec.notes)


def test_all_routes_mostly_unknown_is_noted():
    a = metrics("A", [R.LOW, R.UNKNOWN])
    b = metrics("B", [R.UNKNOWN, R.UNKNOWN])
    rec = recommend([a, b])
    assert rec.route_id == "A"
    assert any("Every route has more than 10%" in n for n in rec.notes)


# --- Average risk tolerance -----------------------------------------------------

def test_tiny_average_risk_difference_lets_time_decide():
    # The Atlanta -> Miami case: 0.03 vs 0.04 must not pick a 6 h longer detour.
    a = metrics("A", [R.MODERATE] + [R.LOW] * 24, duration=10 * 3600)  # avg 0.04
    b = metrics("B", [R.MODERATE] + [R.LOW] * 32, duration=16 * 3600)  # avg 0.03
    assert round(a.avg_risk, 2) == 0.04 and round(b.avg_risk, 2) == 0.03
    rec = recommend([a, b])
    assert rec.route_id == "A" and rec.criterion == "duration_seconds"


def test_average_risk_difference_of_point_one_still_decides():
    a = metrics("A", [R.MODERATE, R.LOW, R.LOW, R.LOW, R.LOW] * 2, duration=100)  # 0.20
    b = metrics("B", [R.MODERATE] + [R.LOW] * 9, duration=200)  # 0.10
    rec = recommend([a, b])
    assert rec.route_id == "B" and rec.criterion == "avg_risk"


def test_spec_order_still_puts_high_miles_before_average():
    a = metrics("A", [R.HIGH, R.LOW, R.LOW, R.LOW], duration=100)
    b = metrics("B", [R.MODERATE] * 4, duration=200)
    assert recommend([a, b]).route_id == "B"


# --- Reason mentions a faster route that lost --------------------------------------

def test_reason_explains_faster_route_that_lost():
    a = metrics("A", [R.HIGH, R.LOW], [25, 75], duration=8 * 3600)
    b = metrics("B", [R.MODERATE, R.LOW], [25, 75], duration=10 * 3600)
    c = metrics("C", [R.LOW, R.LOW], [25, 85], duration=12 * 3600)
    rec = recommend([a, b, c])
    assert rec.route_id == "C"
    assert rec.reason == "Route A is 4h 00m faster but has 25 mi of High risk."
    assert rec.criterion == "high_miles"


def test_reason_compares_against_both_when_winner_has_some_risk():
    a = metrics("A", [R.SEVERE, R.SEVERE, R.LOW], duration=3600)
    b = metrics("B", [R.SEVERE, R.LOW, R.LOW], duration=5400)
    assert recommend([a, b]).reason == (
        "Route A is 30 min faster but has 20 mi of Severe risk (vs 10 mi)."
    )


def test_reason_unchanged_when_winner_is_fastest():
    a = metrics("A", [R.LOW], duration=3600)
    b = metrics("B", [R.HIGH], duration=7200)
    assert recommend([a, b]).reason.startswith("Fewest High miles")
