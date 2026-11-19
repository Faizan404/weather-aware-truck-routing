from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("planner.urls")),
]


def not_found(request, exception=None):
    """Every unknown URL gets the API's JSON error shape, not an HTML page.
    (Django only uses this when DEBUG is off.)"""
    return JsonResponse(
        {"error": {"code": "not_found", "message": "Not found.", "details": {}}}, status=404
    )


handler404 = not_found
