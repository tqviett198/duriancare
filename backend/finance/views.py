import django_filters
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.exceptions import DomainError
from common.serializers import VoidSerializer
from common.models import audit
from common.permissions import OWNER, FarmScopedMixin

from .models import LedgerEntry
from .serializers import LedgerEntrySerializer


class LedgerFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="txn_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="txn_date", lookup_expr="lte")

    class Meta:
        model = LedgerEntry
        fields = ["type", "category", "plot", "season", "status"]


class LedgerViewSet(FarmScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Thu chi — chỉ chủ vườn thấy (ma trận quyền mục 3.2)."""

    queryset = LedgerEntry.objects.order_by("-txn_date", "-id")
    serializer_class = LedgerEntrySerializer
    roles_read = (OWNER,)
    roles_write = (OWNER,)
    filterset_class = LedgerFilter
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(farm=self.farm, created_by=self.request.user)

    def perform_update(self, serializer):
        entry = serializer.instance
        if entry.source_log_id:
            raise DomainError("generated_entry_readonly",
                              "Khoản chi này tự sinh từ nhật ký; hãy sửa nhật ký thay vì sửa tay.", 409)
        if entry.status == LedgerEntry.Status.VOIDED:
            raise DomainError("entry_voided", "Khoản này đã hủy, không sửa được.", 409)
        serializer.save()

    @extend_schema(request=VoidSerializer, responses=LedgerEntrySerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def void(self, request, farm_id=None, pk=None):
        entry = self.get_object()
        if entry.source_log_id:
            raise DomainError("generated_entry_readonly",
                              "Khoản chi tự sinh chỉ hủy được bằng cách hủy nhật ký.", 409)
        if entry.status == LedgerEntry.Status.VOIDED:
            raise DomainError("already_voided", "Khoản này đã được hủy trước đó.", 409)
        ser = VoidSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        entry.status = LedgerEntry.Status.VOIDED
        entry.void_reason = ser.validated_data["reason"]
        entry.voided_by, entry.voided_at = request.user, timezone.now()
        entry.save()
        audit(farm=self.farm, actor=request.user, action="LEDGER_VOID", entity=entry,
              reason=entry.void_reason)
        return Response(self.get_serializer(entry).data)
