from rest_framework import serializers

from common.permissions import FarmScopedField
from farms.models import Plot, Season
from .models import Task, Notification


class TaskSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.username", read_only=True)
    plot_name = serializers.CharField(source="plot.name", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "farm", "plot", "plot_name", "season", "title", "description",
            "task_type", "task_type_display", "status", "status_display",
            "priority", "priority_display", "due_date", "completed_at",
            "assigned_to", "assigned_to_name", "is_recurring", "recurring_interval_days",
            "parent_task", "is_system", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "farm", "completed_at", "created_by", "created_at", "updated_at"]


class TaskCreateSerializer(serializers.Serializer):
    plot = FarmScopedField(queryset=Plot.objects.all(), required=False, allow_null=True)
    season = FarmScopedField(queryset=Season.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    task_type = serializers.ChoiceField(choices=Task.TaskType.choices, default=Task.TaskType.GENERAL)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, default=Task.Priority.MEDIUM)
    due_date = serializers.DateField()
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    is_recurring = serializers.BooleanField(required=False, default=False)
    recurring_interval_days = serializers.IntegerField(required=False, allow_null=True, default=None)


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_notification_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "farm", "title", "message", "notification_type", "type_display",
            "is_read", "link", "created_at",
        ]
        read_only_fields = fields
