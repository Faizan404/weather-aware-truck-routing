from __future__ import annotations

from core.geo import LatLon, cumulative_miles
from routing.models import Route


class ProviderUnavailable(Exception):
    """The provider failed for reasons unrelated to the trip itself."""


class NoRoute(Exception):
    """The provider says there is no drivable route between the points."""


def build_route(
    coords: list[LatLon], cum_seconds: list[float], provider: str, via_names: list[str]
) -> Route:
    return Route(
        coords=coords,
        cum_miles=cumulative_miles(coords),
        cum_seconds=cum_seconds,
        provider=provider,
        via_names=via_names,
    )
