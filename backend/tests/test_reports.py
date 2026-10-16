"""
Tests cho app reports – bao gồm:
- BR-24: Báo cáo giá thành theo kg (bộ dữ liệu mẫu tính tay mục 16.2 đặc tả)
- Báo cáo Lãi lỗ (P&L) theo mùa vụ (BR-15: doanh thu chỉ từ Sale, chi phí từ LedgerEntry)
- Báo cáo Công nợ người mua (Receivables)
- Báo cáo Tồn kho theo phẩm cấp (Stock Inventory)
- Báo cáo Cảnh báo ngày cách ly thuốc BVTV (PHI Warnings)
- Ma trận phân quyền: WORKER/ADVISOR bị chặn tài chính (403), được xem PHI & tồn kho
"""
from datetime import date, timedelta
from decimal import Decimal

from common.exceptions import DomainError
from farms.models import Plot, Season
from finance.models import LedgerEntry
from harvests.models import HarvestBatch, BatchStock, BatchGrade, LabTest
from harvests.services import create_batch, add_lab_test
from logs.models import FarmLog, FarmLogInput
from reports.services import (
    get_cost_per_kg_report,
    get_profit_loss_report,
    get_receivables_report,
    get_stock_inventory_report,
    get_phi_warnings_report,
)
from sales.models import Sale, Buyer
from sales.services import create_sale, add_payment
from tests.base import BaseTest

API = "/api/v1"
TODAY = date.today()


class ReportsTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.plot1 = Plot.objects.create(
            farm=self.farm_a, name="Lô A1 (Thử nghiệm)", area_ha=Decimal("2.00"),
            variety=self.ri6, tree_count=80,
        )
        self.plot2 = Plot.objects.create(
            farm=self.farm_a, name="Lô A2 (Mở rộng)", area_ha=Decimal("3.00"),
            variety=self.ri6, tree_count=120,
        )


    def test_section_16_2_manual_cost_per_kg_calculation(self):
        """
        BR-24 & Mục 16.2 đặc tả: Bộ dữ liệu mẫu tính tay giá thành / kg.

        Dữ liệu:
        - Plot 1 (2.0 ha = 40% diện tích)
        - Plot 2 (3.0 ha = 60% diện tích)
        - Tổng diện tích vườn = 5.0 ha

        Chi phí:
        - Trực tiếp Plot 1 = 30.000.000 đ
        - Trực tiếp Plot 2 = 45.000.000 đ
        - Chi phí chung (điện nước, thuê đất - plot=None) = 50.000.000 đ

        Phân bổ chi phí chung:
        - Plot 1: 50.000.000 * 40% = 20.000.000 đ → Tổng chi phí Plot 1 = 50.000.000 đ
        - Plot 2: 50.000.000 * 60% = 30.000.000 đ → Tổng chi phí Plot 2 = 75.000.000 đ
        - Tổng chi phí toàn vườn = 125.000.000 đ

        Sản lượng:
        - Plot 1: 2.500 kg → Giá thành / kg = 50.000.000 / 2.500 = 20.000 đ/kg
        - Plot 2: 5.000 kg → Giá thành / kg = 75.000.000 / 5.000 = 15.000 đ/kg
        - Bình quân toàn vườn = 125.000.000 / 7.500 = 16.667 đ/kg
        """
        # Tạo vườn riêng để cách ly chính xác 2 plot 2ha và 3ha
        farm = self._farm(self.owner_a, "Vườn Mẫu 16.2")
        p1 = Plot.objects.create(farm=farm, name="Lô 1", area_ha=Decimal("2.00"), variety=self.ri6)
        p2 = Plot.objects.create(farm=farm, name="Lô 2", area_ha=Decimal("3.00"), variety=self.ri6)
        season = Season.objects.create(farm=farm, name="Vụ 2026", status="ACTIVE", start_date=date(2026, 1, 1))

        # 1. Chi phí trực tiếp Plot 1
        LedgerEntry.objects.create(
            farm=farm, season=season, plot=p1,
            type=LedgerEntry.Type.EXPENSE, category=LedgerEntry.Category.FERTILIZER,
            amount=Decimal("30000000"), txn_date=TODAY, created_by=self.owner_a,
        )

        # 2. Chi phí trực tiếp Plot 2
        LedgerEntry.objects.create(
            farm=farm, season=season, plot=p2,
            type=LedgerEntry.Type.EXPENSE, category=LedgerEntry.Category.PESTICIDE,
            amount=Decimal("45000000"), txn_date=TODAY, created_by=self.owner_a,
        )

        # 3. Chi phí chung (plot is NULL)
        LedgerEntry.objects.create(
            farm=farm, season=season, plot=None,
            type=LedgerEntry.Type.EXPENSE, category=LedgerEntry.Category.UTILITIES,
            amount=Decimal("50000000"), txn_date=TODAY, created_by=self.owner_a,
        )

        # 4. Thu hoạch Plot 1: 2.500 kg
        b1 = create_batch(
            farm=farm, plot=p1, season=season, user=self.owner_a,
            batch_code="HARV-P1", harvest_date=TODAY,
            stocks=[{"grade": "GRADE_1", "qty_kg": "2500.00"}],
        )

        # 5. Thu hoạch Plot 2: 5.000 kg
        b2 = create_batch(
            farm=farm, plot=p2, season=season, user=self.owner_a,
            batch_code="HARV-P2", harvest_date=TODAY,
            stocks=[{"grade": "GRADE_1", "qty_kg": "5000.00"}],
        )

        # ── Kiểm tra Service ───────────────────────────────────────────────
        report = get_cost_per_kg_report(farm, season=season)
        summary = report["summary"]
        self.assertEqual(summary["total_direct_cost"], Decimal("75000000"))
        self.assertEqual(summary["total_general_cost"], Decimal("50000000"))
        self.assertEqual(summary["total_cost"], Decimal("125000000"))
        self.assertEqual(summary["total_harvested_kg"], Decimal("7500.00"))
        self.assertEqual(summary["average_cost_per_kg"], Decimal("16667"))

        # Kiểm tra từng Plot
        p1_rep = next(p for p in report["plots"] if p["plot_id"] == p1.id)
        self.assertEqual(p1_rep["direct_cost"], Decimal("30000000"))
        # 50.000.000 * (2.0 / 5.0) = 20.000.000
        self.assertEqual(p1_rep["allocated_general_cost"], Decimal("20000000"))
        self.assertEqual(p1_rep["total_cost"], Decimal("50000000"))
        self.assertEqual(p1_rep["harvested_kg"], Decimal("2500.00"))
        self.assertEqual(p1_rep["cost_per_kg"], Decimal("20000"))

        p2_rep = next(p for p in report["plots"] if p["plot_id"] == p2.id)
        self.assertEqual(p2_rep["direct_cost"], Decimal("45000000"))
        # 50.000.000 * (3.0 / 5.0) = 30.000.000
        self.assertEqual(p2_rep["allocated_general_cost"], Decimal("30000000"))
        self.assertEqual(p2_rep["total_cost"], Decimal("75000000"))
        self.assertEqual(p2_rep["harvested_kg"], Decimal("5000.00"))
        self.assertEqual(p2_rep["cost_per_kg"], Decimal("15000"))

        # ── Kiểm tra API Endpoint ──────────────────────────────────────────
        self.login(self.owner_a)
        res = self.client.get(f"{API}/farms/{farm.id}/reports/cost-per-kg/?season_id={season.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["summary"]["average_cost_per_kg"], Decimal("16667"))


    def test_profit_loss_report(self):
        """Báo cáo P&L: Doanh thu Sale + Thu khác - Chi phí (BR-15)."""
        season = self.season_a

        # Chi phí: Phân bón 10tr, Thuốc 5tr
        LedgerEntry.objects.create(
            farm=self.farm_a, season=season, plot=self.plot1,
            type=LedgerEntry.Type.EXPENSE, category=LedgerEntry.Category.FERTILIZER,
            amount=Decimal("10000000"), txn_date=TODAY, created_by=self.owner_a,
        )
        LedgerEntry.objects.create(
            farm=self.farm_a, season=season, plot=self.plot1,
            type=LedgerEntry.Type.EXPENSE, category=LedgerEntry.Category.PESTICIDE,
            amount=Decimal("5000000"), txn_date=TODAY, created_by=self.owner_a,
        )
        # Thu khác: 2tr
        LedgerEntry.objects.create(
            farm=self.farm_a, season=season, plot=None,
            type=LedgerEntry.Type.OTHER_INCOME, category=LedgerEntry.Category.OTHER,
            amount=Decimal("2000000"), txn_date=TODAY, created_by=self.owner_a,
        )

        # Thu hoạch và bán hàng: 100 kg * 80.000 = 8.000.000 đ
        b = create_batch(
            farm=self.farm_a, plot=self.plot1, season=season, user=self.owner_a,
            batch_code="PL-BATCH-01", harvest_date=TODAY,
            stocks=[{"grade": "GRADE_1", "qty_kg": "100.00"}],
        )
        add_lab_test(batch=b, user=self.owner_a, tested_date=TODAY,
                     lab_name="Lab", result=LabTest.Result.PASS)

        st = b.stocks.get(grade="GRADE_1")
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PL-SALE-01", sale_date=TODAY, customer_name="Đại lý Tiền Giang",
            season=season,
            lines=[{"stock_id": st.id, "qty_kg": "100.00", "unit_price": "80000"}],
        )
        # Thu trước 5.000.000 đ
        add_payment(sale=sale, user=self.owner_a, amount=Decimal("5000000"), payment_date=TODAY)

        # Doanh thu = 8tr (sales) + 2tr (thu khác) = 10tr
        # Chi phí = 15tr
        # Lợi nhuận = -5tr
        rep = get_profit_loss_report(self.farm_a, season=season)
        self.assertEqual(rep["revenue"]["sales_revenue"], Decimal("8000000"))
        self.assertEqual(rep["revenue"]["sales_paid"], Decimal("5000000"))
        self.assertEqual(rep["revenue"]["receivables"], Decimal("3000000"))
        self.assertEqual(rep["revenue"]["other_income"], Decimal("2000000"))
        self.assertEqual(rep["revenue"]["total_revenue"], Decimal("10000000"))
        self.assertEqual(rep["expenses"]["total_expense"], Decimal("15000000"))
        self.assertEqual(rep["profit"]["net_profit"], Decimal("-5000000"))

        # Gọi API endpoint
        self.login(self.owner_a)
        res = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/profit-loss/?season_id={season.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["profit"]["net_profit"], Decimal("-5000000"))

    def test_receivables_report(self):
        """Báo cáo công nợ người mua."""
        buyer = Buyer.objects.create(farm=self.farm_a, name="Vựa Sầu Riêng Chín", phone="0911222333")
        b = create_batch(
            farm=self.farm_a, plot=self.plot1, season=self.season_a, user=self.owner_a,
            batch_code="REC-BATCH", harvest_date=TODAY,
            stocks=[{"grade": "GRADE_1", "qty_kg": "200.00"}],
        )
        add_lab_test(batch=b, user=self.owner_a, tested_date=TODAY, lab_name="Lab", result=LabTest.Result.PASS)
        st = b.stocks.first()

        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="REC-SALE", sale_date=TODAY, customer_name="Vựa Sầu Riêng Chín",
            buyer=buyer, lines=[{"stock_id": st.id, "qty_kg": "100.00", "unit_price": "70000"}],
        )
        add_payment(sale=sale, user=self.owner_a, amount=Decimal("3000000"), payment_date=TODAY)

        rep = get_receivables_report(self.farm_a)
        self.assertEqual(rep["summary"]["total_invoiced"], Decimal("7000000"))
        self.assertEqual(rep["summary"]["total_collected"], Decimal("3000000"))
        self.assertEqual(rep["summary"]["total_debt"], Decimal("4000000"))
        self.assertEqual(len(rep["buyers"]), 1)
        self.assertEqual(rep["buyers"][0]["total_debt"], Decimal("4000000"))

        self.login(self.owner_a)
        res = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/receivables/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["summary"]["total_debt"], Decimal("4000000"))

    def test_stock_inventory_and_phi_reports(self):
        """Kiểm tra báo cáo tồn kho & cảnh báo PHI."""
        create_batch(
            farm=self.farm_a, plot=self.plot1, season=self.season_a, user=self.owner_a,
            batch_code="INV-BATCH", harvest_date=TODAY,
            stocks=[
                {"grade": "GRADE_1", "qty_kg": "300.00", "estimated_price_per_kg": 90000},
                {"grade": "GRADE_2", "qty_kg": "200.00", "estimated_price_per_kg": 70000},
            ],
        )

        # Inventory report
        inv = get_stock_inventory_report(self.farm_a)
        self.assertEqual(inv["summary"]["total_remaining_kg"], Decimal("500.00"))
        # 300 * 90k + 200 * 70k = 27tr + 14tr = 41tr
        self.assertEqual(inv["summary"]["total_estimated_value"], Decimal("41000000"))

        # PHI report (farm_a có plot_a + plot1 + plot2 = 3 plots)
        phi = get_phi_warnings_report(self.farm_a)
        self.assertIn("plots", phi)
        self.assertEqual(phi["summary"]["total_plots"], 3)


    def test_worker_forbidden_financial_reports_allowed_inventory_phi(self):
        """WORKER bị 403 với báo cáo tài chính, nhưng xem được tồn kho và PHI."""
        self.login(self.worker_a)

        # 403 với P&L, Cost/kg, Receivables
        r1 = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/profit-loss/")
        self.assertEqual(r1.status_code, 403)

        r2 = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/cost-per-kg/")
        self.assertEqual(r2.status_code, 403)

        r3 = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/receivables/")
        self.assertEqual(r3.status_code, 403)

        # 200 với Stock Inventory & PHI Warnings
        r4 = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/stock-inventory/")
        self.assertEqual(r4.status_code, 200)

        r5 = self.client.get(f"{API}/farms/{self.farm_a.id}/reports/phi-warnings/")
        self.assertEqual(r5.status_code, 200)
