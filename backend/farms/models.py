from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Farm(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_farms")
    name = models.CharField(max_length=150)
    address_text = models.CharField(max_length=255, blank=True)
    province = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    area_ha = models.DecimalField(max_digits=8, decimal_places=2)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(name="farm_area_positive", condition=Q(area_ha__gt=0))]

    def __str__(self):
        return self.name


class FarmMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Chủ vườn"
        WORKER = "WORKER", "Người làm vườn"
        ADVISOR = "ADVISOR", "Kỹ thuật viên"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["farm", "user"], name="uniq_membership")]


class PlantingCode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Đang hiệu lực"
        SUSPENDED = "SUSPENDED", "Tạm dừng"
        REVOKED = "REVOKED", "Thu hồi"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="planting_codes")
    code = models.CharField(max_length=50)
    target_market = models.CharField(max_length=100, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["farm", "code"], name="uniq_planting_code")]


class Plot(models.Model):
    class GrowthStage(models.TextChoices):
        SEEDLING = "SEEDLING", "Cây con/kiến thiết"
        VEGETATIVE = "VEGETATIVE", "Ra đọt, phát triển"
        FLOWER_INDUCTION = "FLOWER_INDUCTION", "Xử lý ra hoa"
        FLOWERING = "FLOWERING", "Nở hoa"
        FRUIT_SET = "FRUIT_SET", "Đậu trái"
        FRUIT_DEVELOPMENT = "FRUIT_DEVELOPMENT", "Nuôi trái"
        HARVEST = "HARVEST", "Thu hoạch"
        POST_HARVEST = "POST_HARVEST", "Sau thu hoạch"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="plots")
    name = models.CharField(max_length=100)
    variety = models.ForeignKey("catalog.Variety", on_delete=models.PROTECT)
    area_ha = models.DecimalField(max_digits=8, decimal_places=2)
    tree_count = models.PositiveIntegerField(default=0)
    planting_date = models.DateField(null=True, blank=True)
    growth_stage = models.CharField(max_length=25, choices=GrowthStage.choices, default=GrowthStage.VEGETATIVE)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["farm", "name"], name="uniq_plot_name_per_farm"),
            models.CheckConstraint(name="plot_area_positive", condition=Q(area_ha__gt=0)),
        ]

    def __str__(self):
        return self.name


class Season(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Dự kiến"
        ACTIVE = "ACTIVE", "Đang diễn ra"
        CLOSED = "CLOSED", "Đã đóng"

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="seasons")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        constraints = [
            # BR-20: tối đa một mùa vụ ACTIVE mỗi vườn, bảo vệ ở tầng DB
            models.UniqueConstraint(fields=["farm"], condition=Q(status="ACTIVE"), name="uniq_active_season_per_farm"),
            models.CheckConstraint(
                name="season_dates_ordered",
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
            ),
        ]

    def __str__(self):
        return self.name


class PlotSeason(models.Model):
    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name="plot_seasons")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="plot_seasons")
    flower_induction_date = models.DateField(null=True, blank=True)
    fruit_set_date = models.DateField(null=True, blank=True)
    expected_harvest_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plot", "season"], name="uniq_plot_season")]
