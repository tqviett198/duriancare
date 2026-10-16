"""
Tests cho module sales – kiểm tra BR-13, BR-14, BR-17, BR-18, BR-19.

BR-13: Chỉ lô PASSED mới được bán (PENDING/FAILED/VOIDED bị chặn)
BR-14: Tạo phiếu bán bằng transaction + select_for_update, sắp theo ID tránh deadlock
BR-17: Trừ remaining_kg khi bán
BR-18: Thanh toán ≤ total_amount, payment_status suy ra tự động
BR-19: Hủy phiếu bán → hoàn remaining_kg; không hủy phiếu đã có thanh toán

Thêm:
- Chặn stock_id trùng trong một phiếu
- Phân quyền: chỉ OWNER xem/tạo/hủy bán hàng
- Truy cập chéo vườn
- Thanh toán phiếu đã hủy
- Đồng bộ remaining_kg giữa BatchStock và HarvestBatch
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from common.exceptions import DomainError
from common.models import AuditLog
from harvests.models import BatchStock, HarvestBatch, LabTest
from harvests.services import add_lab_test, create_batch
from sales.models import Payment, Sale, SaleLine
from sales.services import add_payment, create_sale, void_sale

from .base import BaseTest, make_user

API = "/api/v1"
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_batch_for_sale(test_case, batch_code="SALE-LOT-001",
                        stocks=None, status="PASSED"):
    """Tạo lô thu hoạch sẵn sàng bán cho vườn A.

    Mặc định: 1 stock GRADE_1, 100 kg, trạng thái PASSED.
    """
    tc = test_case
    stocks = stocks or [{"grade": "GRADE_1", "qty_kg": "100.00"}]
    batch = create_batch(
        farm=tc.farm_a,
        plot=tc.plot_a,
        season=tc.season_a,
        user=tc.owner_a,
        batch_code=batch_code,
        harvest_date=TODAY,
        stocks=stocks,
    )
    # Đưa batch về trạng thái mong muốn
    if status == "PASSED":
        add_lab_test(
            batch=batch, user=tc.owner_a,
            tested_date=TODAY, lab_name="Lab Test",
            result=LabTest.Result.PASS,
        )
        batch.refresh_from_db()
    elif status == "FAILED":
        add_lab_test(
            batch=batch, user=tc.owner_a,
            tested_date=TODAY, lab_name="Lab Test",
            result=LabTest.Result.FAIL,
        )
        batch.refresh_from_db()
    # PENDING: không cần làm gì, mặc định khi tạo
    return batch


def get_stock(batch, grade="GRADE_1"):
    """Lấy BatchStock của lô theo grade."""
    return batch.stocks.get(grade=grade)


def sale_payload(stock, qty_kg="50.00", unit_price="80000",
                 sale_code="PH-001", **extra):
    """Tạo payload tạo phiếu bán đơn giản."""
    data = {
        "sale_code": sale_code,
        "sale_date": str(TODAY),
        "customer_name": "Anh Tèo",
        "lines": [
            {"stock_id": stock.id, "qty_kg": qty_kg, "unit_price": unit_price},
        ],
    }
    data.update(extra)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Service-level tests
# ─────────────────────────────────────────────────────────────────────────────

class CreateSaleServiceTest(BaseTest):
    """Test create_sale service: BR-13, BR-14, BR-17."""

    def setUp(self):
        super().setUp()
        self.batch = make_batch_for_sale(self)
        self.stock = get_stock(self.batch)

    def test_create_sale_basic(self):
        """Tạo phiếu bán đơn giản → sale tạo thành công, tồn kho giảm."""
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-001", sale_date=TODAY,
            customer_name="Anh Ba",
            lines=[{"stock_id": self.stock.id, "qty_kg": "30", "unit_price": "80000"}],
        )
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(sale.total_amount, Decimal("2400000"))  # 30 × 80000
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNPAID)
        self.assertEqual(sale.lines.count(), 1)
        # BR-17: Tồn kho giảm
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("70.00"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining_kg, Decimal("70.00"))

    def test_create_sale_multiple_lines(self):
        """Phiếu bán nhiều dòng (khác grade) → tổng tiền đúng, tồn giảm đúng."""
        batch = make_batch_for_sale(
            self, batch_code="MULTI-001",
            stocks=[
                {"grade": "GRADE_1", "qty_kg": "60.00"},
                {"grade": "GRADE_2", "qty_kg": "40.00"},
            ],
        )
        stock_a = get_stock(batch, "GRADE_1")
        stock_b = get_stock(batch, "GRADE_2")

        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-MULTI", sale_date=TODAY,
            customer_name="Chị Tư",
            lines=[
                {"stock_id": stock_a.id, "qty_kg": "20", "unit_price": "100000"},
                {"stock_id": stock_b.id, "qty_kg": "15", "unit_price": "60000"},
            ],
        )
        # 20×100000 + 15×60000 = 2_000_000 + 900_000 = 2_900_000
        self.assertEqual(sale.total_amount, Decimal("2900000"))
        self.assertEqual(sale.lines.count(), 2)

        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(stock_a.remaining_kg, Decimal("40.00"))
        self.assertEqual(stock_b.remaining_kg, Decimal("25.00"))

    def test_sell_exact_remaining(self):
        """Bán hết tồn kho → remaining_kg = 0 (không lỗi)."""
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-FULL", sale_date=TODAY,
            customer_name="Anh Năm",
            lines=[{"stock_id": self.stock.id, "qty_kg": "100", "unit_price": "80000"}],
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("0.00"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining_kg, Decimal("0.00"))

    def test_sell_exceeds_stock_rejected(self):
        """BR-17: Bán vượt tồn kho → DomainError (insufficient_stock)."""
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-OVER", sale_date=TODAY,
                customer_name="Anh Sáu",
                lines=[{"stock_id": self.stock.id, "qty_kg": "150", "unit_price": "80000"}],
            )
        self.assertEqual(cm.exception.code_str, "insufficient_stock")
        # Tồn kho không thay đổi
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("100.00"))

    def test_sell_failed_batch_rejected(self):
        """BR-13: Lô FAILED → không bán được."""
        batch_fail = make_batch_for_sale(self, batch_code="FAIL-001", status="FAILED")
        stock = get_stock(batch_fail)
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-FAIL", sale_date=TODAY,
                customer_name="Anh Bảy",
                lines=[{"stock_id": stock.id, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "batch_failed")

    def test_sell_voided_batch_rejected(self):
        """Lô VOIDED → không bán được."""
        batch_void = make_batch_for_sale(self, batch_code="VOID-001", status="PENDING")
        batch_void.status = HarvestBatch.Status.VOIDED
        batch_void.save(update_fields=["status"])
        stock = get_stock(batch_void)
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-VOID", sale_date=TODAY,
                customer_name="Anh Tám",
                lines=[{"stock_id": stock.id, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "batch_voided")

    def test_sell_pending_batch_rejected(self):
        """Lô PENDING (chưa kiểm nghiệm) → không bán được (BR-13, fix.md H2)."""
        batch_pending = make_batch_for_sale(
            self, batch_code="PEND-001", status="PENDING",
        )
        stock = get_stock(batch_pending)
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-PEND", sale_date=TODAY,
                customer_name="Anh Chín",
                lines=[{"stock_id": stock.id, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "batch_pending")
        self.assertEqual(cm.exception.status_code, 409)
        stock.refresh_from_db()
        self.assertEqual(stock.remaining_kg, Decimal("100.00"))  # tồn kho không bị trừ

    def test_sell_cross_farm_rejected(self):
        """Stock thuộc vườn khác → từ chối."""
        batch_b = create_batch(
            farm=self.farm_b, plot=self.plot_b, season=None,
            user=self.owner_b, batch_code="B-001",
            harvest_date=TODAY, stocks=[{"grade": "GRADE_1", "qty_kg": "50.00"}],
        )
        stock_b = get_stock(batch_b)
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-CROSS", sale_date=TODAY,
                customer_name="Trùm",
                lines=[{"stock_id": stock_b.id, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "stock_wrong_farm")
        # Không được lộ mã lô / trạng thái lô của vườn khác trong thông báo lỗi
        self.assertNotIn("B-001", str(cm.exception.detail))

    def test_duplicate_sale_code_rejected(self):
        """Mã phiếu trùng trong cùng vườn → 409."""
        create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-DUP", sale_date=TODAY,
            customer_name="A",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "50000"}],
        )
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-DUP", sale_date=TODAY,
                customer_name="B",
                lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "duplicate_sale_code")

    def test_empty_lines_rejected(self):
        """Phiếu bán không có dòng → lỗi."""
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-EMPTY", sale_date=TODAY,
                customer_name="A",
                lines=[],
            )
        self.assertEqual(cm.exception.code_str, "lines_empty")

    def test_stock_not_found(self):
        """stock_id không tồn tại → lỗi."""
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-NF", sale_date=TODAY,
                customer_name="A",
                lines=[{"stock_id": 99999, "qty_kg": "10", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "stock_not_found")

    def test_two_sales_deplete_stock(self):
        """Hai phiếu liên tiếp trừ dần tồn kho → phiếu thứ 3 hết tồn."""
        create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-A", sale_date=TODAY,
            customer_name="A",
            lines=[{"stock_id": self.stock.id, "qty_kg": "60", "unit_price": "80000"}],
        )
        create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-B", sale_date=TODAY,
            customer_name="B",
            lines=[{"stock_id": self.stock.id, "qty_kg": "40", "unit_price": "80000"}],
        )
        # Hết sạch
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("0.00"))

        # Bán thêm → lỗi
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="PH-C", sale_date=TODAY,
                customer_name="C",
                lines=[{"stock_id": self.stock.id, "qty_kg": "1", "unit_price": "80000"}],
            )
        self.assertEqual(cm.exception.code_str, "insufficient_stock")


# ─────────────────────────────────────────────────────────────────────────────
# BR-19: Hủy phiếu bán
# ─────────────────────────────────────────────────────────────────────────────

class VoidSaleServiceTest(BaseTest):
    """Test void_sale: BR-19 hoàn tồn kho."""

    def setUp(self):
        super().setUp()
        self.batch = make_batch_for_sale(self)
        self.stock = get_stock(self.batch)
        self.sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-VOID-TEST", sale_date=TODAY,
            customer_name="Anh Mười",
            lines=[{"stock_id": self.stock.id, "qty_kg": "30", "unit_price": "80000"}],
        )

    def test_void_restores_stock(self):
        """Hủy phiếu → tồn kho hoàn lại + ghi audit log."""
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("70.00"))

        void_sale(sale=self.sale, user=self.owner_a, reason="Khách hủy")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.CANCELLED)
        self.assertEqual(self.sale.void_reason, "Khách hủy")

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("100.00"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining_kg, Decimal("100.00"))

        # Audit log phải có SALE_VOID
        self.assertTrue(
            AuditLog.objects.filter(
                action="SALE_VOID", entity_id=self.sale.pk,
            ).exists()
        )

    def test_void_already_voided(self):
        """Hủy lần 2 → lỗi."""
        void_sale(sale=self.sale, user=self.owner_a, reason="Lần 1")
        with self.assertRaises(DomainError) as cm:
            void_sale(sale=self.sale, user=self.owner_a, reason="Lần 2")
        self.assertEqual(cm.exception.code_str, "already_voided")

    def test_void_with_payment_rejected(self):
        """BR-19: Phiếu có thanh toán → không được hủy."""
        add_payment(
            sale=self.sale, user=self.owner_a,
            amount="100000", payment_date=TODAY,
        )
        with self.assertRaises(DomainError) as cm:
            void_sale(sale=self.sale, user=self.owner_a, reason="Muốn hủy")
        self.assertEqual(cm.exception.code_str, "sale_has_payments")

    def test_void_multi_line_restores_all(self):
        """Hủy phiếu nhiều dòng → hoàn tất tồn của tất cả stock."""
        batch2 = make_batch_for_sale(self, batch_code="MULTI-V-001",
                                     stocks=[{"grade": "GRADE_1", "qty_kg": "80.00"},
                                             {"grade": "GRADE_2", "qty_kg": "20.00"}])
        stock_a = get_stock(batch2, "GRADE_1")
        stock_b = get_stock(batch2, "GRADE_2")
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-MV", sale_date=TODAY,
            customer_name="Multi",
            lines=[
                {"stock_id": stock_a.id, "qty_kg": "25", "unit_price": "100000"},
                {"stock_id": stock_b.id, "qty_kg": "10", "unit_price": "60000"},
            ],
        )
        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(stock_a.remaining_kg, Decimal("55.00"))
        self.assertEqual(stock_b.remaining_kg, Decimal("10.00"))

        void_sale(sale=sale, user=self.owner_a, reason="Test hoàn")
        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(stock_a.remaining_kg, Decimal("80.00"))
        self.assertEqual(stock_b.remaining_kg, Decimal("20.00"))


# ─────────────────────────────────────────────────────────────────────────────
# BR-18: Thanh toán
# ─────────────────────────────────────────────────────────────────────────────

class PaymentServiceTest(BaseTest):
    """Test add_payment: BR-18."""

    def setUp(self):
        super().setUp()
        self.batch = make_batch_for_sale(self)
        self.stock = get_stock(self.batch)
        self.sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-PAY", sale_date=TODAY,
            customer_name="Anh Tèo",
            lines=[{"stock_id": self.stock.id, "qty_kg": "50", "unit_price": "80000"}],
        )
        # total_amount = 50 × 80000 = 4_000_000

    def test_partial_payment(self):
        """Thanh toán một phần → PARTIAL."""
        payment = add_payment(
            sale=self.sale, user=self.owner_a,
            amount="1000000", payment_date=TODAY,
        )
        self.assertIsNotNone(payment.pk)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal("1000000"))
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PARTIAL)

    def test_full_payment(self):
        """Thanh toán đủ → PAID."""
        add_payment(
            sale=self.sale, user=self.owner_a,
            amount="4000000", payment_date=TODAY,
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)

    def test_multiple_payments_to_full(self):
        """Nhiều lần thanh toán cộng dồn → cuối cùng PAID."""
        add_payment(sale=self.sale, user=self.owner_a,
                    amount="1000000", payment_date=TODAY)
        add_payment(sale=self.sale, user=self.owner_a,
                    amount="2000000", payment_date=TODAY)
        add_payment(sale=self.sale, user=self.owner_a,
                    amount="1000000", payment_date=TODAY)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal("4000000"))
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.PAID)
        self.assertEqual(self.sale.payments.count(), 3)

    def test_payment_exceeds_total_rejected(self):
        """BR-18: Thanh toán vượt total_amount → lỗi."""
        with self.assertRaises(DomainError) as cm:
            add_payment(
                sale=self.sale, user=self.owner_a,
                amount="5000000", payment_date=TODAY,
            )
        self.assertEqual(cm.exception.code_str, "payment_exceeds_total")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal("0"))

    def test_second_payment_exceeds_total_rejected(self):
        """Thanh toán 2 lần, lần 2 vượt → lỗi, lần 1 vẫn còn."""
        add_payment(sale=self.sale, user=self.owner_a,
                    amount="3000000", payment_date=TODAY)
        with self.assertRaises(DomainError) as cm:
            add_payment(
                sale=self.sale, user=self.owner_a,
                amount="2000000", payment_date=TODAY,
            )
        self.assertEqual(cm.exception.code_str, "payment_exceeds_total")
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.paid_amount, Decimal("3000000"))

    def test_payment_voided_sale_rejected(self):
        """Thanh toán cho phiếu đã hủy → lỗi."""
        void_sale(sale=self.sale, user=self.owner_a, reason="Hủy")
        with self.assertRaises(DomainError) as cm:
            add_payment(
                sale=self.sale, user=self.owner_a,
                amount="100000", payment_date=TODAY,
            )
        self.assertEqual(cm.exception.code_str, "sale_voided")

    def test_payment_method_saved(self):
        """Method và reference được lưu đúng."""
        payment = add_payment(
            sale=self.sale, user=self.owner_a,
            amount="500000", payment_date=TODAY,
            method="TRANSFER", reference="VCB-123456",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.method, "TRANSFER")
        self.assertEqual(payment.reference, "VCB-123456")


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

class SaleAPITest(BaseTest):
    """Test API /farms/{farm_id}/sales/."""

    def setUp(self):
        super().setUp()
        self.batch = make_batch_for_sale(self)
        self.stock = get_stock(self.batch)

    def _url(self, farm=None, pk=None):
        f = farm or self.farm_a
        base = f"{API}/farms/{f.id}/sales/"
        return f"{base}{pk}/" if pk else base

    def test_create_sale_owner(self):
        """OWNER tạo phiếu bán qua API."""
        self.login(self.owner_a)
        payload = sale_payload(self.stock)
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["sale_code"], "PH-001")
        self.assertEqual(r.data["customer_name"], "Anh Tèo")
        self.assertEqual(len(r.data["lines"]), 1)
        self.assertEqual(r.data["payment_status"], "UNPAID")
        self.assertEqual(r.data["status"], "CONFIRMED")
        # total_amount = 50 × 80000 = 4_000_000
        self.assertEqual(r.data["total_amount"], "4000000")

    def test_create_sale_worker_forbidden(self):
        """WORKER không được tạo phiếu bán."""
        self.login(self.worker_a)
        payload = sale_payload(self.stock)
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 403)

    def test_create_sale_advisor_forbidden(self):
        """ADVISOR không được tạo phiếu bán."""
        self.login(self.advisor_a)
        payload = sale_payload(self.stock)
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 403)

    def test_list_sales_owner(self):
        """OWNER xem danh sách phiếu bán."""
        self.login(self.owner_a)
        create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-LIST", sale_date=TODAY,
            customer_name="A",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)

    def test_list_sales_worker_forbidden(self):
        """WORKER không được xem bán hàng."""
        self.login(self.worker_a)
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 403)

    def test_list_sales_advisor_forbidden(self):
        """ADVISOR không được xem bán hàng."""
        self.login(self.advisor_a)
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 403)

    def test_cross_farm_blocked(self):
        """Owner B không xem được sales của Farm A."""
        self.login(self.owner_b)
        r = self.client.get(self._url(self.farm_a))
        self.assertEqual(r.status_code, 403)

    def test_sell_exceeds_stock_via_api(self):
        """Bán vượt tồn qua API → 409."""
        self.login(self.owner_a)
        payload = sale_payload(self.stock, qty_kg="200.00")
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "insufficient_stock")

    def test_sell_failed_batch_via_api(self):
        """Bán lô FAILED qua API → 409."""
        batch_fail = make_batch_for_sale(self, batch_code="API-FAIL", status="FAILED")
        stock_fail = get_stock(batch_fail)
        self.login(self.owner_a)
        payload = sale_payload(stock_fail, sale_code="PH-FAIL-API")
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "batch_failed")

    def test_duplicate_stock_in_lines_via_api(self):
        """Hai dòng cùng stock_id trong một phiếu → 400 (validate_lines)."""
        self.login(self.owner_a)
        payload = {
            "sale_code": "PH-DUP-STOCK",
            "sale_date": str(TODAY),
            "customer_name": "Test",
            "lines": [
                {"stock_id": self.stock.id, "qty_kg": "10.00", "unit_price": "80000"},
                {"stock_id": self.stock.id, "qty_kg": "20.00", "unit_price": "80000"},
            ],
        }
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 400)

    def test_void_sale_via_api(self):
        """OWNER hủy phiếu bán qua API → tồn hoàn lại."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-VOID-API", sale_date=TODAY,
            customer_name="A",
            lines=[{"stock_id": self.stock.id, "qty_kg": "30", "unit_price": "80000"}],
        )
        r = self.client.post(
            f"{self._url(pk=sale.id)}void/",
            {"reason": "Khách trả hàng"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "CANCELLED")
        # Tồn hoàn lại
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("100.00"))

    def test_void_sale_with_payment_via_api(self):
        """Hủy phiếu đã thanh toán qua API → 409."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-VOID-PAY", sale_date=TODAY,
            customer_name="B",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        add_payment(sale=sale, user=self.owner_a, amount="100000", payment_date=TODAY)
        r = self.client.post(
            f"{self._url(pk=sale.id)}void/",
            {"reason": "Muốn hủy"}, format="json",
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "sale_has_payments")

    def test_add_payment_via_api(self):
        """Thêm thanh toán qua API → payment_status cập nhật."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-PAYAPI", sale_date=TODAY,
            customer_name="C",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        # total_amount = 800000
        r = self.client.post(
            f"{self._url(pk=sale.id)}add_payment/",
            {"amount": "500000", "payment_date": str(TODAY)}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["payment_status"], "PARTIAL")
        self.assertEqual(r.data["paid_amount"], "500000")
        self.assertEqual(len(r.data["payments"]), 1)

    def test_payment_exceeds_total_via_api(self):
        """Thanh toán vượt tổng qua API → 409."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-PAYOVER", sale_date=TODAY,
            customer_name="D",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        r = self.client.post(
            f"{self._url(pk=sale.id)}add_payment/",
            {"amount": "900000", "payment_date": str(TODAY)}, format="json",
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "payment_exceeds_total")

    def test_detail_includes_lines_and_payments(self):
        """GET chi tiết phiếu bán có đầy đủ lines + payments."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-DETAIL", sale_date=TODAY,
            customer_name="E",
            lines=[{"stock_id": self.stock.id, "qty_kg": "20", "unit_price": "80000"}],
        )
        add_payment(sale=sale, user=self.owner_a, amount="500000", payment_date=TODAY)
        r = self.client.get(self._url(pk=sale.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["lines"]), 1)
        self.assertEqual(r.data["lines"][0]["batch_code"], "SALE-LOT-001")
        self.assertEqual(r.data["lines"][0]["grade"], "GRADE_1")
        self.assertEqual(len(r.data["payments"]), 1)

    def test_filter_by_status(self):
        """Lọc phiếu theo status."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-FILTER", sale_date=TODAY,
            customer_name="F",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        r_confirmed = self.client.get(self._url() + "?status=CONFIRMED")
        self.assertEqual(r_confirmed.data["count"], 1)
        r_cancelled = self.client.get(self._url() + "?status=CANCELLED")
        self.assertEqual(r_cancelled.data["count"], 0)

    def test_filter_by_payment_status(self):
        """Lọc phiếu theo payment_status."""
        self.login(self.owner_a)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PH-PFILTER", sale_date=TODAY,
            customer_name="G",
            lines=[{"stock_id": self.stock.id, "qty_kg": "10", "unit_price": "80000"}],
        )
        r = self.client.get(self._url() + "?payment_status=UNPAID")
        self.assertEqual(r.data["count"], 1)
        r_paid = self.client.get(self._url() + "?payment_status=PAID")
        self.assertEqual(r_paid.data["count"], 0)

    def test_unauthenticated_blocked(self):
        """Không xác thực → 401."""
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 401)

    def test_sale_with_note_and_phone(self):
        """Ghi chú và SĐT khách hàng lưu đúng."""
        self.login(self.owner_a)
        payload = sale_payload(
            self.stock, sale_code="PH-NOTE",
            customer_phone="0912345678",
            note="Giao tận nơi",
        )
        r = self.client.post(self._url(), payload, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["customer_phone"], "0912345678")
        self.assertEqual(r.data["note"], "Giao tận nơi")


# ─────────────────────────────────────────────────────────────────────────────
# Đồng bộ remaining_kg giữa BatchStock và HarvestBatch
# ─────────────────────────────────────────────────────────────────────────────

class StockSyncTest(BaseTest):
    """Kiểm tra remaining_kg đồng bộ giữa BatchStock và HarvestBatch."""

    def test_create_and_void_keeps_batch_and_stock_in_sync(self):
        """Tạo phiếu → cả batch lẫn stock giảm; hủy → cả hai hoàn."""
        batch = make_batch_for_sale(
            self, batch_code="SYNC-001",
            stocks=[
                {"grade": "GRADE_1", "qty_kg": "60.00"},
                {"grade": "GRADE_2", "qty_kg": "40.00"},
            ],
        )
        stock_a = get_stock(batch, "GRADE_1")
        stock_b = get_stock(batch, "GRADE_2")
        # Tổng batch = 100
        self.assertEqual(batch.remaining_kg, Decimal("100.00"))

        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="SYNC-SALE", sale_date=TODAY,
            customer_name="Sync",
            lines=[
                {"stock_id": stock_a.id, "qty_kg": "20", "unit_price": "100000"},
                {"stock_id": stock_b.id, "qty_kg": "15", "unit_price": "60000"},
            ],
        )
        # 20 + 15 = 35 kg bán
        batch.refresh_from_db()
        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(batch.remaining_kg, Decimal("65.00"))
        self.assertEqual(stock_a.remaining_kg, Decimal("40.00"))
        self.assertEqual(stock_b.remaining_kg, Decimal("25.00"))

        # Hủy
        void_sale(sale=sale, user=self.owner_a, reason="Hoàn")
        batch.refresh_from_db()
        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(batch.remaining_kg, Decimal("100.00"))
        self.assertEqual(stock_a.remaining_kg, Decimal("60.00"))
        self.assertEqual(stock_b.remaining_kg, Decimal("40.00"))


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent test (dùng TransactionTestCase để có thật sự commit)
# ─────────────────────────────────────────────────────────────────────────────

class ConcurrentStockTest(TransactionTestCase):
    """Test đồng thời: 2 phiếu bán tranh nhau cùng stock (cần TransactionTestCase).

    Lưu ý: TransactionTestCase chậm hơn TestCase vì flush DB giữa các test.
    Chỉ kiểm tra logic service, không test qua API (TransactionTestCase
    không có force_authenticate sẵn như APITestCase).
    """

    def setUp(self):
        from catalog.models import InputProduct, Variety
        from farms.models import Farm, FarmMembership, Plot, Season
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.ri6 = Variety.objects.create(name="Ri6")
        self.owner = User.objects.create_user(
            username="0900099001", phone="0900099001",
            full_name="Owner Concurrent", password="matkhau-1234",
        )
        self.farm = Farm.objects.create(owner=self.owner, name="Vườn Concurrent", area_ha="5")
        FarmMembership.objects.create(farm=self.farm, user=self.owner, role="OWNER")
        self.plot = Plot.objects.create(farm=self.farm, name="Lô C1", variety=self.ri6, area_ha="1")
        self.season = Season.objects.create(
            farm=self.farm, name="Vụ Test", status="ACTIVE", start_date=date(2026, 1, 1),
        )
        batch = create_batch(
            farm=self.farm, plot=self.plot, season=self.season,
            user=self.owner, batch_code="CONC-001",
            harvest_date=TODAY,
            stocks=[{"grade": "GRADE_1", "qty_kg": "50.00"}],
        )
        # Đưa sang PASSED
        add_lab_test(
            batch=batch, user=self.owner,
            tested_date=TODAY, lab_name="Lab", result="PASS",
        )
        self.stock = batch.stocks.get(grade="GRADE_1")

    def test_concurrent_sales_one_wins(self):
        """Hai lần gọi create_sale tranh cùng 50 kg:
        - Lần 1 bán 50 kg → thành công
        - Lần 2 bán 50 kg → insufficient_stock
        (Vì select_for_update sẽ serialize; lần 2 thấy remaining_kg=0 sau khi lần 1 commit.)
        """
        # Bán lần 1 – chiếm hết tồn
        create_sale(
            farm=self.farm, user=self.owner,
            sale_code="CONC-A", sale_date=TODAY,
            customer_name="A",
            lines=[{"stock_id": self.stock.id, "qty_kg": "50", "unit_price": "80000"}],
        )

        # Bán lần 2 – tồn đã hết
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm, user=self.owner,
                sale_code="CONC-B", sale_date=TODAY,
                customer_name="B",
                lines=[{"stock_id": self.stock.id, "qty_kg": "50", "unit_price": "80000"}],
            )
        self.assertEqual(cm.exception.code_str, "insufficient_stock")

        # Kiểm tra trạng thái cuối
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.remaining_kg, Decimal("0.00"))
        # Chỉ 1 phiếu thành công
        self.assertEqual(Sale.objects.filter(farm=self.farm, status="CONFIRMED").count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# BR-13 Export Validation & URL Alias Tests
# ─────────────────────────────────────────────────────────────────────────────

class ExportSalesTest(BaseTest):
    """Kiểm tra quy tắc xuất khẩu theo BR-13."""

    def setUp(self):
        super().setUp()
        self.batch = create_batch(
            farm=self.farm_a,
            plot=self.plot_a,
            season=self.season_a,
            user=self.owner_a,
            batch_code="EXP-BATCH-01",
            harvest_date=TODAY,
            stocks=[
                {"grade": "GRADE_1", "qty_kg": "100.00"},
                {"grade": "GRADE_3", "qty_kg": "50.00"},
            ],
        )
        self.stock_g1 = self.batch.stocks.get(grade="GRADE_1")
        self.stock_g3 = self.batch.stocks.get(grade="GRADE_3")

    def test_export_sale_grade_3_rejected(self):
        """Bán xuất khẩu với GRADE_3 bị chặn (BR-13)."""
        add_lab_test(batch=self.batch, user=self.owner_a, tested_date=TODAY,
                     lab_name="Lab", result=LabTest.Result.PASS)
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="EXP-01", sale_date=TODAY,
                customer_name="Công ty Xuất khẩu",
                destination="EXPORT",
                lines=[{"stock_id": self.stock_g3.id, "qty_kg": "20.00", "unit_price": "50000"}],
            )
        self.assertEqual(cm.exception.code_str, "export_grade_not_allowed")

    def test_export_sale_expired_lab_test_rejected(self):
        """Bán xuất khẩu khi kiểm nghiệm đã hết hạn bị chặn (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY - timedelta(days=60),
            lab_name="Lab", result=LabTest.Result.PASS,
            valid_until=TODAY - timedelta(days=5),  # Đã hết hạn
        )
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="EXP-02", sale_date=TODAY,
                customer_name="Công ty Xuất khẩu",
                destination="EXPORT",
                lines=[{"stock_id": self.stock_g1.id, "qty_kg": "20.00", "unit_price": "90000"}],
            )
        self.assertEqual(cm.exception.code_str, "export_lab_test_expired")

    def test_export_sale_limit_exceeded_rejected(self):
        """Bán xuất khẩu khi result_value > limit_value bị chặn (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY,
            lab_name="Lab", result=LabTest.Result.PASS,
            analyte="Cadmium",
            result_value=Decimal("0.0800"),
            limit_value=Decimal("0.0500"),
            valid_until=TODAY + timedelta(days=30),
        )
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="EXP-03", sale_date=TODAY,
                customer_name="Công ty Xuất khẩu",
                destination="EXPORT",
                lines=[{"stock_id": self.stock_g1.id, "qty_kg": "20.00", "unit_price": "90000"}],
            )
        self.assertEqual(cm.exception.code_str, "export_limit_exceeded")

    def test_export_sale_cadmium_in_json_exceeded_rejected(self):
        """Bán xuất khẩu khi cadmium_ppm > 0.05 trong parameters_json bị chặn (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY,
            lab_name="Lab", result=LabTest.Result.PASS,
            parameters_json={"cadmium_ppm": 0.09},
        )
        with self.assertRaises(DomainError) as cm:
            create_sale(
                farm=self.farm_a, user=self.owner_a,
                sale_code="EXP-04", sale_date=TODAY,
                customer_name="Công ty Xuất khẩu",
                destination="EXPORT",
                lines=[{"stock_id": self.stock_g1.id, "qty_kg": "20.00", "unit_price": "90000"}],
            )
        self.assertEqual(cm.exception.code_str, "export_cadmium_exceeded")

    def test_export_sale_valid_success(self):
        """Bán xuất khẩu đạt mọi tiêu chuẩn thành công (BR-13)."""
        add_lab_test(
            batch=self.batch, user=self.owner_a,
            tested_date=TODAY,
            lab_name="Lab Eurofins", result=LabTest.Result.PASS,
            analyte="Cadmium",
            result_value=Decimal("0.0200"),
            limit_value=Decimal("0.0500"),
            valid_until=TODAY + timedelta(days=60),
            parameters_json={"cadmium_ppm": 0.02},
        )
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="EXP-PASS-01", sale_date=TODAY,
            customer_name="Tập đoàn Nông sản Quốc tế",
            destination="EXPORT",
            lines=[{"stock_id": self.stock_g1.id, "qty_kg": "40.00", "unit_price": "95000"}],
        )
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(sale.destination, "EXPORT")
        self.assertEqual(sale.total_amount, Decimal("3800000"))

    def test_payments_endpoint_alias(self):
        """POST /farms/{farm_id}/sales/{id}/payments/ hoạt động chuẩn đặc tả."""
        add_lab_test(batch=self.batch, user=self.owner_a, tested_date=TODAY,
                     lab_name="Lab", result=LabTest.Result.PASS)
        sale = create_sale(
            farm=self.farm_a, user=self.owner_a,
            sale_code="PAY-ALIAS-01", sale_date=TODAY,
            customer_name="Khách mua",
            lines=[{"stock_id": self.stock_g1.id, "qty_kg": "10.00", "unit_price": "80000"}],
        )
        self.login(self.owner_a)
        r = self.client.post(
            f"{API}/farms/{self.farm_a.id}/sales/{sale.id}/payments/",
            {"amount": "400000", "payment_date": str(TODAY), "method": "TRANSFER"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        sale.refresh_from_db()
        self.assertEqual(sale.paid_amount, Decimal("400000"))
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.PARTIAL)

