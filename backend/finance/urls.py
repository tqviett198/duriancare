from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

r = SimpleRouter()
r.register("", views.LedgerViewSet, basename="transaction")

urlpatterns = [path("farms/<int:farm_id>/transactions/", include(r.urls))]
