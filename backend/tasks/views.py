import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import User
from common.permissions import FarmScopedMixin, OWNER, ADVISOR, WORKER
from .models import Task, Notification
from .serializers import TaskSerializer, TaskCreateSerializer, NotificationSerializer
from .services import create_task, update_task, complete_task


class TaskFilter(django_filters.FilterSet):
    due_from = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")

    class Meta:
        model = Task
        fields = ["plot", "season", "status", "priority", "task_type", "assigned_to"]


class TaskViewSet(
    FarmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    /farms/{farm_id}/tasks/

    - GET list/detail: OWNER, ADVISOR, WORKER
    - POST create: OWNER, ADVISOR, WORKER
    - PATCH update: OWNER, WORKER (cập nhật tiến độ)
    - POST {id}/complete/: đánh dấu hoàn thành (BR-22 sinh việc tiếp theo nếu recurring)
    """
    queryset = Task.objects.select_related("plot", "season", "assigned_to", "created_by").all()
    serializer_class = TaskSerializer
    filterset_class = TaskFilter
    roles_read = (OWNER, ADVISOR, WORKER)
    roles_write = (OWNER, ADVISOR, WORKER)

    def create(self, request, *args, **kwargs):
        ser = TaskCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        assigned_to = None
        if d.get("assigned_to_id"):
            try:
                assigned_to = User.objects.get(id=d["assigned_to_id"])
            except User.DoesNotExist:
                pass

        task = create_task(
            farm=self.farm,
            user=request.user,
            title=d["title"],
            due_date=d["due_date"],
            description=d.get("description", ""),
            task_type=d.get("task_type", "GENERAL"),
            priority=d.get("priority", "MEDIUM"),
            plot=d.get("plot"),
            season=d.get("season"),
            assigned_to=assigned_to,
            is_recurring=d.get("is_recurring", False),
            recurring_interval_days=d.get("recurring_interval_days"),
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        task = self.get_object()
        updated = update_task(task, user=request.user, **request.data)
        return Response(TaskSerializer(updated).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @extend_schema(responses={200: TaskSerializer})
    @action(detail=True, methods=["post"])
    def complete(self, request, farm_id=None, pk=None):
        task = self.get_object()
        task = complete_task(task, user=request.user)
        return Response(TaskSerializer(task).data)


class NotificationViewSet(
    FarmScopedMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    /farms/{farm_id}/notifications/

    Xem và đánh dấu đã đọc các thông báo của người dùng.
    """
    serializer_class = NotificationSerializer
    roles_read = (OWNER, ADVISOR, WORKER)
    roles_write = (OWNER, ADVISOR, WORKER)

    def get_queryset(self):

        return Notification.objects.filter(farm=self.farm, user=self.request.user)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, farm_id=None, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notif).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request, farm_id=None):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"status": "ok"})
