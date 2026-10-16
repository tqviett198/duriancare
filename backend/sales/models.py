"""
Mô-đun Bán hàng (sales).

Nghiệp vụ cốt lõi:
- BR-13: Chỉ lô PASSED mới được bán
- BR-14: Tạo phiếu bán bằng transaction + select_for_update, sắp theo ID tránh deadlock
- BR-17: Trừ remaining_kg của BatchStock khi tạo dòng bán
- BR-18: Tổng thanh toán ≤ total_amount; payment_status suy ra tự động
- BR-19: Hủy phiếu bán → hoàn remaining_kg cho BatchStock
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Buyer(models.Model):
    """Khách hàng mua sầu riêng.

    Phase 2: Tạo Buyer để hỗ trợ công nợ, báo cáo xuất khẩu (BR-13).
    Sale.buyer = FK(Buyer, null=True) — giữ customer_name làm cache/fallback.
    """
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="buyers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    tax_code = models.CharField(max_length=30, blank=True, help_text="Mã số thuế (nếu có)")
    is_export = models.BooleanField(default=False, help_text="Khách hàng xuất khẩu")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"], name="uniq_buyer_name_per_farm",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Sale(models.Model):
    """Phiếu bán hàng."""

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Chưa thanh toán"
        PARTIAL = "PARTIAL", "Thanh toán một phần"
        PAID = "PAID", "Đã thanh toán đủ"

    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        CANCELLED = "CANCELLED", "Đã hủy"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="sales")
    sale_code = models.CharField(max_length=50)
    sale_date = models.DateField(db_index=True)
    # Buyer FK (Phase 2) — customer_name giữ làm cache/fallback
    buyer = models.ForeignKey(
        Buyer, null=True, blank=True,
        on_delete=models.PROTECT, related_name="sales",
    )
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20, blank=True)
    # Season + destination (Phase 2: BR-13 xuất khẩu)
    season = models.ForeignKey(
        "farms.Season", null=True, blank=True,
        on_delete=models.PROTECT, related_name="sales",
    )
    destination = models.CharField(
        max_length=10, default="DOMESTIC",
        help_text="DOMESTIC hoặc EXPORT",
    )
    # Tổng tiền (tính từ các dòng SaleLine)
    total_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    # Tổng đã thu (tính từ các Payment ACTIVE)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    payment_status = models.CharField(
        max_length=8, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Hủy phiếu
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "sale_code"], name="uniq_sale_code_per_farm",
            ),
            models.CheckConstraint(
                name="sale_total_amount_nonneg", condition=Q(total_amount__gte=0),
            ),
            models.CheckConstraint(
                name="sale_paid_nonneg", condition=Q(paid_amount__gte=0),
            ),
            models.CheckConstraint(
                name="sale_paid_lte_total",
                condition=Q(paid_amount__lte=F("total_amount")),
            ),
        ]
        indexes = [models.Index(fields=["farm", "sale_date"])]
        ordering = ["-sale_date", "-id"]

    def __str__(self):
        return f"{self.sale_code} ({self.sale_date})"

    def recompute_payment_status(self):
        """Suy ra payment_status từ paid_amount và total_amount (BR-18)."""
        if self.paid_amount <= 0:
            return self.PaymentStatus.UNPAID
        if self.paid_amount >= self.total_amount:
            return self.PaymentStatus.PAID
        return self.PaymentStatus.PARTIAL


class SaleLine(models.Model):
    """
    Dòng bán: mỗi dòng tham chiếu một BatchStock (lô + grade) cụ thể.

    BR-17: qty_kg được trừ vào BatchStock.remaining_kg khi tạo.
    """
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    stock = models.ForeignKey(
        "harvests.BatchStock", on_delete=models.PROTECT, related_name="sale_lines",
    )
    qty_kg = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=0)

    class Meta:
        constraints = [
            models.CheckConstraint(name="line_qty_positive", condition=Q(qty_kg__gt=0)),
            models.CheckConstraint(name="line_price_nonneg", condition=Q(unit_price__gte=0)),
            models.CheckConstraint(name="line_total_nonneg", condition=Q(line_total__gte=0)),
        ]

    def __str__(self):
        return f"SaleLine #{self.pk} – {self.qty_kg}kg @ {self.unit_price}"


class Payment(models.Model):
    """
    Khoản thanh toán cho phiếu bán.

    BR-18: Tổng thanh toán không vượt total_amount.
    Phase 2: Thêm status (ACTIVE/VOIDED) để hỗ trợ hủy thanh toán.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Hiệu lực"
        VOIDED = "VOIDED", "Đã hủy"

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    payment_date = models.DateField()
    method = models.CharField(
        max_length=20, default="CASH",
        help_text="CASH, TRANSFER, CHECK, …",
    )
    reference = models.CharField(max_length=100, blank=True, help_text="Mã giao dịch / số séc")
    note = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="payment_amount_positive", condition=Q(amount__gt=0)),
        ]
        ordering = ["payment_date", "id"]

    def __str__(self):
        return f"Payment #{self.pk} – {self.amount}"
