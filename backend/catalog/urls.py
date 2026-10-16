from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

r = SimpleRouter()
r.register("", views.ProductViewSet, basename="product")

urlpatterns = [
    path("varieties/", views.VarietyListView.as_view()),
    path("farms/<int:farm_id>/products/", include(r.urls)),
]
