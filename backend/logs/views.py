import django_filters
from datetime import timedelta
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import serializers

from common.exceptions import DomainError
from common.serializers import VoidSerializer
from common.permissions import ADVISOR, OWNER, WORKER, FarmScopedMixin

from .models import FarmLog
from .serializers import FarmLogSerializer
from .services import save_log, void_log


class FarmLogFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="activity_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="activity_date", lookup_expr="lte")

    class Meta:
        model = FarmLog
        fields = ["plot", "activity_type", "season", "status"]


class FarmLogViewSet(FarmScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = (FarmLog.objects.select_related("plot", "season")
                .prefetch_related("inputs", "expenses").order_by("-activity_date", "-id"))
    serializer_class = FarmLogSerializer
    farm_field = "plot__farm_id"
    filterset_class = FarmLogFilter
    http_method_names = ["get", "post", "patch", "head", "options"]
    roles_by_action = {
        "create": (OWNER, WORKER),
        "partial_update": (OWNER, WORKER),
        "void": (OWNER,),
    }
    WORKER_EDIT_WINDOW = timedelta(hours=24)

    def _respond(self, log, warnings, code):
        log = self.get_queryset().get(pk=log.pk)
        data = self.get_serializer(log).data
        data["warnings"] = warnings
        return Response(data, status=code)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        log, warnings, _ = save_log(farm=self.farm, user=request.user, data=ser.validated_data)
        return self._respond(log, warnings, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        log = self.get_object()
        if log.status == FarmLog.Status.VOIDED:
            raise DomainError("log_voided", "Nhật ký đã hủy, không sửa được.", 409)
        if request.farm_role == WORKER:       # người làm chỉ sửa bản của mình trong 24 giờ
            own = log.created_by_id == request.user.id
            fresh = timezone.now() - log.created_at <= self.WORKER_EDIT_WINDOW
            if not (own and fresh):
                raise PermissionDenied("Bạn chỉ được sửa nhật ký do mình tạo trong 24 giờ.")
        ser = self.get_serializer(log, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        log, warnings, _ = save_log(farm=self.farm, user=request.user, data=ser.validated_data, log=log)
        return self._respond(log, warnings, status.HTTP_200_OK)

    @extend_schema(request=VoidSerializer, responses=FarmLogSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, farm_id=None, pk=None):
        log = self.get_object()
        reason = VoidSerializer(data=request.data)
        reason.is_valid(raise_exception=True)
        void_log(log=log, user=request.user, reason=reason.validated_data["reason"])
        return self._respond(log, [], status.HTTP_200_OK)
