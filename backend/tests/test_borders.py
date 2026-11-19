"""The local US check (core/borders.py): no network, real legal boundaries."""

import socket

import pytest

from core import borders


@pytest.mark.parametrize("name, lat, lon", [
    ("Chicago", 41.8781, -87.6298),
    ("Honolulu", 21.3069, -157.8583),
    ("Anchorage", 61.2181, -149.9003),
    ("Washington DC", 38.9072, -77.0369),
    ("Detroit, across the river from Windsor", 42.3314, -83.0458),
    ("San Ysidro, across the border from Tijuana", 32.5556, -117.0470),
    ("Key West", 24.5551, -81.7800),
    ("Adak, Aleutians", 51.88, -176.65),
    ("Attu, Aleutians, east of the date line", 52.90, 172.90),
    # Legal boundaries include coastal and Great Lakes waters, so shoreline
    # ports and bridges over bays count as US.
    ("Port of Miami", 25.7743, -80.1665),
    ("Navy Pier, Chicago lakefront", 41.8917, -87.6086),
    ("Mackinac Bridge", 45.817, -84.727),
    ("Chesapeake Bay Bridge-Tunnel", 37.03, -76.08),
    ("Seven Mile Bridge, Florida Keys", 24.70, -81.15),
])
def test_points_in_the_us(name, lat, lon):
    assert borders.in_us(lat, lon), name


@pytest.mark.parametrize("name, lat, lon", [
    ("Toronto", 43.6532, -79.3832),
    ("Tijuana", 32.5149, -117.0382),
    ("Windsor, Ontario", 42.3149, -83.0364),
    ("Open Pacific", 35.0, -140.0),
    ("Gulf of Mexico", 25.0, -90.0),
    ("Open Atlantic", 35.0, -70.0),
    ("Vancouver", 49.2827, -123.1207),
    ("Ciudad Juarez", 31.6904, -106.4245),
    ("San Juan, Puerto Rico (territory, not a state)", 18.4655, -66.1057),
    ("London", 51.5, -0.13),
])
def test_points_outside_the_us(name, lat, lon):
    assert not borders.in_us(lat, lon), name


def test_check_makes_no_network_calls(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("borders.in_us must not touch the network")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert borders.in_us(41.8781, -87.6298)


def test_data_is_loaded_once():
    borders._bands.cache_clear()
    borders.in_us(41.88, -87.63)
    borders.in_us(21.31, -157.86)
    assert borders._bands.cache_info().misses == 1


def test_state_borders_leave_no_gaps():
    """Neighbouring states share identical borders in the bundled data, so a
    point just beside any interior border is still in the US."""
    import json
    import math

    edges = {}
    for feature in json.loads(borders.DATA.read_text())["features"]:
        for polygon in feature["geometry"]["coordinates"]:
            for ring in polygon:
                for a, b in zip(ring, ring[1:]):
                    if a == b:  # zero-length after rounding
                        continue
                    key = tuple(sorted([tuple(a), tuple(b)]))
                    edges[key] = edges.get(key, 0) + 1
    shared = [k for k, n in edges.items() if n == 2]
    assert len(shared) > 5_000
    for (x1, y1), (x2, y2) in shared[::7]:
        mx, my, length = (x1 + x2) / 2, (y1 + y2) / 2, math.hypot(x2 - x1, y2 - y1)
        nx, ny = -(y2 - y1) / length, (x2 - x1) / length
        for side in (1e-5, -1e-5):
            assert borders.in_us(my + ny * side, mx + nx * side)


def test_bundled_data_has_50_states_and_dc():
    import json

    codes = {f["properties"]["code"] for f in json.loads(borders.DATA.read_text())["features"]}
    assert len(codes) == 51 and {"AK", "HI", "DC"} <= codes and "PR" not in codes
