from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

root = SimpleRouter()
root.register("farms", views.FarmViewSet, basename="farm")


def nested(prefix, viewset, basename):
    r = SimpleRouter()
    r.register("", viewset, basename=basename)
    return path(f"farms/<int:farm_id>/{prefix}/", include(r.urls))


urlpatterns = [
    path("", include(root.urls)),
    nested("members", views.MembershipViewSet, "member"),
    nested("planting-codes", views.PlantingCodeViewSet, "planting-code"),
    nested("plots", views.PlotViewSet, "plot"),
    nested("seasons", views.SeasonViewSet, "season"),
    path("farms/<int:farm_id>/plots/<int:plot_id>/seasons/<int:season_id>/", views.PlotSeasonView.as_view()),
]
