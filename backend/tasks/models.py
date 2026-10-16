"""
Models cho app tasks (BR-22, BR-23).

- Task: quản lý việc làm vườn, giao việc, việc lặp tự sinh việc tiếp theo, việc hệ thống không sửa.
- Notification: thông báo trong hệ thống cho người dùng (cảnh báo PHI, việc tới hạn).
"""
from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ thực hiện"
        IN_PROGRESS = "IN_PROGRESS", "Đang thực hiện"
        COMPLETED = "COMPLETED", "Đã hoàn thành"
        CANCELLED = "CANCELLED", "Đã hủy"

    class Priority(models.TextChoices):
        LOW = "LOW", "Thấp"
        MEDIUM = "MEDIUM", "Trung bình"
        HIGH = "HIGH", "Cao"
        URGENT = "URGENT", "Khẩn cấp"

    class TaskType(models.TextChoices):
        GENERAL = "GENERAL", "Công việc chung"
        FERTILIZE = "FERTILIZE", "Bón phân"
        PESTICIDE = "PESTICIDE", "Phun thuốc BVTV"
        WATER = "WATER", "Tưới nước"
        PRUNE = "PRUNE", "Tỉa cành / hoa / trái"
        HARVEST = "HARVEST", "Thu hoạch"
        LAB_TEST = "LAB_TEST", "Lấy mẫu kiểm nghiệm"
        INSPECTION = "INSPECTION", "Kiểm tra sâu bệnh"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="tasks")
    plot = models.ForeignKey("farms.Plot", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    season = models.ForeignKey("farms.Season", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.GENERAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="assigned_tasks")

    # BR-22: Việc lặp sinh việc tiếp theo khi hoàn thành
    is_recurring = models.BooleanField(default=False)
    recurring_interval_days = models.PositiveIntegerField(null=True, blank=True,
                                                          help_text="Số ngày lặp lại chu kỳ")
    parent_task = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="child_tasks")

    # BR-23: Việc hệ thống (cảnh báo cách ly, lịch định kỳ) không cho sửa nội dung
    is_system = models.BooleanField(default=False, help_text="Công việc tự động tạo bởi hệ thống")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-priority", "-id"]
        indexes = [models.Index(fields=["farm", "due_date", "status"])]

    def __str__(self):
        return f"[{self.status}] {self.title} (hạn {self.due_date})"


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        INFO = "INFO", "Thông tin"
        WARNING = "WARNING", "Cảnh báo"
        PHI_ALERT = "PHI_ALERT", "Cảnh báo ngày cách ly"
        TASK_DUE = "TASK_DUE", "Hạn công việc"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices, default=NotificationType.INFO)
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.title} - {self.user.username}"
