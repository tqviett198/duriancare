from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from catalog.models import InputProduct, Variety
from farms.models import Farm, FarmMembership, Plot, Season

User = get_user_model()
API = "/api/v1"


def make_user(phone, name="Người dùng"):
    return User.objects.create_user(username=phone, phone=phone, full_name=name, password="matkhau-1234")


class BaseTest(APITestCase):
    """Dựng sẵn 2 vườn độc lập (A, B) để test truy cập chéo."""

    def setUp(self):
        self.ri6 = Variety.objects.create(name="Ri6")
        self.owner_a = make_user("0900000001", "Chủ A")
        self.worker_a = make_user("0900000002", "Thợ A")
        self.advisor_a = make_user("0900000003", "KTV A")
        self.owner_b = make_user("0900000004", "Chủ B")
        self.farm_a = self._farm(self.owner_a, "Vườn A")
        self.farm_b = self._farm(self.owner_b, "Vườn B")
        FarmMembership.objects.create(farm=self.farm_a, user=self.worker_a, role="WORKER")
        FarmMembership.objects.create(farm=self.farm_a, user=self.advisor_a, role="ADVISOR")
        self.plot_a = Plot.objects.create(farm=self.farm_a, name="Lô A1", variety=self.ri6, area_ha="1.5")
        self.plot_b = Plot.objects.create(farm=self.farm_b, name="Lô B1", variety=self.ri6, area_ha="2.0")
        self.season_a = Season.objects.create(farm=self.farm_a, name="Vụ 2026", status="ACTIVE",
                                              start_date=date(2026, 1, 1))
        self.fert = InputProduct.objects.create(name="NPK demo", kind="FERTILIZER", unit="kg",
                                                registered_for_durian="YES", is_demo=True)
        self.spray = InputProduct.objects.create(name="Thuốc DEMO-A", kind="PESTICIDE", unit="lít",
                                                 phi_days=14, registered_for_durian="YES", is_demo=True)

    def _farm(self, owner, name):
        farm = Farm.objects.create(owner=owner, name=name, area_ha="5")
        FarmMembership.objects.create(farm=farm, user=owner, role="OWNER")
        return farm

    def login(self, user):
        self.client.force_authenticate(user)

    def url(self, farm, path):
        return f"{API}/farms/{farm.id}/{path}"

    def log_payload(self, **over):
        body = {"plot": self.plot_a.id, "activity_type": "FERTILIZE",
                "activity_date": str(date.today() - timedelta(days=1)),
                "description": "Bón phân", "inputs": []}
        body.update(over)
        return body

    def post_log(self, farm=None, **over):
        f = farm or self.farm_a
        return self.client.post(self.url(f, "logs/"), self.log_payload(**over), format="json")
