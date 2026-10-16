from django.db import models
from django.db.models import Q


class Variety(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "varieties"

    def __str__(self):
        return self.name


class InputProduct(models.Model):
    """Danh mục vật tư. farm = NULL là danh mục toàn cục do admin quản lý."""

    class Kind(models.TextChoices):
        FERTILIZER = "FERTILIZER", "Phân bón"
        PESTICIDE = "PESTICIDE", "Thuốc BVTV"
        OTHER = "OTHER", "Khác"

    class DurianStatus(models.TextChoices):
        YES = "YES", "Có trong danh mục cho sầu riêng"
        NO = "NO", "Không có trong danh mục"
        UNKNOWN = "UNKNOWN", "Chưa xác định"

    farm = models.ForeignKey("farms.Farm", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="products")
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=15, choices=Kind.choices)
    active_ingredient = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=20)
    phi_days = models.PositiveSmallIntegerField(null=True, blank=True)
    max_applications_per_season = models.PositiveSmallIntegerField(null=True, blank=True)
    registered_for_durian = models.CharField(max_length=8, choices=DurianStatus.choices,
                                             default=DurianStatus.UNKNOWN)
    source_note = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    verified_at = models.DateField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # BR-05 ở tầng DB: thuốc BVTV bắt buộc có số ngày cách ly
            models.CheckConstraint(
                name="pesticide_requires_phi",
                condition=~Q(kind="PESTICIDE") | Q(phi_days__isnull=False),
            ),
        ]

    def __str__(self):
        return self.name
