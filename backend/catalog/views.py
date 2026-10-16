from django.db.models import Q
from rest_framework import generics, viewsets

from common.permissions import FarmScopedMixin, OWNER

from .models import InputProduct, Variety
from .serializers import InputProductSerializer, VarietySerializer


class VarietyListView(generics.ListAPIView):
    queryset = Variety.objects.filter(is_active=True).order_by("name")
    serializer_class = VarietySerializer
    pagination_class = None


class ProductViewSet(FarmScopedMixin, viewsets.ModelViewSet):
    """Vật tư toàn cục + vật tư riêng của vườn. Chỉ sửa được vật tư riêng."""

    queryset = InputProduct.objects.order_by("name")
    serializer_class = InputProductSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["kind", "is_active"]
    search_fields = ["name"]

    def get_queryset(self):
        fid = self.kwargs["farm_id"]
        qs = InputProduct.objects.order_by("name")
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return qs.filter(Q(farm_id=fid) | Q(farm__isnull=True))
        return qs.filter(farm_id=fid)   # vật tư toàn cục chỉ admin sửa

    def perform_create(self, serializer):
        serializer.save(farm=self.farm)
