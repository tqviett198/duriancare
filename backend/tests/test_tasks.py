"""
Tests cho app tasks & notifications:
- BR-22: Việc lặp lại tự động sinh việc tiếp theo khi hoàn thành
- BR-23: Công việc hệ thống không cho phép sửa nội dung
- Giao việc và nhận thông báo
- Đánh dấu đã đọc thông báo
"""
from datetime import date, timedelta

from common.exceptions import DomainError
from tasks.models import Task, Notification
from tasks.services import create_task, update_task, complete_task
from tasks.tasks import check_daily_phi_alerts, check_due_tasks_reminders
from tests.base import BaseTest

API = "/api/v1"
TODAY = date.today()


class TasksTest(BaseTest):
    def test_create_and_list_tasks(self):
        """Tạo công việc và liệt kê qua API."""
        self.login(self.owner_a)
        res = self.client.post(
            f"{API}/farms/{self.farm_a.id}/tasks/",
            {
                "title": "Bón phân đợt 1",
                "due_date": str(TODAY + timedelta(days=5)),
                "task_type": "FERTILIZE",
                "priority": "HIGH",
                "description": "Bón NPK 16-16-8 cho Lô A1",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["title"], "Bón phân đợt 1")
        self.assertEqual(res.data["status"], "PENDING")

        # Worker cũng xem được việc của vườn
        self.login(self.worker_a)
        list_res = self.client.get(f"{API}/farms/{self.farm_a.id}/tasks/")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(list_res.data["count"], 1)

    def test_br22_recurring_task_spawns_next_task(self):
        """
        BR-22: Khi hoàn thành công việc lặp lại (is_recurring=True),
        hệ thống tự động sinh việc tiếp theo với due_date mới.
        """
        task = create_task(
            farm=self.farm_a,
            user=self.owner_a,
            title="Kiểm tra hệ thống tưới nhỏ giọt",
            due_date=TODAY,
            is_recurring=True,
            recurring_interval_days=7,
        )

        complete_task(task=task, user=self.owner_a)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)

        # Kiểm tra công việc tiếp theo được sinh ra
        child = Task.objects.filter(parent_task=task).first()
        self.assertIsNotNone(child)
        self.assertEqual(child.title, task.title)
        self.assertEqual(child.due_date, TODAY + timedelta(days=7))
        self.assertEqual(child.status, Task.Status.PENDING)
        self.assertTrue(child.is_recurring)
        self.assertEqual(child.recurring_interval_days, 7)

    def test_br23_system_task_immutable_core_content(self):
        """
        BR-23: Công việc hệ thống (is_system=True) không được sửa nội dung (title, description, task_type).
        """
        sys_task = create_task(
            farm=self.farm_a,
            user=self.owner_a,
            title="LỊCH HỆ THỐNG: Lấy mẫu kiểm nghiệm xuất khẩu",
            description="Tự động lập lịch bởi hệ thống",
            task_type="LAB_TEST",
            due_date=TODAY + timedelta(days=10),
            is_system=True,
        )

        # Cố tình sửa title
        with self.assertRaises(DomainError) as cm:
            update_task(sys_task, user=self.owner_a, title="Đổi tên việc linh tinh")
        self.assertEqual(cm.exception.code_str, "system_task_immutable")

        # Cố tình sửa task_type
        with self.assertRaises(DomainError) as cm:
            update_task(sys_task, user=self.owner_a, task_type="WATER")
        self.assertEqual(cm.exception.code_str, "system_task_immutable")

        # Được phép cập nhật priority hoặc assigned_to
        update_task(sys_task, user=self.owner_a, priority="URGENT")
        sys_task.refresh_from_db()
        self.assertEqual(sys_task.priority, "URGENT")

    def test_notification_flow(self):
        """Kiểm tra giao việc sinh thông báo và đánh dấu đã đọc."""
        # Giao việc cho worker_a
        create_task(
            farm=self.farm_a,
            user=self.owner_a,
            title="Cắt tỉa cành la",
            due_date=TODAY + timedelta(days=2),
            assigned_to=self.worker_a,
        )

        # Worker nhận được thông báo
        notifs = Notification.objects.filter(user=self.worker_a)
        self.assertEqual(notifs.count(), 1)
        n = notifs.first()
        self.assertFalse(n.is_read)

        # Đánh dấu đã đọc qua API
        self.login(self.worker_a)
        res = self.client.post(f"{API}/farms/{self.farm_a.id}/notifications/{n.id}/mark-read/")
        self.assertEqual(res.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_celery_due_tasks_reminder(self):
        """Kiểm tra celery task nhắc việc đến hạn."""
        create_task(
            farm=self.farm_a,
            user=self.owner_a,
            title="Phun phòng ngừa nấm Phytophthora",
            due_date=TODAY,
            assigned_to=self.worker_a,
        )
        msg = check_due_tasks_reminders()
        self.assertIn("Created", msg)
