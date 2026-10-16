"""
Services cho module tasks & notifications (BR-22, BR-23).
"""
from datetime import date, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from common.exceptions import DomainError
from common.models import audit
from .models import Task, Notification


@transaction.atomic
def create_task(farm, user, title: str, due_date: date, description: str = "",
                task_type: str = "GENERAL", priority: str = "MEDIUM",
                plot=None, season=None, assigned_to=None,
                is_recurring: bool = False, recurring_interval_days: Optional[int] = None,
                is_system: bool = False, parent_task=None) -> Task:
    """
    Tạo mới một công việc trong vườn.
    """
    if is_recurring and (not recurring_interval_days or recurring_interval_days <= 0):
        raise DomainError("invalid_recurring_interval", "Công việc lặp lại phải có số ngày chu kỳ lớn hơn 0.", 400)

    task = Task.objects.create(
        farm=farm,
        plot=plot,
        season=season,
        title=title,
        description=description,
        task_type=task_type,
        priority=priority,
        due_date=due_date,
        assigned_to=assigned_to,
        is_recurring=is_recurring,
        recurring_interval_days=recurring_interval_days if is_recurring else None,
        is_system=is_system,
        parent_task=parent_task,
        created_by=user,
    )

    if assigned_to and assigned_to != user:
        create_notification(
            farm=farm,
            user=assigned_to,
            title=f"Bạn được giao việc mới: {title}",
            message=f"Hạn hoàn thành: {due_date}. Nội dung: {description or 'Không có ghi chú'}",
            notification_type=Notification.NotificationType.TASK_DUE,
            link=f"/tasks/{task.id}",
        )

    return task


@transaction.atomic
def update_task(task: Task, user, **fields) -> Task:
    """
    Cập nhật công việc.
    BR-23: Công việc hệ thống (is_system=True) không được sửa title, description, task_type.
    """
    if task.is_system:
        immutable_keys = {"title", "description", "task_type"}
        attempted_changes = set(fields.keys()).intersection(immutable_keys)
        if any(fields.get(k) != getattr(task, k) for k in attempted_changes):
            raise DomainError(
                "system_task_immutable",
                "Không thể thay đổi nội dung của công việc hệ thống tự động (BR-23).",
                400,
            )

    for k, v in fields.items():
        if hasattr(task, k):
            setattr(task, k, v)

    task.save()
    return task


@transaction.atomic
def complete_task(task: Task, user) -> Task:
    """
    Hoàn thành công việc.

    BR-22: Nếu là việc lặp lại (is_recurring=True), tự động sinh công việc tiếp theo
    với due_date = task.due_date + recurring_interval_days.
    """
    if task.status == Task.Status.COMPLETED:
        return task

    task.status = Task.Status.COMPLETED
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at", "updated_at"])

    # BR-22: Tự động sinh công việc tiếp theo
    if task.is_recurring and task.recurring_interval_days:
        next_due = task.due_date + timedelta(days=task.recurring_interval_days)
        create_task(
            farm=task.farm,
            user=user,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            due_date=next_due,
            plot=task.plot,
            season=task.season,
            assigned_to=task.assigned_to,
            is_recurring=True,
            recurring_interval_days=task.recurring_interval_days,
            is_system=task.is_system,
            parent_task=task,
        )

    audit(
        farm=task.farm,
        actor=user,
        action="TASK_COMPLETE",
        entity=task,
        task_id=task.id,
    )

    return task


def create_notification(farm, user, title: str, message: str,
                        notification_type: str = Notification.NotificationType.INFO,
                        link: str = "") -> Notification:
    """Tạo thông báo trong hệ thống."""
    return Notification.objects.create(
        farm=farm,
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )
