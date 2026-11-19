import math

import pytest

from core.geo import (
    coverage_miles,
    cumulative_miles,
    decode_polyline,
    destination_point,
    encode_polyline,
    haversine_mi,
    interpolate_at,
    overlap_ratio,
    sample_distances,
    simplify,
)


def test_haversine_known_distance():
    # Chicago -> Denver is about 920 miles great-circle.
    assert haversine_mi((41.8781, -87.6298), (39.7392, -104.9903)) == pytest.approx(920, abs=5)


def test_polyline_roundtrip_precision_5_and_6():
    coords = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert encode_polyline(coords) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    for precision in (5, 6):
        decoded = decode_polyline(encode_polyline(coords, precision), precision)
        for (a, b), (c, d) in zip(coords, decoded):
            assert a == pytest.approx(c) and b == pytest.approx(d)


@pytest.mark.parametrize(
    "total, interval, expected",
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (60, 25, [0, 25, 50, 60]),
        (50.3, 25, [0, 25, 50.3]),  # 50 is within 0.5 mi of the end -> dropped
        (5, 10, [0, 5]),  # shorter than one interval
        (0, 10, [0]),  # origin == destination
    ],
)
def test_sample_distances(total, interval, expected):
    assert sample_distances(total, interval) == pytest.approx(expected)


@pytest.mark.parametrize("marks", [[0, 25, 50, 60], [0, 5], [0, 10, 20, 30, 40, 47.3]])
def test_coverage_sums_to_total(marks):
    cov = coverage_miles(marks)
    assert sum(cov) == pytest.approx(marks[-1])
    assert cov[0] == pytest.approx(marks[1] / 2)


def test_coverage_single_point():
    assert coverage_miles([0]) == [0.0]


def test_interpolate_position_and_time():
    coords = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = cumulative_miles(coords)
    seconds = [0, 3600, 5400]  # second leg is faster
    (lat, lon), t = interpolate_at(coords, cum, seconds, cum[1] + (cum[2] - cum[1]) / 2)
    assert lon == pytest.approx(1.5) and lat == pytest.approx(0)
    assert t == pytest.approx(4500)
    assert interpolate_at(coords, cum, seconds, -1)[1] == 0
    assert interpolate_at(coords, cum, seconds, 1e9)[1] == 5400


def test_destination_point_roundtrip():
    start = (40.0, -100.0)
    end = destination_point(start, 90, 50)
    assert haversine_mi(start, end) == pytest.approx(50, rel=1e-3)


def test_simplify_keeps_endpoints_and_drops_collinear():
    line = [(0, i / 10) for i in range(101)]
    out = simplify(line)
    assert out == [line[0], line[-1]]


def test_overlap_ratio():
    a = [(40.0, -100.0 + i * 0.1) for i in range(30)]
    shifted = [(40.5, lon) for _, lon in a]  # ~35 miles north
    assert overlap_ratio(a, a) == pytest.approx(1.0)
    assert overlap_ratio(a, shifted) == 0
    assert not math.isnan(overlap_ratio(a, shifted))


def test_slice_line():
    from core.geo import slice_line

    coords = [(0.0, float(i)) for i in range(5)]
    cum = cumulative_miles(coords)
    part = slice_line(coords, cum, cum[1] / 2, cum[3])
    assert part[0][1] == pytest.approx(0.5)
    assert part[-1][1] == pytest.approx(3)
    assert [p[1] for p in part[1:-1]] == [1.0, 2.0]
