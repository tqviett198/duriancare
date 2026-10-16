from django.conf import settings
from django.db import models
from django.db.models import Q


class LedgerEntry(models.Model):
    """Sổ thu chi. Chỉ chứa chi phí và thu khác — doanh thu bán hàng KHÔNG nằm ở đây (BR-15)."""

    class Type(models.TextChoices):
        EXPENSE = "EXPENSE", "Chi phí"
        OTHER_INCOME = "OTHER_INCOME", "Thu khác"

    class Category(models.TextChoices):
        FERTILIZER = "FERTILIZER", "Phân bón"
        PESTICIDE = "PESTICIDE", "Thuốc BVTV"
        LABOR = "LABOR", "Nhân công"
        UTILITIES = "UTILITIES", "Điện nước"
        TRANSPORT = "TRANSPORT", "Vận chuyển"
        LAND_RENT = "LAND_RENT", "Thuê đất"
        EQUIPMENT = "EQUIPMENT", "Máy móc"
        OTHER = "OTHER", "Khác"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Hiệu lực"
        VOIDED = "VOIDED", "Đã hủy"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="ledger_entries")
    plot = models.ForeignKey("farms.Plot", null=True, blank=True, on_delete=models.PROTECT)
    season = models.ForeignKey("farms.Season", null=True, blank=True, on_delete=models.PROTECT)
    type = models.CharField(max_length=12, choices=Type.choices)
    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    txn_date = models.DateField(db_index=True)
    description = models.CharField(max_length=255, blank=True)
    # BR-16: có giá trị khi khoản chi được sinh tự động từ nhật ký (tách theo từng loại vật tư)
    source_log = models.ForeignKey("logs.FarmLog", null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="expenses")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="ledger_amount_positive", condition=Q(amount__gt=0)),
            models.UniqueConstraint(fields=["source_log", "category"], condition=Q(source_log__isnull=False),
                                    name="uniq_expense_source_log_category"),
        ]
        indexes = [models.Index(fields=["farm", "txn_date"])]
