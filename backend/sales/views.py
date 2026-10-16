import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import ADVISOR, OWNER, WORKER, FarmScopedMixin
from common.serializers import VoidSerializer

from .models import Buyer, Payment, Sale
from .serializers import (
    BuyerCreateSerializer,
    BuyerSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    SaleCreateSerializer,
    SaleSerializer,
)
from .services import add_payment, create_sale, void_payment, void_sale


# ─────────────────────────────────────────────────────────────────────────────
# Buyer
# ─────────────────────────────────────────────────────────────────────────────

class BuyerFilter(django_filters.FilterSet):
    class Meta:
        model = Buyer
        fields = ["is_export"]


class BuyerViewSet(
    FarmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /farms/{farm_id}/buyers/

    - GET list/detail: OWNER
    - POST create: OWNER
    - PUT/PATCH update: OWNER
    """
    queryset = Buyer.objects.all()
    serializer_class = BuyerSerializer
    filterset_class = BuyerFilter
    roles_read = (OWNER,)
    roles_write = (OWNER,)

    def create(self, request, *args, **kwargs):
        ser = BuyerCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        buyer = Buyer.objects.create(farm=self.farm, **d)
        return Response(BuyerSerializer(buyer).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        buyer = self.get_object()
        ser = BuyerSerializer(buyer, data=request.data, partial=kwargs.get("partial", False))
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Sale
# ─────────────────────────────────────────────────────────────────────────────

class SaleFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="sale_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="sale_date", lookup_expr="lte")

    class Meta:
        model = Sale
        fields = ["status", "payment_status"]


class SaleViewSet(
    FarmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /farms/{farm_id}/sales/

    - GET list / detail: OWNER (WORKER và ADVISOR không thấy tài chính)
    - POST create: OWNER
    - POST void: OWNER
    - POST payment: OWNER
    - POST void_payment: OWNER
    """

    queryset = (
        Sale.objects
        .select_related("created_by", "buyer")
        .prefetch_related("lines__stock__batch", "payments")
    )
    serializer_class = SaleSerializer
    filterset_class = SaleFilter
    http_method_names = ["get", "post", "head", "options"]
    # WORKER và ADVISOR không được xem bán hàng / tài chính
    roles_read = (OWNER,)
    roles_write = (OWNER,)
    roles_by_action = {
        "void": (OWNER,),
        "add_payment": (OWNER,),
        "payments": (OWNER,),
        "void_payment_action": (OWNER,),
    }


    def _detail_response(self, sale, code=status.HTTP_200_OK):
        """Tải lại sale đầy đủ quan hệ rồi trả về."""
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(self.get_serializer(sale).data, status=code)

    def create(self, request, *args, **kwargs):
        ser = SaleCreateSerializer(
            data=request.data, context=self.get_serializer_context(),
        )
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        sale = create_sale(
            farm=self.farm,
            user=request.user,
            sale_code=d["sale_code"],
            sale_date=d["sale_date"],
            buyer=d.get("buyer"),
            customer_name=d["customer_name"],
            customer_phone=d.get("customer_phone", ""),
            season=d.get("season"),
            destination=d.get("destination", "DOMESTIC"),
            lines=d["lines"],
            note=d.get("note", ""),
        )
        return self._detail_response(sale, status.HTTP_201_CREATED)

    @extend_schema(request=VoidSerializer, responses=SaleSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, farm_id=None, pk=None):
        sale = self.get_object()
        ser = VoidSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        void_sale(sale=sale, user=request.user, reason=ser.validated_data["reason"])
        return self._detail_response(sale)

    @extend_schema(request=PaymentCreateSerializer, responses=SaleSerializer)
    @action(detail=True, methods=["post"])
    def add_payment(self, request, farm_id=None, pk=None):
        """POST /farms/{farm_id}/sales/{id}/add_payment/ – BR-18."""
        sale = self.get_object()
        ser = PaymentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        add_payment(
            sale=sale,
            user=request.user,
            amount=d["amount"],
            payment_date=d["payment_date"],
            method=d.get("method", "CASH"),
            reference=d.get("reference", ""),
            note=d.get("note", ""),
        )
        return self._detail_response(sale)

    @extend_schema(request=PaymentCreateSerializer, responses=SaleSerializer)
    @action(detail=True, methods=["post"], url_path="payments")
    def payments(self, request, farm_id=None, pk=None):
        """POST /farms/{farm_id}/sales/{id}/payments/ – BR-18 (chuẩn đặc tả)."""
        return self.add_payment(request, farm_id=farm_id, pk=pk)


    @extend_schema(request=VoidSerializer, responses=SaleSerializer)
    @action(
        detail=True, methods=["post"],
        url_path=r"payments/(?P<payment_id>\d+)/void",
        url_name="void-payment",
    )
    def void_payment_action(self, request, farm_id=None, pk=None, payment_id=None):
        """POST /farms/{farm_id}/sales/{id}/payments/{payment_id}/void/ – Phase 2."""
        sale = self.get_object()
        payment = Payment.objects.get(pk=payment_id, sale=sale)
        ser = VoidSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        void_payment(payment=payment, user=request.user, reason=ser.validated_data["reason"])
        return self._detail_response(sale)
