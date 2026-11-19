from __future__ import annotations

from array import array
from dataclasses import dataclass, field

from core.geo import LatLon, decode_polyline, encode_polyline


@dataclass
class Route:
    """A drivable route with per-coordinate cumulative distance and time.

    `cum_seconds[i]` is the drive time from the origin to `coords[i]`; this is
    what checkpoint ETAs are interpolated from.
    """

    coords: list[LatLon]
    cum_miles: list[float]
    cum_seconds: list[float]
    provider: str
    via_names: list[str] = field(default_factory=list)
    synthetic: bool = False  # generated via a forced waypoint

    @property
    def distance_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_seconds(self) -> float:
        return self.cum_seconds[-1]

    def thinned(self, spacing_mi: float) -> Route:
        """A copy keeping one vertex per `spacing_mi` (plus both ends). The
        kept vertices keep their original cumulative miles and seconds, so the
        route's distance, duration and checkpoint ETAs don't change."""
        if len(self.coords) <= 2:
            return self
        keep = [0]
        for i in range(1, len(self.coords) - 1):
            if self.cum_miles[i] - self.cum_miles[keep[-1]] >= spacing_mi:
                keep.append(i)
        keep.append(len(self.coords) - 1)
        return Route(
            coords=[self.coords[i] for i in keep],
            cum_miles=[self.cum_miles[i] for i in keep],
            cum_seconds=[self.cum_seconds[i] for i in keep],
            provider=self.provider,
            via_names=list(self.via_names),
            synthetic=self.synthetic,
        )

    def to_cache(self) -> dict:
        """Compact form for the cache: about 15 bytes per vertex instead of
        about 37 for the pickled lists (polyline ~1 m precision; miles and
        seconds as 4-byte floats)."""
        return {
            "polyline": encode_polyline(self.coords),
            "cum_miles": array("f", self.cum_miles),
            "cum_seconds": array("f", self.cum_seconds),
            "provider": self.provider,
            "via_names": self.via_names,
            "synthetic": self.synthetic,
        }

    @classmethod
    def from_cache(cls, data: dict) -> Route:
        return cls(
            coords=decode_polyline(data["polyline"]),
            cum_miles=list(data["cum_miles"]),
            cum_seconds=list(data["cum_seconds"]),
            provider=data["provider"],
            via_names=list(data["via_names"]),
            synthetic=data["synthetic"],
        )
