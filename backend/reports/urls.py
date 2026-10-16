from django.urls import path

from .views import (
    ProfitLossReportView,
    CostPerKgReportView,
    ReceivablesReportView,
    StockInventoryReportView,
    PHIWarningsReportView,
)

urlpatterns = [
    path("farms/<int:farm_id>/reports/profit-loss/", ProfitLossReportView.as_view(), name="report-profit-loss"),
    path("farms/<int:farm_id>/reports/cost-per-kg/", CostPerKgReportView.as_view(), name="report-cost-per-kg"),
    path("farms/<int:farm_id>/reports/receivables/", ReceivablesReportView.as_view(), name="report-receivables"),
    path("farms/<int:farm_id>/reports/stock-inventory/", StockInventoryReportView.as_view(), name="report-stock-inventory"),
    path("farms/<int:farm_id>/reports/inventory/", StockInventoryReportView.as_view(), name="report-inventory-alias"),
    path("farms/<int:farm_id>/reports/phi-warnings/", PHIWarningsReportView.as_view(), name="report-phi-warnings"),
]
