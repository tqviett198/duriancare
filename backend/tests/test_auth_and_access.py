from django.db import IntegrityError, transaction

from catalog.models import InputProduct

from .base import API, BaseTest


class AuthTests(BaseTest):
    def test_register_login_me(self):
        r = self.client.post(f"{API}/auth/register/", {"phone": "0911222333", "full_name": "Nông dân",
                                                         "password": "matkhau-1234"})
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post(f"{API}/auth/login/", {"username": "0911222333", "password": "matkhau-1234"})
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        me = self.client.get(f"{API}/auth/me/")
        self.assertEqual(me.data["phone"], "0911222333")

    def test_register_rejects_bad_phone_and_duplicates(self):
        bad = self.client.post(f"{API}/auth/register/", {"phone": "123", "full_name": "x", "password": "matkhau-1234"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.data["code"], "validation_error")
        dup = self.client.post(f"{API}/auth/register/", {"phone": "0900000001", "full_name": "x", "password": "matkhau-1234"})
        self.assertEqual(dup.status_code, 400)

    def test_create_farm_makes_creator_owner(self):
        self.login(self.worker_a)
        r = self.client.post(f"{API}/farms/", {"name": "Vườn mới", "area_ha": "3"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["my_role"], "OWNER")


class CrossFarmAccessTests(BaseTest):
    """BR-01, BR-02: người dùng vườn này không chạm được dữ liệu vườn kia."""

    def test_non_member_cannot_read_any_farm_endpoint(self):
        self.login(self.owner_b)
        for path in ("plots/", "seasons/", "logs/", "products/", "members/", "transactions/", "planting-codes/"):
            r = self.client.get(self.url(self.farm_a, path))
            self.assertEqual(r.status_code, 403, path)

    def test_farm_list_only_contains_own_farms(self):
        self.login(self.owner_b)
        ids = [f["id"] for f in self.client.get(f"{API}/farms/").data["results"]]
        self.assertEqual(ids, [self.farm_b.id])
        self.assertEqual(self.client.get(f"{API}/farms/{self.farm_a.id}/").status_code, 404)

    def test_cannot_use_other_farm_plot_in_my_farm(self):
        self.login(self.owner_b)
        r = self.client.post(self.url(self.farm_b, "logs/"), self.log_payload(plot=self.plot_a.id), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plot", r.data["fields"])

    def test_cannot_read_other_farm_plot_detail_through_my_farm_url(self):
        self.login(self.owner_b)
        r = self.client.get(self.url(self.farm_b, f"plots/{self.plot_a.id}/"))
        self.assertEqual(r.status_code, 404)

    def test_private_product_of_other_farm_is_not_usable(self):
        private = InputProduct.objects.create(farm=self.farm_b, name="Riêng B", kind="FERTILIZER", unit="kg",
                                              registered_for_durian="YES")
        self.login(self.owner_a)
        body = self.log_payload(inputs=[{"product": private.id, "quantity": "1", "unit_cost": "1000"}])
        r = self.client.post(self.url(self.farm_a, "logs/"), body, format="json")
        self.assertEqual(r.status_code, 400)


class RoleTests(BaseTest):
    def test_worker_cannot_see_finance_or_create_plot(self):
        self.login(self.worker_a)
        self.assertEqual(self.client.get(self.url(self.farm_a, "transactions/")).status_code, 403)
        r = self.client.post(self.url(self.farm_a, "plots/"),
                             {"name": "Lô mới", "variety": self.ri6.id, "area_ha": "1"})
        self.assertEqual(r.status_code, 403)

    def test_advisor_can_read_but_not_write_logs(self):
        self.login(self.advisor_a)
        self.assertEqual(self.client.get(self.url(self.farm_a, "logs/")).status_code, 200)
        r = self.client.post(self.url(self.farm_a, "logs/"), self.log_payload(), format="json")
        self.assertEqual(r.status_code, 403)

    def test_cannot_remove_last_owner(self):
        self.login(self.owner_a)
        m = self.farm_a.memberships.get(user=self.owner_a)
        r = self.client.delete(self.url(self.farm_a, f"members/{m.id}/"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "last_owner")

    def test_owner_adds_member_by_phone(self):
        self.login(self.owner_a)
        r = self.client.post(self.url(self.farm_a, "members/"), {"phone": "0900000004", "role": "ADVISOR"})
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post(self.url(self.farm_a, "members/"), {"phone": "0900000004", "role": "ADVISOR"})
        self.assertEqual(r.status_code, 400)


class CatalogTests(BaseTest):
    def test_br05_pesticide_without_phi_rejected_in_api_and_db(self):
        self.login(self.owner_a)
        r = self.client.post(self.url(self.farm_a, "products/"),
                             {"name": "Thuốc X", "kind": "PESTICIDE", "unit": "lít", "registered_for_durian": "UNKNOWN"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("phi_days", r.data["fields"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            InputProduct.objects.create(name="Thuốc Y", kind="PESTICIDE", unit="lít")

    def test_global_products_visible_but_not_editable_by_owner(self):
        self.login(self.owner_a)
        names = [p["name"] for p in self.client.get(self.url(self.farm_a, "products/")).data["results"]]
        self.assertIn("NPK demo", names)
        r = self.client.patch(self.url(self.farm_a, f"products/{self.fert.id}/"), {"name": "Đổi tên"})
        self.assertEqual(r.status_code, 404)
