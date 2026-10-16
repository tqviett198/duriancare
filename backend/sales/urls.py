from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import BuyerViewSet, SaleViewSet

_sale_router = SimpleRouter()
_sale_router.register("", SaleViewSet, basename="sale")

_buyer_router = SimpleRouter()
_buyer_router.register("", BuyerViewSet, basename="buyer")

urlpatterns = [
    path("farms/<int:farm_id>/sales/", include(_sale_router.urls)),
    path("farms/<int:farm_id>/buyers/", include(_buyer_router.urls)),
]
