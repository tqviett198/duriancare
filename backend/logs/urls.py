from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

r = SimpleRouter()
r.register("", views.FarmLogViewSet, basename="farmlog")

urlpatterns = [path("farms/<int:farm_id>/logs/", include(r.urls))]
