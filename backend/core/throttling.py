"""Per-IP request throttles (DRF). Each public endpoint that triggers upstream
calls gets its own budget, so one client can't spend the shared free-API
quotas. Counters live in the Django cache (one process, see Dockerfile)."""

from rest_framework.throttling import SimpleRateThrottle

from core.client_ip import client_ip_for


class _PerIPThrottle(SimpleRateThrottle):
    def get_ident(self, request):
        return client_ip_for(request)

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PlanThrottle(_PerIPThrottle):
    scope = "plan"


class HeatmapThrottle(_PerIPThrottle):
    scope = "heatmap"


class GeocodeThrottle(_PerIPThrottle):
    scope = "geocode"
