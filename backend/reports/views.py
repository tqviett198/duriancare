"""
Views cho API Reports.

Endpoints:
- GET /farms/{farm_id}/reports/profit-loss/ (OWNER)
- GET /farms/{farm_id}/reports/cost-per-kg/ (OWNER)
- GET /farms/{farm_id}/reports/receivables/ (OWNER)
- GET /farms/{farm_id}/reports/stock-inventory/ (OWNER, ADVISOR, WORKER)
- GET /farms/{farm_id}/reports/phi-warnings/ (OWNER, ADVISOR, WORKER)
"""
from datetime import datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import FarmScopedMixin, OWNER, ADVISOR, WORKER
from farms.models import Season
from .services import (
    get_profit_loss_report,
    get_cost_per_kg_report,
    get_receivables_report,
    get_stock_inventory_report,
    get_phi_warnings_report,
)


class ProfitLossReportView(FarmScopedMixin, APIView):
    """
    Báo cáo lãi lỗ (P&L) cho mùa vụ hoặc khoảng thời gian.
    Chỉ OWNER được xem.
    """
    roles_read = (OWNER,)

    @extend_schema(
        parameters=[
            OpenApiParameter("season_id", int, description="ID mùa vụ (tùy chọn)"),
            OpenApiParameter("date_from", str, description="Từ ngày (YYYY-MM-DD)"),
            OpenApiParameter("date_to", str, description="Đến ngày (YYYY-MM-DD)"),
        ],
        responses={200: dict},
    )
    def get(self, request, farm_id=None):
        season_id = request.query_params.get("season_id")
        date_from_str = request.query_params.get("date_from")
        date_to_str = request.query_params.get("date_to")

        season = None
        if season_id:
            try:
                season = Season.objects.get(id=season_id, farm=self.farm)
            except Season.DoesNotExist:
                return Response({"detail": "Mùa vụ không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else None
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else None

        data = get_profit_loss_report(
            farm=self.farm,
            season=season,
            date_from=date_from,
            date_to=date_to,
        )
        return Response(data)


class CostPerKgReportView(FarmScopedMixin, APIView):
    """
    BR-24: Báo cáo giá thành theo kg cho mùa vụ.
    Chỉ OWNER được xem.
    """
    roles_read = (OWNER,)

    @extend_schema(
        parameters=[
            OpenApiParameter("season_id", int, description="ID mùa vụ (bắt buộc hoặc lấy ACTIVE season)"),
        ],
        responses={200: dict},
    )
    def get(self, request, farm_id=None):
        season_id = request.query_params.get("season_id")
        if season_id:
            try:
                season = Season.objects.get(id=season_id, farm=self.farm)
            except Season.DoesNotExist:
                return Response({"detail": "Mùa vụ không tồn tại."}, status=status.HTTP_404_NOT_FOUND)
        else:
            season = Season.objects.filter(farm=self.farm, status=Season.Status.ACTIVE).first()
            if not season:
                season = Season.objects.filter(farm=self.farm).order_by("-start_date").first()

        if not season:
            return Response(
                {"detail": "Vui lòng chọn hoặc tạo ít nhất một mùa vụ để tính giá thành."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = get_cost_per_kg_report(farm=self.farm, season=season)
        return Response(data)


class ReceivablesReportView(FarmScopedMixin, APIView):
    """
    Báo cáo công nợ người mua.
    Chỉ OWNER được xem.
    """
    roles_read = (OWNER,)

    @extend_schema(responses={200: dict})
    def get(self, request, farm_id=None):
        data = get_receivables_report(farm=self.farm)
        return Response(data)


class StockInventoryReportView(FarmScopedMixin, APIView):
    """
    Báo cáo tồn kho sầu riêng phân theo phẩm cấp.
    OWNER, ADVISOR, WORKER đều được xem.
    """
    roles_read = (OWNER, ADVISOR, WORKER)

    @extend_schema(responses={200: dict})
    def get(self, request, farm_id=None):
        data = get_stock_inventory_report(farm=self.farm)
        return Response(data)


class PHIWarningsReportView(FarmScopedMixin, APIView):
    """
    Báo cáo cảnh báo thời gian an toàn cách ly thuốc BVTV (PHI).
    OWNER, ADVISOR, WORKER đều được xem.
    """
    roles_read = (OWNER, ADVISOR, WORKER)

    @extend_schema(
        parameters=[
            OpenApiParameter("as_of_date", str, description="Ngày mốc kiểm tra (YYYY-MM-DD, mặc định hôm nay)"),
        ],
        responses={200: dict},
    )
    def get(self, request, farm_id=None):
        as_of_str = request.query_params.get("as_of_date")
        as_of_date = datetime.strptime(as_of_str, "%Y-%m-%d").date() if as_of_str else None
        data = get_phi_warnings_report(farm=self.farm, as_of_date=as_of_date)
        return Response(data)
