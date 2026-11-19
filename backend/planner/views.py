from django.conf import settings
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.request import Request
from rest_framework.response import Response

from core.deadline import deadline
from core.health import health_payload
from core.throttling import GeocodeThrottle, HeatmapThrottle, PlanThrottle
from planner.serializers import (
    GeocodeQuerySerializer,
    HeatmapRequestSerializer,
    PlanRequestSerializer,
)
from planner.services import TripRequest, heatmap, plan_trip
from risk.rules import rules_payload
from routing import geocoding


@api_view(["GET", "HEAD"])
def health(request: Request) -> Response:
    # Normally answered earlier by core.middleware.HealthCheckMiddleware; this
    # view serves the same payload if that middleware is ever removed.
    return Response(health_payload())


@api_view(["GET"])
def risk_rules(request: Request) -> Response:
    return Response(rules_payload())


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def geocode(request: Request) -> Response:
    params = GeocodeQuerySerializer(data=request.query_params)
    params.is_valid(raise_exception=True)
    return Response({"results": geocoding.search(params.validated_data["q"])})


@api_view(["POST"])
@throttle_classes([PlanThrottle])
def plan(request: Request) -> Response:
    body = PlanRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    trip = TripRequest(
        origin=(data["origin"]["lat"], data["origin"]["lon"]),
        destination=(data["destination"]["lat"], data["destination"]["lon"]),
        departure=data["departure_time"],
        load_lbs=data["load_weight_lbs"],
        interval_miles=int(data["interval_miles"]),
    )
    with deadline(settings.PLAN_DEADLINE_SECONDS):
        return Response(plan_trip(trip))


@api_view(["POST"])
@throttle_classes([HeatmapThrottle])
def corridor_heatmap(request: Request) -> Response:
    body = HeatmapRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    with deadline(settings.PLAN_DEADLINE_SECONDS):
        return Response(
            heatmap(data["polylines"], data["departure_time"], data["load_weight_lbs"])
        )
