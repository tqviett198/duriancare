"""
Mô-đun Thu hoạch (harvests).

Nghiệp vụ cốt lõi:
- BR-08: Không thu hoạch trước ngày cách ly an toàn; OWNER có thể override với lý do
- BR-09: batch_code duy nhất trong phạm vi vườn
- BR-10: Tổng kg xuất ≤ remaining_kg (được bảo vệ bởi service với select_for_update)
- BR-11: Không sửa/xóa lô đã có phiếu bán (xử lý ở tầng sales)
- BR-12: Kết quả kiểm nghiệm bắt buộc là PASS/FAIL
- BR-13: Lô FAIL bị chặn bán (spec: FAIL → HOLD); PENDING/PASSED cho bán
"""
from django.conf import settings
from django.db import models
from django.db.models import Q


class HarvestBatch(models.Model):
    """Lô thu hoạch – đơn vị quản lý sau thu hoạch."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ kiểm nghiệm"
        PASSED = "PASSED", "Đạt"
        FAILED = "FAILED", "Không đạt"
        VOIDED = "VOIDED", "Đã hủy"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="harvest_batches")
    plot = models.ForeignKey("farms.Plot", on_delete=models.PROTECT, related_name="harvest_batches")
    season = models.ForeignKey("farms.Season", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="harvest_batches")
    # BR-09: batch_code duy nhất trong vườn
    batch_code = models.CharField(max_length=50)
    harvest_date = models.DateField(db_index=True)
    # Ngày an toàn PHI suy ra từ nhật ký phun thuốc – lưu để audit trail
    phi_safe_date = models.DateField(
        null=True, blank=True,
        help_text="Ngày cách ly PHI an toàn sớm nhất (tính từ lần phun cuối + phi_days). "
                  "NULL khi không có thuốc BVTV nào trong mùa.",
    )
    # Tổng sản lượng thu về (kg)
    total_kg = models.DecimalField(max_digits=10, decimal_places=2)
    # Tồn kho còn lại chưa bán (kg) – cập nhật bởi sales khi tạo/hủy SaleOrderLine
    remaining_kg = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # BR-08: OWNER override PHI
    override_reason = models.CharField(
        max_length=255, blank=True,
        help_text="Lý do OWNER cho phép thu hoạch dù chưa hết PHI (audit trail).",
    )
    # Hủy lô
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # BR-09
            models.UniqueConstraint(fields=["farm", "batch_code"], name="uniq_batch_code_per_farm"),
            # Tổng kg dương
            models.CheckConstraint(name="batch_total_kg_positive", condition=Q(total_kg__gt=0)),
            # remaining_kg không âm và không vượt total_kg
            models.CheckConstraint(name="batch_remaining_nonneg", condition=Q(remaining_kg__gte=0)),
            models.CheckConstraint(
                name="batch_remaining_lte_total",
                condition=Q(remaining_kg__lte=models.F("total_kg")),
            ),
            # BR-08: harvest_date >= phi_safe_date, HOẶC có override_reason (OWNER bypass)
            models.CheckConstraint(
                name="batch_phi_date_respected",
                condition=(
                    Q(phi_safe_date__isnull=True)
                    | Q(harvest_date__gte=models.F("phi_safe_date"))
                    | ~Q(override_reason="")
                ),
            ),
        ]
        indexes = [models.Index(fields=["farm", "harvest_date"])]

    def __str__(self):
        return f"{self.batch_code} ({self.harvest_date})"


class BatchGrade(models.TextChoices):
    """Phân loại chất lượng sầu riêng thu hoạch."""
    GRADE_1 = "GRADE_1", "Loại 1 (xuất khẩu)"
    GRADE_2 = "GRADE_2", "Loại 2 (nội địa cao cấp)"
    GRADE_3 = "GRADE_3", "Loại 3 (nội địa thường)"
    REJECT = "REJECT", "Loại thải"


class BatchStock(models.Model):
    """
    Tồn kho của lô thu hoạch chia theo phân loại (grade).

    Một lô có thể có nhiều dòng grade khác nhau.
    Tổng `qty_kg` của tất cả dòng trong một lô phải bằng `HarvestBatch.total_kg`
    – ràng buộc này được kiểm tra bởi service, không phải DB (vì phải tổng hợp nhiều dòng).
    """
    batch = models.ForeignKey(HarvestBatch, on_delete=models.CASCADE, related_name="stocks")
    grade = models.CharField(max_length=8, choices=BatchGrade.choices)
    qty_kg = models.DecimalField(max_digits=10, decimal_places=2)
    # Tồn riêng từng grade (để tính khả năng xuất theo grade)
    remaining_kg = models.DecimalField(max_digits=10, decimal_places=2)
    # Đơn giá ước tính (không bắt buộc, dùng cho dự báo doanh thu)
    estimated_price_per_kg = models.DecimalField(max_digits=10, decimal_places=0,
                                                 null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "grade"], name="uniq_stock_grade_per_batch"),
            models.CheckConstraint(name="stock_qty_positive", condition=Q(qty_kg__gt=0)),
            models.CheckConstraint(name="stock_remaining_nonneg", condition=Q(remaining_kg__gte=0)),
            models.CheckConstraint(
                name="stock_remaining_lte_qty",
                condition=Q(remaining_kg__lte=models.F("qty_kg")),
            ),
        ]

    def __str__(self):
        return f"{self.batch.batch_code} – {self.grade}"


class LabTest(models.Model):
    """
    Kết quả kiểm nghiệm chất lượng / an toàn vệ sinh thực phẩm cho lô thu hoạch.

    BR-12: result bắt buộc là PASS hoặc FAIL.
    BR-13: Batch chỉ sang PASSED nếu kết quả kiểm nghiệm còn hiệu lực gần nhất là PASS.
    """

    class Result(models.TextChoices):
        PASS = "PASS", "Đạt"
        FAIL = "FAIL", "Không đạt"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Hiệu lực"
        VOIDED = "VOIDED", "Đã hủy"

    batch = models.ForeignKey(HarvestBatch, on_delete=models.CASCADE, related_name="lab_tests")
    tested_date = models.DateField()
    lab_name = models.CharField(max_length=200)
    result = models.CharField(max_length=4, choices=Result.choices)
    analyte = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Chỉ tiêu kiểm nghiệm chính (ví dụ: Cadmium, Chlorpyrifos, Dư lượng BVTV)",
    )
    result_value = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Giá trị kiểm nghiệm đo được",
    )
    limit_value = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Ngưỡng quy định tối đa cho phép (MRL)",
    )
    valid_until = models.DateField(
        null=True, blank=True,
        help_text="Hiệu lực kết quả kiểm nghiệm",
    )
    # Chỉ tiêu kiểm nghiệm chi tiết dạng JSON
    parameters_json = models.JSONField(
        default=dict, blank=True,
        help_text='{"cadmium_ppm": 0.02, "chlorpyrifos_ppm": 0.01, ...}',
    )
    certificate_url = models.URLField(max_length=500, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-tested_date", "-id"]

    def __str__(self):
        return f"LabTest #{self.pk} – {self.batch.batch_code} – {self.result} ({self.status})"

