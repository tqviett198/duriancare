from django.conf import settings
from django.db import models
from django.db.models import Q


class FarmLog(models.Model):
    class Activity(models.TextChoices):
        FERTILIZE = "FERTILIZE", "Bón phân"
        SPRAY = "SPRAY", "Phun thuốc"
        IRRIGATE = "IRRIGATE", "Tưới"
        PRUNE = "PRUNE", "Tỉa cành"
        FRUIT_THINNING = "FRUIT_THINNING", "Tỉa trái"
        WEEDING = "WEEDING", "Làm cỏ"
        FLOWER_INDUCTION = "FLOWER_INDUCTION", "Xử lý ra hoa"
        DRAINAGE = "DRAINAGE", "Thoát nước"
        SOIL_TEST = "SOIL_TEST", "Phân tích đất"
        OTHER = "OTHER", "Khác"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Hiệu lực"
        VOIDED = "VOIDED", "Đã hủy"

    plot = models.ForeignKey("farms.Plot", on_delete=models.PROTECT, related_name="logs")
    season = models.ForeignKey("farms.Season", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="logs")
    activity_type = models.CharField(max_length=20, choices=Activity.choices)
    activity_date = models.DateField(db_index=True)
    description = models.TextField(blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["plot", "activity_date"])]


class FarmLogInput(models.Model):
    log = models.ForeignKey(FarmLog, on_delete=models.CASCADE, related_name="inputs")
    product = models.ForeignKey("catalog.InputProduct", on_delete=models.PROTECT, related_name="uses")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=0)
    warning_acknowledged = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(name="loginput_qty_positive", condition=Q(quantity__gt=0)),
            models.CheckConstraint(name="loginput_cost_nonneg", condition=Q(unit_cost__gte=0)),
        ]
