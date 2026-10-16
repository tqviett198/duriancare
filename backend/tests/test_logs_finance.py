from datetime import date, timedelta

from django.db import IntegrityError, transaction

from farms.models import Season
from finance.models import LedgerEntry
from logs.models import FarmLog

from .base import BaseTest


class LogRuleTests(BaseTest):
    def post_log(self, **over):
        return self.client.post(self.url(self.farm_a, "logs/"), self.log_payload(**over), format="json")

    def test_br04_future_date_rejected(self):
        self.login(self.owner_a)
        r = self.post_log(activity_date=str(date.today() + timedelta(days=1)))
        self.assertEqual(r.status_code, 400)
        self.assertIn("activity_date", r.data["fields"])

    def test_br07_br16_cost_rounding_and_generated_expense(self):
        self.login(self.owner_a)
        r = self.post_log(inputs=[{"product": self.fert.id, "quantity": "2.50", "unit_cost": "180000"},
                                  {"product": self.fert.id, "quantity": "0.33", "unit_cost": "1001"}])
        self.assertEqual(r.status_code, 201, r.data)
        totals = [i["total_cost"] for i in r.data["inputs"]]
        self.assertEqual(totals, ["450000", "330"])           # 0.33 × 1001 = 330.33 → 330
        self.assertEqual(r.data["generated_expense"]["amount"], "450330")
        self.assertEqual(LedgerEntry.objects.filter(source_log_id=r.data["id"]).count(), 1)
        self.assertEqual(r.data["season"], self.season_a.id)   # tự gán vụ ACTIVE

    def test_br16_update_and_void_keep_expense_in_sync(self):
        self.login(self.owner_a)
        log_id = self.post_log(inputs=[{"product": self.fert.id, "quantity": "1", "unit_cost": "100000"}]).data["id"]
        r = self.client.patch(self.url(self.farm_a, f"logs/{log_id}/"),
                              {"inputs": [{"product": self.fert.id, "quantity": "3", "unit_cost": "100000"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        entry = LedgerEntry.objects.get(source_log_id=log_id)
        self.assertEqual(int(entry.amount), 300000)
        self.assertEqual(LedgerEntry.objects.filter(source_log_id=log_id).count(), 1)

        # không sửa/hủy tay khoản tự sinh
        r = self.client.patch(self.url(self.farm_a, f"transactions/{entry.id}/"), {"amount": "1"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "generated_entry_readonly")
        r = self.client.post(self.url(self.farm_a, f"transactions/{entry.id}/void/"), {"reason": "x"})
        self.assertEqual(r.status_code, 409)

        # BR-03: hủy nhật ký không xóa dòng, khoản chi bị hủy theo
        r = self.client.post(self.url(self.farm_a, f"logs/{log_id}/void/"), {"reason": "Nhập nhầm"})
        self.assertEqual(r.status_code, 200, r.data)
        log = FarmLog.objects.get(pk=log_id)
        self.assertEqual((log.status, log.void_reason, log.voided_by_id), ("VOIDED", "Nhập nhầm", self.owner_a.id))
        entry.refresh_from_db()
        self.assertEqual(entry.status, "VOIDED")
        self.assertEqual(self.client.patch(self.url(self.farm_a, f"logs/{log_id}/"), {"description": "x"}).status_code, 409)

    def test_br06_product_not_registered_is_blocked(self):
        self.fert.registered_for_durian = "NO"
        self.fert.save()
        self.login(self.owner_a)
        r = self.post_log(inputs=[{"product": self.fert.id, "quantity": "1", "unit_cost": "1000"}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "product_not_allowed")
        self.assertEqual(FarmLog.objects.count(), 0)

    def test_br06_unknown_requires_acknowledgement(self):
        self.fert.registered_for_durian = "UNKNOWN"
        self.fert.save()
        self.login(self.owner_a)
        inputs = [{"product": self.fert.id, "quantity": "1", "unit_cost": "1000"}]
        r = self.post_log(inputs=inputs)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "warning_unacknowledged")
        self.assertEqual(FarmLog.objects.count(), 0)          # không lưu gì khi chưa xác nhận
        r = self.post_log(inputs=inputs, acknowledged_warnings=[self.fert.id])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["warnings"][0]["code"], "registered_unknown")
        self.assertTrue(r.data["inputs"][0]["warning_acknowledged"])

    def test_br06_max_applications_warns_but_saves(self):
        self.spray.max_applications_per_season = 1
        self.spray.save()
        self.login(self.owner_a)
        inputs = [{"product": self.spray.id, "quantity": "1", "unit_cost": "5000"}]
        self.assertEqual(self.post_log(inputs=inputs, activity_type="SPRAY").data["warnings"], [])
        r = self.post_log(inputs=inputs, activity_type="SPRAY")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["warnings"][0]["code"], "max_applications_exceeded")

    def test_closed_season_blocks_new_logs(self):
        self.season_a.status = "CLOSED"
        self.season_a.save()
        self.login(self.owner_a)
        r = self.post_log(season=self.season_a.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "season_closed")

    def test_worker_edit_only_own_within_24h(self):
        self.login(self.worker_a)
        log_id = self.post_log().data["id"]
        self.assertEqual(self.client.patch(self.url(self.farm_a, f"logs/{log_id}/"), {"description": "sửa"}).status_code, 200)
        FarmLog.objects.filter(pk=log_id).update(created_at=FarmLog.objects.get(pk=log_id).created_at - timedelta(hours=25))
        self.assertEqual(self.client.patch(self.url(self.farm_a, f"logs/{log_id}/"), {"description": "muộn"}).status_code, 403)
        self.assertEqual(self.client.post(self.url(self.farm_a, f"logs/{log_id}/void/"), {"reason": "x"}).status_code, 403)

    def test_logs_filter_by_date_range(self):
        self.login(self.owner_a)
        self.post_log(activity_date=str(date.today() - timedelta(days=10)))
        self.post_log(activity_date=str(date.today() - timedelta(days=1)))
        r = self.client.get(self.url(self.farm_a, f"logs/?date_from={date.today() - timedelta(days=3)}"))
        self.assertEqual(r.data["count"], 1)


class LedgerTests(BaseTest):
    def test_br15_manual_entries_only_expense_or_other_income(self):
        self.login(self.owner_a)
        ok = self.client.post(self.url(self.farm_a, "transactions/"),
                              {"type": "EXPENSE", "category": "LABOR", "amount": "500000", "txn_date": "2026-10-01"})
        self.assertEqual(ok.status_code, 201, ok.data)
        bad = self.client.post(self.url(self.farm_a, "transactions/"),
                               {"type": "SALE_REVENUE", "category": "OTHER", "amount": "1", "txn_date": "2026-10-01"})
        self.assertEqual(bad.status_code, 400)

    def test_amount_must_be_positive_in_api_and_db(self):
        self.login(self.owner_a)
        r = self.client.post(self.url(self.farm_a, "transactions/"),
                             {"type": "EXPENSE", "category": "OTHER", "amount": "0", "txn_date": "2026-10-01"})
        self.assertEqual(r.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(farm=self.farm_a, type="EXPENSE", category="OTHER", amount=0,
                                       txn_date=date.today(), created_by=self.owner_a)

    def test_void_manual_entry_keeps_row_and_writes_audit(self):
        self.login(self.owner_a)
        eid = self.client.post(self.url(self.farm_a, "transactions/"),
                               {"type": "EXPENSE", "category": "UTILITIES", "amount": "100000",
                                "txn_date": "2026-10-01"}).data["id"]
        r = self.client.post(self.url(self.farm_a, f"transactions/{eid}/void/"), {"reason": "Nhập sai"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(LedgerEntry.objects.filter(pk=eid, status="VOIDED").exists())
        from common.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(action="LEDGER_VOID", entity_id=eid).exists())


    def test_owner_cannot_self_verify_product(self):
        self.login(self.owner_a)
        r = self.client.post(self.url(self.farm_a, "products/"), {
            "name": "Thuốc tự chế", "kind": "PESTICIDE", "unit": "chai", "phi_days": 7,
            "registered_for_durian": "YES", "verified_at": "2026-10-15", "source_note": "Tự duyệt",
        })
        self.assertEqual(r.status_code, 201, r.data)
        # Bắt buộc phải là UNKNOWN và không cho phép tự điền thông tin kiểm chứng
        self.assertEqual(r.data["registered_for_durian"], "UNKNOWN")
        self.assertIsNone(r.data["verified_at"])
        self.assertEqual(r.data["source_note"], "")

    def test_log_splits_expenses_by_material_kind(self):
        self.login(self.owner_a)
        r = self.post_log(inputs=[
            {"product": self.fert.id, "quantity": "10", "unit_cost": "20000"},  # 200,000 FERTILIZER
            {"product": self.spray.id, "quantity": "2", "unit_cost": "150000"}, # 300,000 PESTICIDE
        ])
        self.assertEqual(r.status_code, 201, r.data)
        log_id = r.data["id"]
        entries = list(LedgerEntry.objects.filter(source_log_id=log_id, status="ACTIVE").order_by("category"))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].category, "FERTILIZER")
        self.assertEqual(int(entries[0].amount), 200000)
        self.assertEqual(entries[1].category, "PESTICIDE")
        self.assertEqual(int(entries[1].amount), 300000)

        # Khi hủy nhật ký, cả 2 khoản chi đều phải bị VOID
        self.client.post(self.url(self.farm_a, f"logs/{log_id}/void/"), {"reason": "test"})
        self.assertEqual(LedgerEntry.objects.filter(source_log_id=log_id, status="ACTIVE").count(), 0)
        self.assertEqual(LedgerEntry.objects.filter(source_log_id=log_id, status="VOIDED").count(), 2)

    def test_performed_by_non_member_returns_generic_error(self):
        self.login(self.owner_a)
        # ID không tồn tại
        r1 = self.post_log(performed_by=99999)
        self.assertEqual(r1.status_code, 400)
        # ID tồn tại nhưng thuộc vườn khác
        r2 = self.post_log(performed_by=self.owner_b.id)
        self.assertEqual(r2.status_code, 400)
        # Cả 2 đều có mã lỗi does_not_exist và thông báo 'Không tìm thấy trong vườn này', không phân biệt ID có trong hệ thống hay không
        self.assertEqual(r1.data["fields"]["performed_by"][0].code, "does_not_exist")
        self.assertEqual(r2.data["fields"]["performed_by"][0].code, "does_not_exist")
        self.assertIn("Không tìm thấy trong vườn này", str(r1.data["fields"]["performed_by"][0]))
        self.assertIn("Không tìm thấy trong vườn này", str(r2.data["fields"]["performed_by"][0]))


class SeasonTests(BaseTest):
    def test_br20_only_one_active_season(self):
        self.login(self.owner_a)
        sid = self.client.post(self.url(self.farm_a, "seasons/"), {"name": "Vụ 2027", "start_date": "2027-01-01"}).data["id"]
        r = self.client.post(self.url(self.farm_a, f"seasons/{sid}/activate/"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "active_season_exists")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Season.objects.create(farm=self.farm_a, name="Trùng", start_date=date(2027, 1, 1), status="ACTIVE")
        self.client.post(self.url(self.farm_a, f"seasons/{self.season_a.id}/close/"))
        self.assertEqual(self.client.post(self.url(self.farm_a, f"seasons/{sid}/activate/")).status_code, 200)

    def test_closed_season_cannot_be_modified(self):
        self.login(self.owner_a)
        self.client.post(self.url(self.farm_a, f"seasons/{self.season_a.id}/close/"))
        r = self.client.patch(self.url(self.farm_a, f"seasons/{self.season_a.id}/"), {"name": "Tên mới"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("đã đóng", str(r.data))

    def test_br21_plot_season_date_order(self):
        self.login(self.owner_a)
        url = self.url(self.farm_a, f"plots/{self.plot_a.id}/seasons/{self.season_a.id}/")
        bad = self.client.put(url, {"flower_induction_date": "2026-03-01", "fruit_set_date": "2026-02-01"}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.put(url, {"flower_induction_date": "2026-02-01", "fruit_set_date": "2026-02-25",
                                     "expected_harvest_date": "2026-06-01"}, format="json")
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual(self.client.get(url).data["fruit_set_date"], "2026-02-25")
