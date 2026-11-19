from django.urls import path

from planner import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("risk-rules/", views.risk_rules, name="risk-rules"),
    path("geocode/", views.geocode, name="geocode"),
    path("plan/", views.plan, name="plan"),
    path("heatmap/", views.corridor_heatmap, name="heatmap"),
]
