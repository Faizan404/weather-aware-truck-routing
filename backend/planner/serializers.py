from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework import serializers

from core import borders
from core.geo import decode_polyline, haversine_mi

INTERVAL_CHOICES = (10, 25, 50)
# Load = cargo weight. 80,000 lb is the US federal Interstate weight limit; 0 is
# an empty trailer (the PDF's ">= 55 mph -> No Travel for any load" rule).
MAX_LOAD_LBS = 80_000
LOAD_ERROR = "Load weight must be between 0 and 80,000 lb (US federal limit)."
# Allow a little slack for the time between filling the form and submitting.
PAST_TOLERANCE = timedelta(minutes=15)
MAX_DEPARTURE_AHEAD = timedelta(days=14)
MIN_TRIP_MILES = 0.1


class PointSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    # The API field is called "label", which shadows DRF's Field.label attribute in the stubs.
    label = serializers.CharField(required=False, allow_blank=True, max_length=300)  # type: ignore[assignment]


class AwareDateTimeField(serializers.Field):
    """ISO 8601 datetime that must carry a timezone offset (e.g. ...Z or +05:00).
    A naive time is ambiguous for a trip that crosses time zones, so reject it."""

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected an ISO 8601 string.")
        try:
            value = datetime.fromisoformat(data.replace("Z", "+00:00"))
        except ValueError:
            raise serializers.ValidationError("Invalid ISO 8601 datetime.") from None
        if value.tzinfo is None or value.utcoffset() is None:
            raise serializers.ValidationError("Include a timezone offset (ISO 8601).")
        return value

    def to_representation(self, value):
        return value.isoformat()


def validate_departure(value: datetime) -> datetime:
    now = datetime.now(UTC)
    if value < now - PAST_TOLERANCE:
        raise serializers.ValidationError("Departure time cannot be in the past.")
    if value > now + MAX_DEPARTURE_AHEAD:
        raise serializers.ValidationError(
            "Departure must be within 14 days; forecasts don't go further ahead."
        )
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    departure_time = AwareDateTimeField()
    load_weight_lbs = serializers.FloatField(
        min_value=0,
        max_value=MAX_LOAD_LBS,
        error_messages={"min_value": LOAD_ERROR, "max_value": LOAD_ERROR},
    )
    interval_miles = serializers.ChoiceField(choices=INTERVAL_CHOICES, default=25)

    def validate_departure_time(self, value):
        return validate_departure(value)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if haversine_mi((o["lat"], o["lon"]), (d["lat"], d["lon"])) < MIN_TRIP_MILES:
            raise serializers.ValidationError(
                {"destination": "Origin and destination must be different places."}
            )
        errors = {}
        for field in ("origin", "destination"):
            point = attrs[field]
            if not borders.in_us(point["lat"], point["lon"]):
                errors[field] = f"The {field} must be in the United States."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    polylines = serializers.ListField(
        child=serializers.CharField(max_length=200_000), min_length=1, max_length=3
    )
    departure_time = AwareDateTimeField()
    load_weight_lbs = serializers.FloatField(
        min_value=0,
        max_value=MAX_LOAD_LBS,
        error_messages={"min_value": LOAD_ERROR, "max_value": LOAD_ERROR},
    )

    def validate_departure_time(self, value):
        return validate_departure(value)

    def validate_polylines(self, value):
        for encoded in value:
            try:
                coords = decode_polyline(encoded)
            except (IndexError, ValueError):
                raise serializers.ValidationError("Invalid encoded polyline.") from None
            if not coords or any(abs(lat) > 90 or abs(lon) > 180 for lat, lon in coords):
                raise serializers.ValidationError("Invalid encoded polyline.")
            # Only trip corridors in the US: this endpoint fetches weather for
            # every cell along the line, so don't serve arbitrary geometry.
            if not all(borders.in_us(lat, lon) for lat, lon in coords):
                raise serializers.ValidationError("Routes must be inside the United States.")
        return value


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=3, max_length=200, trim_whitespace=True)
