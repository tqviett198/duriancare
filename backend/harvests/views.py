import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import ADVISOR, OWNER, WORKER, FarmScopedMixin
from common.serializers import VoidSerializer

from .models import HarvestBatch, LabTest
from .serializers import (
    HarvestBatchCreateSerializer,
    HarvestBatchSerializer,
    LabTestCreateSerializer,
    LabTestSerializer,
    VoidBatchSerializer,
)
from .services import add_lab_test, create_batch, void_batch, void_lab_test



class HarvestBatchFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="harvest_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="harvest_date", lookup_expr="lte")

    class Meta:
        model = HarvestBatch
        fields = ["plot", "season", "status"]


class HarvestBatchViewSet(
    FarmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /farms/{farm_id}/harvest-batches/

    - GET list: tất cả vai trò
    - GET detail: tất cả vai trò
    - POST: OWNER, WORKER
    - POST void: OWNER
    - POST lab-tests (nested): OWNER, ADVISOR
    """

    queryset = (
        HarvestBatch.objects
        .select_related("plot", "season", "created_by")
        .prefetch_related("stocks", "lab_tests")
        .order_by("-harvest_date", "-id")
    )
    serializer_class = HarvestBatchSerializer
    filterset_class = HarvestBatchFilter
    http_method_names = ["get", "post", "head", "options"]
    roles_by_action = {
        "create": (OWNER, WORKER),
        "void": (OWNER,),
        "lab_tests": (OWNER, WORKER, ADVISOR),
        "void_lab_test_action": (OWNER,),
    }

    def _detail_response(self, batch, code=status.HTTP_200_OK):
        """Tải lại batch đầy đủ quan hệ rồi trả về."""
        batch = self.get_queryset().get(pk=batch.pk)
        return Response(self.get_serializer(batch).data, status=code)

    def create(self, request, *args, **kwargs):
        ser = HarvestBatchCreateSerializer(data=request.data,
                                           context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        batch = create_batch(
            farm=self.farm,
            plot=d["plot"],
            season=d.get("season"),
            user=request.user,
            batch_code=d["batch_code"],
            harvest_date=d["harvest_date"],
            stocks=d["stocks"],
            note=d.get("note", ""),
            override_reason=d.get("override_reason", ""),
            user_role=getattr(request, "farm_role", ""),
        )
        return self._detail_response(batch, status.HTTP_201_CREATED)

    @extend_schema(request=VoidBatchSerializer, responses=HarvestBatchSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, farm_id=None, pk=None):
        batch = self.get_object()
        ser = VoidBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        void_batch(batch=batch, user=request.user, reason=ser.validated_data["reason"])
        return self._detail_response(batch)

    @extend_schema(
        request=LabTestCreateSerializer,
        responses={200: LabTestSerializer(many=True), 201: LabTestSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="lab-tests")
    def lab_tests(self, request, farm_id=None, pk=None):
        """
        GET  /farms/{farm_id}/harvest-batches/{id}/lab-tests/ – liệt kê kiểm nghiệm.
        POST /farms/{farm_id}/harvest-batches/{id}/lab-tests/ – thêm kiểm nghiệm (BR-12, BR-13).
        Quyền POST: OWNER, ADVISOR, WORKER (theo đặc tả hợp nhất).
        """
        batch = self.get_object()

        if request.method == "GET":
            tests = LabTest.objects.filter(batch=batch).select_related("created_by")
            return Response(LabTestSerializer(tests, many=True).data)

        # POST – OWNER, ADVISOR, WORKER can record lab tests
        if getattr(request, "farm_role", None) not in (OWNER, ADVISOR, WORKER):
            return Response(
                {"detail": "Bạn không có quyền thêm kiểm nghiệm."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = LabTestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        test = add_lab_test(
            batch=batch,
            user=request.user,
            tested_date=d["tested_date"],
            lab_name=d["lab_name"],
            result=d["result"],
            analyte=d.get("analyte", ""),
            result_value=d.get("result_value"),
            limit_value=d.get("limit_value"),
            valid_until=d.get("valid_until"),
            parameters_json=d.get("parameters_json", {}),
            certificate_url=d.get("certificate_url", ""),
            note=d.get("note", ""),
        )
        # Trả về detail của batch (đã cập nhật status) kèm test mới
        batch.refresh_from_db()
        batch_data = self.get_serializer(self.get_queryset().get(pk=batch.pk)).data
        test_data = LabTestSerializer(test).data
        return Response({"batch": batch_data, "lab_test": test_data},
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=VoidSerializer, responses=HarvestBatchSerializer)
    @action(
        detail=True, methods=["post"],
        url_path=r"lab-tests/(?P<test_id>\d+)/void",
        url_name="void-lab-test",
    )
    def void_lab_test_action(self, request, farm_id=None, pk=None, test_id=None):
        """POST /farms/{farm_id}/harvest-batches/{id}/lab-tests/{test_id}/void/"""
        batch = self.get_object()
        try:
            lab_test = LabTest.objects.get(pk=test_id, batch=batch)
        except LabTest.DoesNotExist:
            return Response({"detail": "Không tìm thấy kết quả kiểm nghiệm."},
                            status=status.HTTP_404_NOT_FOUND)
        ser = VoidSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        void_lab_test(lab_test=lab_test, user=request.user, reason=ser.validated_data["reason"])
        return self._detail_response(batch)


