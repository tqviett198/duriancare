"""python manage.py seed_demo — dữ liệu GIẢ để demo. Chạy lại nhiều lần được."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import InputProduct, Variety
from farms.models import Farm, FarmMembership, Plot, PlotSeason, Season
from logs.services import save_log

User = get_user_model()
FARM_NAME = "[DEMO] Vườn Mẫu"
DEMO_NOTE = "DEMO – dữ liệu giả, không dùng tham khảo thực tế"


class Command(BaseCommand):
    help = "Tạo vườn demo, 3 tài khoản (owner/worker/advisor_demo), vật tư giả và nhật ký mẫu."

    @staticmethod
    def _reset():
        # Lô/nhật ký/sổ thu chi/audit_log dùng PROTECT để giữ lịch sử, nên xóa theo thứ tự từ con đến cha.
        from common.models import AuditLog
        from finance.models import LedgerEntry
        from logs.models import FarmLog
        demo_usernames = ["owner_demo", "worker_demo", "advisor_demo"]
        AuditLog.objects.filter(actor__username__in=demo_usernames).delete()
        farms = Farm.objects.filter(name=FARM_NAME)
        LedgerEntry.objects.filter(farm__in=farms).delete()
        FarmLog.objects.filter(plot__farm__in=farms).delete()
        farms.delete()

    @transaction.atomic
    def handle(self, *args, **opts):
        self._reset()
        InputProduct.objects.filter(is_demo=True).delete()
        users = {}
        for key, full_name in (("owner", "Chủ Vườn Demo"), ("worker", "Người Làm Demo"), ("advisor", "Kỹ Thuật Viên Demo")):
            phone = {"owner": "0900000101", "worker": "0900000102", "advisor": "0900000103"}[key]
            User.objects.filter(username=f"{key}_demo").delete()
            users[key] = User.objects.create_user(username=f"{key}_demo", phone=phone, full_name=full_name,
                                                  password="demo-12345")
        owner = users["owner"]
        farm = Farm.objects.create(owner=owner, name=FARM_NAME, province="Demo", area_ha="6.5",
                                   note="Dữ liệu minh họa")
        for key, role in (("owner", "OWNER"), ("worker", "WORKER"), ("advisor", "ADVISOR")):
            FarmMembership.objects.create(farm=farm, user=users[key], role=role)

        varieties = [Variety.objects.get_or_create(name=n)[0] for n in ("Ri6", "Monthong")]
        plots = [Plot.objects.create(farm=farm, name=f"Lô {c}", variety=varieties[i % 2], area_ha=a,
                                     tree_count=int(float(a) * 120), growth_stage="FRUIT_DEVELOPMENT")
                 for i, (c, a) in enumerate((("A", "2.0"), ("B", "1.5"), ("C", "1.8"), ("D", "1.2")))]

        def product(**kw):
            return InputProduct.objects.create(is_demo=True, source_note=DEMO_NOTE, **kw)
        npk = product(name="[DEMO] Phân NPK 16-16-8", kind="FERTILIZER", unit="kg", registered_for_durian="YES")
        spray = product(name="[DEMO] Thuốc A", kind="PESTICIDE", unit="lít", phi_days=14,
                        max_applications_per_season=3, registered_for_durian="YES")
        unknown = product(name="[DEMO] Thuốc B (chưa xác định)", kind="PESTICIDE", unit="lít", phi_days=21,
                          registered_for_durian="UNKNOWN")

        today = date.today()
        season = Season.objects.create(farm=farm, name=f"Vụ {today.year}", start_date=date(today.year, 1, 1),
                                       status="ACTIVE")
        for i, plot in enumerate(plots):
            PlotSeason.objects.create(plot=plot, season=season,
                                      flower_induction_date=today - timedelta(days=120 + i * 7),
                                      fruit_set_date=today - timedelta(days=90 + i * 7),
                                      expected_harvest_date=today + timedelta(days=30 + i * 7))

        def log(plot, days_ago, activity, items=(), ack=()):
            save_log(farm=farm, user=owner, data={
                "plot": plot, "activity_type": activity, "activity_date": today - timedelta(days=days_ago),
                "description": "Dữ liệu demo",
                "inputs": [{"product": p, "quantity": q, "unit_cost": c} for p, q, c in items],
                "acknowledged_warnings": list(ack)})
        for d in (80, 50, 20):
            log(plots[0], d, "FERTILIZE", [(npk, "40.00", "15000")])
        log(plots[0], 5, "SPRAY", [(spray, "2.50", "180000")])      # vừa phun, chưa đủ ngày cách ly
        log(plots[1], 30, "SPRAY", [(spray, "2.00", "180000")])
        log(plots[2], 10, "SPRAY", [(unknown, "1.00", "220000")], ack=[unknown.id])
        log(plots[3], 3, "IRRIGATE")
        msg = "Đã tạo dữ liệu demo. Đăng nhập: owner_demo / worker_demo / advisor_demo, mật khẩu demo-12345"
        try:
            self.stdout.write(self.style.SUCCESS(msg))
        except UnicodeEncodeError:
            self.stdout.write(self.style.SUCCESS(
                "Da tao du lieu demo. Dang nhap: owner_demo / worker_demo / advisor_demo, mat khau demo-12345"))
