from datetime import date, timedelta
from celery import shared_task
from farms.models import Farm
from reports.services import get_phi_warnings_report
from tasks.models import Task, Notification
from tasks.services import create_notification


@shared_task
def check_daily_phi_alerts():
    """Kiểm tra và tạo thông báo nếu có lô đất chạm ngưỡng ngày an toàn PHI."""
    farms = Farm.objects.all()
    count = 0
    today = date.today()

    for farm in farms:
        rep = get_phi_warnings_report(farm, as_of_date=today)
        for p in rep["plots"]:
            if p["status"] in ("WARNING", "RESTRICTED") and p["days_remaining"] <= 3:
                # Gửi thông báo cho chủ vườn
                create_notification(
                    farm=farm,
                    user=farm.owner,
                    title=f"Cảnh báo PHI: Lô {p['plot_name']}",
                    message=f"Lô {p['plot_name']} còn {p['days_remaining']} ngày trước khi an toàn thu hoạch ({p['phi_safe_date']}).",
                    notification_type=Notification.NotificationType.PHI_ALERT,
                    link="/reports/phi-warnings",
                )
                count += 1
    return f"Created {count} PHI alert notifications"


@shared_task
def check_due_tasks_reminders():
    """Nhắc nhở các công việc đến hạn hôm nay."""
    today = date.today()
    due_tasks = Task.objects.filter(
        due_date=today,
        status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        assigned_to__isnull=False,
    ).select_related("farm", "assigned_to")

    count = 0
    for t in due_tasks:
        create_notification(
            farm=t.farm,
            user=t.assigned_to,
            title=f"Công việc đến hạn hôm nay: {t.title}",
            message=f"Vui lòng kiểm tra và cập nhật tiến độ công việc trước cuối ngày.",
            notification_type=Notification.NotificationType.TASK_DUE,
            link=f"/tasks/{t.id}",
        )
        count += 1
    return f"Created {count} task due reminders"
