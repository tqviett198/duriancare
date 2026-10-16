from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainError
from common.permissions import ADVISOR, ALL_ROLES, OWNER, WORKER, FarmRolePermission, FarmScopedMixin

from .models import Farm, FarmMembership, PlantingCode, Plot, PlotSeason, Season
from .serializers import (FarmSerializer, MembershipSerializer, PlantingCodeSerializer,
                          PlotSeasonSerializer, PlotSerializer, SeasonSerializer)


class FarmViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Danh sách vườn mình thuộc; tạo vườn thì tự thành OWNER."""

    serializer_class = FarmSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Farm.objects.none()
        return (Farm.objects.filter(memberships__user=self.request.user)
                .prefetch_related("memberships").order_by("id"))

    @transaction.atomic
    def perform_create(self, serializer):
        farm = serializer.save(owner=self.request.user)
        FarmMembership.objects.create(farm=farm, user=self.request.user, role=OWNER)

    def perform_update(self, serializer):
        is_owner = FarmMembership.objects.filter(
            farm=serializer.instance, user=self.request.user, role=OWNER).exists()
        if not is_owner:
            raise PermissionDenied("Chỉ chủ vườn được sửa thông tin vườn.")
        serializer.save()


class MembershipViewSet(FarmScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = FarmMembership.objects.select_related("user").order_by("id")
    serializer_class = MembershipSerializer
    roles_read = (OWNER,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def _last_owner_guard(self, membership, new_role=None):
        if membership.role == OWNER and new_role != OWNER:
            owners = FarmMembership.objects.filter(farm=membership.farm, role=OWNER).count()
            if owners <= 1:
                raise DomainError("last_owner", "Không thể bỏ hoặc hạ quyền chủ vườn cuối cùng.")

    def perform_create(self, serializer):
        serializer.save(farm=self.farm)

    def perform_update(self, serializer):
        self._last_owner_guard(serializer.instance, serializer.validated_data.get("role"))
        serializer.save()

    def perform_destroy(self, instance):
        self._last_owner_guard(instance)
        instance.delete()


class PlantingCodeViewSet(FarmScopedMixin, viewsets.ModelViewSet):
    queryset = PlantingCode.objects.order_by("id")
    serializer_class = PlantingCodeSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(farm=self.farm)


class PlotViewSet(FarmScopedMixin, viewsets.ModelViewSet):
    queryset = Plot.objects.select_related("variety").order_by("id")
    serializer_class = PlotSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]   # lưu trữ bằng is_active, không xóa
    filterset_fields = ["is_active", "variety"]

    def perform_create(self, serializer):
        serializer.save(farm=self.farm)


class SeasonViewSet(FarmScopedMixin, viewsets.ModelViewSet):
    queryset = Season.objects.order_by("-start_date", "id")
    serializer_class = SeasonSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status"]

    def perform_create(self, serializer):
        serializer.save(farm=self.farm)

    @extend_schema(request=None, responses=SeasonSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request, farm_id=None, pk=None):
        season = self.get_object()
        if season.status == Season.Status.CLOSED:
            raise DomainError("season_closed", "Vụ đã đóng. Hãy tạo vụ mới.", 409)
        other = Season.objects.filter(farm_id=farm_id, status=Season.Status.ACTIVE).exclude(pk=season.pk)
        if other.exists():
            raise DomainError("active_season_exists",
                              "Vườn đã có một vụ đang diễn ra. Hãy đóng vụ đó trước.", 409)
        season.status = Season.Status.ACTIVE
        try:
            season.save(update_fields=["status"])
        except IntegrityError:
            raise DomainError("active_season_exists",
                              "Vườn đã có một vụ đang diễn ra. Hãy đóng vụ đó trước.", 409)
        return Response(self.get_serializer(season).data)

    @extend_schema(request=None, responses=SeasonSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, farm_id=None, pk=None):
        season = self.get_object()
        season.status = Season.Status.CLOSED
        season.save(update_fields=["status"])
        return Response(self.get_serializer(season).data)


class PlotSeasonView(APIView):
    """GET/PUT tiến độ một lô trong một vụ (BR-21)."""

    permission_classes = [FarmRolePermission]
    serializer_class = PlotSeasonSerializer

    def get_allowed_roles(self, request):
        return ALL_ROLES if request.method == "GET" else (OWNER,)

    def _objs(self, farm_id, plot_id, season_id):
        plot = get_object_or_404(Plot, pk=plot_id, farm_id=farm_id)
        season = get_object_or_404(Season, pk=season_id, farm_id=farm_id)
        return plot, season

    @extend_schema(responses=PlotSeasonSerializer)
    def get(self, request, farm_id, plot_id, season_id):
        plot, season = self._objs(farm_id, plot_id, season_id)
        ps = PlotSeason.objects.filter(plot=plot, season=season).first()
        return Response(PlotSeasonSerializer(ps).data if ps else PlotSeasonSerializer().to_representation(
            PlotSeason(plot=plot, season=season)))

    @extend_schema(request=PlotSeasonSerializer, responses=PlotSeasonSerializer)
    def put(self, request, farm_id, plot_id, season_id):
        plot, season = self._objs(farm_id, plot_id, season_id)
        ps = PlotSeason.objects.filter(plot=plot, season=season).first()
        ser = PlotSeasonSerializer(ps, data=request.data, context={"farm_id": int(farm_id)})
        ser.is_valid(raise_exception=True)
        ser.save(plot=plot, season=season)
        return Response(ser.data)
