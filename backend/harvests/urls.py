from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import HarvestBatchViewSet

_r = SimpleRouter()
_r.register("", HarvestBatchViewSet, basename="harvest-batch")

# Hỗ trợ cả 2 chuẩn URL:
# - /farms/{farm_id}/batches/ (chuẩn đặc tả)
# - /farms/{farm_id}/harvest-batches/ (tương thích ngược)
urlpatterns = [
    path("farms/<int:farm_id>/harvest-batches/", include(_r.urls)),
    path("farms/<int:farm_id>/batches/", include(_r.urls)),
]

